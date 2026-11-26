"""Trusted composed-task response authoring. Inert, exact, unsigned and bounded.

No agent endpoint. A processed request is necessary before exposing its contents.
The existing durable owner request ledger is the idempotency ledger: the earliest
identical envelope wins across every lifecycle state, including agent imports.
"""
import json
from network import Denied, canonical, digest
from generic_protocol import task_envelope
from generic_capabilities import validate_payload, validate_result_against_request
from task_composer import composed_fixture


class OwnerResponses:
    def _response_context(self, owner, allow_terminal=False):
        self._owner(owner)
        spec = getattr(self, 'composed_spec', None)
        if spec is None or owner != self.session.task.responder:
            raise Denied('Only the composed task responder can compose its response')
        projection = self.session._restore()
        if not allow_terminal and (projection.cancellation or projection.result is not None):
            raise Denied('Task is terminal')
        incoming = projection.request
        if incoming is None or incoming != composed_fixture(spec)[2]:
            raise Denied('An exact processed incoming request is required')
        return {'owner':owner,'recipient':self.session.task.requester,
                'context':self.session.context,'request_digest':digest(incoming),
                'incoming_request':json.loads(canonical(incoming))}

    def response_context(self, owner):
        with self.store.transaction():
            return self._response_context(owner)

    def _response_preview(self, owner, request_digest, payload, allow_terminal=False):
        result = self._response_context(owner, allow_terminal)
        if type(request_digest) is not str or request_digest != result['request_digest']:
            raise Denied('Response must reference the exact processed request digest')
        validate_payload(self.session.task.capability, 'result', payload)
        envelope = task_envelope(self.session.task, 'result', payload, reply_to=request_digest)
        validate_result_against_request(self.session.task.capability, result['incoming_request']['payload'], envelope['payload'])
        # Leave space for the decision, transport bindings and confirmation in
        # the unchanged 16KiB signer input frame. Output review repeats text.
        if len(json.dumps(envelope, allow_nan=False)) > 12000:
            raise Denied('Response exceeds bounded owner review transport size')
        result['envelope'] = envelope
        result['preview_digest'] = digest({'domain':'agent-network-owner-response-preview/v1',**result})
        return result

    def preview_response(self, owner, request_digest, payload):
        with self.store.transaction():
            return self._response_preview(owner, request_digest, payload)

    def prepare_response(self, owner, request_digest, payload, preview_digest, confirmation):
        with self.store.transaction():
            preview = self._response_preview(owner, request_digest, payload, allow_terminal=True)
            if type(preview_digest) is not str or preview_digest != preview['preview_digest'] or type(confirmation) is not str or confirmation != 'REVIEW RESPONSE '+owner:
                raise Denied('Review and confirm this exact response preview')
            # Do not filter by approval state, expiry, replacement or withdrawal.
            # Those are historical outcomes, never permission to mint approval.
            row = self.db.execute('SELECT * FROM owner_requests WHERE context=? AND owner=? AND envelope=? ORDER BY rowid LIMIT 1',
                                  (self.session.context,owner,canonical(preview['envelope']))).fetchone()
            if row is not None:
                return self._card(row)
            self._response_context(owner)  # Terminal tasks cannot gain new reviews.
            decision, message, meaning = self._draft(owner,'send',envelope=preview['envelope'])
            self._insert_draft(decision,message,meaning)
            return self._card(self._row(owner,decision['nonce']))
