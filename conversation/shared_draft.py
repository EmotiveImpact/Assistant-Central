"""Assistant-facing shared drafts, built on exact local proposals.

Borrowed idea (ericscalibur/Parley): a shared draft beside the conversation that
the assistants work on together, which only becomes final when every person
approves the same exact version.

Here a draft is a ``LocalProposals`` series. An assistant can start a draft,
revise its own owner's draft, or suggest changes to someone else's draft as a
new draft. It can read the current state. It can never approve: approval stays
an owner control, bound to the exact revision, and any new revision starts with
no approvals.
"""
import math

from .inbox import AssistantLease, InboxStore
from .ledger import MAX_GRANT_SECONDS, bounded_text, identifier, need
from .proposals import LocalProposals
from .timeline import record_safely

DEFAULT_SECONDS = 86400


def draft_view(result):
    """A compact view of one ``LocalProposals`` inspection."""
    body = result['proposal']['statement']
    return {'draft_id': body['id'], 'series_id': body['series_id'], 'revision': body['revision'],
            'author': body['author'], 'text': body['content'], 'content_digest': body['content_digest'],
            'expires_at': body['expires_at'], 'current': result['proposal_current'],
            'people': [member['principal'] for member in body['audience']],
            'approved_by': list(result['current_approval_owners']),
            'final': result['proposal_current'] and result['all_owners_approved'],
            'trust': 'untrusted-draft', 'execution_authority': False, 'external_agreement': False}


class DraftAccess:
    """What a trusted host hands to an assistant-facing server for drafts.

    The lease is fixed at construction and the owner's session comes from a
    host callback, so a model cannot choose the owner or the conversation.
    """

    def __init__(self, proposals, inbox, lease, session_provider, timeline=None):
        self._timeline = timeline
        need(type(proposals) is LocalProposals and type(inbox) is InboxStore and proposals.ledger is inbox.ledger)
        need(type(lease) is AssistantLease and callable(session_provider))
        self._proposals, self._inbox, self._lease, self._session = proposals, inbox, lease, session_provider

    @property
    def conversation_id(self):
        return self._lease.conversation_id

    def _bound(self):
        session = self._session()
        self._inbox.check_lease(session, self._lease)
        binding = self._proposals.ledger.bind_context(self._lease.principal, session, self._lease.conversation_id)
        return session, binding

    def _expiry(self, seconds):
        need(type(seconds) in (int, float) and math.isfinite(seconds) and 60 <= seconds <= MAX_GRANT_SECONDS)
        return self._proposals.ledger.clock() + seconds

    def start(self, request_id, text, *, seconds=DEFAULT_SECONDS):
        identifier(request_id); bounded_text(text)
        session, binding = self._bound()
        existing = self._proposals.inspect_request(self._lease.principal, session, binding, request_id)
        if existing is not None:
            need(existing['proposal']['statement']['content'] == text
                 and existing['proposal']['statement']['previous'] is None)
            return draft_view(existing)
        view = draft_view(self._proposals.create(self._lease.principal, session, binding, request_id=request_id,
                                                 content=text, expires_at=self._expiry(seconds)))
        self._record('draft_started', view)
        return view

    def _record(self, kind, view, responds_to=None):
        record_safely(self._timeline, kind, self._lease.conversation_id, role='your_assistant',
                      ref='proposal:' + view['draft_id'],
                      detail={'draft_id': view['draft_id'], 'series_id': view['series_id'], 'revision': view['revision'],
                              'responds_to': responds_to, 'assistant_id': self._lease.assistant_id})

    def revise(self, request_id, draft_id, text, *, seconds=DEFAULT_SECONDS):
        """Revise your owner's own draft, or suggest changes to another person's as a new draft."""
        identifier(request_id); identifier(draft_id); bounded_text(text)
        session, binding = self._bound()
        principal = self._lease.principal
        existing = self._proposals.inspect_request(principal, session, binding, request_id)
        if existing is not None:
            need(existing['proposal']['statement']['content'] == text)
            return {**draft_view(existing), 'responds_to': draft_id}
        base = self._proposals.inspect(principal, session, binding, draft_id)['proposal']['statement']
        own = base['author'] == principal
        result = self._proposals.create(principal, session, binding, request_id=request_id, content=text,
                                        expires_at=self._expiry(seconds), replaces=draft_id if own else None)
        view = {**draft_view(result), 'responds_to': draft_id, 'kind': 'revision' if own else 'suggestion'}
        self._record('draft_revised' if own else 'draft_suggested', view, draft_id)
        return view

    def view(self, draft_id):
        identifier(draft_id)
        session, binding = self._bound()
        return draft_view(self._proposals.inspect(self._lease.principal, session, binding, draft_id))

    def list(self, limit=20):
        session, binding = self._bound()
        return [draft_view(r) for r in self._proposals.latest(self._lease.principal, session, binding, limit=limit)]
