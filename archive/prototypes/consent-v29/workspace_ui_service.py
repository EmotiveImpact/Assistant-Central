"""Closed trusted-owner HTTP adapter over disposable, exact-context workspace.

This is not an agent endpoint or authentication mechanism. It creates no service
until explicitly requested. The adapter owns no mutable selected-task state.
"""
from network import Denied
from owner_workspace import OwnerWorkspace


class WorkspaceUIService:
    def __init__(self, *, continuity=False):
        self.workspace = OwnerWorkspace(continuity=continuity)
        self.continuity_enabled = continuity

    def close(self):
        self.workspace.close()

    def tasks(self):
        return self.workspace.list_tasks()

    def state(self, selector, context, owner):
        return self.workspace.state(selector, context, owner)

    def received_messages(self, selector, context, owner):
        return self.workspace.received_messages(selector, context, owner)

    def response_context(self, selector, context, owner):
        return self.workspace.response_context(selector, context, owner)

    def review(self, selector, context, owner, request_id):
        return self.workspace.review(selector, context, owner, request_id)

    def delivery(self, selector, context, owner, request_id):
        return self.workspace.delivery(selector, context, owner, request_id)

    def proposals(self, selector, context, owner):
        return self.workspace.proposals(selector, context, owner)

    def task_preview(self, spec):
        return self.workspace.task_preview(spec)

    def relationships(self):
        return self.workspace.relationships()

    def relationship_preview(self, body):
        return self.workspace.relationship_preview(body)

    def continuity_state(self):
        if not self.continuity_enabled:
            return {"enabled": False}
        return {"enabled": True, **self.workspace.continuity_state()}

    def continuity_preview(self, body):
        return self.workspace.continuity_preview(body)

    def action(self, body):
        if type(body) is dict and body.get("action") in ("continuity_enroll", "continuity_associate", "continuity_retire"):
            if set(body) != {"action", "review", "confirmation"}:
                raise Denied("Expected exact reviewed continuity action")
            return self.workspace.continuity_commit(body["action"][11:], body["review"], body["confirmation"])
        if type(body) is dict and body.get('action') in ('relationship_create', 'relationship_attach', 'relationship_stop'):
            if set(body) != {'action', 'review', 'confirmation'}:
                raise Denied('Expected exact reviewed relationship action')
            return self.workspace.relationship_commit(body['action'][13:], body['review'], body['confirmation'])
        if type(body) is dict and body.get("action") == "compose_task":
            if set(body) != {"action","spec","review_digest","confirmation"}:
                raise Denied("Expected exact reviewed task composition")
            return self.workspace.compose(body["spec"],body["review_digest"],body["confirmation"])
        if type(body) is not dict or set(body) != {'selector', 'context', 'request'}:
            raise Denied('Every workspace action requires an exact selector, context and request')
        selector, context, request = body['selector'], body['context'], body['request']
        if type(selector) is not str or type(context) is not str:
            raise Denied('Expected a catalog selector and exact task context')
        if type(request) is not dict or type(request.get('action')) is not str:
            raise Denied('Expected a closed local workspace action')
        action = request['action']
        if action == 'create':
            if set(request) != {'action'}:
                raise Denied('Unexpected creation fields')
            return self.workspace.create(selector, context)
        if action == 'import_proposal':
            if set(request) != {'action', 'owner', 'proposal_id'}:
                raise Denied('Expected only owner and exact staged proposal ID')
            card = self.workspace.import_proposal(selector, context, request['owner'], request['proposal_id'])
            return {'kind': 'request', 'card': card}
        result = self.workspace.action(selector, context, request)
        # A task close must never trigger the legacy whole-launcher shutdown.
        if action == 'close':
            return {'task_closed': result['closed'], 'selector': selector, 'context': context}
        return result
