"""Owner-set autonomy for an assistant's outbound messages, plus private guidance.

Borrowed idea (ericscalibur/Parley): an autonomy dial and private nudges. Here
they sit on owner sessions, leases and exact review:

* ``review_each`` (the default): every message the assistant proposes waits
  for the owner to approve the exact text.
* ``check_in``: the assistant may send up to ``every`` messages in a row, then
  the next one waits for the owner. Approving it starts a new run.
* ``within_limits``: the assistant may send on its own while the caps hold.

Every mode has hard caps: a total number of unreviewed messages, a maximum
message size and an expiry of at most seven days. Only plain new messages can
be sent without review. Quotes and summaries, history sharing, provider
disclosure, execution and spending have no automatic path here at all.

Messages sent without review use the ledger kind ``assistant``, so every reader
can see the owner's assistant sent them under a standing policy. Owner guidance
is encrypted to the owner's own key and never enters the conversation.
"""
import math
import sqlite3
import threading
import uuid
from pathlib import Path

from pilot.auth import _create_private_file, _private_path
from pilot.crypto import canonical, digest, fingerprint
from pilot.storage import RecordStorage

from .inbox import AssistantLease, InboxStore
from .timeline import record_safely
from .ledger import (ConversationDenied, ConversationLedger, ConversationOutcomeUnknown,
                     bounded_text, identifier, need)

VERSION = 'assistant-central-autonomy/1'
MODES = ('review_each', 'check_in', 'within_limits')
MAX_POLICY_SECONDS = 7 * 86400
MAX_AUTO_MESSAGES = 200
MAX_MESSAGE_BYTES = 16384
MAX_GUIDANCE_BYTES = 4096
MAX_GUIDANCE_NOTES = 32
MAX_DRAFTS = 1024


