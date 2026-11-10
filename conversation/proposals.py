"""Immutable local proposals and separate authenticated owner approval records.

No model, provider, transport, execution or legal-agreement authority is exposed.
This module intentionally shares the reviewed ledger's private transaction boundary.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import uuid

from pilot.crypto import b64, canonical, digest
from pilot.storage import RecordStorage
from .ledger import (ConversationLedger, ConversationDenied, ContextBinding,
                     MAX_EVENTS, MAX_SOURCES, MAX_GRANT_SECONDS,
                     bounded_text, identifier, need, snapshot)

VERSION = 'assistant-central-local-proposals/1'
TABLES = ('conversation_proposals', 'conversation_approvals', 'conversation_approval_revocations')


def content_digest(text):
    """Exact UTF-8 bytes, without normalisation or line-ending changes."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class _ProposalStorage(RecordStorage):
    def _context(self, table, row_id, column):
        need(table in TABLES and column == 'body' and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class LocalProposals:
    """Trusted owner-control API, never an agent/model approval tool.

    The frozen room roster is the required approver set. The coordinating storage
    owner has no approval role unless they are a member, and then only their own.
    """
    def __init__(self, ledger, principal, session):
        need(type(ledger) is ConversationLedger)
        self.ledger = ledger
        self.db = ledger.db
        self.storage = _ProposalStorage(self.db, ledger.storage.auth)
        with ledger._transaction(principal, session, final_checks=(self._format,)):
            need(principal == ledger.storage_owner)
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected = set(TABLES) | {'conversation_proposal_meta'}
            present = expected & tables
            need(not present or present == expected)
            if not present:
                self.db.execute('CREATE TABLE conversation_proposal_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL)')
                self.db.execute('INSERT INTO conversation_proposal_meta VALUES(1,?)', (VERSION,))
                self.db.execute('CREATE TABLE conversation_proposals(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,author TEXT NOT NULL,request_id TEXT NOT NULL,request_digest TEXT NOT NULL,series_id TEXT NOT NULL,revision INTEGER NOT NULL,body TEXT NOT NULL,UNIQUE(conversation_id,author,request_id),UNIQUE(series_id,revision))')
                self.db.execute('CREATE TABLE conversation_approvals(id TEXT PRIMARY KEY,proposal_id TEXT NOT NULL,owner TEXT NOT NULL,body TEXT NOT NULL,UNIQUE(proposal_id,owner))')
                self.db.execute('CREATE TABLE conversation_approval_revocations(id TEXT PRIMARY KEY,approval_id TEXT UNIQUE NOT NULL,owner TEXT NOT NULL,body TEXT NOT NULL)')
            self._format()

    def _format(self):
        rows = self.db.execute('SELECT singleton,version FROM conversation_proposal_meta').fetchall()
        need(len(rows) == 1 and tuple(rows[0]) == (1, VERSION))

    @contextmanager
    def _transaction(self, principal, session, checks):
        def final_review():
            for check in checks:
                check()
        with self.ledger._transaction(principal, session, checks=checks, final_checks=(final_review,)) as auth:
            self._format()
            try:
                yield auth
            finally:
                # Observe time before the ledger's final authentication check,
                # including a body refusal or a session expiring before commit.
                # The ledger persists this fence even when that check refuses.
                self.ledger._now()

    def _roster(self, room):
        return [dict(r) for r in self.db.execute(
            'SELECT principal,epoch FROM conversation_members WHERE conversation_id=? AND active=1 ORDER BY principal', (room,))]

    def _seal(self, table, body, auth, session):
        signed = {'statement': body, 'signature': b64(auth.sign(session, canonical(body)))}
        return self.storage.seal(table, body['id'], 'body', canonical(signed).decode())

    def _open(self, table, row, domain, signer):
        need(row is not None)
        try:
            signed = json.loads(self.storage.open(table, row['id'], 'body', row['body']))
            need(type(signed) is dict and set(signed) == {'statement', 'signature'})
            body = signed['statement']
            need(body['domain'] == VERSION + '/' + domain and body['id'] == row['id'] and body[signer] == row[signer])
            self.ledger._verify(body[signer], body, signed['signature'])
            return signed
        except (KeyError, TypeError, ValueError):
            raise ConversationDenied('Conversation operation unavailable') from None

    def _proposal(self, proposal_id):
        identifier(proposal_id)
        row = self.db.execute('SELECT * FROM conversation_proposals WHERE id=?', (proposal_id,)).fetchone()
        signed = self._open(TABLES[0], row, 'proposal', 'author')
        body = signed['statement']
        need(set(body) == {'domain', 'id', 'conversation_id', 'author', 'author_epoch', 'request_id', 'request_digest',
                           'series_id', 'revision', 'previous', 'content', 'content_digest', 'sources', 'audience',
                           'policy_generation', 'expires_at', 'scope'})
        for field in ('conversation_id', 'request_id', 'request_digest', 'series_id', 'revision'):
            need(body[field] == row[field])
        need(body['scope'] == 'local-discussion-only' and content_digest(body['content']) == body['content_digest'])
        return signed

    def _readable(self, principal, binding, body):
        self.ledger._check_binding(principal, binding)
        need(body['conversation_id'] == binding.conversation_id)
        need({'principal': principal, 'epoch': binding.member_epoch} in body['audience'])
        for source in body['sources']:
            event = self.ledger._event(source['id'])[1]['body']
            need(digest(event) == source['digest'])
            need(self.ledger._visible(source['id'], principal, binding, {}))

    def _source_deadlines(self, body, observed_start):
        # Reuse the ledger's authority algorithm, but reject a mixed-time proof.
        # Conservatively refuse if any active room grant expired during this
        # scan. An unrelated expiry can require fresh inspection, never access.
        if body['sources']:
            need(self.db.execute(
                'SELECT 1 FROM conversation_grants WHERE conversation_id=? AND revoked=0 AND expires>? AND expires<=? LIMIT 1',
                (body['conversation_id'], observed_start, self.ledger._last_time)).fetchone() is None)

    def _current(self, body):
        # Currency is not a permanent property of a signed historical statement.
        observed_start = self.ledger._now()
        room = self.ledger._conversation(body['conversation_id'])
        latest = self.db.execute('SELECT MAX(revision) FROM conversation_proposals WHERE series_id=?', (body['series_id'],)).fetchone()[0]
        if (body['revision'] != latest or body['policy_generation'] != room['generation']
                or body['audience'] != self._roster(body['conversation_id']) or observed_start >= body['expires_at']):
            return False
        for member in body['audience']:
            binding = self.ledger._binding(body['conversation_id'], member['principal'])
            for source in body['sources']:
                event = self.ledger._event(source['id'])[1]['body']
                need(digest(event) == source['digest'])
                if not self.ledger._visible(source['id'], member['principal'], binding, {}):
                    return False
        self._source_deadlines(body, observed_start)
        return self.ledger._last_time < body['expires_at']

    def _require_current(self, body):
        need(self._current(body))

    def _approval_statement(self, body, owner):
        epoch = next((m['epoch'] for m in body['audience'] if m['principal'] == owner), None)
        need(epoch is not None)
        return {'domain': VERSION + '/approval', 'id': digest([VERSION, body['id'], owner]),
                'owner': owner, 'owner_epoch': epoch, 'proposal_id': body['id'],
                'proposal_digest': digest(body), 'series_id': body['series_id'], 'revision': body['revision'],
                'conversation_id': body['conversation_id'], 'content_digest': body['content_digest'],
                'sources': snapshot(body['sources']), 'audience': snapshot(body['audience']),
                'policy_generation': body['policy_generation'], 'expires_at': body['expires_at'],
                'scope': 'local-discussion-only'}

    def _records(self, body):
        approvals, revocations = [], []
        for row in self.db.execute('SELECT * FROM conversation_approvals WHERE proposal_id=? ORDER BY owner', (body['id'],)):
            signed = self._open(TABLES[1], row, 'approval', 'owner')
            expected = self._approval_statement(body, row['owner'])
            need(signed['statement'] == expected and row['proposal_id'] == body['id'])
            approvals.append(signed)
            revoked = self.db.execute('SELECT * FROM conversation_approval_revocations WHERE approval_id=?', (row['id'],)).fetchone()
            if revoked:
                record = self._open(TABLES[2], revoked, 'revocation', 'owner')
                need(record['statement'] == self._revocation_statement(expected) and revoked['owner'] == row['owner'])
                revocations.append(record)
        return approvals, revocations

    @staticmethod
    def _revocation_statement(approval):
        return {'domain': VERSION + '/revocation', 'id': digest([VERSION, 'revoke', approval['id']]),
                'owner': approval['owner'], 'approval_id': approval['id'], 'approval_digest': digest(approval),
                'proposal_id': approval['proposal_id'], 'scope': 'local-discussion-only'}

    def _view(self, principal, binding, signed):
        observed_start = self.ledger._now()
        body = signed['statement']
        self._readable(principal, binding, body)
        approvals, revocations = self._records(body)
        revoked = {r['statement']['approval_id'] for r in revocations}
        current = self._current(body)
        self._source_deadlines(body, observed_start)
        current_owners = [a['statement']['owner'] for a in approvals if current and a['statement']['id'] not in revoked]
        return {'proposal': snapshot(signed), 'approvals': approvals, 'revocations': revocations,
                'proposal_current': current, 'current_approval_owners': current_owners,
                'all_owners_approved': len(current_owners) == len(body['audience']),
                'trust': 'untrusted-proposal', 'execution_authority': False,
                'provider_disclosure_authority': False, 'external_agreement': False}

    def _check_view(self, principal, binding, signed, result):
        # Final auth/clock observation occurs first in the shared transaction.
        # If expiry changes the answer, refuse rather than return a stale status.
        need(self._view(principal, binding, signed) == result)

    def create(self, principal, session, binding, *, request_id, content, expires_at, source_ids=(), replaces=None):
        identifier(request_id); bounded_text(content)
        need(type(expires_at) in (int, float) and math.isfinite(expires_at))
        need(type(source_ids) in (list, tuple) and len(source_ids) <= MAX_SOURCES)
        for source in source_ids:
            identifier(source)
        need(len(set(source_ids)) == len(source_ids))
        if replaces is not None:
            identifier(replaces)
        request = {'content': content, 'expires_at': expires_at, 'source_ids': list(source_ids), 'replaces': replaces}
        request_digest = digest(request)
        checks = []
        with self._transaction(principal, session, checks) as auth:
            self.ledger._check_binding(principal, binding)
            row = self.db.execute('SELECT id,request_digest FROM conversation_proposals WHERE conversation_id=? AND author=? AND request_id=?',
                                  (binding.conversation_id, principal, request_id)).fetchone()
            if row:
                need(row['request_digest'] == request_digest)
                signed = self._proposal(row['id'])
                result = self._view(principal, binding, signed)
                checks.append(lambda: self._check_view(principal, binding, signed, result))
                return result
            need(0 < expires_at - self.ledger._now() <= MAX_GRANT_SECONDS)
            need(self.db.execute('SELECT COUNT(*) FROM conversation_proposals').fetchone()[0] < MAX_EVENTS)
            roster = self._roster(binding.conversation_id)
            previous, revision, series = None, 1, uuid.uuid4().hex
            sources = list(source_ids)
            if replaces is not None:
                old = self._proposal(replaces)['statement']
                self._readable(principal, binding, old)
                need(old['author'] == principal and old['audience'] == roster)
                latest = self.db.execute('SELECT MAX(revision) FROM conversation_proposals WHERE series_id=?', (old['series_id'],)).fetchone()[0]
                need(old['revision'] == latest)
                previous, revision, series = {'id': old['id'], 'digest': digest(old)}, latest + 1, old['series_id']
                sources = sorted(set(sources) | {s['id'] for s in old['sources']})
            need(len(sources) <= MAX_SOURCES)
            source_refs = []
            for source in sources:
                event = self.ledger._event(source)[1]['body']
                need(event['conversation_id'] == binding.conversation_id)
                for member in roster:
                    need(self.ledger._visible(source, member['principal'], self.ledger._binding(binding.conversation_id, member['principal']), {}))
                source_refs.append({'id': source, 'digest': digest(event)})
            body = {'domain': VERSION + '/proposal', 'id': uuid.uuid4().hex, 'conversation_id': binding.conversation_id,
                    'author': principal, 'author_epoch': binding.member_epoch, 'request_id': request_id,
                    'request_digest': request_digest, 'series_id': series, 'revision': revision, 'previous': previous,
                    'content': content, 'content_digest': content_digest(content), 'sources': source_refs, 'audience': roster,
                    'policy_generation': binding.policy_generation, 'expires_at': expires_at, 'scope': 'local-discussion-only'}
            encoded = self._seal(TABLES[0], body, auth, session)
            self.db.execute('INSERT INTO conversation_proposals VALUES(?,?,?,?,?,?,?,?)',
                            (body['id'], binding.conversation_id, principal, request_id, request_digest, series, revision, encoded))
            signed = self._proposal(body['id'])
            result = self._view(principal, binding, signed)
            checks.append(lambda: self._require_current(body))
            checks.append(lambda: self._check_view(principal, binding, signed, result))
            return result

    def inspect(self, principal, session, binding, proposal_id):
        checks = []
        with self._transaction(principal, session, checks):
            signed = self._proposal(proposal_id)
            result = self._view(principal, binding, signed)
            checks.append(lambda: self._check_view(principal, binding, signed, result))
            return result

    def inspect_request(self, principal, session, binding, request_id):
        """Reconcile a lost create response without repeating an external effect."""
        identifier(request_id)
        checks = []
        with self._transaction(principal, session, checks):
            self.ledger._check_binding(principal, binding)
            row = self.db.execute('SELECT id FROM conversation_proposals WHERE conversation_id=? AND author=? AND request_id=?',
                                  (binding.conversation_id, principal, request_id)).fetchone()
            if row is None:
                return None
            signed = self._proposal(row['id'])
            result = self._view(principal, binding, signed)
            checks.append(lambda: self._check_view(principal, binding, signed, result))
            return result

    def prepare_approval(self, principal, session, binding, proposal_id):
        checks = []
        with self._transaction(principal, session, checks):
            signed = self._proposal(proposal_id)
            body = signed['statement']
            self._readable(principal, binding, body)
            self._require_current(body)
            statement = self._approval_statement(body, principal)
            need(self.db.execute('SELECT 1 FROM conversation_approval_revocations WHERE approval_id=?', (statement['id'],)).fetchone() is None)
            checks.extend([lambda: self._readable(principal, binding, body), lambda: self._require_current(body)])
            return {'proposal': snapshot(signed), 'statement': statement, 'review_digest': digest(statement)}

    def approve(self, principal, session, binding, review, expected_review_digest):
        need(type(review) is dict and set(review) == {'proposal', 'statement', 'review_digest'})
        try:
            review = snapshot(review)
            statement = review['statement']
            need(type(statement) is dict and digest(statement) == review['review_digest'] == expected_review_digest)
            proposal_id = statement['proposal_id']
        except (ValueError, TypeError, KeyError):
            raise ConversationDenied('Conversation operation unavailable') from None
        checks = []
        with self._transaction(principal, session, checks) as auth:
            signed = self._proposal(proposal_id)
            body = signed['statement']
            self._readable(principal, binding, body)
            self._require_current(body)
            need(review['proposal'] == signed and statement == self._approval_statement(body, principal))
            need(self.db.execute('SELECT 1 FROM conversation_approval_revocations WHERE approval_id=?', (statement['id'],)).fetchone() is None)
            existing = self.db.execute('SELECT * FROM conversation_approvals WHERE id=?', (statement['id'],)).fetchone()
            if existing:
                need(self._open(TABLES[1], existing, 'approval', 'owner')['statement'] == statement)
            else:
                self.db.execute('INSERT INTO conversation_approvals VALUES(?,?,?,?)',
                                (statement['id'], body['id'], principal, self._seal(TABLES[1], statement, auth, session)))
            result = self._view(principal, binding, signed)
            checks.extend([lambda: self._require_current(body), lambda: self._check_view(principal, binding, signed, result)])
            return result

    def revoke(self, principal, session, binding, proposal_id):
        checks = []
        with self._transaction(principal, session, checks) as auth:
            signed = self._proposal(proposal_id)
            body = signed['statement']
            self._readable(principal, binding, body)
            statement = self._approval_statement(body, principal)
            existing = self.db.execute('SELECT * FROM conversation_approvals WHERE id=?', (statement['id'],)).fetchone()
            need(self._open(TABLES[1], existing, 'approval', 'owner')['statement'] == statement)
            revoked = self._revocation_statement(statement)
            if not self.db.execute('SELECT 1 FROM conversation_approval_revocations WHERE id=?', (revoked['id'],)).fetchone():
                self.db.execute('INSERT INTO conversation_approval_revocations VALUES(?,?,?,?)',
                                (revoked['id'], statement['id'], principal, self._seal(TABLES[2], revoked, auth, session)))
            result = self._view(principal, binding, signed)
            checks.append(lambda: self._check_view(principal, binding, signed, result))
            return result
