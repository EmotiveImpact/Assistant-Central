"""Scoped encrypted payload columns, retaining ordinary SQLite transactions.

Public-key sealing permits a late provider result to be retained after logout.
Opening requires the unlocked local identity. Metadata/indexes are not encrypted.
"""
import base64
import json
import os
import sqlite3

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .crypto import canonical, fingerprint, unb64

VERSION = 'assistant-central-application-storage/1'
PREFIX = 'ac-storage-v1:'
MAX_FIELD = 256 * 1024
# Only these payloads contain application text. Routing/state/digest metadata,
# public identities and already-encrypted transport packets remain unchanged.
FIELDS = {'runtime_items': ('id', ('body',)),
          'runtime_audit': ('sequence', ('data',)),
          'pilot_provider_runs': ('id', ('binding', 'request', 'review', 'result')),
          'pilot_workflow_artifacts': ('run_id', ('review',))}


class StorageDenied(PermissionError):
    """Fixed failure, without plaintext, key material or underlying error text."""


class _DecodedRow(dict):
    pass


def _key(shared, context):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=VERSION.encode() + b'\0' + context).derive(shared)


class RecordStorage:
    def __init__(self, db, auth, *, create=False, legacy_fixture=False):
        self.db, self.auth = db, auth
        self.legacy = False
        existing = db.execute("SELECT 1 FROM sqlite_master WHERE name='application_storage'").fetchone()
        if not existing:
            if legacy_fixture and not hasattr(auth, "public_identity") and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='runtime_meta'").fetchone():
                self.legacy = True
                return
            if not create or db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                raise StorageDenied('Plaintext or missing storage format: explicit offline migration required')
            db.execute('CREATE TABLE application_storage(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL)')
            db.execute('INSERT INTO application_storage VALUES(1,?,?)', (VERSION, fingerprint(auth.public_identity())))
        self.owner = fingerprint(auth.public_identity())
        self.public = auth.public_identity()
        self._check()

    def _check(self):
        if self.legacy:
            return
        try:
            rows = self.db.execute('SELECT singleton,version,owner FROM application_storage').fetchall()
            if len(rows) != 1 or tuple(rows[0]) != (1, VERSION, self.owner):
                raise ValueError()
            if fingerprint(self.auth.public_identity()) != self.owner:
                raise ValueError()
        except (ValueError, sqlite3.Error):
            raise StorageDenied('Application storage identity or format unavailable') from None

    def _context(self, table, row_id, column):
        if table not in FIELDS or column not in FIELDS[table][1] or type(row_id) not in (str, int):
            raise StorageDenied('Invalid application storage context')
        return canonical([VERSION, self.owner, table, str(row_id), column])

    def seal(self, table, row_id, column, value):
        if self.legacy or value is None:
            return value
        self._check()
        context = self._context(table, row_id, column)
        if type(value) is not str:
            raise StorageDenied('Invalid application payload')
        try:
            raw = value.encode('utf-8')
            if len(raw) > MAX_FIELD:
                raise ValueError()
            ephemeral = X25519PrivateKey.generate()
            shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(unb64(self.public['exchange_key'], 32)))
            nonce = os.urandom(12)
            packed = ephemeral.public_key().public_bytes_raw() + nonce + AESGCM(_key(shared, context)).encrypt(nonce, raw, context)
            return PREFIX + base64.b64encode(packed).decode('ascii')
        except (ValueError, UnicodeError):
            raise StorageDenied('Application payload encryption unavailable') from None

    def open(self, table, row_id, column, value):
        if self.legacy or value is None:
            return value
        self._check()
        context = self._context(table, row_id, column)
        try:
            if type(value) is not str or not value.startswith(PREFIX) or len(value) > (MAX_FIELD + 60) * 2:
                raise ValueError()
            packed = base64.b64decode(value[len(PREFIX):], validate=True)
            if not 60 <= len(packed) <= MAX_FIELD + 60 or base64.b64encode(packed).decode() != value[len(PREFIX):]:
                raise ValueError()
            shared = self.auth._application_storage_exchange(packed[:32])
            return AESGCM(_key(shared, context)).decrypt(packed[32:44], packed[44:], context).decode('utf-8')
        except (ValueError, UnicodeError, InvalidTag):
            raise StorageDenied('Encrypted application payload unavailable') from None

    def row(self, table, value):
        if value is None:
            return None
        if isinstance(value, _DecodedRow):
            return value
        result = _DecodedRow(value)
        primary, columns = FIELDS[table]
        for column in columns:
            if column in result:
                result[column] = self.open(table, result[primary], column, result[column])
        return result


class StoreLease:
    """Co-operative shared-runtime/exclusive-migration lease on a private file."""
    def __init__(self, directory, *, exclusive=False):
        import fcntl
        from pathlib import Path
        from .auth import _create_private_file, _private_path
        self.fd = None
        path = Path(directory)
        _private_path(path, directory=True)
        _create_private_file(path / 'runtime.lock')
        descriptor = os.open(path / 'runtime.lock', os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            self.fd = descriptor
        except BaseException:
            os.close(descriptor)
            raise StorageDenied('Runtime store is already open') from None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