class _DeskStorage(RecordStorage):
    # Reuse the reviewed sealing primitive under a disjoint AEAD domain.
    def _context(self, table, row_id, column):
        need(table in ('desk_guidance', 'desk_drafts') and column == 'body' and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class OwnerDesk:
    """One owner's policies, guidance and pending assistant drafts."""

    def __init__(self, directory, ledger, inbox, principal, timeline=None):
        self.timeline = timeline
        need(type(ledger) is ConversationLedger and type(inbox) is InboxStore and inbox.ledger is ledger)
        need(type(principal) is str and principal in ledger.actors)
        self.ledger, self.inbox, self.principal = ledger, inbox, principal
        self.auth = ledger.actors[principal]
        self._lock, self._closed = threading.RLock(), False
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private_path(self.directory, directory=True)
        path = self.directory / 'desk.sqlite'
        _create_private_file(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            new_store = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchone() is None
            self.storage = _DeskStorage(self.db, self.auth, create=True)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS desk_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL,observed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS desk_policies(assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,version INTEGER NOT NULL,mode TEXT NOT NULL,every INTEGER NOT NULL,max_auto INTEGER NOT NULL,max_bytes INTEGER NOT NULL,expires REAL NOT NULL,auto_used INTEGER NOT NULL,streak INTEGER NOT NULL,PRIMARY KEY(assistant_id,conversation_id));
                CREATE TABLE IF NOT EXISTS desk_guidance(id TEXT PRIMARY KEY,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,created REAL NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS desk_drafts(id TEXT PRIMARY KEY,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,request_id TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,auto INTEGER NOT NULL,created REAL NOT NULL,event_id TEXT,body TEXT NOT NULL,UNIQUE(assistant_id,conversation_id,request_id));
            ''')
            with self._lock:
                self.db.execute('BEGIN IMMEDIATE')
                row = self.db.execute('SELECT * FROM desk_meta WHERE singleton=1').fetchone()
                if row is None:
                    need(new_store or self.db.execute('SELECT COUNT(*) FROM desk_policies').fetchone()[0] == 0)
                    self.db.execute('INSERT INTO desk_meta VALUES(1,?,?,0)', (VERSION, principal))
                else:
                    need(row['version'] == VERSION and row['owner'] == principal
                         and type(row['observed']) in (int, float) and math.isfinite(row['observed']))
                self.db.execute('COMMIT')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            if not self._closed:
                self.db.close()
                self._closed = True

    # Guards ----------------------------------------------------------------

    def _owner(self, session):
        identity = self.auth.authenticate(session)
        need(identity['identity_fingerprint'] == self.principal)

    def _assistant(self, session, lease):
        need(type(lease) is AssistantLease and lease.principal == self.principal)
        self.inbox.check_lease(session, lease)
        return lease.assistant_id, lease.conversation_id

    def _now(self):
        value = self.ledger.clock()
        need(type(value) in (int, float) and math.isfinite(value) and value > 0)
        observed = self.db.execute('SELECT observed FROM desk_meta WHERE singleton=1').fetchone()['observed']
        need(value >= observed)
        self.db.execute('UPDATE desk_meta SET observed=? WHERE singleton=1', (value,))
        return value

    def _txn(self):
        need(not self._closed)
        return _Txn(self.db)

    # Owner: policy and guidance ---------------------------------------------

    def set_policy(self, session, assistant_id, conversation_id, *, mode, every=1,
                   max_auto=20, max_bytes=2000, ttl=86400):
        identifier(assistant_id); identifier(conversation_id)
        need(mode in MODES)
        need(type(every) is int and 1 <= every <= 50)
        need(type(max_auto) is int and 0 <= max_auto <= MAX_AUTO_MESSAGES)
        need(type(max_bytes) is int and 1 <= max_bytes <= MAX_MESSAGE_BYTES)
        need(type(ttl) in (int, float) and math.isfinite(ttl) and 0 < ttl <= MAX_POLICY_SECONDS)
        with self._lock:
            self._owner(session)
            self.ledger.bind_context(self.principal, session, conversation_id)  # Owner must be a member.
            with self._txn():
                now = self._now()
                old = self.db.execute('SELECT version FROM desk_policies WHERE assistant_id=? AND conversation_id=?',
                                      (assistant_id, conversation_id)).fetchone()
                version = 1 if old is None else old['version'] + 1
                self.db.execute('INSERT OR REPLACE INTO desk_policies VALUES(?,?,?,?,?,?,?,?,0,0)',
                                (assistant_id, conversation_id, version, mode, every, max_auto, max_bytes, now + ttl))
                view = self._policy_view(assistant_id, conversation_id, now)
            record_safely(self.timeline, 'policy_changed', conversation_id, role='you',
                          ref=f'policy:{assistant_id}:{conversation_id}:{version}',
                          detail={'assistant_id': assistant_id, 'mode': mode, 'every': every, 'max_auto': max_auto,
                                  'max_bytes': max_bytes, 'expires_at': now + ttl})
            return view

    def clear_policy(self, session, assistant_id, conversation_id):
        """Back to the default: review every message."""
        identifier(assistant_id); identifier(conversation_id)
        with self._lock:
            self._owner(session)
            with self._txn():
                now = self._now()
                self.db.execute('DELETE FROM desk_policies WHERE assistant_id=? AND conversation_id=?',
                                (assistant_id, conversation_id))
            record_safely(self.timeline, 'policy_changed', conversation_id, role='you',
                          ref=f'policy-clear:{assistant_id}:{conversation_id}:{now}',
                          detail={'assistant_id': assistant_id, 'mode': 'review_each'})

    def policy(self, session, assistant_id, conversation_id):
        identifier(assistant_id); identifier(conversation_id)
        with self._lock:
            self._owner(session)
            with self._txn():
                return self._policy_view(assistant_id, conversation_id, self._now())

    def _policy_view(self, assistant_id, conversation_id, now):
        row = self.db.execute('SELECT * FROM desk_policies WHERE assistant_id=? AND conversation_id=?',
                              (assistant_id, conversation_id)).fetchone()
        if row is None or now >= row['expires']:
            return {'mode': 'review_each', 'standing': False}
        return {'mode': row['mode'], 'standing': row['mode'] != 'review_each', 'every': row['every'],
                'max_auto': row['max_auto'], 'auto_used': row['auto_used'], 'max_bytes': row['max_bytes'],
                'expires_at': row['expires'], 'version': row['version']}

    def add_guidance(self, session, assistant_id, conversation_id, text):
        identifier(assistant_id); identifier(conversation_id); bounded_text(text, MAX_GUIDANCE_BYTES)
        with self._lock:
            self._owner(session)
            with self._txn():
                now = self._now()
                count = self.db.execute('SELECT COUNT(*) FROM desk_guidance WHERE assistant_id=? AND conversation_id=?',
                                        (assistant_id, conversation_id)).fetchone()[0]
                need(count < MAX_GUIDANCE_NOTES)
                note_id = uuid.uuid4().hex
                self.db.execute('INSERT INTO desk_guidance VALUES(?,?,?,?,?)',
                                (note_id, assistant_id, conversation_id, now,
                                 self.storage.seal('desk_guidance', note_id, 'body', text)))
            record_safely(self.timeline, 'guidance_changed', conversation_id, role='you',
                          ref=f'guidance:{note_id}:added', detail={'assistant_id': assistant_id, 'note_id': note_id})
            return {'id': note_id}

    def remove_guidance(self, session, note_id):
        identifier(note_id)
        with self._lock:
            self._owner(session)
            with self._txn():
                self._now()
                row = self.db.execute('SELECT assistant_id,conversation_id FROM desk_guidance WHERE id=?', (note_id,)).fetchone()
                need(row is not None)
                self.db.execute('DELETE FROM desk_guidance WHERE id=?', (note_id,))
            record_safely(self.timeline, 'guidance_changed', row['conversation_id'], role='you',
                          ref=f'guidance:{note_id}:removed', detail={'assistant_id': row['assistant_id'], 'note_id': note_id})

    def _guidance(self, assistant_id, conversation_id):
        return [{'id': row['id'], 'text': self.storage.open('desk_guidance', row['id'], 'body', row['body'])}
                for row in self.db.execute('SELECT id,body FROM desk_guidance WHERE assistant_id=? AND conversation_id=? ORDER BY created,id',
                                           (assistant_id, conversation_id)).fetchall()]

    def guidance(self, session, assistant_id, conversation_id):
        identifier(assistant_id); identifier(conversation_id)
        with self._lock:
            self._owner(session)
            return self._guidance(assistant_id, conversation_id)

    # Assistant: guidance and proposals --------------------------------------

    def guidance_for(self, session, lease):
        """Private owner notes for this assistant. Never part of the conversation."""
        with self._lock:
            assistant_id, conversation_id = self._assistant(session, lease)
            return {'notes': self._guidance(assistant_id, conversation_id),
                    'audience': 'this-assistant-only', 'from': 'your-owner'}

    def propose(self, session, lease, *, request_id, text):
        """Send now if the owner's policy allows it, otherwise queue for review.

        Idempotent by ``request_id``: the same text returns the same draft, and
        an uncertain send is retried with the ledger's exact-request dedupe.
        """
        identifier(request_id); bounded_text(text, MAX_MESSAGE_BYTES)
        text_digest = digest({'request_id': request_id, 'text': text})
        with self._lock:
            assistant_id, conversation_id = self._assistant(session, lease)
            with self._txn():
                now = self._now()
                existing = self.db.execute('SELECT * FROM desk_drafts WHERE assistant_id=? AND conversation_id=? AND request_id=?',
                                           (assistant_id, conversation_id, request_id)).fetchone()
                if existing is not None:
                    need(existing['digest'] == text_digest)
                    draft = dict(existing)
                else:
                    need(self.db.execute('SELECT COUNT(*) FROM desk_drafts').fetchone()[0] < MAX_DRAFTS)
                    auto = self._consume_allowance(assistant_id, conversation_id, len(text.encode('utf-8')), now)
                    draft = {'id': uuid.uuid4().hex, 'assistant_id': assistant_id, 'conversation_id': conversation_id,
                             'request_id': request_id, 'digest': text_digest,
                             'state': 'sending' if auto else 'awaiting_owner', 'auto': int(auto),
                             'created': now, 'event_id': None}
                    self.db.execute('INSERT INTO desk_drafts VALUES(?,?,?,?,?,?,?,?,NULL,?)',
                                    (draft['id'], assistant_id, conversation_id, request_id, text_digest,
                                     draft['state'], draft['auto'], now,
                                     self.storage.seal('desk_drafts', draft['id'], 'body', text)))
            record_safely(self.timeline, 'message_proposed', conversation_id, role='your_assistant',
                          ref='draft:' + draft['id'], detail={'draft_id': draft['id'], 'assistant_id': assistant_id,
                                                              'request_id': request_id, 'under_policy': bool(draft['auto'])})
            if draft['state'] in ('sending', 'uncertain'):
                # Retry with the same kind so the ledger's exact-request dedupe holds.
                draft = self._send(session, draft, text, kind='assistant' if draft['auto'] else 'message')
            return self._draft_view(draft)

    def _consume_allowance(self, assistant_id, conversation_id, size, now):
        row = self.db.execute('SELECT * FROM desk_policies WHERE assistant_id=? AND conversation_id=?',
                              (assistant_id, conversation_id)).fetchone()
        if row is None or now >= row['expires'] or row['mode'] == 'review_each':
            return False
        if size > row['max_bytes'] or row['auto_used'] >= row['max_auto']:
            return False
        if row['mode'] == 'check_in' and row['streak'] >= row['every']:
            return False
        self.db.execute('UPDATE desk_policies SET auto_used=auto_used+1,streak=streak+1 WHERE assistant_id=? AND conversation_id=?',
                        (assistant_id, conversation_id))
        return True

    def _send(self, session, draft, text, *, kind):
        try:
            binding = self.ledger.bind_context(self.principal, session, draft['conversation_id'])
            event = self.ledger.append(self.principal, session, binding,
                                       request_id=draft['request_id'], text=text, kind=kind)
            state, event_id = 'sent', event['id']
        except ConversationOutcomeUnknown:
            state, event_id = 'uncertain', None
        except ConversationDenied:
            state, event_id = 'failed', None
        with self._txn():
            self._now()
            self.db.execute('UPDATE desk_drafts SET state=?,event_id=? WHERE id=?', (state, event_id, draft['id']))
            if state == 'failed' and draft['auto']:
                # A definite refusal sent nothing: return the allowance.
                self.db.execute('UPDATE desk_policies SET auto_used=MAX(auto_used-1,0),streak=MAX(streak-1,0) WHERE assistant_id=? AND conversation_id=?',
                                (draft['assistant_id'], draft['conversation_id']))
        if state in ('sent', 'failed'):
            entry = 'message_failed' if state == 'failed' else (
                'message_sent_by_assistant' if kind == 'assistant' else 'message_approved')
            role = {'message_failed': 'system', 'message_sent_by_assistant': 'your_assistant'}.get(entry, 'you')
            record_safely(self.timeline, entry, draft['conversation_id'], role=role,
                          ref='draft:' + draft['id'],
                          detail={'draft_id': draft['id'], 'message_id': event_id, 'assistant_id': draft['assistant_id']})
        return {**draft, 'state': state, 'event_id': event_id}

    def status_for(self, session, lease, request_id):
        identifier(request_id)
        with self._lock:
            assistant_id, conversation_id = self._assistant(session, lease)
            row = self.db.execute('SELECT * FROM desk_drafts WHERE assistant_id=? AND conversation_id=? AND request_id=?',
                                  (assistant_id, conversation_id, request_id)).fetchone()
            need(row is not None)
            return self._draft_view(dict(row))

    @staticmethod
    def _draft_view(draft):
        return {'draft_id': draft['id'], 'request_id': draft['request_id'], 'state': draft['state'],
                'sent_without_review': bool(draft['auto']) and draft['state'] == 'sent',
                'message_id': draft['event_id']}

    # Owner: review ----------------------------------------------------------

    def drafts(self, session):
        with self._lock:
            self._owner(session)
            rows = self.db.execute("SELECT * FROM desk_drafts WHERE state='awaiting_owner' ORDER BY created,id").fetchall()
            return [{'draft_id': row['id'], 'assistant_id': row['assistant_id'], 'conversation_id': row['conversation_id'],
                     'text': self.storage.open('desk_drafts', row['id'], 'body', row['body']),
                     'digest': row['digest'], 'trust': 'assistant-written'} for row in rows]

    def approve(self, session, draft_id, expected_digest):
        """Send exactly the reviewed text, as the owner's own message."""
        identifier(draft_id)
        with self._lock:
            self._owner(session)
            with self._txn():
                self._now()
                row = self.db.execute('SELECT * FROM desk_drafts WHERE id=?', (draft_id,)).fetchone()
                need(row is not None and row['state'] in ('awaiting_owner', 'uncertain') and row['auto'] == 0)
                need(row['digest'] == expected_digest)
                text = self.storage.open('desk_drafts', row['id'], 'body', row['body'])
                self.db.execute("UPDATE desk_drafts SET state='sending' WHERE id=?", (draft_id,))
                # A reviewed message ends a check-in run.
                self.db.execute('UPDATE desk_policies SET streak=0 WHERE assistant_id=? AND conversation_id=?',
                                (row['assistant_id'], row['conversation_id']))
                draft = dict(row)
            return self._draft_view(self._send(session, draft, text, kind='message'))

    def decline(self, session, draft_id):
        identifier(draft_id)
        with self._lock:
            self._owner(session)
            with self._txn():
                self._now()
                need(self.db.execute("UPDATE desk_drafts SET state='declined' WHERE id=? AND state='awaiting_owner'",
                                     (draft_id,)).rowcount == 1)
                row = self.db.execute('SELECT assistant_id,conversation_id FROM desk_drafts WHERE id=?', (draft_id,)).fetchone()
            record_safely(self.timeline, 'message_declined', row['conversation_id'], role='you', ref='draft:' + draft_id,
                          detail={'draft_id': draft_id, 'assistant_id': row['assistant_id']})


class _Txn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute('BEGIN IMMEDIATE')

    def __exit__(self, kind, error, trace):
        if self.db.in_transaction:
            self.db.execute('ROLLBACK' if kind else 'COMMIT')
        if isinstance(error, sqlite3.Error):
            raise ConversationOutcomeUnknown('Inspect the retained draft by request id') from None
        return False


class DeskAccess:
    """Assistant-facing handle: fixed lease, owner session from a host callback."""

    def __init__(self, desk, lease, session_provider):
        need(type(desk) is OwnerDesk and type(lease) is AssistantLease and callable(session_provider))
        self._desk, self._lease, self._session = desk, lease, session_provider

    def guidance(self):
        return self._desk.guidance_for(self._session(), self._lease)

    def propose(self, request_id, text):
        return self._desk.propose(self._session(), self._lease, request_id=request_id, text=text)

    def status(self, request_id):
        return self._desk.status_for(self._session(), self._lease, request_id)
