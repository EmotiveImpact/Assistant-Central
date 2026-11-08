"""Untrusted JSON boundary, NOT a Python/OS sandbox or provider MCP server.

Only dispatch() is the adapter surface. Construction, store access and
prepare_owner_review() belong to the trusted host. Do not hand arbitrary Python
code this object, the executor's trusted pipe, or its filesystem permissions.
"""
import json
from generic_protocol import identifier, validate_task_scope
from generic_session import GenericPersistentSession
from network import Denied, canonical, digest


class AgentProposalBoundary:
    def __init__(self, workflow, actor):
        if type(workflow.session) is not GenericPersistentSession:
            raise Denied('Agent boundary requires a generic task')
        if type(actor) is not str or actor not in workflow.session.task.participants:
            raise Denied('Actor must be a pre-bound task peer')
        self.workflow, self.actor = workflow, actor
        self.session, self.store, self.db = workflow.session, workflow.store, workflow.db
        self.context = self.session.context
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS agent_proposals (
                context TEXT NOT NULL, actor TEXT NOT NULL, fingerprint TEXT NOT NULL,
                envelope TEXT NOT NULL, request_id TEXT,
                PRIMARY KEY(context,actor,fingerprint));
            CREATE TABLE IF NOT EXISTS agent_proposal_ids (
                context TEXT NOT NULL, actor TEXT NOT NULL, proposal_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                PRIMARY KEY(context,actor,proposal_id));
        ''')

    def _row(self, proposal_id):
        identifier(proposal_id)
        row = self.db.execute('''SELECT p.* FROM agent_proposal_ids i JOIN agent_proposals p
            ON p.context=i.context AND p.actor=i.actor AND p.fingerprint=i.fingerprint
            WHERE i.context=? AND i.actor=? AND i.proposal_id=?''',
            (self.context, self.actor, proposal_id)).fetchone()
        if row is None:
            raise Denied('Unknown proposal')
        return row

    def _status(self, row, proposal_id):
        # Whitelist only, never pass through owner cards, signatures, nonces,
        # reason strings, binding material, or unrelated status snapshots.
        state, delivery = 'awaiting_owner_review', None
        if row['request_id']:
            card = self.workflow._card(self.workflow._row(self.actor, row['request_id']))
            state = card['state']
            out = self.db.execute('SELECT state FROM encrypted_outbox WHERE nonce=? AND context=? AND sender=?',
                                 (row['request_id'], self.context, self.actor)).fetchone()
            if out:
                delivery = out['state']
        else:
            try:
                self.session._restore()._validate(json.loads(row['envelope']))
            except Denied:
                state = 'unavailable'
        return {'proposal_id': proposal_id, 'envelope_digest': row['fingerprint'],
                'state': state, 'delivery_state': delivery}

    def dispatch(self, command):
        """Only this closed JSON interface may be routed to an untrusted adapter."""
        try:
            encoded = canonical(command)
            if len(encoded.encode('utf-8')) > 12288:
                raise Denied('Agent command too large')
            command = json.loads(encoded)
            if type(command) is not dict or type(command.get('method')) is not str:
                raise Denied('Expected a closed agent command')
            method = command['method']
            if method == 'propose' and set(command) == {'method', 'proposal_id', 'envelope'}:
                identifier(command['proposal_id'])
                message = validate_task_scope(self.session.task, command['envelope'])
                if getattr(self.workflow, 'composed_spec', None) is not None:
                    from task_composer import validate_composed_request
                    validate_composed_request(self.workflow.composed_spec, message)
                if message['sender'] != self.actor:
                    raise Denied('Proposal sender is not the bound actor')
                fingerprint = digest(message)
                with self.store.transaction():
                    existing = self.db.execute('SELECT fingerprint FROM agent_proposal_ids WHERE context=? AND actor=? AND proposal_id=?',
                        (self.context, self.actor, command['proposal_id'])).fetchone()
                    if existing and existing['fingerprint'] != fingerprint:
                        raise Denied('Proposal ID reused with different payload')
                    if not existing:
                        # Aliases add durable rows too. Validate coherence without
                        # rejecting valid terminal history or renewing authority.
                        projection = self.session._restore()
                        prior = self.db.execute('SELECT 1 FROM agent_proposals WHERE context=? AND actor=? AND fingerprint=?',
                            (self.context, self.actor, fingerprint)).fetchone()
                        if self.db.execute('SELECT COUNT(*) FROM agent_proposal_ids').fetchone()[0] >= self.store.max_records:
                            raise Denied('Proposal record limit reached')
                        if not prior:
                            projection._validate(message)
                            self.db.execute('INSERT INTO agent_proposals VALUES (?,?,?,?,NULL)',
                                (self.context, self.actor, fingerprint, canonical(message)))
                        self.db.execute('INSERT INTO agent_proposal_ids VALUES (?,?,?,?)',
                            (self.context, self.actor, command['proposal_id'], fingerprint))
                    return self._status(self._row(command['proposal_id']), command['proposal_id'])
            if method == 'proposal_status' and set(command) == {'method', 'proposal_id'}:
                with self.store.transaction():
                    return self._status(self._row(command['proposal_id']), command['proposal_id'])
            if method == 'inbox' and set(command) == {'method'}:
                with self.store.transaction():
                    messages = []
                    # Validate the full history, not individual raw rows: a
                    # receipt, malformed linkage, duplicate transition or wrong
                    # durable context must not become an inbox disclosure.
                    projection = self.session._restore()
                    if getattr(self.workflow, 'composed_spec', None) is not None:
                        from task_composer import validate_composed_request
                        validate_composed_request(self.workflow.composed_spec, projection.request)
                        validate_composed_request(self.workflow.composed_spec, projection.result)
                    for message in (projection.request, projection.result):
                        if message is None:
                            continue
                        if message['recipient'] == self.actor:
                            messages.append({'envelope_digest': digest(message), 'envelope': message})
                    return {'messages': messages, 'payload_trust': 'untrusted_inert'}
            raise Denied('Unknown agent method or fields')
        except (ValueError, TypeError, RecursionError) as exc:
            raise Denied('Invalid bounded agent JSON') from exc

    def list_owner_proposals(self):
        """TRUSTED OWNER ONLY: bounded distinct proposal discovery, no import."""
        with self.store.transaction():
            rows = self.db.execute("""SELECT p.*, (SELECT i.proposal_id FROM agent_proposal_ids i
                WHERE i.context=p.context AND i.actor=p.actor AND i.fingerprint=p.fingerprint
                ORDER BY i.rowid LIMIT 1) AS proposal_id FROM agent_proposals p
                WHERE p.context=? AND p.actor=? ORDER BY p.rowid DESC LIMIT 20""",
                (self.context, self.actor)).fetchall()
            return [{'proposal_id': row['proposal_id'], 'envelope_digest': row['fingerprint'],
                     'state': self._status(row, row['proposal_id'])['state'],
                     'type': json.loads(row['envelope'])['type'],
                     'recipient': json.loads(row['envelope'])['recipient']}
                    for row in rows]

    def prepare_owner_review(self, proposal_id):
        """TRUSTED OWNER ONLY: import into unsigned review, never grant or send.

        Exact fingerprints retain one original review forever, including refused,
        withdrawn, expired and uncertain history. Only existing owner controls
        may explicitly create successors; adapter retries cannot follow them.
        """
        with self.store.transaction():
            row = self._row(proposal_id)
            if row['request_id']:
                return self.workflow._card(self.workflow._row(self.actor, row['request_id']))
            message = json.loads(row['envelope'])
            # Respect exact matching owner reviews made outside this boundary too.
            prior = self.db.execute('SELECT nonce FROM owner_requests WHERE context=? AND owner=? AND envelope=? ORDER BY rowid LIMIT 1',
                                    (self.context, self.actor, canonical(message))).fetchone()
            if prior:
                nonce = prior['nonce']
            else:
                decision, message, meaning = self.workflow._draft(self.actor, 'send', envelope=message)
                self.workflow._insert_draft(decision, message, meaning)
                nonce = decision['nonce']
            self.db.execute('UPDATE agent_proposals SET request_id=? WHERE context=? AND actor=? AND fingerprint=?',
                            (nonce, self.context, self.actor, row['fingerprint']))
            return self.workflow._card(self.workflow._row(self.actor, nonce))
