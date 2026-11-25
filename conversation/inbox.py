"""Durable assistant inboxes over the conversation ledger.

An assistant acting for one owner reads that owner's visible conversation
messages through a host-held lease, acknowledges what it has processed and can
be woken by a body-free hint. Nothing here sends, approves, discloses or
executes. Message text remains untrusted input with no authority.

Contract, in short:

* The trusted host provisions a lease after authenticating the owner. A lease
  names one owner, one assistant identity and one conversation. Provisioning
  again starts a new session *generation* and fences every older lease.
* ``pending`` returns visible messages after the durable cursor, in ledger
  order, and records each one as delivered to the current generation.
* ``acknowledge`` advances the cursor only to a message delivered to the
  current generation. It never moves backwards and repeating it is harmless,
  so a lost acknowledgement response can be retried safely.
* ``wake_hint`` reveals only whether something is waiting and an opaque change
  token. It carries no text, identifiers, counts or authors.
* Rejoining a conversation creates a new membership epoch. The cursor of the
  old epoch is discarded rather than reinterpreted, matching the ledger's
  future-only membership rule.
"""
from dataclasses import dataclass
import hashlib
import hmac
import math
import secrets
import sqlite3
import threading
from pathlib import Path

from pilot.auth import _create_private_file, _private_path
from pilot.crypto import canonical

from .ledger import ConversationDenied, ConversationLedger, identifier, need

VERSION = 'assistant-central-inbox/1'
MAX_LEASE_SECONDS = 900
MAX_KEYS = 256
MAX_DELIVERIES = 4096
MAX_BATCH = 50


@dataclass(frozen=True)
class AssistantLease:
    """Host-held binding. Never accept these fields from model input."""
    principal: str
    assistant_id: str
    conversation_id: str
    generation: int
    expires_at: float


