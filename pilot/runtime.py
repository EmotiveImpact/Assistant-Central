"""Owner-authenticated local runtime with its own durable inbox and decisions.

Peer packets are cryptographically bound to explicitly enrolled identities. A
sender cannot write the receiver's SQLite state. The current process/OS account
still controls its own files, and remote withdrawal takes effect when observed.
"""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time

from .crypto import canonical, digest, fingerprint, packet_header, seal, token, TransportDenied
from .transport import PeerExchange

VERSION = 'assistant-central-pilot-runtime/1'
MAX_ITEMS = 256
MAX_HISTORY = 4096
HEX = re.compile(r'[0-9a-f]{64}\Z')


class RuntimeDenied(ValueError):
    """A fixed refusal, without raw content or credential detail."""


class RuntimeOutcomeUnknown(RuntimeError):
    """Inspect retained history; do not infer that an exception meant rollback."""


def need(condition, message='Invalid runtime operation'):
    if not condition:
        raise RuntimeDenied(message)


def text(value, limit):
    need(type(value) is str and bool(value), 'Expected bounded nonempty text')
    try:
        need(len(value.encode('utf-8')) <= limit, 'Text exceeds the pilot bound')
    except UnicodeError:
        raise RuntimeDenied('Invalid Unicode text') from None
    return value


def hash_id(value):
    need(type(value) is str and HEX.fullmatch(value) is not None, 'Expected exact digest')
    return value


def clone(value):
    return json.loads(canonical(value))


