"""Exact team artifact -> unsigned r5 proposal mapping. No approval or sending.

One trusted construction binds one completed source artifact and one downstream
agent/task. The returned exact AssistantFacade can use the unchanged r3/r4 wire
building blocks. The standalone r5 launcher and its allowlist remain unchanged.
"""
import json

from .bootstrap import (TeamWorkflow, Denied, digest, canonical, PUBLIC_FIXTURE,
                        AssistantFacade, ProposalStore, protocol_digest)

DOMAIN = 'assistant-central-team-r5-proposal/1'
PROTOCOL_CAPABILITY = 'fictional-answer/1'
MAX_UTF8 = 1024


class OutcomeUnknown(RuntimeError):
    """Local proposal may have committed. Inspect the exact ID; never auto-retry."""


def _copy(value):
    return json.loads(canonical(value))


class BoundArtifactProposal:
    """Trusted host-only constructor; never expose this selector to a tool caller.

    Existing owner methods remain outside the protocol. No owner-review, publisher,
    peer endpoint, key generation, worker process or transport is constructed.
    """
    def __init__(self, workflow, source_artifact_id, recipient_task_id, *,
                 expected_context, database=':memory:'):
        if type(workflow) is not TeamWorkflow:
            raise Denied('An exact trusted team workflow is required')
        workflow._check(expected_context)
        if workflow.plan.context != expected_context:
            raise Denied('Immutable team context mismatch')
        self._workflow = workflow
        self._context = expected_context
        self._artifact_id = source_artifact_id
        self._recipient_task_id = recipient_task_id
        self._closed = False
        # Serialize the permission snapshot against other connections to this team.
        with workflow._transaction():
            mapping, text = self._current_mapping()
        self._mapping = canonical(mapping)
        self._text = text
        self._mapping_digest = digest(mapping)
        self._protocol_task = canonical({'id': self.mapping_digest[:32], 'context': self.mapping_digest,
                                         'capability': PROTOCOL_CAPABILITY})
        self._store = ProposalStore(database, actor='alice', task_value=self.protocol_task,
                                    public=_copy(PUBLIC_FIXTURE['public']))
        self._binding = canonical(self._store._binding)
        self._proposal_id = protocol_digest({'binding': self._store._binding, 'text': text})
        self._content_digest = protocol_digest({'text': text})
        self.facade = AssistantFacade(self._store)
        self._plain_propose = self.facade.propose
        self._plain_status = self.facade.status
        self._plain_inbox = self.facade.processed_inbox
        # r3 intentionally requires the exact AssistantFacade type. Narrow only
        # this instance, as r5 does; never modify a frozen class or source file.
        self.facade.propose = self._propose
        self.facade.status = self._status
        self.facade.processed_inbox = self._inbox

    @property
    def mapping_digest(self):
        return self._mapping_digest

    @property
    def protocol_task(self):
        return json.loads(self._protocol_task)

    @property
    def proposal_id(self):
        return self._proposal_id

    @property
    def content_digest(self):
        return self._content_digest

    def _current_mapping(self):
        w = self._workflow
        w._check(self._context)
        if w.plan.context != self._context:
            raise Denied('Immutable team context mismatch')
        w._live()
        artifact = w._artifact(self._artifact_id)
        source = w._task(artifact['task_id'])
        source_state = w._row(source.id)
        target = w._task(self._recipient_task_id)
        if (source_state['state'] != 'completed' or source_state['artifact_id'] != self._artifact_id
                or artifact['state'] != 'accepted' or artifact['producer'] != source.assignee):
            raise Denied('An exact completed and accepted source artifact is required')
        if source.assignee == target.assignee:
            raise Denied('This two-agent mapping requires distinct agent references')
        body = json.loads(artifact['body'])
        if digest(body) != artifact['digest'] or body['context'] != self._context:
            raise Denied('Artifact integrity or context mismatch')
        request = w._request(source_state['request_id'])
        if body['start_review_digest'] != request['digest']:
            raise Denied('Artifact does not commit the source start review')
        text = body['content']
        if type(text) is not str or not text or len(text) > MAX_UTF8:
            raise Denied('Only bounded nonempty text artifacts can be mapped')
        try:
            if len(text.encode('utf-8')) > MAX_UTF8:
                raise Denied('Artifact exceeds the protocol UTF-8 bound; no truncation is allowed')
        except UnicodeError:
            raise Denied('Artifact must contain Unicode scalar text') from None
        # Reuse the exact team-side recipient/purpose rules, then require the
        # current explicit grant. Same-owner agents receive no implicit sharing.
        owner = w.agents[source.assignee].owner
        review = w._disclosure_review(owner, self._artifact_id, target.assignee, target.id)
        grant = w.db.execute('SELECT * FROM disclosures WHERE artifact_id=? AND recipient=? AND purpose=?',
                             (self._artifact_id, target.assignee, 'task:' + target.id)).fetchone()
        if not grant or grant['state'] != 'granted' or grant['review_digest'] != digest(review):
            raise Denied('Exact current downstream disclosure approval is required')
        mapping = {
            'domain': DOMAIN, 'team_context': self._context,
            'source_task': source.to_dict(), 'recipient_task': target.to_dict(),
            'source_agent': w.agents[source.assignee].to_dict(),
            'recipient_agent': w.agents[target.assignee].to_dict(),
            'artifact_id': self._artifact_id, 'artifact_digest': artifact['digest'],
            'start_review_digest': request['digest'], 'disclosure_review_digest': grant['review_digest'],
            'protocol_roles': {'alice': source.assignee, 'bob': target.assignee},
            'protocol_capability': PROTOCOL_CAPABILITY,
            'public_descriptors': 'r5 public RFC fixtures, not real identities',
        }
        return mapping, text

    def _open(self):
        if self._closed:
            raise Denied('Mapped proposal store is closed')
        if canonical(self._store._binding) != self._binding:
            raise Denied('Protocol binding changed')

    def binding_review(self):
        """Trusted operator metadata. This is not a new approval or a tool result."""
        self._open()
        return {'mapping': json.loads(self._mapping), 'mapping_digest': self.mapping_digest,
                'protocol_task': _copy(self.protocol_task), 'proposal_id': self.proposal_id,
                'content_digest': self.content_digest,
                'effect': 'Unsigned local proposal only; no start, approval, release, delivery or processing.'}

    def _propose(self, arguments):
        self._open()
        if type(arguments) is not dict or set(arguments) != {'text'} or type(arguments['text']) is not str:
            raise Denied('Only an exact text proposal is accepted')
        if arguments['text'] != self._text:
            raise Denied('Proposed text does not match the bound artifact')
        attempted = False
        try:
            with self._workflow._transaction():
                mapping, text = self._current_mapping()
                if canonical(mapping) != self._mapping or text != self._text:
                    raise Denied('Mapped artifact or authority changed')
                # The team lock prevents revocation from passing this check then
                # committing before this local stage completes. The lower store is
                # still a separate transaction: an escaping failure is conservative.
                attempted = True
                result = self._plain_propose({'text': self._text})
                if (result.get('proposal_id') != self.proposal_id
                        or result.get('content_digest') != self.content_digest):
                    raise ValueError('Unexpected local proposal identity')
        except Exception:
            if attempted:
                raise OutcomeUnknown('Local staging outcome unavailable; inspect the exact proposal ID.') from None
            raise
        return _copy(result)

    def _status(self, arguments):
        self._open()
        if (type(arguments) is not dict or set(arguments) != {'proposal_id'}
                or arguments['proposal_id'] != self.proposal_id):
            raise Denied('Only this exact mapped proposal may be inspected')
        # Read-only history remains available after revocation, without text,
        # hidden owner commands, renewal or a new proposal.
        return _copy(self._plain_status({'proposal_id': self.proposal_id}))

    def _inbox(self, arguments):
        self._open()
        if type(arguments) is not dict or arguments:
            raise Denied('Inbox accepts no selectors')
        result = self._plain_inbox({})
        if result != {'knowledge': 'No trusted local snapshot published.', 'publication': 0, 'items': []}:
            raise Denied('This mapping has no authorized incoming publication path')
        return _copy(result)

    def close(self):
        if not self._closed:
            self._closed = True
            self._store.close()