class InboxStore:
    """Trusted local-host API layered on one :class:`ConversationLedger`."""

    def __init__(self, directory, ledger):
        need(type(ledger) is ConversationLedger)
        self.ledger = ledger
        self._lock, self._closed = threading.RLock(), False
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private_path(self.directory, directory=True)
        path = self.directory / 'inbox.sqlite'
        _create_private_file(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            new_store = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchone() is None
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS inbox_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,hint_key TEXT NOT NULL,observed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS inbox_leases(principal TEXT NOT NULL,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,generation INTEGER NOT NULL,epoch TEXT NOT NULL,expires REAL NOT NULL,revoked INTEGER NOT NULL,PRIMARY KEY(principal,assistant_id,conversation_id));
                CREATE TABLE IF NOT EXISTS inbox_cursors(principal TEXT NOT NULL,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,epoch TEXT NOT NULL,through_event TEXT,through_ordinal INTEGER NOT NULL,next_ordinal INTEGER NOT NULL,PRIMARY KEY(principal,assistant_id,conversation_id));
                CREATE TABLE IF NOT EXISTS inbox_deliveries(principal TEXT NOT NULL,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,event_id TEXT NOT NULL,ordinal INTEGER NOT NULL,generation INTEGER NOT NULL,PRIMARY KEY(principal,assistant_id,conversation_id,event_id));
            ''')
            with self._lock:
                self.db.execute('BEGIN IMMEDIATE')
                row = self.db.execute('SELECT * FROM inbox_meta WHERE singleton=1').fetchone()
                if row is None:
                    need(new_store)  # Never silently reset an existing store's clock fence.
                    self.db.execute('INSERT INTO inbox_meta VALUES(1,?,?,0)', (VERSION, secrets.token_hex(32)))
                else:
                    need(row['version'] == VERSION and type(row['observed']) in (int, float) and math.isfinite(row['observed']))
                self.db.execute('COMMIT')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            if not self._closed:
                self.db.close()
                self._closed = True

    # Internal guards -----------------------------------------------------

    def _now(self):
        # Persist the highest observed time so a clock rewind after restart
        # cannot revive an expired lease. Called inside a write transaction.
        value = self.ledger.clock()
        need(type(value) in (int, float) and math.isfinite(value) and value > 0)
        observed = self.db.execute('SELECT observed FROM inbox_meta WHERE singleton=1').fetchone()['observed']
        need(value >= observed)
        self.db.execute('UPDATE inbox_meta SET observed=? WHERE singleton=1', (value,))
        return value

    def _authenticate(self, principal, session):
        need(type(principal) is str and principal in self.ledger.actors)
        identity = self.ledger.actors[principal].authenticate(session)
        need(identity['identity_fingerprint'] == principal)

    def _key(self, lease):
        need(type(lease) is AssistantLease)
        return (lease.principal, lease.assistant_id, lease.conversation_id)

    def _live(self, lease):
        row = self.db.execute('SELECT * FROM inbox_leases WHERE principal=? AND assistant_id=? AND conversation_id=?',
                              self._key(lease)).fetchone()
        need(row is not None and row['revoked'] == 0 and row['generation'] == lease.generation
             and row['expires'] == lease.expires_at)
        if not self._now() < row['expires']:
            # _live runs first in its transaction, so only the observed-time
            # fence is pending. Keep it, so a later rewind cannot revive this.
            self.db.execute('COMMIT')
            need(False)
        return row

    def _write(self):
        need(not self._closed)
        self.db.execute('BEGIN IMMEDIATE')

    def _commit_or_rollback(self, error):
        if self.db.in_transaction:
            self.db.execute('ROLLBACK' if error else 'COMMIT')

    def _cursor(self, lease, epoch):
        row = self.db.execute('SELECT * FROM inbox_cursors WHERE principal=? AND assistant_id=? AND conversation_id=?',
                              self._key(lease)).fetchone()
        need(row is not None and row['epoch'] == epoch)
        return row

    def _binding(self, lease, session, lease_row):
        binding = self.ledger.bind_context(lease.principal, session, lease.conversation_id)
        # A rejoin after provisioning is a new audience: require a new lease.
        need(binding.member_epoch == lease_row['epoch'])
        return binding

    # Host API ------------------------------------------------------------

    def provision(self, principal, session, assistant_id, conversation_id, *, ttl=MAX_LEASE_SECONDS):
        identifier(assistant_id); identifier(conversation_id)
        need(type(ttl) in (int, float) and math.isfinite(ttl) and 0 < ttl <= MAX_LEASE_SECONDS)
        with self._lock:
            self._authenticate(principal, session)
            binding = self.ledger.bind_context(principal, session, conversation_id)
            key = (principal, assistant_id, conversation_id)
            error = None
            self._write()
            try:
                now = self._now()
                old = self.db.execute('SELECT generation FROM inbox_leases WHERE principal=? AND assistant_id=? AND conversation_id=?', key).fetchone()
                if old is None:
                    need(self.db.execute('SELECT COUNT(*) FROM inbox_leases').fetchone()[0] < MAX_KEYS)
                generation = 1 if old is None else old['generation'] + 1
                expires = now + ttl
                self.db.execute('INSERT OR REPLACE INTO inbox_leases VALUES(?,?,?,?,?,?,0)',
                                (*key, generation, binding.member_epoch, expires))
                cursor = self.db.execute('SELECT epoch FROM inbox_cursors WHERE principal=? AND assistant_id=? AND conversation_id=?', key).fetchone()
                if cursor is None or cursor['epoch'] != binding.member_epoch:
                    # Future-only membership: an old epoch's position means nothing now.
                    self.db.execute('DELETE FROM inbox_deliveries WHERE principal=? AND assistant_id=? AND conversation_id=?', key)
                    self.db.execute('INSERT OR REPLACE INTO inbox_cursors VALUES(?,?,?,?,NULL,0,1)', (*key, binding.member_epoch))
                return AssistantLease(principal, assistant_id, conversation_id, generation, expires)
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._commit_or_rollback(error)

    def revoke(self, session, lease):
        """Terminal for this generation. Retained cursor and deliveries remain."""
        with self._lock:
            self._authenticate(self._key(lease)[0], session)
            error = None
            self._write()
            try:
                self._now()
                row = self.db.execute('SELECT generation FROM inbox_leases WHERE principal=? AND assistant_id=? AND conversation_id=?',
                                      self._key(lease)).fetchone()
                need(row is not None and row['generation'] == lease.generation)
                self.db.execute('UPDATE inbox_leases SET revoked=1 WHERE principal=? AND assistant_id=? AND conversation_id=?', self._key(lease))
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._commit_or_rollback(error)

    def pending(self, session, lease, *, limit=20):
        """Visible messages after the cursor, recorded as delivered."""
        need(type(limit) is int and 1 <= limit <= MAX_BATCH)
        with self._lock:
            self._authenticate(self._key(lease)[0], session)
            error = None
            self._write()
            try:
                row = self._live(lease)
                cursor = self._cursor(lease, row['epoch'])
                # The ledger runs its own authenticated, visibility-checked
                # transaction; ours is released for the read, then re-taken.
                self.db.execute('COMMIT')
                binding = self._binding(lease, session, row)
                messages = self.ledger.history(lease.principal, session, binding,
                                               after=cursor['through_event'], limit=limit)
                self._write()
                row = self._live(lease)
                fresh = self._cursor(lease, row['epoch'])
                # A concurrent acknowledgement may have moved the cursor while
                # the ledger read ran: refuse rather than return stale order.
                need(fresh['through_event'] == cursor['through_event'])
                ordinal = fresh['next_ordinal']
                for message in messages:
                    known = self.db.execute('SELECT ordinal FROM inbox_deliveries WHERE principal=? AND assistant_id=? AND conversation_id=? AND event_id=?',
                                            (*self._key(lease), message['id'])).fetchone()
                    if known is None:
                        need(self.db.execute('SELECT COUNT(*) FROM inbox_deliveries WHERE principal=? AND assistant_id=? AND conversation_id=?',
                                             self._key(lease)).fetchone()[0] < MAX_DELIVERIES)
                        self.db.execute('INSERT INTO inbox_deliveries VALUES(?,?,?,?,?,?)',
                                        (*self._key(lease), message['id'], ordinal, lease.generation))
                        ordinal += 1
                    else:
                        self.db.execute('UPDATE inbox_deliveries SET generation=? WHERE principal=? AND assistant_id=? AND conversation_id=? AND event_id=?',
                                        (lease.generation, *self._key(lease), message['id']))
                self.db.execute('UPDATE inbox_cursors SET next_ordinal=? WHERE principal=? AND assistant_id=? AND conversation_id=?',
                                (ordinal, *self._key(lease)))
                return {'conversation_id': lease.conversation_id, 'messages': messages,
                        'more': len(messages) == limit, 'trust': 'untrusted-messages',
                        'execution_authority': False}
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._commit_or_rollback(error)

    def acknowledge(self, session, lease, through_event_id):
        """Advance the cursor to a message delivered to this generation.

        Idempotent: acknowledging the current or an earlier position changes
        nothing and reports the current cursor.
        """
        identifier(through_event_id)
        with self._lock:
            self._authenticate(self._key(lease)[0], session)
            error = None
            self._write()
            try:
                row = self._live(lease)
                cursor = self._cursor(lease, row['epoch'])
                delivered = self.db.execute('SELECT ordinal,generation FROM inbox_deliveries WHERE principal=? AND assistant_id=? AND conversation_id=? AND event_id=?',
                                            (*self._key(lease), through_event_id)).fetchone()
                need(delivered is not None)
                if delivered['ordinal'] > cursor['through_ordinal']:
                    need(delivered['generation'] == lease.generation)
                    self.db.execute('UPDATE inbox_cursors SET through_event=?,through_ordinal=? WHERE principal=? AND assistant_id=? AND conversation_id=?',
                                    (through_event_id, delivered['ordinal'], *self._key(lease)))
                    current = through_event_id
                else:
                    current = cursor['through_event']
                return {'conversation_id': lease.conversation_id, 'acknowledged_through': current}
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._commit_or_rollback(error)

    def wake_hint(self, session, lease):
        """Body-free notification state for an already running assistant."""
        with self._lock:
            self._authenticate(self._key(lease)[0], session)
            error = None
            self._write()
            try:
                row = self._live(lease)
                cursor = self._cursor(lease, row['epoch'])
                key = self.db.execute('SELECT hint_key FROM inbox_meta WHERE singleton=1').fetchone()['hint_key']
                self.db.execute('COMMIT')
                binding = self._binding(lease, session, row)
                # Page to the newest visible message so any arrival changes the token.
                after, latest, pages = cursor['through_event'], '', 0
                while True:
                    page = self.ledger.history(lease.principal, session, binding, after=after, limit=MAX_BATCH)
                    if not page:
                        break
                    latest = after = page[-1]['id']
                    pages += 1
                    need(pages <= MAX_DELIVERIES // MAX_BATCH + 1)
                    if len(page) < MAX_BATCH:
                        break
                waiting = bool(latest)
                material = canonical([VERSION + '/hint', *self._key(lease), lease.generation,
                                      cursor['through_event'] or '', latest])
                token = hmac.new(bytes.fromhex(key), material, hashlib.sha256).hexdigest()[:32]
                return {'pending': waiting, 'hint': token}
            except BaseException as exc:
                error = exc
                raise
            finally:
                self._commit_or_rollback(error)


class InboxAccess:
    """What a trusted host hands to an assistant-facing server.

    The lease is fixed at construction and the owner's current session comes
    from a host callback, so nothing a model sends can choose the owner, the
    assistant identity, the conversation or the session.
    """

    def __init__(self, store, lease, session_provider):
        need(type(store) is InboxStore and type(lease) is AssistantLease and callable(session_provider))
        self._store, self._lease, self._session = store, lease, session_provider

    @property
    def conversation_id(self):
        return self._lease.conversation_id

    def pending(self, limit=20):
        return self._store.pending(self._session(), self._lease, limit=limit)

    def acknowledge(self, through_event_id):
        return self._store.acknowledge(self._session(), self._lease, through_event_id)

    def wake_hint(self):
        return self._store.wake_hint(self._session(), self._lease)
