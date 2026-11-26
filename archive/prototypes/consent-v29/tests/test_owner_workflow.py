import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from demo import fixture
from durable import LocalDelivery
from session import PersistentSession
from owner_auth import SignedOwnerGateway
from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver
from integrated_fixture import FixtureAuthorities
from bound_identity import signed_bytes
from network import Denied, canonical
from owner_workflow import OwnerWorkflow


class OwnerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name); self.now=[1000]
        self.meeting,self.agents,_=fixture();self.a=FixtureAuthorities(self.meeting,1000)
        self.open()
        self.a.pair_all(self.gateway,1000)
        self.rs=LocalDelivery(self.path/'receiver.sqlite3',clock=lambda:self.now[0])
        self.receiver=OfflineReceiver(self.rs,self.a.registry,'alice',self.a.transport_keys['alice'])
        self.message=self.agents[1].preview_availability(self.meeting)

    def open(self):
        self.store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
        self.session=PersistentSession(self.store,self.agents,self.meeting)
        self.gateway=SignedOwnerGateway(self.session,self.a.owner_roots)
        self.box=DurableEncryptedOutbox(self.gateway,self.a.registry,self.a.transport_keys)
        self.flow=OwnerWorkflow(self.gateway,self.box)

    def tearDown(self):self.store.close();self.rs.close();self.tmp.cleanup()
    def prepare(self):return self.flow.prepare('bob','send',envelope=self.message)
    def sign(self,card):
        d=card['decision'];return {'decision':copy.deepcopy(d),'signature':self.a.owner_keys[d['owner']].sign(signed_bytes(d['domain'],d)).hex()}
    def resolve(self,card,choice='approve',signed=None):
        return self.flow.resolve(card['owner'],card['request_id'],card['review_digest'],choice,self.sign(card) if choice=='approve' and signed is None else signed)
    def submit(self,card):self.resolve(card);return self.flow.submit(card['owner'],card['request_id'])
    def control(self,owner,action,peer=None):
        c=self.flow.prepare(owner,action,peer=peer);return self.submit(c)

    def test_prepare_and_review_are_not_approval_or_delivery(self):
        card=self.prepare();self.assertEqual(card['state'],'pending')
        self.assertEqual(len(self.flow.inbox('bob')),1);self.assertEqual(self.flow.inbox('dana'),[])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)
        self.assertIn('Only recipient of this message: Alice',card['review'])
        self.assertIn('Exact structured message:',card['review']);self.assertIn('1970-01-01T00:21:40',card['review'])
        with self.assertRaises(Denied):self.flow.submit('bob',card['request_id'])

    def test_repeated_prepare_reuses_exact_pending_request(self):
        one=self.prepare();two=self.prepare();self.assertEqual(one,two)
        self.assertEqual(len(self.flow.inbox('bob')),1)

    def test_approve_then_submit_is_separate_from_dispatch(self):
        c=self.prepare();self.assertEqual(self.resolve(c)['state'],'authorized')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)
        result=self.flow.submit('bob',c['request_id']);self.assertEqual(result['state'],'submitted')
        self.assertEqual(self.flow.delivery('bob',c['request_id'])['state'],'queued')
        self.assertEqual(self.rs.db.execute('SELECT COUNT(*) FROM encrypted_inbox').fetchone()[0],0)
        self.flow.submit('bob',c['request_id']);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],1)

    def test_decline_is_terminal_and_survives_reopen(self):
        c=self.prepare();signed=self.sign(c);self.resolve(c,'decline')
        self.store.close();self.open()
        card=self.flow.review('bob',c['request_id']);self.assertEqual(card['state'],'declined')
        with self.assertRaises(Denied):self.flow.resolve('bob',c['request_id'],card['review_digest'],'approve',signed)
        with self.assertRaises(Denied):self.flow.submit('bob',c['request_id'])

    def test_defer_invalidates_previously_displayed_review(self):
        c=self.prepare();signed=self.sign(c);deferred=self.resolve(c,'defer')
        self.assertEqual(deferred['revision'],1);self.assertEqual(deferred['state'],'deferred')
        with self.assertRaisesRegex(Denied,'Review changed'):self.resolve(c,signed=signed)
        self.assertEqual(self.resolve(deferred,signed=signed)['state'],'authorized')

    def test_wrong_owner_cannot_read_resolve_or_deliver_request(self):
        c=self.prepare()
        for operation in (lambda:self.flow.review('dana',c['request_id']),lambda:self.flow.resolve('dana',c['request_id'],c['review_digest'],'decline'),lambda:self.flow.delivery('dana',c['request_id'])):
            with self.assertRaises(Denied):operation()

    def test_mutating_card_or_envelope_does_not_change_pending_request(self):
        c=self.prepare();c['envelope']['payload']['candidate_indices']=[]
        c['decision']['target']['recipient']='dana';self.message['payload']['candidate_indices']=[]
        saved=self.flow.review('bob',c['request_id'])
        self.assertEqual(saved['decision']['target']['recipient'],'alice')
        self.assertNotEqual(saved['envelope']['payload']['candidate_indices'],[])

    def test_wrong_signature_or_changed_decision_cannot_authorize(self):
        c=self.prepare();bad=self.sign(c);bad['signature']='0'*128
        with self.assertRaises(Denied):self.resolve(c,signed=bad)
        bad=self.sign(c);bad['decision']['expires_at']+=1
        with self.assertRaises(Denied):self.resolve(c,signed=bad)
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'pending')

    def test_decline_and_approval_repeated_resolution_cannot_flip_outcome(self):
        for choice in ('decline','approve'):
            c=self.prepare();self.resolve(c,choice)
            with self.assertRaises(Denied):self.resolve(c,'defer')
            if choice=='approve':break

    def test_expired_card_cannot_authorize_or_renew_itself(self):
        c=self.prepare();self.now[0]=1300
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'expired')
        with self.assertRaises(Denied):self.resolve(c)
        fresh=self.prepare();self.assertNotEqual(fresh['request_id'],c['request_id'])
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'expired')

    def test_revoke_repair_requires_new_card_and_new_decision(self):
        c=self.prepare();self.control('bob','revoke','alice');self.control('bob','pair','alice')
        with self.assertRaises(Denied):self.resolve(c)
        current=self.flow.review('bob',c['request_id']);self.assertEqual(current['state'],'stale')
        with self.assertRaises(Denied):self.resolve(current)
        self.assertNotEqual(self.prepare()['request_id'],c['request_id'])

    def test_cancellation_after_display_invalidates_review(self):
        c=self.prepare();self.control('charlie','cancel')
        with self.assertRaises(Denied):self.resolve(c)
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'stale')

    def test_any_session_change_requires_fresh_review_token(self):
        c=self.prepare();other=self.flow.prepare('dana','revoke',peer='alice');self.submit(other)
        with self.assertRaisesRegex(Denied,'Review changed'):self.resolve(c)
        fresh=self.flow.review('bob',c['request_id']);self.assertEqual(fresh['state'],'pending')
        self.assertEqual(self.resolve(fresh)['state'],'authorized')

    def test_competing_scheduling_reservation_invalidates_pending_request(self):
        c=self.prepare();signed=self.a.delivery(self.message,self.gateway.contact_versions('bob','alice'),1000)
        self.box.enqueue(signed,self.message)
        with self.assertRaises(Denied):self.resolve(c)
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'stale')

    def test_crash_after_authorization_recovers_without_implicit_execution(self):
        c=self.prepare();self.resolve(c);self.store.close();self.open()
        recovered=self.flow.reconcile_request('bob',c['request_id']);self.assertEqual(recovered['state'],'authorized')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)
        self.flow.submit('bob',c['request_id'])
        self.assertEqual(self.flow.delivery('bob',c['request_id'])['state'],'queued')

    def test_crash_after_execution_recovers_status_without_second_enqueue(self):
        c=self.prepare();signed=self.sign(c);self.resolve(c,signed=signed)
        self.box.enqueue(signed,c['envelope']) # crash before request status record
        self.store.close();self.open()
        with patch.object(self.box,'enqueue',side_effect=AssertionError('must not execute')):
            self.assertEqual(self.flow.submit('bob',c['request_id'])['state'],'submitted')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],1)

    def test_failed_enqueue_keeps_exact_authorized_nonce(self):
        c=self.prepare();self.resolve(c)
        with patch.object(self.box,'enqueue',side_effect=RuntimeError('fault')):
            with self.assertRaises(RuntimeError):self.flow.submit('bob',c['request_id'])
        self.assertEqual(self.flow.reconcile_request('bob',c['request_id'])['state'],'authorized')
        self.assertEqual(self.flow.submit('bob',c['request_id'])['request_id'],c['request_id'])

    def test_resolution_transaction_failure_rolls_back_signature_and_state(self):
        c=self.prepare()
        self.store.db.execute("CREATE TRIGGER fail_resolution BEFORE UPDATE ON owner_requests BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.resolve(c)
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'pending')
        self.assertIsNone(self.store.db.execute('SELECT signed FROM owner_requests').fetchone()[0])

    def test_control_cards_explain_pairing_revoke_and_cancel_limits(self):
        for action in ('pair','revoke','cancel'):
            c=self.flow.prepare('bob',action,peer=None if action=='cancel' else 'alice')
            self.assertIn('Exact meeting:',c['review'])
            if action=='pair':self.assertIn('permits no message',c['review'])
            if action=='cancel':self.assertIn('No remote notification',c['review'])
            if action=='revoke':self.assertIn('cannot be recalled',c['review'])

    def test_status_inspection_does_not_send_or_reconcile(self):
        c=self.prepare();self.submit(c)
        with patch.object(self.box,'dispatch',side_effect=AssertionError()),patch.object(self.box,'reconcile',side_effect=AssertionError()):
            s=self.flow.delivery('bob',c['request_id']);self.assertIn('not dispatched',s['label'])
            self.assertFalse(s['calendar_booked'])
        self.assertEqual(s['attempts'],0)

    def test_uncertain_state_and_receipt_recovery_preserve_attempt_count(self):
        c=self.prepare();self.submit(c);receiver=self.receiver
        class LostAck:
            owner,registry=receiver.owner,receiver.registry
            def receipt(self,nonce):return receiver.receipt(nonce)
            def receive(self,packet):receiver.receive(packet);raise ConnectionError('lost')
        with self.assertRaises(ConnectionError):self.box.dispatch(c['request_id'],LostAck())
        self.assertIn('uncertain',self.flow.delivery('bob',c['request_id'])['label'])
        self.box.reconcile(c['request_id'],self.receiver)
        status=self.flow.delivery('bob',c['request_id']);self.assertEqual(status['state'],'received');self.assertEqual(status['attempts'],1)
        self.assertEqual(len(self.session.view().audit),0)

    def test_received_then_cancelled_never_says_not_sent(self):
        c=self.prepare();self.submit(c);self.box.dispatch(c['request_id'],self.receiver)
        self.control('charlie','cancel');self.box.process_received(c['request_id'])
        s=self.flow.delivery('bob',c['request_id']);self.assertEqual(s['label'],'Received; processing blocked')
        self.assertFalse(s['can_start_attempt']);self.assertFalse(s['can_process'])

    def test_request_limits_and_unknown_ids_fail_closed(self):
        self.store.max_records=1;self.prepare()
        with self.assertRaises(Denied):self.flow.prepare('dana','send',envelope=self.agents[3].preview_availability(self.meeting))
        for owner,nonce in [('nobody','a'*32),('bob',[]),('bob','z'*32),('bob','a'*32)]:
            with self.assertRaises(Denied):self.flow.review(owner,nonce)

    def test_unsigned_validator_does_not_create_signed_authority(self):
        c=self.prepare();decision,message=self.a.registry.validate_delivery(c['decision'],c['envelope'])
        with self.assertRaises(Denied):self.box.enqueue({'decision':decision,'signature':'0'*128},message)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)

    def test_approve_decline_race_has_only_one_persisted_outcome(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        c=self.prepare();signed=self.sign(c);barrier=threading.Barrier(2)
        def resolve(choice):
            store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
            session=PersistentSession(store,self.agents,self.meeting)
            gateway=SignedOwnerGateway(session,self.a.owner_roots)
            box=DurableEncryptedOutbox(gateway,self.a.registry,self.a.transport_keys)
            flow=OwnerWorkflow(gateway,box)
            try:
                barrier.wait()
                try:return flow.resolve('bob',c['request_id'],c['review_digest'],choice,signed if choice=='approve' else None)['stored_state']
                except Denied:return 'refused'
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(resolve,('approve','decline')))
        self.assertEqual(results.count('refused'),1)
        self.assertIn(self.flow.review('bob',c['request_id'])['stored_state'],('authorized','declined'))

    def test_read_only_reconciliation_failure_keeps_uncertain_attempts(self):
        c=self.prepare();self.submit(c)
        class Unavailable:
            owner='alice';registry=self.a.registry
            def receive(self,packet):raise ConnectionError('uncertain')
            def receipt(self,nonce):raise ConnectionError('query unavailable')
        with self.assertRaises(ConnectionError):self.box.dispatch(c['request_id'],Unavailable())
        with self.assertRaises(ConnectionError):self.box.reconcile(c['request_id'],Unavailable())
        status=self.flow.delivery('bob',c['request_id']);self.assertEqual(status['attempts'],1);self.assertEqual(status['state'],'dispatched')

    def test_guided_path_recovers_enqueue_commit_before_stale_display(self):
        c=self.prepare();signed=self.sign(c);self.resolve(c,signed=signed);self.box.enqueue(signed,c['envelope'])
        step=self.flow.next_step()
        self.assertEqual(step['kind'],'delivery');self.assertEqual(step['state'],'queued')
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'submitted')

    def test_cancelled_guide_still_exposes_existing_uncertain_receipt_checks(self):
        c=self.prepare();self.submit(c);receiver=self.receiver
        class LostAck:
            owner,registry=receiver.owner,receiver.registry
            def receipt(self,nonce):return receiver.receipt(nonce)
            def receive(self,packet):receiver.receive(packet);raise ConnectionError('lost')
        with self.assertRaises(ConnectionError):self.box.dispatch(c['request_id'],LostAck())
        self.control('charlie','cancel')
        step=self.flow.next_step();self.assertEqual(step['kind'],'delivery');self.assertTrue(step['cancelled'])
        self.assertFalse(step['can_start_attempt'])
        self.box.reconcile(c['request_id'],self.receiver)
        self.assertEqual(self.flow.next_step()['state'],'received')
        self.box.process_received(c['request_id'])
        self.assertEqual(self.flow.next_step()['kind'],'stopped')
        self.assertEqual(self.flow.delivery('bob',c['request_id'])['state'],'received_blocked')

    def test_dashboard_disables_attempt_if_consent_expired_or_cancelled(self):
        c=self.prepare();self.submit(c);self.now[0]=1300
        status=self.flow.delivery('bob',c['request_id'])
        self.assertFalse(status['can_start_attempt']);self.assertIn('expired',status['attempt_blocker'])
        self.assertEqual(status['attempts'],0)
