"""Local owner-facing mission operations on the existing agreement and peer protocols."""
import re

from conversation.ledger import ConversationDenied, need
from conversation.proposals import LocalProposals
from pilot.crypto import digest
from pilot.mission import AGREEMENT, PROJECTION, agreement_content, evaluate, mission_context, read_agreement, task_text
from pilot.server import exact
from pilot.workflow import FIXTURE_GRANT

ROUTE = re.compile(r'/api/conversations/([A-Za-z0-9_-]{1,64})/missions/(list|create|inspect|review|approve|withdraw|draft|evaluate)')


class MissionService:
    def __init__(self, host):
        self.host = host
        self.proposals = None

    def call(self, principal, session, room, action, body):
        if self.proposals is None:
            # Only the coordinating account can initialise the local proposal store.
            self.proposals = LocalProposals(self.host.ledger, principal, session)
        binding = self.host.binding(principal, room, body.get('binding'))
        actor = (principal, session, binding)
        runtime = self.host.services[principal].runtime
        api = self.proposals
        if action == 'list':
            exact(body, ('binding',))
            # Only return revisions still visible to this exact membership epoch.
            def visible():
                self.host.ledger._check_binding(principal, binding)
                results = []
                rows = api.db.execute('SELECT id FROM conversation_proposals WHERE conversation_id=? ORDER BY rowid DESC LIMIT 50', (room,))
                for row in rows:
                    signed = api._proposal(row[0])
                    statement = signed['statement']
                    if not statement['content'].startswith('{"domain":"' + AGREEMENT + '"') or statement['sources']:
                        continue
                    try:
                        api._readable(principal, binding, statement)
                    except ConversationDenied:
                        continue
                    results.append({'id': row[0], 'revision': statement['revision'],
                                    'goal': read_agreement(statement)['goal']})
                return results
            checks = []
            with api._transaction(principal, session, checks):
                result = visible()
                checks.append(lambda: need(visible() == result))
                return {'missions': result}
        if action == 'create':
            exact(body, ('binding', 'request_id', 'terms', 'expires_at'), ('replaces',))
            content = agreement_content(body['terms'])
            members = self.host.ledger.participants(*actor)
            need(any(m['principal'] == body['terms']['executor'] != principal for m in members))
            if body.get('replaces') is not None:
                previous = api.inspect(*actor, body['replaces'])
                read_agreement(previous['proposal']['statement'])
            return api.create(*actor, request_id=body['request_id'], content=content,
                              expires_at=body['expires_at'], replaces=body.get('replaces'))

        fields = {'inspect': (), 'review': (), 'approve': ('review_digest',), 'withdraw': ('proposal_digest',),
                  'draft': ('proposal_digest', 'brief', 'task_id'), 'evaluate': ('artifact_id',)}
        exact(body, ('binding', 'proposal_id', *fields[action]))
        pid = body['proposal_id']
        view = api.inspect(*actor, pid)
        statement = view['proposal']['statement']
        need(not statement['sources'])
        agreed = read_agreement(statement)
        commitment = digest(statement)
        if action == 'inspect':
            return {**view, 'mission_digest': commitment, 'task_context': mission_context(commitment, agreed['cap_microusd'])}
        if action == 'withdraw':
            need(body['proposal_digest'] == commitment)
            return api.revoke(*actor, pid)
        if action in ('review', 'approve'):
            review = api.prepare_approval(*actor, pid)
            if action == 'review':
                return review
            return api.approve(*actor, review, body['review_digest'])

        need(view['all_owners_approved'] and principal == statement['author'])
        if action == 'draft':
            need(commitment == body['proposal_digest'] and not statement['sources'])
            # Only an explicitly entered, original brief and public fixture budget
            # cross into the draft. No proposal prose or conversation sources.
            return runtime.propose(session, agreed['executor'], 'task', 'Mission task',
                                   task_text(body['brief'], agreed['cap_microusd'], commitment),
                                   mission_context(commitment, agreed['cap_microusd']), body['task_id'],
                                   min(statement['expires_at'], runtime._now() + 3600), provider_disclosure={**FIXTURE_GRANT, 'projection': PROJECTION})
        with runtime._transaction(session) as checks:
            artifact_id = body['artifact_id']
            row, artifact = runtime._row(artifact_id)
            need(row['direction'] == 'incoming' and row['state'] in ('pending', 'accepted'))
            need(row['peer_id'] == agreed['executor'] and artifact['kind'] == 'artifact')
            def current():
                runtime._current(row)
                runtime._parent(artifact, sending=False)
                need(api.inspect(*actor, pid)['all_owners_approved'])
            current()
            checks.append(current)
            return evaluate(statement, artifact_id, artifact)