class PilotRuntime:
    """One local identity and store. Public methods require a current session."""

    def __init__(self, directory, auth, *, clock=time.time):
        self.auth, self.clock = auth, clock
        self.identity = auth.public_identity()
        self.fingerprint = fingerprint(self.identity)
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        need(stat.S_ISDIR(info.st_mode) and not self.directory.is_symlink()
             and stat.S_IMODE(info.st_mode) & 0o077 == 0 and info.st_uid == os.getuid(),
             'Runtime directory must be private and locally owned')
        path = self.directory / 'runtime.sqlite'
        if not path.exists():
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        info = path.lstat()
        need(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o077 == 0
             and info.st_uid == os.getuid(), 'Runtime store must be private and locally owned')
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA synchronous=FULL')
        self._lock = threading.RLock()
        try:
            self.exchange = PeerExchange(self.db, self.identity, clock=clock)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS runtime_meta(id INTEGER PRIMARY KEY CHECK(id=1),version TEXT NOT NULL,identity TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_items(
                    id TEXT PRIMARY KEY,direction TEXT NOT NULL CHECK(direction IN ('incoming','outgoing')),
                    peer_id TEXT NOT NULL,body TEXT NOT NULL,kind TEXT NOT NULL,
                    created_at REAL NOT NULL,expires REAL NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('draft','released','pending','accepted','rejected')),
                    cancelled INTEGER NOT NULL DEFAULT 0,message_id TEXT,
                    decision_digest TEXT,decision_message_id TEXT,cancel_message_id TEXT,
                    cancel_acknowledged INTEGER NOT NULL DEFAULT 0,peer_cancelled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS runtime_tombstones(
                    peer_id TEXT NOT NULL,item_id TEXT NOT NULL,context TEXT NOT NULL,route TEXT NOT NULL,artifact_digest TEXT NOT NULL,
                    PRIMARY KEY(peer_id,item_id));
                CREATE TABLE IF NOT EXISTS runtime_controls(
                    message_id TEXT PRIMARY KEY,item_id TEXT NOT NULL,kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_audit(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT NOT NULL,item_id TEXT,data TEXT NOT NULL);
            ''')
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT * FROM runtime_meta').fetchone()
            if old:
                need(old['version'] == VERSION and old['identity'] == canonical(self.identity).decode(),
                     'Runtime identity and version are immutable')
            else:
                self.db.execute('INSERT INTO runtime_meta VALUES(1,?,?)', (VERSION, canonical(self.identity).decode()))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _now(self):
        now = self.clock()
        need(type(now) in (int, float) and math.isfinite(now) and now > 0, 'Invalid runtime clock')
        return now

    @contextmanager
    def _transaction(self, session):
        # Auth logout/lock cannot interleave with a mutation; expiry is rechecked
        # just before commit. Each runtime is normally served on one worker.
        with self.auth.authorised(session) as identity, self._lock:
            need(identity['identity_fingerprint'] == self.fingerprint, 'Wrong local session identity')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                commit_checks = []
                yield commit_checks
                for check in commit_checks:
                    check()
                self.auth.authenticate(session)
                self.db.execute('COMMIT')
            except BaseException as exc:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                if isinstance(exc, Exception) and not isinstance(exc, (RuntimeDenied, TransportDenied, PermissionError)):
                    raise RuntimeOutcomeUnknown('Local operation outcome unavailable; inspect the retained exact item and original packet.') from None
                raise

    def _event(self, event, item_id=None, **data):
        need(self.db.execute('SELECT COUNT(*) FROM runtime_audit').fetchone()[0] < MAX_HISTORY,
             'Runtime audit capacity reached; no history eviction')
        self.db.execute('INSERT INTO runtime_audit(event,item_id,data) VALUES(?,?,?)',
                        (event, item_id, canonical(data).decode()))

    def _row(self, item_id):
        hash_id(item_id)
        row = self.db.execute('SELECT * FROM runtime_items WHERE id=?', (item_id,)).fetchone()
        need(row is not None, 'Unknown local item')
        body = json.loads(row['body'])
        need(digest(body) == row['id'], 'Retained item integrity mismatch')
        return row, body

    def _current(self, row):
        need(not row['cancelled'] and row['expires'] > self._now(), 'Item is cancelled or expired')
        self.exchange.peer_public(row['peer_id'])

    def enrol_peer(self, session, public, expected_fingerprint):
        with self._transaction(session):
            result = self.exchange.enroll_peer(public, expected_fingerprint)
            self._event('peer_enrolled', peer=result['fingerprint'])
            return result

    enroll_peer = enrol_peer

    def revoke_peer(self, session, peer_id):
        with self._transaction(session):
            self.exchange.revoke_peer(peer_id)
            self._event('peer_revoked', peer=peer_id)

    @staticmethod
    def _provider(value):
        if value is None:
            return None
        need(type(value) is dict and set(value) == {'provider', 'model', 'max_output_tokens'},
             'Provider disclosure must name its exact bounded route')
        need(value['provider'] == 'openai', 'Unsupported provider disclosure route')
        text(value['model'], 128)
        need(type(value['max_output_tokens']) is int and 1 <= value['max_output_tokens'] <= 2048,
             'Provider output token bound is invalid')
        return clone(value)

    @staticmethod
    def _permissions(body, provider):
        return {'domain': VERSION + '/source-permissions',
                'owner_fingerprint': fingerprint(body['sender']),
                'recipient_fingerprint': fingerprint(body['recipient']),
                'context': body['context'], 'content_digest': body['artifact_digest'],
                'synthetic_only': True,
                'origin': 'owner-originated' if body['kind'] == 'task' else 'task-derived-return',
                'upstream': [] if body['kind'] == 'task' else [body['parent_id']],
                'return_policy': 'origin-only', 'provider_disclosure': provider}

    def _parent(self, body, *, sending):
        if body['kind'] == 'task':
            need(body['parent_id'] is None, 'A task cannot invent inherited inputs')
            return
        parent, original = self._row(body['parent_id'])
        self._current(parent)
        need(original['kind'] == 'task' and original['task_id'] == body['task_id']
             and original['context'] == body['context'] and body['expires'] <= original['expires'],
             'Artifact must bind its exact original task and lifetime')
        need(body['sender'] == original['recipient'] and body['recipient'] == original['sender'],
             'Artifact can return only to the exact originating task owner')
        if sending:
            need(parent['direction'] == 'incoming' and parent['state'] == 'accepted',
                 'Only an accepted incoming task can produce a return artifact')
        else:
            need(parent['direction'] == 'outgoing' and parent['state'] in ('released', 'accepted'),
                 'Returned artifact has no released originating task')
        need(original['source_permissions']['return_policy'] == 'origin-only',
             'Original task did not authorise this return route')

    def _validate_body(self, body, sender, recipient, *, sending):
        fields = {'domain','kind','sender','recipient','context','task_id','parent_id','title','text',
                  'artifact_digest','created_at','expires','source_permissions'}
        need(type(body) is dict and set(body) == fields and body['domain'] == VERSION + '/proposal',
             'Invalid exact proposal shape')
        need(body['sender'] == sender and body['recipient'] == recipient, 'Proposal identity mismatch')
        need(body['kind'] in ('task', 'artifact'), 'Unsupported proposal kind')
        hash_id(body['context']); token(body['task_id']); text(body['title'], 128); text(body['text'], 8192)
        need(body['artifact_digest'] == digest({'text': body['text']}), 'Artifact digest mismatch')
        need(type(body['created_at']) in (int, float) and math.isfinite(body['created_at'])
             and type(body['expires']) in (int, float) and math.isfinite(body['expires'])
             and body['created_at'] > 0 and body['created_at'] < body['expires'] <= body['created_at'] + 3600,
             'Proposal lifetime must be finite and at most one hour')
        need(body['created_at'] <= self._now() + 30 and body['expires'] > self._now(),
             'Proposal is future dated or expired')
        permissions = body['source_permissions']
        need(type(permissions) is dict, 'Exact source permissions are required')
        provider = self._provider(permissions.get('provider_disclosure'))
        need(body['kind'] == 'task' or provider is None, 'Returned artifacts cannot grant onward provider disclosure')
        need(permissions == self._permissions(body, provider),
             'Unverified inherited sources or substituted source permissions are forbidden')
        self._parent(body, sending=sending)

    def propose(self, session, peer_id, kind, title, text, context, task_id, expires,
                parent_id=None, provider_disclosure=None, source_permissions=None):
        with self._transaction(session):
            recipient = self.exchange.peer_public(peer_id)
            now = self._now()
            need(type(expires) in (int, float) and math.isfinite(expires) and now < expires <= now + 3600,
                 'Proposal must expire within one hour')
            body = {'domain': VERSION + '/proposal', 'kind': kind, 'sender': self.identity,
                    'recipient': recipient, 'context': context, 'task_id': task_id, 'parent_id': parent_id,
                    'title': title, 'text': text, 'artifact_digest': digest({'text': text}),
                    'created_at': now, 'expires': expires}
            body['source_permissions'] = self._permissions(body, self._provider(provider_disclosure))
            need(source_permissions is None or source_permissions == body['source_permissions'],
                 'Caller-supplied source rights cannot broaden exact authority')
            return self._stage_proposal(body)

    def _stage_proposal(self, body):
        """Stage one exact inert proposal inside an existing owner transaction."""
        need(self.db.in_transaction, 'Proposal staging requires an owner transaction')
        peer_id = fingerprint(body['recipient'])
        recipient = self.exchange.peer_public(peer_id)
        kind, context, task_id, parent_id = (body[key] for key in ('kind', 'context', 'task_id', 'parent_id'))
        now, expires = body['created_at'], body['expires']
        self._validate_body(body, self.identity, recipient, sending=True)
        item_id = digest(body)
        old = self.db.execute('SELECT * FROM runtime_items WHERE id=?', (item_id,)).fetchone()
        if old:
            return self._status(old)
        # Do not mint aliases for the same logical task/return in this context.
        for candidate in self.db.execute("SELECT body FROM runtime_items WHERE direction='outgoing'"):
            prior = json.loads(candidate['body'])
            need((prior['kind'],prior['context'],prior['task_id'],prior['parent_id'],fingerprint(prior['recipient'])) !=
                 (kind,context,task_id,parent_id,peer_id), 'Original task/artifact route is immutable; aliases cannot renew it')
        need(self.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0] < MAX_ITEMS,
             'Runtime item capacity reached')
        self.db.execute("INSERT INTO runtime_items(id,direction,peer_id,body,kind,created_at,expires,state) VALUES(?,'outgoing',?,?,?,?,?,'draft')",
                        (item_id, peer_id, canonical(body).decode(), kind, now, expires))
        self._event('proposal_created', item_id, peer=peer_id, kind=kind)
        return self._status(self._row(item_id)[0])

    def _review(self, row, body):
        commitment = {'domain': VERSION + '/review', 'item_id': row['id'], 'direction': row['direction'],
                      'local_identity': self.fingerprint, 'source_permissions_digest': digest(body['source_permissions']),
                      'scope': 'Release exact content, or accept/reject an inert received item; no execution'}
        try:
            self._current(row)
            active = True
        except (RuntimeDenied, ValueError):
            active = False
        actions = []
        if row['direction'] == 'outgoing' and row['state'] == 'draft' and active:
            actions.append('release')
        if row['direction'] == 'incoming' and row['state'] == 'pending':
            if active: actions.append('accept')
            actions.append('reject')
        if not row['cancelled']:
            actions.append('cancel')
        return {'review_digest': digest(commitment), 'review': commitment,
                'content': body['text'] if active or row['direction'] == 'outgoing' else None,
                'context': body['context'], 'artifact_digest': body['artifact_digest'],
                'recipient': body['recipient'], 'source_permissions': body['source_permissions'],
                'allowed_actions': actions, 'authorises_execution': False}

    def review(self, session, item_id):
        with self._transaction(session):
            row, body = self._row(item_id)
            return self._review(row, body)

    def _check_review(self, row, body, review_digest):
        need(type(review_digest) is str and review_digest == self._review(row, body)['review_digest'],
             'Exact immutable local review required')

    def _packet(self, session, body, kind, payload, message_id, expires):
        peer = body['recipient'] if fingerprint(body['sender']) == self.fingerprint else body['sender']
        return seal(self.auth, session, peer, message_id=message_id, context=body['context'],
                    artifact_id=body['artifact_digest'], proposal_id=digest(body), kind=kind,
                    payload=payload, expires=expires, now=self._now())

    def release(self, session, item_id, review_digest):
        with self._transaction(session) as commit_checks:
            row, body = self._row(item_id)
            self._check_review(row, body, review_digest)
            need(row['direction'] == 'outgoing' and row['state'] == 'draft', 'Only an unreleased local draft can be released')
            self._current(row)
            commit_checks.append(lambda:(self._current(row),
                self._validate_body(body,self.identity,self.exchange.peer_public(row['peer_id']),sending=True)))
            self._validate_body(body, self.identity, self.exchange.peer_public(row['peer_id']), sending=True)
            message_id = 'proposal-' + item_id
            packet = self._packet(session, body, 'proposal', body, message_id, row['expires'])
            self.exchange.queue(packet)
            self.db.execute("UPDATE runtime_items SET state='released',message_id=? WHERE id=?", (message_id,item_id))
            self._event('proposal_released', item_id, message_id=message_id, digest=digest(packet))
            return self._status(self._row(item_id)[0])

    def decide(self, session, item_id, review_digest, decision):
        need(decision in ('accept','reject'), 'Expected recipient accept or reject')
        with self._transaction(session) as commit_checks:
            row, body = self._row(item_id)
            self._check_review(row, body, review_digest)
            need(row['direction'] == 'incoming', 'Only the local recipient can decide incoming work')
            decision_body = {'domain': VERSION + '/decision', 'item_id': item_id,
                             'review_digest': review_digest, 'decision': decision,
                             'recipient': self.fingerprint}
            decided = digest(decision_body)
            if row['state'] in ('accepted','rejected'):
                need(row['decision_digest'] == decided, 'Recipient decision is terminal')
                return self._status(row)
            need(row['state'] == 'pending', 'Incoming item is not pending')
            if decision == 'accept':
                self._current(row)
                commit_checks.append(lambda:(self._current(row),
                    self._validate_body(body,self.exchange.peer_public(row['peer_id']),self.identity,sending=False)))
                self._validate_body(body, self.exchange.peer_public(row['peer_id']), self.identity, sending=False)
            packet = self._packet(session, body, 'decision', decision_body, 'decision-' + decided, self._now() + 3600)
            self.exchange.queue(packet)
            self.db.execute('UPDATE runtime_items SET state=?,decision_digest=?,decision_message_id=? WHERE id=?',
                            ('accepted' if decision == 'accept' else 'rejected', decided, 'decision-' + decided, item_id))
            self._event('recipient_decided', item_id, decision=decision, decision_digest=decided)
            return self._status(self._row(item_id)[0])

    def cancel(self, session, item_id, review_digest):
        with self._transaction(session):
            return self._cancel(session, item_id, review_digest)

    def _cancel(self, session, item_id, review_digest):
        """Cancel inside an existing owner transaction, preserving peer notices."""
        need(self.db.in_transaction, 'Cancellation requires an owner transaction')
        row, body = self._row(item_id)
        self._check_review(row, body, review_digest)
        if row['cancelled']:
            return self._status(row)
        message_id = None
        try:
            self.exchange.peer_public(row['peer_id'])
            peer_active = True
        except TransportDenied:
            peer_active = False
        if (row['direction'] == 'outgoing' and row['state'] == 'draft') or not peer_active:
            pass  # no peer has been given this draft
        else:
            role = 'source' if row['direction'] == 'outgoing' else 'recipient'
            payload = {'domain': VERSION + '/cancel', 'item_id': item_id, 'role': role,
                       'context': body['context'], 'artifact_digest': body['artifact_digest'],
                       'route':{key:body[key] for key in ('kind','task_id','parent_id')}}
            message_id = 'cancel-' + digest({'payload':payload,'actor':self.fingerprint})
            packet = self._packet(session, body, 'cancel', payload, message_id, self._now() + 3600)
            self.exchange.queue(packet)
        if row['direction'] == 'outgoing' and row['message_id']:
            self.exchange.cancel(row['message_id'])
        self.db.execute('UPDATE runtime_items SET cancelled=1,cancel_message_id=? WHERE id=?', (message_id,item_id))
        self._event('cancellation_requested', item_id, message_id=message_id)
        return self._status(self._row(item_id)[0])

    def prepare_delivery(self, session, message_id):
        with self._transaction(session):
            return self.exchange.prepare_attempt(message_id)

    def _receive_proposal(self, header, body):
        peer = self.exchange.peer_public(header['sender'])
        self._validate_body(body, peer, self.identity, sending=False)
        item_id = digest(body)
        need(header['proposal_id'] == item_id and header['context'] == body['context']
             and header['artifact_id'] == body['artifact_digest'] and header['expires'] == body['expires'],
             'Packet and proposal commitments differ')
        existing = self.db.execute('SELECT * FROM runtime_items WHERE id=?', (item_id,)).fetchone()
        if existing:
            need(existing['direction'] == 'incoming' and existing['peer_id'] == header['sender']
                 and existing['body'] == canonical(body).decode(), 'Received proposal conflicts with retained item')
            return item_id
        route = {key:body[key] for key in ('kind','task_id','parent_id')}
        for candidate in self.db.execute("SELECT body FROM runtime_items WHERE direction='incoming' AND peer_id=?", (header['sender'],)):
            prior = json.loads(candidate['body'])
            need((prior['context'],prior['kind'],prior['task_id'],prior['parent_id']) !=
                 (body['context'],body['kind'],body['task_id'],body['parent_id']),
                 'Received logical route already has its immutable original proposal')
        need(self.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0] < MAX_ITEMS, 'Runtime item capacity reached')
        cancelled = self.db.execute('SELECT * FROM runtime_tombstones WHERE peer_id=? AND context=? AND route=?',
                                    (header['sender'],body['context'],canonical(route).decode())).fetchone()
        if cancelled:
            need(cancelled['item_id'] == item_id and cancelled['artifact_digest']==body['artifact_digest'],
                 'Cancellation cannot be bypassed by a new proposal alias')
        self.db.execute("INSERT INTO runtime_items(id,direction,peer_id,body,kind,created_at,expires,state,cancelled,message_id,peer_cancelled) VALUES(?,'incoming',?,?,?,?,?,'pending',?,?,?)",
                        (item_id,header['sender'],canonical(body).decode(),body['kind'],body['created_at'],body['expires'],
                         int(bool(cancelled)),header['message_id'],int(bool(cancelled))))
        self._event('proposal_received', item_id, peer=header['sender'], cancelled=bool(cancelled))
        return item_id

    def _receive_decision(self, header, payload):
        need(type(payload) is dict and set(payload) == {'domain','item_id','review_digest','decision','recipient'}
             and payload['domain'] == VERSION + '/decision' and payload['decision'] in ('accept','reject'),
             'Invalid recipient decision')
        row, body = self._row(payload['item_id'])
        need(row['direction'] == 'outgoing' and row['state'] != 'draft' and row['peer_id'] == header['sender']
             and payload['recipient'] == header['sender'] and header['proposal_id'] == row['id']
             and header['context'] == body['context'] and header['artifact_id'] == body['artifact_digest'],
             'Decision belongs to a different original proposal')
        # Reconstruct the receiver's review, not the sender's differently scoped review.
        expected = {'domain': VERSION + '/review','item_id':row['id'],'direction':'incoming',
                    'local_identity':header['sender'],'source_permissions_digest':digest(body['source_permissions']),
                    'scope':'Release exact content, or accept/reject an inert received item; no execution'}
        need(payload['review_digest'] == digest(expected), 'Recipient decision does not bind the exact review')
        decision_digest = digest(payload)
        if row['state'] in ('accepted','rejected'):
            need(row['decision_digest'] == decision_digest, 'Conflicting terminal peer decision')
            return row['id']
        self.db.execute('UPDATE runtime_items SET state=?,decision_digest=?,decision_message_id=? WHERE id=?',
                        ('accepted' if payload['decision']=='accept' else 'rejected',decision_digest,header['message_id'],row['id']))
        self._event('peer_decision_observed', row['id'], decision=payload['decision'], digest=decision_digest)
        return row['id']

    def _receive_cancel(self, header, payload):
        need(type(payload) is dict and set(payload) == {'domain','item_id','role','context','artifact_digest','route'}
             and payload['domain'] == VERSION + '/cancel' and payload['role'] in ('source','recipient'),
             'Invalid exact cancellation')
        item_id = hash_id(payload['item_id'])
        route=payload['route']
        need(type(route) is dict and set(route)=={'kind','task_id','parent_id'} and route['kind'] in ('task','artifact'),
             'Cancellation requires the exact logical proposal route')
        token(route['task_id'])
        need((route['kind']=='task' and route['parent_id'] is None)
             or (route['kind']=='artifact' and type(route['parent_id']) is str and HEX.fullmatch(route['parent_id']) is not None),
             'Invalid cancellation parent route')
        need(header['proposal_id'] == item_id and header['context'] == payload['context']
             and header['artifact_id'] == payload['artifact_digest'], 'Cancellation commitment mismatch')
        row = self.db.execute('SELECT * FROM runtime_items WHERE id=?', (item_id,)).fetchone()
        if row:
            _, body = self._row(item_id)
            expected_direction = 'incoming' if payload['role']=='source' else 'outgoing'
            need(row['direction'] == expected_direction and row['peer_id'] == header['sender']
                 and body['context'] == payload['context'] and body['artifact_digest'] == payload['artifact_digest'],
                 'Cancellation is outside the original peer route')
            need(row['state'] != 'draft', 'Peer cannot cancel an unreleased local draft')
            need(route=={key:body[key] for key in ('kind','task_id','parent_id')}, 'Cancellation logical route mismatch')
            self.db.execute('UPDATE runtime_items SET cancelled=1,peer_cancelled=1 WHERE id=?', (item_id,))
            if row['direction']=='outgoing' and row['message_id']:
                self.exchange.cancel(row['message_id'])
        else:
            need(payload['role']=='source', 'Recipient cannot cancel an unknown local outgoing proposal')
            need(self.db.execute('SELECT COUNT(*) FROM runtime_tombstones').fetchone()[0] < MAX_ITEMS,
                 'Cancellation history capacity reached')
            old = self.db.execute('SELECT * FROM runtime_tombstones WHERE peer_id=? AND (item_id=? OR (context=? AND route=?))',
                                  (header['sender'],item_id,payload['context'],canonical(route).decode())).fetchone()
            need(not old or (old['context']==payload['context'] and old['route']==canonical(route).decode()
                            and old['item_id']==item_id and old['artifact_digest']==payload['artifact_digest']),
                 'Cancellation route cannot change')
            self.db.execute('INSERT OR IGNORE INTO runtime_tombstones VALUES(?,?,?,?,?)',
                            (header['sender'],item_id,payload['context'],canonical(route).decode(),payload['artifact_digest']))
        self._event('peer_cancellation_observed', item_id, peer=header['sender'], role=payload['role'])
        return item_id

    def receive(self, session, packet):
        with self._transaction(session) as commit_checks:
            header = packet_header(packet)
            result = self.exchange.receive(packet, self.auth, session)
            item_id = header['proposal_id']
            if not result['duplicate']:
                envelope = result['envelope']
                body = envelope['payload']
                if header['kind']=='proposal':
                    item_id = self._receive_proposal(header,body)
                    commit_checks.append(lambda:self._validate_body(body,
                        self.exchange.peer_public(header['sender']),self.identity,sending=False))
                elif header['kind']=='decision': item_id = self._receive_decision(header,body)
                elif header['kind']=='cancel': item_id = self._receive_cancel(header,body)
                elif header['kind']=='receipt':
                    # A transport receipt is not recipient acceptance. It can
                    # acknowledge exposure of the cancellation packet only.
                    self.db.execute('UPDATE runtime_items SET cancel_acknowledged=1 WHERE cancel_message_id=?',
                                    (body['message_id'],))
                    self._event('transport_receipt_observed', item_id, message_id=body['message_id'])
                else: raise RuntimeDenied('Unknown peer packet kind')
            receipt = None if header['kind']=='receipt' else self.exchange.receipt_for(self.auth,session,header['message_id'])
            row = self.db.execute('SELECT * FROM runtime_items WHERE id=?', (item_id,)).fetchone()
            return {'duplicate':result['duplicate'],'message_id':header['message_id'],
                    'item':self._status(row) if row else None,'receipt':receipt,
                    'owner_acceptance': row['state'] if row and row['state'] in ('accepted','rejected') else 'not_established'}

    def _status(self, row):
        body = json.loads(row['body'])
        active = not row['cancelled'] and row['expires'] > self._now()
        return {'id':row['id'],'direction':row['direction'],'kind':row['kind'],
                'state':'cancelled' if row['cancelled'] else ('expired' if not active else row['state']),
                'historical_state':row['state'],'title':body['title'],'peer_id':row['peer_id'],
                'created_at':row['created_at'],'expires':row['expires'],'context':body['context'],
                'task_id':body['task_id'],'parent_id':body['parent_id'],'artifact_digest':body['artifact_digest'],
                'message_id':row['message_id'],'decision_digest':row['decision_digest'],
                'cancel_message_id':row['cancel_message_id'],
                'cancel_requested':bool(row['cancel_message_id']),
                'cancel_packet_receipt_observed':bool(row['cancel_acknowledged']),
                'peer_cancellation_observed':bool(row['peer_cancelled']),
                'authorises_execution':False,'synthetic_only':True}

    def status(self, session, item_id):
        with self._transaction(session):
            return self._status(self._row(item_id)[0])

    def state(self, session):
        with self._transaction(session):
            peers = [{**peer,'peer_id':peer['fingerprint'], 'owner_id':peer['public']['owner_id'],
                      'agent_id':peer['public']['agent_id']} for peer in self.exchange.peers()]
            return {'identity':{**self.identity,'fingerprint':self.fingerprint},'peers':peers,
                    'items':[self._status(row) for row in self.db.execute('SELECT * FROM runtime_items ORDER BY created_at,id')],
                    'history':[{'sequence':row['sequence'],'event':row['event'],'item_id':row['item_id'],
                                'data':json.loads(row['data'])} for row in self.db.execute('SELECT * FROM runtime_audit ORDER BY sequence')],
                    'outbox':self.exchange.pending(),'session_ready':True,'synthetic_only':True}

    def authorise_provider(self, session, binding):
        """Provider adapter calls inside its existing local write transaction."""
        need(self.db.in_transaction, 'Provider authorisation requires an atomic local transaction')
        identity = self.auth.authenticate(session)
        need(identity['identity_fingerprint']==self.fingerprint, 'Wrong local owner session')
        need(type(binding) is dict and set(binding)=={'item_id','context','payload_digest','provider','model','max_output_tokens'},
             'Expected exact provider binding')
        row, body = self._row(binding['item_id'])
        self._current(row)
        need(row['direction']=='incoming' and row['state']=='accepted' and body['kind']=='task',
             'Provider work requires a currently accepted incoming task')
        self._validate_body(body,self.exchange.peer_public(row['peer_id']),self.identity,sending=False)
        grant = body['source_permissions']['provider_disclosure']
        need(grant is not None and grant=={key:binding[key] for key in ('provider','model','max_output_tokens')}
             and binding['context']==body['context'] and binding['payload_digest']==body['artifact_digest'],
             'Exact signed direct-source provider disclosure is missing or changed')
        return {'task_text':body['text'],'context':body['context'],'recipient':self.identity['agent_id'],
                'synthetic_only':True}
