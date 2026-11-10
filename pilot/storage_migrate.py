"""Explicit stopped-service conversion. No plaintext staging file or backup.

Original plaintext is retained until an encrypted, verified replacement is
fsynced. Failure after replacement is uncertain; inspect after restart, no retry.
This cannot erase prior filesystem blocks, snapshots, copies or backups.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import warnings

from .auth import LocalOwnerAuth, AuthError, _private_path
from .crypto import canonical, fingerprint
from .storage import RecordStorage, StorageDenied, StoreLease, FIELDS, VERSION, PREFIX

MAX_DATABASE = 128 * 1024 * 1024
PENDING = 'runtime.sqlite.encrypted.pending'
TABLES = frozenset(('runtime_meta', 'runtime_items', 'runtime_tombstones', 'runtime_controls',
    'runtime_audit', 'peer_meta', 'peer_enrolment', 'peer_outbox', 'peer_inbox', 'peer_receipts',
    'pilot_provider_meta', 'pilot_provider_runs', 'pilot_workflow_meta', 'pilot_workflow_artifacts',
    'https_send_attempts', 'source_grant_meta', 'source_grant_observations', 'source_grant_withdrawals',
    'source_grant_claims', 'source_grant_cancellations', 'source_grant_revocations', 'sqlite_sequence'))


class MigrationOutcomeUnknown(RuntimeError):
    pass


def _read(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_DATABASE):
            raise StorageDenied('Private bounded runtime file required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(MAX_DATABASE + 1)
        after = os.fstat(fd)
        if len(raw) != info.st_size or any(getattr(after, field) != getattr(info, field)
                for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
            raise StorageDenied('Runtime file changed during migration')
        return raw, (info.st_dev, info.st_ino)
    finally:
        os.close(fd)


def _sidecars(directory_fd, *, pending_allowed=False):
    for name in ('runtime.sqlite-journal', 'runtime.sqlite-wal', 'runtime.sqlite-shm', PENDING):
        if name == PENDING and pending_allowed:
            continue
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise StorageDenied('Retained sidecar or migration output requires explicit inspection; no automatic recovery')


def _convert(raw, auth, session):
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.deserialize(raw)
        db.execute('PRAGMA temp_store=MEMORY')
        db.execute('PRAGMA secure_delete=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise StorageDenied('Legacy database integrity check failed')
        schema = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%'").fetchall()
        if any(row['type'] != 'table' or row['name'] not in TABLES for row in schema):
            raise StorageDenied('Unknown or already encrypted database schema requires explicit review')
        from .runtime import VERSION as RUNTIME_VERSION
        metadata = db.execute('SELECT id,version,identity FROM runtime_meta').fetchall()
        if len(metadata) != 1 or tuple(metadata[0]) != (1, RUNTIME_VERSION, canonical(auth.public_identity()).decode()):
            raise StorageDenied('Legacy runtime belongs to a different owner or format')
        tables = {row['name'] for row in schema}
        before = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in tables}
        if sum(len(rows) for rows in before.values()) > 100000:
            raise StorageDenied('Legacy row count exceeds migration bound')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE application_storage(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL)')
        db.execute('INSERT INTO application_storage VALUES(1,?,?)', (VERSION, fingerprint(auth.public_identity())))
        codec = RecordStorage(db, auth)
        for table, (primary, columns) in FIELDS.items():
            for row in before.get(table, []):
                for column in columns:
                    value = row[column]
                    if value is not None:
                        if type(value) is not str or value.startswith(PREFIX):
                            raise StorageDenied('Legacy payload type or missing encrypted format requires explicit review')
                        encoded = codec.seal(table, row[primary], column, value)
                        db.execute('UPDATE ' + table + ' SET ' + column + '=? WHERE ' + primary + '=?', (encoded, row[primary]))
        auth.authenticate(session)
        db.execute('COMMIT')
        # A memory-only VACUUM drops freed plaintext cells/pages before serialising.
        db.execute('VACUUM')
        for table, original in before.items():
            current = [dict(codec.row(table, row)) if table in FIELDS else dict(row)
                       for row in db.execute('SELECT * FROM ' + table)]
            if sorted(map(canonical, current)) != sorted(map(canonical, original)):
                raise StorageDenied('Migration altered retained logical records')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise StorageDenied('Encrypted database integrity check failed')
        auth.authenticate(session)
        return db.serialize()
    finally:
        db.close()


def migrate(directory, auth, session):
    """Replace exactly one stopped runtime, using an already-authenticated owner."""
    directory = Path(directory)
    _private_path(directory, directory=True)
    lease = StoreLease(directory, exclusive=True)
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except BaseException:
        lease.close()
        raise
    started_write = False
    try:
        with auth.authorised(session):
            _sidecars(directory_fd)
            original, identity = _read(directory_fd, 'runtime.sqlite')
            encrypted = _convert(original, auth, session)
            # Refuse source replacement/mutation or a new journal before publishing.
            current, current_identity = _read(directory_fd, 'runtime.sqlite')
            if current_identity != identity or current != original:
                raise StorageDenied('Runtime changed before migration publication')
            _sidecars(directory_fd)
            auth.authenticate(session)
            fd = os.open(PENDING, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            started_write = True
            with os.fdopen(fd, 'wb') as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            written, _ = _read(directory_fd, PENDING)
            if written != encrypted:
                raise StorageDenied('Encrypted migration output verification failed')
            current, current_identity = _read(directory_fd, 'runtime.sqlite')
            if current_identity != identity or current != original:
                raise StorageDenied('Runtime changed before replacement')
            _sidecars(directory_fd, pending_allowed=True)
            auth.authenticate(session)
            os.replace(PENDING, 'runtime.sqlite', src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
            return {'storage': VERSION, 'migrated': True, 'plaintext_backup_created': False,
                    'secure_erasure': False, 'database_sha256': hashlib.sha256(encrypted).hexdigest()}
    except BaseException as error:
        if started_write and isinstance(error, Exception):
            raise MigrationOutcomeUnknown('Migration outcome unavailable; stop and inspect retained runtime and pending output before any retry') from None
        raise
    finally:
        os.close(directory_fd)
        lease.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Encrypt existing local application payloads; stop the owner service first')
    parser.add_argument('--directory', required=True, help='Existing owner authentication directory')
    parser.add_argument('--runtime-directory', help='Runtime directory if separate from owner directory')
    args = parser.parse_args(argv)
    directory = Path(args.directory)
    runtime = Path(args.runtime_directory) if args.runtime_directory else directory
    auth = None
    try:
        _private_path(directory, directory=True)
        _private_path(directory / 'auth.sqlite')
        _private_path(runtime / 'runtime.sqlite')
        auth = LocalOwnerAuth(directory)
        auth.public_identity()
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            session = auth.login(getpass.getpass('Current owner password: '))
        print(json.dumps(migrate(runtime, auth, session), sort_keys=True))
    except getpass.GetPassWarning:
        raise SystemExit('A private interactive terminal is required') from None
    except (AuthError, StorageDenied, MigrationOutcomeUnknown) as error:
        raise SystemExit(str(error)) from None
    except (OSError, sqlite3.Error, ValueError):
        raise SystemExit('Storage migration unavailable; stop and inspect before retrying') from None
    finally:
        if auth is not None:
            auth.close()


if __name__ == '__main__':
    main()
