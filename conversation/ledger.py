"""Durable, owner-authenticated local conversations with epoch-bound history.

The trusted host supplies authenticators and sessions. Message bodies are inert.
No network, model invocation, embeddings, attachment fetch or execution is here.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from pilot.auth import LocalOwnerAuth, _create_private_file, _private_path
from pilot.crypto import b64, canonical, digest, fingerprint, unb64
from pilot.storage import RecordStorage, StoreLease

VERSION = 'assistant-central-conversation/1'
MAX_EVENTS = 4096
MAX_MEMBERS = 32
MAX_SOURCES = 32
MAX_TEXT = 16384
MAX_GRANT_SECONDS = 86400
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')


class ConversationDenied(PermissionError):
    """Generic refusal does not disclose inaccessible records or text."""


class ConversationOutcomeUnknown(RuntimeError):
    """Inspect the stable request identifier; never infer rollback or retry effects."""


def need(condition):
    if not condition:
        raise ConversationDenied('Conversation operation unavailable')


def identifier(value):
    need(type(value) is str and _ID.fullmatch(value) is not None)
    return value


def bounded_text(value, maximum=MAX_TEXT):
    try:
        need(type(value) is str and 0 < len(value.encode('utf-8')) <= maximum)
    except UnicodeError:
        raise ConversationDenied('Conversation operation unavailable') from None
    return value


def snapshot(value):
    return json.loads(canonical(value))


@dataclass(frozen=True)
class ContextBinding:
    """Trusted host binding, not a bearer token or model-selectable identity."""
    conversation_id: str
    principal: str
    member_epoch: str
    policy_generation: int


class _ConversationStorage(RecordStorage):
    # Use the reviewed storage primitive and owner identity, but a disjoint AEAD
    # domain. Never mutate pilot.storage.FIELDS or masquerade as pilot rows.
    def _context(self, table, row_id, column):
        need(table in ('conversation_events', 'conversation_audit', 'conversation_grants')
             and column == 'body' and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class ConversationLedger:
    """Trusted local-host API, not a remotely accessible multi-owner service.

    `actors` is a provisioning-only mapping from pinned fingerprint to genuine
    LocalOwnerAuth. The coordinating storage owner must also be unlocked to open
    payloads. Each operation independently requires its actor's current session.
    """
    def __init__(self, directory, storage_auth, actors, *, clock=time.time):
        need(type(storage_auth) is LocalOwnerAuth and type(actors) is dict and 1 <= len(actors) <= MAX_MEMBERS)
        self.actors = dict(actors)
        for principal, auth in self.actors.items():
            need(type(auth) is LocalOwnerAuth and fingerprint(auth.public_identity()) == principal)
        self.storage_owner = fingerprint(storage_auth.public_identity())
        need(self.actors.get(self.storage_owner) is storage_auth)
        self.clock, self._last_time = clock, None
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private_path(self.directory, directory=True)
        path = self.directory / 'conversation.sqlite'
        _create_private_file(path)
        self._file_identity = (path.stat().st_dev, path.stat().st_ino)
        self._lock, self._closed = threading.RLock(), False
        self._lease = StoreLease(self.directory, exclusive=True)
        self.db = None
        try:
            self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA synchronous=FULL')
            new_store = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone() is None
            self.storage = _ConversationStorage(self.db, storage_auth, create=True)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS conversation_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_clock(singleton INTEGER PRIMARY KEY CHECK(singleton=1),observed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_principals(id TEXT PRIMARY KEY,public TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,admin TEXT NOT NULL,generation INTEGER NOT NULL,mode TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_members(conversation_id TEXT NOT NULL,principal TEXT NOT NULL,epoch TEXT NOT NULL,active INTEGER NOT NULL,PRIMARY KEY(conversation_id,principal));
                CREATE TABLE IF NOT EXISTS conversation_invites(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,principal TEXT NOT NULL,epoch TEXT NOT NULL,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,conversation_id TEXT NOT NULL,author TEXT NOT NULL,request_id TEXT NOT NULL,request_digest TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(conversation_id,author,request_id));
                CREATE TABLE IF NOT EXISTS conversation_grants(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,issuer TEXT NOT NULL,recipient TEXT NOT NULL,epoch TEXT NOT NULL,expires REAL NOT NULL,revoked INTEGER NOT NULL,statement TEXT NOT NULL,signature TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,body TEXT NOT NULL);
            ''')
            with self._lock:
                self.db.execute('BEGIN IMMEDIATE')
                old = self.db.execute('SELECT version FROM conversation_meta WHERE singleton=1').fetchone()
                if old:
                    need(old['version'] == VERSION)
                else:
                    need(new_store)
                    self.db.execute('INSERT INTO conversation_meta VALUES(1,?)', (VERSION,))
                observed = self.db.execute('SELECT observed FROM conversation_clock WHERE singleton=1').fetchone()
                if observed is None:
                    need(new_store)  # Never silently reset an existing ledger's clock fence.
                    self.db.execute('INSERT INTO conversation_clock VALUES(1,0)')
                    self._last_time = 0
                else:
                    need(type(observed['observed']) in (int, float) and math.isfinite(observed['observed']) and observed['observed'] >= 0)
                    self._last_time = observed['observed']
                for principal, auth in self.actors.items():
                    public = canonical(auth.public_identity()).decode()
                    old = self.db.execute('SELECT public FROM conversation_principals WHERE id=?', (principal,)).fetchone()
                    need(old is None or old['public'] == public)
                    self.db.execute('INSERT OR IGNORE INTO conversation_principals VALUES(?,?)', (principal, public))
                self.db.execute('COMMIT')
        except BaseException:
            if self.db is not None:
                self.db.close()
            self._lease.close()
            raise

    def close(self):
        with self._lock:
            if not self._closed:
                self.db.close()
                self._lease.close()
                self._closed = True

    def _now(self):
        value = self.clock()
        need(type(value) in (int, float) and math.isfinite(value) and value > 0)
        need(self._last_time is None or value >= self._last_time)
        self._last_time = value
        return value

    def _persist_observed_time(self):
        # This fence deliberately commits outside the message/grant transaction.
        # A refused/rolled-back read must not forget that expiry was observed.
        try:
            need(not self.db.in_transaction)
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT observed FROM conversation_clock WHERE singleton=1').fetchone()
            need(row is not None and type(row['observed']) in (int, float)
                 and math.isfinite(row['observed']) and 0 <= row['observed'] <= self._last_time)
            self.db.execute('UPDATE conversation_clock SET observed=? WHERE singleton=1', (self._last_time,))
            self.db.execute('COMMIT')
        except BaseException as error:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error):
                raise ConversationOutcomeUnknown('Conversation clock fence unavailable; reopen and inspect retained state') from None
            raise

    @contextmanager
    def _authorised(self, principal, session):
        # Two trusted stores may reuse the same authenticators with different
        # storage owners. Acquire distinct auth locks in a stable global order.
        with ExitStack() as guards:
            for owner in sorted({self.storage_owner, principal}):
                guards.enter_context(self.actors[owner]._lock)
            yield guards.enter_context(self.actors[principal].authorised(session))

    @contextmanager
    def _transaction(self, principal, session, *, checks=(), final_checks=()):
        # All local operations (including reads) are ordered against membership
        # changes and revocation. No plaintext cache can bypass these guards.
        with self._lock:
            need(not self._closed and type(principal) is str and principal in self.actors)
            auth = self.actors[principal]
            with self._authorised(principal, session) as identity:
                need(identity['identity_fingerprint'] == principal)
                need(self.storage.auth.status()['unlocked'])
                if final_checks:
                    # Both genuine auth locks are held. status() keeps the vault
                    # unlocked while at least one retained session is unexpired.
                    # Capture that deadline without a trailing auth callback.
                    storage_deadline = self.storage.auth._db.execute('SELECT MAX(expires) FROM sessions').fetchone()[0]
                    need(type(storage_deadline) in (int, float) and math.isfinite(storage_deadline))
                _private_path(self.directory, directory=True)
                path = self.directory / 'conversation.sqlite'
                _private_path(path)
                need((path.stat().st_dev, path.stat().st_ino) == self._file_identity)
                self.storage._check()
                self._now()
                self._persist_observed_time()
                self.db.execute('BEGIN IMMEDIATE')
                try:
                    yield auth
                    try:
                        auth.authenticate(session)  # Expiry/credential changes fail closed.
                    finally:
                        if final_checks:
                            self._now()  # Keep time observed during a refusal.
                    self._now()
                    for check in checks:
                        check()
                    need(self.storage.auth.status()['unlocked'])
                    try:
                        auth.authenticate(session)
                    finally:
                        if final_checks:
                            self._now()
                    for check in final_checks:
                        check()
                    if final_checks:
                        # Auth locks still order logout/revocation. A policy check
                        # may itself observe session expiry; compare the captured
                        # deadline without another authentication callback gap.
                        need(self._last_time < identity['expires_at'] and self._last_time < storage_deadline)
                    self.db.execute('COMMIT')
                except BaseException as error:
                    if self.db.in_transaction:
                        self.db.execute('ROLLBACK')
                    if isinstance(error, sqlite3.Error):
                        raise ConversationOutcomeUnknown('Inspect the retained exact request after reopening the ledger') from None
                    raise
                finally:
                    self._persist_observed_time()

    def _conversation(self, conversation_id):
        identifier(conversation_id)
        row = self.db.execute('SELECT * FROM conversations WHERE id=?', (conversation_id,)).fetchone()
        need(row is not None)
        return row

    def _member(self, conversation_id, principal):
        row = self.db.execute('SELECT * FROM conversation_members WHERE conversation_id=? AND principal=?', (conversation_id, principal)).fetchone()
        need(row is not None and row['active'] == 1)
        return row

    def _admin(self, conversation_id, principal):
        row = self._conversation(conversation_id)
        self._member(conversation_id, principal)
        need(row['admin'] == principal)
        return row

    def _bump(self, conversation_id):
        self.db.execute('UPDATE conversations SET generation=generation+1 WHERE id=?', (conversation_id,))

    def _audit(self, auth, session, kind, data):
        need(self.db.execute('SELECT COUNT(*) FROM conversation_audit').fetchone()[0] < MAX_EVENTS * 4)
        record_id = uuid.uuid4().hex
        body = {'domain': VERSION + '/audit', 'id': record_id, 'actor': fingerprint(auth.public_identity()),
                'kind': kind, 'data': data}
        signed = {'body': body, 'signature': b64(auth.sign(session, canonical(body)))}
        self.db.execute('INSERT INTO conversation_audit(id,body) VALUES(?,?)',
                        (record_id, self.storage.seal('conversation_audit', record_id, 'body', canonical(signed).decode())))

    def create(self, principal, session, conversation_id):
        identifier(conversation_id)
        with self._transaction(principal, session) as auth:
            need(not self.db.execute('SELECT 1 FROM conversations WHERE id=?', (conversation_id,)).fetchone())
            need(self.db.execute('SELECT COUNT(*) FROM conversations').fetchone()[0] < 256)
            self.db.execute('INSERT INTO conversations VALUES(?,?,1,?)', (conversation_id, principal, 'direct'))
            self.db.execute('INSERT INTO conversation_members VALUES(?,?,?,1)', (conversation_id, principal, uuid.uuid4().hex))
            self._audit(auth, session, 'created', {'conversation_id': conversation_id})
            return self._binding(conversation_id, principal)

    def invite(self, principal, session, conversation_id, recipient):
        with self._transaction(principal, session) as auth:
            self._admin(conversation_id, principal)
            need(type(recipient) is str and recipient in self.actors)
            old = self.db.execute('SELECT active FROM conversation_members WHERE conversation_id=? AND principal=?', (conversation_id, recipient)).fetchone()
            need(old is None or old['active'] == 0)
            need(not self.db.execute("SELECT 1 FROM conversation_invites WHERE conversation_id=? AND principal=? AND state='pending'", (conversation_id, recipient)).fetchone())
            invitation = {'id': uuid.uuid4().hex, 'conversation_id': conversation_id, 'principal': recipient, 'epoch': uuid.uuid4().hex}
            self.db.execute('INSERT INTO conversation_invites VALUES(?,?,?,?,?)', (*invitation.values(), 'pending'))
            self._audit(auth, session, 'invited', invitation)
            return dict(invitation)

    def accept_invitation(self, principal, session, invitation_id):
        identifier(invitation_id)
        with self._transaction(principal, session) as auth:
            row = self.db.execute("SELECT * FROM conversation_invites WHERE id=? AND principal=? AND state='pending'", (invitation_id, principal)).fetchone()
            need(row is not None)
            conversation_id = row['conversation_id']
            need(self.db.execute('SELECT COUNT(*) FROM conversation_members WHERE conversation_id=? AND active=1', (conversation_id,)).fetchone()[0] < MAX_MEMBERS)
            self.db.execute('INSERT INTO conversation_members VALUES(?,?,?,1) ON CONFLICT(conversation_id,principal) DO UPDATE SET epoch=excluded.epoch,active=1', (conversation_id, principal, row['epoch']))
            self.db.execute("UPDATE conversation_invites SET state='accepted' WHERE id=?", (invitation_id,))
            if self.db.execute('SELECT COUNT(*) FROM conversation_members WHERE conversation_id=? AND active=1', (conversation_id,)).fetchone()[0] > 2:
                self.db.execute("UPDATE conversations SET mode='group' WHERE id=?", (conversation_id,))
            self._bump(conversation_id)
            self._audit(auth, session, 'joined', {'invitation_id': invitation_id, 'conversation_id': conversation_id, 'epoch': row['epoch']})
            return self._binding(conversation_id, principal)

    def cancel_invitation(self, principal, session, invitation_id):
        identifier(invitation_id)
        with self._transaction(principal, session) as auth:
            row = self.db.execute('SELECT * FROM conversation_invites WHERE id=?', (invitation_id,)).fetchone()
            need(row is not None and row['state'] == 'pending')
            if row['principal'] != principal:
                self._admin(row['conversation_id'], principal)
            self.db.execute("UPDATE conversation_invites SET state='cancelled' WHERE id=?", (invitation_id,))
            self._audit(auth, session, 'invitation_cancelled', {'id': invitation_id})

    def remove_member(self, principal, session, conversation_id, recipient):
        with self._transaction(principal, session) as auth:
            conversation = self._conversation(conversation_id)
            if principal != recipient:
                self._admin(conversation_id, principal)
            self._member(conversation_id, principal)
            member = self._member(conversation_id, recipient)
            need(recipient != conversation['admin'])  # Admin transfer/room closure is a separate feature.
            self.db.execute('UPDATE conversation_members SET active=0 WHERE conversation_id=? AND principal=?', (conversation_id, recipient))
            self.db.execute("UPDATE conversation_invites SET state='cancelled' WHERE conversation_id=? AND principal=? AND state='pending'", (conversation_id, recipient))
            self._bump(conversation_id)
            self._audit(auth, session, 'removed', {'conversation_id': conversation_id, 'principal': recipient, 'epoch': member['epoch']})

    def _binding(self, conversation_id, principal):
        room = self._conversation(conversation_id)
        member = self._member(conversation_id, principal)
        return ContextBinding(conversation_id, principal, member['epoch'], room['generation'])

    def bind_context(self, principal, session, conversation_id):
        with self._transaction(principal, session):
            return self._binding(conversation_id, principal)

    def participants(self, principal, session, binding):
        with self._transaction(principal, session):
            self._check_binding(principal, binding)
            return [dict(row) for row in self.db.execute(
                'SELECT principal,epoch FROM conversation_members WHERE conversation_id=? AND active=1 ORDER BY principal',
                (binding.conversation_id,)).fetchall()]

    def _check_binding(self, principal, binding):
        need(type(binding) is ContextBinding and binding.principal == principal)
        need(binding == self._binding(binding.conversation_id, principal))

    def _verify(self, principal, body, signature):
        try:
            row = self.db.execute('SELECT public FROM conversation_principals WHERE id=?', (principal,)).fetchone()
            need(row is not None)
            public = json.loads(row['public'])
            need(fingerprint(public) == principal)
            Ed25519PublicKey.from_public_bytes(unb64(public['signing_key'], 32)).verify(unb64(signature, 64), canonical(body))
        except (ValueError, KeyError, TypeError, InvalidSignature):
            raise ConversationDenied('Conversation operation unavailable') from None

    def _event(self, event_id):
        identifier(event_id)
        row = self.db.execute('SELECT * FROM conversation_events WHERE id=?', (event_id,)).fetchone()
        need(row is not None)
        try:
            signed = json.loads(self.storage.open('conversation_events', event_id, 'body', row['body']))
            body = signed['body']
            need(type(body) is dict and set(body) == {'domain', 'id', 'conversation_id', 'author', 'author_epoch', 'request_id', 'request_digest', 'kind', 'text', 'sources', 'audience'})
            need(body['domain'] == VERSION + '/message' and body['id'] == row['id'] and body['author'] == row['author']
                 and body['conversation_id'] == row['conversation_id'] and body['request_id'] == row['request_id'] and body['request_digest'] == row['request_digest'])
            self._verify(body['author'], body, signed['signature'])
            return row, signed
        except (KeyError, TypeError, ValueError):
            raise ConversationDenied('Conversation operation unavailable') from None

    def _has_grant(self, event, principal, epoch):
        for row in self.db.execute('SELECT * FROM conversation_grants WHERE conversation_id=? AND recipient=? AND epoch=? AND revoked=0 AND expires>?',
                                   (event['conversation_id'], principal, epoch, self._now())).fetchall():
            try:
                statement = json.loads(self.storage.open('conversation_grants', row['id'], 'body', row['statement']))
                need(statement['domain'] == VERSION + '/history-grant' and statement['id'] == row['id']
                     and statement['issuer'] == row['issuer'] and statement['recipient'] == principal and statement['member_epoch'] == epoch
                     and statement['conversation_id'] == event['conversation_id'] and statement['expires_at'] == row['expires']
                     and statement['audience'] == 'local-owner-only')
                self._verify(row['issuer'], statement, row['signature'])
                if event['author'] == row['issuer'] and {'id': event['id'], 'digest': digest(event)} in statement['events']:
                    return True
            except (KeyError, TypeError, ValueError):
                raise ConversationDenied('Conversation operation unavailable') from None
        return False

    def _visible(self, event_id, principal, binding, cache, visiting=None):
        if event_id in cache:
            return cache[event_id]
        visiting = set() if visiting is None else visiting
        need(event_id not in visiting and len(visiting) <= 64)
        visiting.add(event_id)
        row, signed = self._event(event_id)
        body = signed['body']
        need(body['conversation_id'] == binding.conversation_id)
        audience = {'principal': principal, 'epoch': binding.member_epoch}
        visible = audience in body['audience'] or self._has_grant(body, principal, binding.member_epoch)
        if visible:
            for source in body['sources']:
                source_row, source_signed = self._event(source['id'])
                need(source_row['sequence'] < row['sequence'] and source_signed['body']['conversation_id'] == body['conversation_id']
                     and digest(source_signed['body']) == source['digest'])
                if not self._visible(source['id'], principal, binding, cache, visiting):
                    visible = False
                    break
        visiting.remove(event_id)
        cache[event_id] = visible
        return visible

    def append(self, principal, session, binding, *, request_id, text, kind='message', source_ids=()):
        identifier(request_id); bounded_text(text)
        need(kind in ('message', 'quote', 'summary') and type(source_ids) in (list, tuple) and len(source_ids) <= MAX_SOURCES)
        need(all(type(x) is str for x in source_ids) and len(set(source_ids)) == len(source_ids))
        need(kind == 'message' or bool(source_ids))
        for source in source_ids:
            identifier(source)
        request = {'kind': kind, 'text': text, 'source_ids': list(source_ids)}
        request_digest = digest(request)
        checks = []
        with self._transaction(principal, session, checks=checks) as auth:
            self._check_binding(principal, binding)
            conversation_id = binding.conversation_id
            existing = self.db.execute('SELECT id,request_digest FROM conversation_events WHERE conversation_id=? AND author=? AND request_id=?',
                                       (conversation_id, principal, request_id)).fetchone()
            if existing:
                need(existing['request_digest'] == request_digest)
                # A retry after removal/rejoin, grant expiry or withdrawal must
                # not disclose a retained old event or restore its permissions.
                need(self._visible(existing['id'], principal, binding, {}))
                checks.append(lambda: self._assert_visible(principal, binding, [existing['id']]))
                return self._public_event(existing['id'])
            need(self.db.execute('SELECT COUNT(*) FROM conversation_events').fetchone()[0] < MAX_EVENTS)
            sources = []
            for event_id in source_ids:
                need(self._visible(event_id, principal, binding, {}))
                sources.append({'id': event_id, 'digest': digest(self._event(event_id)[1]['body'])})
            members = self.db.execute('SELECT principal,epoch FROM conversation_members WHERE conversation_id=? AND active=1 ORDER BY principal', (conversation_id,)).fetchall()
            body = {'domain': VERSION + '/message', 'id': uuid.uuid4().hex, 'conversation_id': conversation_id,
                    'author': principal, 'author_epoch': binding.member_epoch, 'request_id': request_id,
                    'request_digest': request_digest, 'kind': kind, 'text': text, 'sources': sources,
                    'audience': [dict(row) for row in members]}
            signed = {'body': body, 'signature': b64(auth.sign(session, canonical(body)))}
            encoded = self.storage.seal('conversation_events', body['id'], 'body', canonical(signed).decode())
            self.db.execute('INSERT INTO conversation_events(id,conversation_id,author,request_id,request_digest,body) VALUES(?,?,?,?,?,?)',
                            (body['id'], conversation_id, principal, request_id, request_digest, encoded))
            checks.append(lambda: self._assert_visible(principal, binding, [body['id']]))
            return self._public_event(body['id'])

    def _public_event(self, event_id):
        _, signed = self._event(event_id)
        body = signed['body']
        # No internal sequence, historical recipient list, total count or author
        # session token appears in search/context results.
        return {'id': body['id'], 'conversation_id': body['conversation_id'], 'author': body['author'],
                'kind': body['kind'], 'text': body['text'], 'sources': snapshot(body['sources']),
                'provenance_digest': digest(body), 'trust': 'untrusted-message', 'execution_authority': False}

    def _assert_visible(self, principal, binding, event_ids):
        self._check_binding(principal, binding)
        cache = {}
        for event_id in event_ids:
            need(self._visible(event_id, principal, binding, cache))

    def read(self, principal, session, binding, event_id):
        checks = [lambda: self._assert_visible(principal, binding, [event_id])]
        with self._transaction(principal, session, checks=checks):
            self._check_binding(principal, binding)
            need(self._visible(event_id, principal, binding, {}))
            result = self._public_event(event_id)
            self._check_binding(principal, binding)
            return result

    def history(self, principal, session, binding, *, after=None, limit=50, query=None):
        need(type(limit) is int and 1 <= limit <= 50)
        if query is not None:
            bounded_text(query, 256)
        checks = []
        with self._transaction(principal, session, checks=checks):
            self._check_binding(principal, binding)
            start = 0
            if after is not None:
                need(self._visible(after, principal, binding, {}))
                start = self._event(after)[0]['sequence']
            cache, result = {}, []
            for row in self.db.execute('SELECT id FROM conversation_events WHERE conversation_id=? AND sequence>? ORDER BY sequence', (binding.conversation_id, start)).fetchall():
                if not self._visible(row['id'], principal, binding, cache):
                    continue
                item = self._public_event(row['id'])
                if query is None or query.casefold() in item['text'].casefold():
                    result.append(item)
                    if len(result) == limit:
                        break
            checks.append(lambda: self._assert_visible(principal, binding, [item['id'] for item in result]))
            return result

    def context(self, principal, session, binding, event_ids):
        need(type(event_ids) is list and 1 <= len(event_ids) <= 50 and all(type(x) is str for x in event_ids)
             and len(event_ids) == len(set(event_ids)))
        checks = [lambda: self._assert_visible(principal, binding, event_ids)]
        with self._transaction(principal, session, checks=checks):
            self._check_binding(principal, binding)
            cache, messages = {}, []
            for event_id in event_ids:
                need(self._visible(event_id, principal, binding, cache))
                messages.append(self._public_event(event_id))
            self._check_binding(principal, binding)
            return {'conversation_id': binding.conversation_id, 'member_epoch': binding.member_epoch,
                    'policy_generation': binding.policy_generation, 'audience': 'local-owner-only',
                    'execution_authority': False, 'messages': messages}

    def prepare_history_grant(self, principal, session, conversation_id, recipient, event_ids, *, purpose, expires_at):
        bounded_text(purpose, 512)
        need(type(event_ids) is list and 1 <= len(event_ids) <= MAX_SOURCES
             and all(type(x) is str for x in event_ids) and len(set(event_ids)) == len(event_ids))
        with self._transaction(principal, session):
            self._member(conversation_id, principal)
            member = self._member(conversation_id, recipient)
            need(type(expires_at) in (int, float) and math.isfinite(expires_at) and 0 < expires_at - self._now() <= MAX_GRANT_SECONDS)
            events = []
            for event_id in event_ids:
                _, signed = self._event(event_id)
                body = signed['body']
                need(body['author'] == principal and body['conversation_id'] == conversation_id)
                events.append({'id': event_id, 'digest': digest(body)})
            statement = {'domain': VERSION + '/history-grant', 'id': uuid.uuid4().hex,
                         'conversation_id': conversation_id, 'issuer': principal, 'recipient': recipient,
                         'member_epoch': member['epoch'], 'policy_generation': self._conversation(conversation_id)['generation'],
                         'events': events, 'purpose': purpose, 'expires_at': expires_at, 'audience': 'local-owner-only'}
            return {'statement': statement, 'review_digest': digest(statement)}

    def approve_history_grant(self, principal, session, review, expected_review_digest):
        # This is a trusted owner-UI capability, never a model tool. Supplying a
        # JSON claim that an owner approved cannot invoke it or replace a session.
        need(type(review) is dict and set(review) == {'statement', 'review_digest'})
        statement = snapshot(review['statement'])
        need(type(statement) is dict and set(statement) == {'domain', 'id', 'conversation_id', 'issuer', 'recipient', 'member_epoch', 'policy_generation', 'events', 'purpose', 'expires_at', 'audience'})
        need(digest(statement) == review['review_digest'] == expected_review_digest)
        identifier(statement['id']); identifier(statement['conversation_id'])
        bounded_text(statement['purpose'], 512)
        with self._transaction(principal, session) as auth:
            need(statement['domain'] == VERSION + '/history-grant' and statement['issuer'] == principal
                 and statement['audience'] == 'local-owner-only')
            self._member(statement['conversation_id'], principal)
            member = self._member(statement['conversation_id'], statement['recipient'])
            need(member['epoch'] == statement['member_epoch'])
            old = self.db.execute('SELECT * FROM conversation_grants WHERE id=?', (statement['id'],)).fetchone()
            if old:
                need(self.storage.open('conversation_grants', old['id'], 'body', old['statement']) == canonical(statement).decode() and old['revoked'] == 0 and old['expires'] > self._now())
                return statement['id']
            need(statement['policy_generation'] == self._conversation(statement['conversation_id'])['generation'])
            expiry = statement['expires_at']
            need(type(expiry) in (int, float) and math.isfinite(expiry) and 0 < expiry - self._now() <= MAX_GRANT_SECONDS)
            events = statement['events']
            need(type(events) is list and 1 <= len(events) <= MAX_SOURCES)
            ids = []
            for event in events:
                need(type(event) is dict and set(event) == {'id', 'digest'})
                _, signed = self._event(event['id'])
                body = signed['body']
                need(body['author'] == principal and body['conversation_id'] == statement['conversation_id'] and digest(body) == event['digest'])
                ids.append(event['id'])
            need(len(set(ids)) == len(ids))
            self.db.execute('INSERT INTO conversation_grants VALUES(?,?,?,?,?,?,0,?,?)',
                            (statement['id'], statement['conversation_id'], principal, statement['recipient'], statement['member_epoch'], expiry,
                             self.storage.seal('conversation_grants', statement['id'], 'body', canonical(statement).decode()), b64(auth.sign(session, canonical(statement)))))
            self._bump(statement['conversation_id'])
            self._audit(auth, session, 'history_granted', statement)
            return statement['id']

    def revoke_history_grant(self, principal, session, grant_id):
        identifier(grant_id)
        with self._transaction(principal, session) as auth:
            row = self.db.execute('SELECT * FROM conversation_grants WHERE id=? AND issuer=?', (grant_id, principal)).fetchone()
            need(row is not None)
            if not row['revoked']:
                self.db.execute('UPDATE conversation_grants SET revoked=1 WHERE id=?', (grant_id,))
                self._bump(row['conversation_id'])
                self._audit(auth, session, 'history_revoked', {'id': grant_id})
