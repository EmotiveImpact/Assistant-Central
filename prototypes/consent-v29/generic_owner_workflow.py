"""Generic task review/guide adapter over the shared exact owner authorization ledger."""
from datetime import datetime, timezone
from network import Denied, canonical
from owner_workflow import OwnerWorkflow
from workflow_scenarios import render_scope_review


from owner_responses import OwnerResponses


class GenericOwnerWorkflow(OwnerResponses, OwnerWorkflow):
    def received_messages(self, owner):
        """Trusted read-only owner view of validated, processed inbound content.

        sender_binding is the current local fictional binding fingerprint, not
        authentication of a human or provider. Cancellation cannot undo disclosure.
        No proposal boundary is constructed and no request is reconciled here.
        """
        import json
        from network import digest
        with self.store.transaction():
            self._owner(owner)
            projection = self.session._restore()
            if getattr(self, 'composed_spec', None) is not None:
                from task_composer import validate_composed_request
                validate_composed_request(self.composed_spec, projection.request)
                validate_composed_request(self.composed_spec, projection.result)
            messages = []
            # Replay validates the complete protocol history, including linkage.
            # The protocol admits only one request and one result, not a page of
            # raw outbox/receipt rows. Neither receipt nor dispatch is processing.
            for message in (projection.request, projection.result):
                if message is not None and message['recipient'] == owner:
                    messages.append({'envelope_digest':digest(message),
                                     'envelope':json.loads(canonical(message)),
                                     'sender_binding':self.registry.binding_digest(message['sender'])})
            return {'owner':owner, 'task':self.session.task.id,
                    'context':self.session.context, 'task_state':projection.state,
                    'messages':messages, 'payload_trust':'untrusted_inert',
                    'fictional':True, 'temporary':True}

    def _validate(self, decision, envelope):
        decision, message = super()._validate(decision, envelope)
        if getattr(self, 'composed_spec', None) is not None:
            from task_composer import validate_composed_request
            validate_composed_request(self.composed_spec, message)
        if decision['action'] in ('pair', 'revoke') and decision['target']['peer'] == decision['owner']:
            raise Denied('Generic task pairing requires the other task participant')
        return decision, message

    def _review_text(self, decision, message):
        action, target = decision['action'], decision['target']
        if action == 'send':
            review = render_scope_review(self.session.task, message)
            review += '\nRecipient transport binding: '+target['recipient_binding']
            review += '\nExact structured message: '+canonical(message)
        elif action == 'pair':
            review = f"Allow {decision['owner']} to pair with {target['peer']} for this task for {target['ttl']} seconds. Both directions require separate approval. This sends nothing."
        elif action == 'revoke':
            review = f"Revoke {decision['owner']}'s pairing with {target['peer']} for this task. Unused approvals become invalid. Already-started dispatches and disclosed data cannot be recalled."
        else:
            review = 'Cancel this local task permanently for both participants. In-flight messages may arrive; no remote notification is sent. The signed v1 control field named meeting is a compatibility alias for this task ID.'
        return review + f"\nExact task: {self.session.task.id}\nContext: {self.session.context}\nDecision expires: {datetime.fromtimestamp(decision['expires_at'],timezone.utc).isoformat()}\nFictional owner/transport identity only; not real-person authentication."

    def next_step(self):
        for row in list(self.db.execute("SELECT owner,nonce FROM owner_requests WHERE context=? AND state='authorized'", (self.session.context,))):
            self.reconcile_request(row['owner'], row['nonce'])
        with self.store.transaction():
            projection = self.session._restore()
            if projection.cancellation:
                attempted = self.db.execute("SELECT sender,nonce FROM encrypted_outbox WHERE context=? AND state IN ('dispatched','received','stopped_uncertain') ORDER BY rowid LIMIT 1", (self.session.context,)).fetchone()
                if attempted:
                    return {'kind':'delivery','owner':attempted['sender'],'cancelled':True,**self.delivery(attempted['sender'],attempted['nonce'])}
                return {'kind':'stopped','reason':'Task cancelled. No unresolved attempted deliveries remain.'}
            pending = self.db.execute("SELECT owner,nonce FROM owner_requests r WHERE context=? AND state!='submitted' AND NOT EXISTS (SELECT 1 FROM owner_request_replacements l WHERE l.original=r.nonce) AND NOT EXISTS (SELECT 1 FROM owner_authorization_withdrawals w WHERE w.source_nonce=r.nonce) ORDER BY rowid LIMIT 1", (self.session.context,)).fetchone()
            if pending:
                return {'kind':'request','card':self._card(self._row(pending['owner'],pending['nonce']))}
            delivery = self.db.execute("SELECT sender,nonce FROM encrypted_outbox WHERE context=? AND state!='processed' ORDER BY rowid LIMIT 1", (self.session.context,)).fetchone()
            if delivery:
                return {'kind':'delivery','owner':delivery['sender'],**self.delivery(delivery['sender'],delivery['nonce'])}
            if projection.state == 'completed':
                return {'kind':'complete','reason':'Exact request and linked synthetic result processed. No resource visited or tool executed.'}
            a, b = self.session.task.participants
            next_pair = None
            for owner, peer in ((a,b),(b,a)):
                row = self.db.execute('SELECT expires FROM contacts WHERE owner=? AND peer=? AND purpose=?', (owner,peer,self.session.context)).fetchone()
                if row is None or row['expires'] <= self.store.clock():
                    next_pair = (owner, peer)
                    break
            from task_fixtures import exact_fixture
            if getattr(self, 'composed_spec', None) is not None:
                from task_composer import composed_fixture
                task, _, request, result = composed_fixture(self.composed_spec)
            else:
                task, _, request, result = exact_fixture(self.session.task)
            message = request if projection.request is None else result
        if next_pair:
            return {'kind':'request','card':self.prepare(next_pair[0],'pair',peer=next_pair[1])}
        if message is None:
            return {'kind':'awaiting','reason':'Waiting for an explicitly staged and owner-reviewed responder proposal. No result was generated.'}
        return {'kind':'request','card':self.prepare(message['sender'],'send',envelope=message)}
