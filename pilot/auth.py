"""Local password-authenticated owner sessions with an encrypted identity vault.

This binds a local account, not a legally verified human. A private directory and
an independently owned OS account are deployment requirements. Process memory,
same-UID attackers, root, rollback of backups and compromised hosts are outside
this first pilot's protection. No raw password, bearer token or private key is
written to disk or returned by metadata methods.
"""
from contextlib import contextmanager
import base64
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


VERSION = "assistant-central-local-owner-auth/1"
KDF_N, KDF_R, KDF_P = 2**15, 8, 1
MAX_SESSION_SECONDS = 3600
MAX_ACTIVE_SESSIONS = 32
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class AuthError(PermissionError):
    """Fixed-message local authentication failure; never include supplied secrets."""


class AuthOutcomeUnknown(RuntimeError):
    """Credential commit outcome is unknown; local key access is locked."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value, length):
    if type(value) is not str:
        raise AuthError("Identity vault unavailable")
    try:
        result = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise AuthError("Identity vault unavailable") from None
    if len(result) != length or _b64(result) != value:
        raise AuthError("Identity vault unavailable")
    return result


def _password(value):
    if type(value) is not str or len(value) < 12:
        raise AuthError("Password must contain 12 to 1024 UTF-8 bytes")
    try:
        result = value.encode("utf-8", "strict")
    except UnicodeError:
        raise AuthError("Password must contain 12 to 1024 UTF-8 bytes") from None
    if len(result) > 1024:
        raise AuthError("Password must contain 12 to 1024 UTF-8 bytes")
    return result


def _derive(password, salt):
    return Scrypt(salt=salt, length=64, n=KDF_N, r=KDF_R, p=KDF_P).derive(password)


def _private_path(path, *, directory=False):
    """Reject symlinks, foreign ownership and over-permissive existing paths."""
    try:
        info = path.lstat()
    except OSError:
        raise AuthError("Private owner storage unavailable") from None
    expected = 0o700 if directory else 0o600
    if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != expected
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise AuthError("Owner storage must be privately owned with mode 0700 directories and 0600 files")


def _create_private_file(path):
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        _private_path(path)
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    except OSError:
        raise AuthError("Private owner storage unavailable") from None
    os.close(fd)
    _private_path(path)


class LocalOwnerAuth:
    """One immutable local owner/agent account per independently controlled directory.

    Constructors and bootstrap are trusted provisioning controls. HTTP routes must
    never expose bootstrap or accept an owner label as authentication. All public
    owner mutations require a current bearer session. Keys stay encrypted at rest
    and are unlocked only by a successful password login.
    """

    def __init__(self, directory, *, clock=time.time):
        self.directory = Path(directory).absolute()
        self.clock = clock
        self._lock = threading.RLock()
        self._vault = None
        self._public = None
        self._closed = False
        self._credential_uncertain = False
        self._db = None
        self._lock_fd = None
        self._last_now = None
        try:
            try:
                self.directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
            _private_path(self.directory, directory=True)
            for name in ("auth.lock", "auth.sqlite"):
                _create_private_file(self.directory / name)
            self._file_identity = {name: ((self.directory / name).stat().st_dev, (self.directory / name).stat().st_ino)
                                   for name in ("auth.lock", "auth.sqlite")}
            self._lock_fd = os.open(self.directory / "auth.lock", os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AuthError("Owner authentication store is already open") from None
            self._db = sqlite3.connect(self.directory / "auth.sqlite", timeout=5, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS account(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL,
                    public TEXT NOT NULL, salt BLOB NOT NULL, verifier BLOB NOT NULL,
                    nonce BLOB NOT NULL, vault BLOB NOT NULL,
                    failures INTEGER NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sessions(
                    digest TEXT PRIMARY KEY, issued REAL NOT NULL, expires REAL NOT NULL);
            """)
            with self._db:
                # A restart is an explicit lock boundary. Persisted token hashes
                # never unlock a key vault or survive a new owner process.
                self._db.execute("DELETE FROM sessions")
            account = self._account(required=False)
            if account:
                self._public = self._descriptor(account)
        except BaseException:
            if self._db is not None:
                self._db.close()
            if self._lock_fd is not None:
                os.close(self._lock_fd)
            self._closed = True
            raise

    def _open(self):
        if self._credential_uncertain:
            raise AuthOutcomeUnknown("Restart the local pilot before inspecting a password change outcome")
        if self._closed:
            raise AuthError("Owner authentication is closed")
        _private_path(self.directory, directory=True)
        _private_path(self.directory / "auth.sqlite")
        _private_path(self.directory / "auth.lock")
        for name, expected in self._file_identity.items():
            actual = (self.directory / name).stat()
            if (actual.st_dev, actual.st_ino) != expected:
                raise AuthError("Private owner storage changed")

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise AuthError("Owner authentication clock unavailable")
        if self._last_now is not None and now < self._last_now:
            raise AuthError("Owner authentication clock moved backwards")
        self._last_now = now
        return now

    def _account(self, required=True):
        row = self._db.execute("SELECT * FROM account WHERE singleton=1").fetchone()
        if row is None and required:
            raise AuthError("Local owner has not been provisioned")
        return row

    @staticmethod
    def _descriptor(account):
        try:
            descriptor = json.loads(account["public"])
            if (account["version"] != VERSION or type(descriptor) is not dict
                    or set(descriptor) != {"owner_id", "agent_id", "signing_key", "exchange_key"}
                    or any(type(descriptor[key]) is not str or not _ID.fullmatch(descriptor[key])
                           for key in ("owner_id", "agent_id"))
                    or _canonical(descriptor).decode() != account["public"]):
                raise ValueError()
            if any(type(account[key]) is not bytes or len(account[key]) != length
                   for key, length in (("salt", 16), ("verifier", 32), ("nonce", 12), ("vault", 80))):
                raise ValueError()
            _unb64(descriptor["signing_key"], 32)
            _unb64(descriptor["exchange_key"], 32)
        except (ValueError, TypeError, KeyError):
            raise AuthError("Identity vault unavailable") from None
        return descriptor

    def bootstrap(self, owner_id, agent_id, password):
        """Trusted one-time local account provisioning, not an unauthenticated route."""
        if any(type(value) is not str or not _ID.fullmatch(value) for value in (owner_id, agent_id)):
            raise AuthError("Expected bounded owner and agent identifiers")
        password_bytes = _password(password)
        with self._lock:
            self._open()
            if self._account(required=False):
                raise AuthError("Local owner enrollment is immutable")
            signing, exchange = Ed25519PrivateKey.generate(), X25519PrivateKey.generate()
            public = {"owner_id": owner_id, "agent_id": agent_id,
                      "signing_key": _b64(signing.public_key().public_bytes_raw()),
                      "exchange_key": _b64(exchange.public_key().public_bytes_raw())}
            salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            derived = _derive(password_bytes, salt)
            verifier = hmac.digest(derived[:32], VERSION.encode() + _canonical(public), "sha256")
            private = signing.private_bytes_raw() + exchange.private_bytes_raw()
            ciphertext = AESGCM(derived[32:]).encrypt(nonce, private, VERSION.encode() + _canonical(public))
            with self._db:
                self._db.execute("INSERT INTO account VALUES(1,?,?,?,?,?,?,0,0)",
                                 (VERSION, _canonical(public).decode(), salt, verifier, nonce, ciphertext))
            self._public = dict(public)
            return dict(public)

    def public_identity(self):
        with self._lock:
            self._open()
            public = self._descriptor(self._account())
            if public != self._public:
                raise AuthError("Enrolled identity changed")
            return public

    def _unlock(self, password_bytes):
        """Verify the current password with the shared persistent failure budget."""
        now, account = self._now(), self._account()
        public = self.public_identity()
        if now < account["retry_after"]:
            raise AuthError("Authentication temporarily unavailable")
        derived = _derive(password_bytes, account["salt"])
        expected = hmac.digest(derived[:32], VERSION.encode() + _canonical(public), "sha256")
        if not hmac.compare_digest(expected, account["verifier"]):
            failures = min(account["failures"] + 1, 10)
            with self._db:
                self._db.execute("UPDATE account SET failures=?,retry_after=? WHERE singleton=1",
                                 (failures, now + min(2 ** (failures - 1), 30)))
            raise AuthError("Authentication failed")
        try:
            private = AESGCM(derived[32:]).decrypt(account["nonce"], account["vault"],
                                                  VERSION.encode() + _canonical(public))
            if len(private) != 64:
                raise ValueError()
            signing = Ed25519PrivateKey.from_private_bytes(private[:32])
            exchange = X25519PrivateKey.from_private_bytes(private[32:])
            if (_b64(signing.public_key().public_bytes_raw()) != public["signing_key"]
                    or _b64(exchange.public_key().public_bytes_raw()) != public["exchange_key"]):
                raise ValueError()
        except (InvalidTag, ValueError):
            raise AuthError("Identity vault unavailable") from None
        return signing, exchange

    def login(self, password, *, ttl=900):
        """Return a single bearer token. Caller must not log or persist it."""
        if type(ttl) not in (int, float) or not math.isfinite(ttl) or not 1 <= ttl <= MAX_SESSION_SECONDS:
            raise AuthError("Session duration must be between one second and one hour")
        try:
            password_bytes = _password(password)
        except AuthError:
            raise AuthError("Authentication failed") from None
        with self._lock:
            self._open()
            signing, exchange = self._unlock(password_bytes)
            now = self._now()
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256((VERSION + "/session\0" + token).encode()).hexdigest()
            with self._db:
                self._db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
                if self._db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= MAX_ACTIVE_SESSIONS:
                    raise AuthError("Active session limit reached")
                self._db.execute("INSERT INTO sessions VALUES(?,?,?)", (token_hash, now, now + ttl))
                self._db.execute("UPDATE account SET failures=0,retry_after=0 WHERE singleton=1")
            self._vault = (signing, exchange)
            return token

    def change_password(self, token, current_password, new_password):
        """Rewrap the same identity, atomically revoke every session, then lock.

        This is not lost-password recovery or identity-key rotation. No replacement
        session is returned. On an uncertain commit the in-memory vault is locked;
        restart and sign in explicitly; never retry this mutation automatically.
        """
        new_bytes = _password(new_password)
        try:
            current_bytes = _password(current_password)
        except AuthError:
            raise AuthError("Authentication failed") from None
        with self._lock:
            self._session(token)
            signing, exchange = self._unlock(current_bytes)
            if hmac.compare_digest(current_bytes, new_bytes):
                raise AuthError("Choose a different new password")
            public = self.public_identity()
            salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
            derived = _derive(new_bytes, salt)
            verifier = hmac.digest(derived[:32], VERSION.encode() + _canonical(public), "sha256")
            private = signing.private_bytes_raw() + exchange.private_bytes_raw()
            ciphertext = AESGCM(derived[32:]).encrypt(nonce, private, VERSION.encode() + _canonical(public))
            # Both KDFs can take time. Expiry and file identity must still hold
            # immediately before the credential/session transaction commits.
            self._session(token)
            try:
                with self._db:
                    self._db.execute("UPDATE account SET salt=?,verifier=?,nonce=?,vault=?,failures=0,retry_after=0 WHERE singleton=1",
                                     (salt, verifier, nonce, ciphertext))
                    self._session(token)  # Recheck after writes, before revocation/commit.
                    self._db.execute("DELETE FROM sessions")
            except BaseException as error:
                self._credential_uncertain = True
                if not isinstance(error, Exception):
                    raise
                raise AuthOutcomeUnknown("Password change outcome unavailable. Restart the local pilot and sign in explicitly; do not automatically retry.") from None
            finally:
                self._vault = None
            return {"password_changed": True, "all_sessions_revoked": True, "identity_unchanged": True}

    def _session(self, token):
        self._open()
        if type(token) is not str or not _TOKEN.fullmatch(token) or self._vault is None:
            raise AuthError("Current owner session required")
        now = self._now()
        token_hash = hashlib.sha256((VERSION + "/session\0" + token).encode()).hexdigest()
        session = self._db.execute("SELECT * FROM sessions WHERE digest=?", (token_hash,)).fetchone()
        if not session or not session["issued"] <= now < session["expires"]:
            if self._db.execute("SELECT COUNT(*) FROM sessions WHERE expires>?", (now,)).fetchone()[0] == 0:
                self._vault = None
            raise AuthError("Current owner session required")
        public = self.public_identity()
        return token_hash, {"owner_id": public["owner_id"], "agent_id": public["agent_id"],
                            "identity_fingerprint": hashlib.sha256(_canonical(public)).hexdigest(),
                            "expires_at": session["expires"]}

    def authenticate(self, token):
        with self._lock:
            return self._session(token)[1]

    @contextmanager
    def authorised(self, token):
        """Hold session revocation ordering through the caller's local transaction.

        Nest the runtime transaction *inside* this guard. Recheck authenticate()
        immediately before committing if the transaction may take time. The
        guard prevents local logout/revocation from passing its final check.
        """
        with self._lock:
            yield self._session(token)[1]

    def sign(self, token, data):
        if type(data) is not bytes or not 1 <= len(data) <= 1024 * 1024:
            raise AuthError("Expected bounded bytes to sign")
        with self._lock:
            self._session(token)
            return self._vault[0].sign(data)

    def exchange(self, token, peer_public):
        if type(peer_public) is not bytes or len(peer_public) != 32:
            raise AuthError("Expected an exact peer exchange key")
        with self._lock:
            self._session(token)
            try:
                return self._vault[1].exchange(X25519PublicKey.from_public_bytes(peer_public))
            except ValueError:
                raise AuthError("Peer exchange key rejected") from None

    def _application_storage_exchange(self, ephemeral_public):
        """Internal record-opening primitive, never an owner/peer route.

        Runtime APIs remain responsible for the exact caller session. Refuse
        opening after lock, logout, expiry, credential uncertainty or close.
        Public-key record sealing needs no unlocked private key.
        """
        with self._lock:
            self._open()
            now = self._now()
            if self._vault is None or not self._db.execute(
                    "SELECT 1 FROM sessions WHERE issued<=? AND expires>?", (now, now)).fetchone():
                raise AuthError("Current owner session required")
            try:
                return self._vault[1].exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
            except (ValueError, TypeError):
                raise AuthError("Application storage key unavailable") from None

    def logout(self, token):
        with self._lock:
            token_hash, _ = self._session(token)
            with self._db:
                self._db.execute("DELETE FROM sessions WHERE digest=?", (token_hash,))
            if not self._db.execute("SELECT 1 FROM sessions WHERE expires>?", (self._now(),)).fetchone():
                self._vault = None

    def revoke_all(self, token):
        with self._lock:
            self._session(token)
            self.lock()

    def lock(self):
        """Trusted process lifecycle control; does not grant authority."""
        with self._lock:
            self._open()
            self._vault = None
            with self._db:
                self._db.execute("DELETE FROM sessions")

    def status(self):
        with self._lock:
            self._open()
            now = self._now()
            enrolled = self._account(required=False) is not None
            count = self._db.execute("SELECT COUNT(*) FROM sessions WHERE expires>?", (now,)).fetchone()[0]
            if not count:
                self._vault = None
            return {"enrolled": enrolled, "unlocked": self._vault is not None, "active_sessions": count,
                    "authentication": "local-password", "human_identity_verified": False}

    def close(self):
        with self._lock:
            if not self._closed:
                try:
                    self._vault = None
                    with self._db:
                        self._db.execute("DELETE FROM sessions")
                finally:
                    self._db.close()
                    os.close(self._lock_fd)
                    self._closed = True
