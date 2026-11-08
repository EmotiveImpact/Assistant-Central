import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from demo import fixture
from durable import LocalDelivery
from session import PersistentSession
from owner_auth import SignedOwnerGateway
from network import Denied, canonical, digest
from bound_identity import DELIVERY_DOMAIN, RECEIPT_DOMAIN, signed_bytes
from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver
from integrated_fixture import FixtureAuthorities
from vendor.a4a_sdk import crypto


class EncryptedDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.now = [1000]
        self.meeting, self.agents, _ = fixture()
        self.authorities = FixtureAuthorities(self.meeting, self.now[0])
        self.sender = LocalDelivery(self.directory / 'sender.sqlite3', clock=lambda: self.now[0])
        self.session = PersistentSession(self.sender, self.agents, self.meeting)
        self.gateway = SignedOwnerGateway(self.session, self.authorities.owner_roots)
        self.authorities.pair_all(self.gateway, self.now[0])
        self.box = DurableEncryptedOutbox(self.gateway, self.authorities.registry, self.authorities.transport_keys)
        self.receiver_stores, self.receivers = {}, {}
        for owner in self.meeting.participants:
            store = LocalDelivery(self.directory / (owner + '.sqlite3'), clock=lambda: self.now[0])
            self.receiver_stores[owner] = store
            self.receivers[owner] = OfflineReceiver(store, self.authorities.registry, owner, self.authorities.transport_keys[owner])
        self.message = self.agents[1].preview_availability(self.meeting)
        self.signed = self.sign(self.message)
        self.nonce = self.signed['decision']['nonce']

    def tearDown(self):
        self.sender.close()
        for store in self.receiver_stores.values(): store.close()
        self.tmp.cleanup()

    def sign(self, message):
        return self.authorities.delivery(message, self.gateway.contact_versions(message['sender'], message['recipient']), self.now[0])

    def queue(self):
        return self.box.enqueue(self.signed, self.message)

    def cancel(self):
        return self.gateway.apply(self.authorities.control('charlie', 'cancel', {'meeting': self.meeting.id}, self.now[0]))

    def reopen_sender(self, keys=None):
        self.sender.close()
        self.sender = LocalDelivery(self.directory / 'sender.sqlite3', clock=lambda: self.now[0])
        self.session = PersistentSession(self.sender, self.agents, self.meeting)
        self.gateway = SignedOwnerGateway(self.session, self.authorities.owner_roots)
        self.box = DurableEncryptedOutbox(self.gateway, self.authorities.registry, keys)

    def receiver_count(self, owner='alice'):
        return self.receiver_stores[owner].db.execute('SELECT COUNT(*) FROM encrypted_inbox').fetchone()[0]

    def lose_ack(self):
        receiver = self.receivers['alice']
        class DropAck:
            owner, registry = receiver.owner, receiver.registry
            def receipt(self, nonce): return receiver.receipt(nonce)
            def receive(self, packet):
                receiver.receive(packet)
                raise ConnectionError('synthetic lost acknowledgement after receiver commit')
        with self.assertRaises(ConnectionError): self.box.dispatch(self.nonce, DropAck())

    def test_queue_received_and_processed_are_distinct(self):
        self.assertEqual(self.queue()['state'], 'queued')
        self.assertEqual(self.receiver_count(), 0)
        self.assertEqual(self.session.view().audit, [])
        self.assertEqual(self.sender.owner_inbox('alice'), [])
        self.assertEqual(self.box.dispatch(self.nonce, self.receivers['alice'])['state'], 'received')
        self.assertEqual(self.receiver_count(), 1)
        self.assertEqual(self.sender.owner_inbox('alice')[0]['state'], 'received')
        self.assertEqual(self.session.view().audit, [])
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'processed')
        self.assertEqual(len(self.session.view().audit), 1)
        self.assertEqual(self.sender.owner_inbox('alice')[0]['state'], 'processed')

    def test_ciphertext_is_fixed_for_retry_and_contains_no_plain_message(self):
        self.queue(); first = self.box.packet(self.nonce)
        self.assertNotIn(canonical(self.message), first['wire']['content'])
        self.assertEqual(self.box.enqueue(self.signed, self.message)['state'], 'queued')
        self.assertEqual(first, self.box.packet(self.nonce))

    def test_application_storage_restart_does_not_require_resealing(self):
        self.queue(); packet = self.box.packet(self.nonce)
        self.reopen_sender()  # No sender private keys supplied to reopened queue.
        self.assertEqual(self.box.packet(self.nonce), packet)
        self.box.dispatch(self.nonce, self.receivers['alice'])
        self.box.process_received(self.nonce)
        self.reopen_sender()
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'processed')
        self.assertEqual(len(self.session.view().audit), 1)

    def test_lost_ack_reconciles_after_restart_without_resending(self):
        self.queue(); self.lose_ack()
        self.assertEqual(self.box.status(self.nonce)['state'], 'dispatched')
        self.assertEqual(self.receiver_count(), 1)
        self.reopen_sender(); self.now[0] = 1500  # Owner's send grant expired, but receipt predates expiry.
        status = self.box.dispatch(self.nonce, self.receivers['alice'])
        self.assertEqual(status['state'], 'received'); self.assertEqual(status['attempts'], 1)
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'processed')
        self.assertEqual(self.receiver_count(), 1)

    def test_receiver_storage_restart_preserves_exact_receipt(self):
        self.queue(); self.lose_ack()
        receipt = self.receivers['alice'].receipt(self.nonce)
        self.receiver_stores['alice'].close()
        store = LocalDelivery(self.directory / 'alice.sqlite3', clock=lambda: self.now[0])
        self.receiver_stores['alice'] = store
        self.receivers['alice'] = OfflineReceiver(store, self.authorities.registry, 'alice', self.authorities.transport_keys['alice'])
        self.assertEqual(self.receivers['alice'].receipt(self.nonce), receipt)
        self.assertEqual(self.box.reconcile(self.nonce, self.receivers['alice'])['state'], 'received')

    def test_cancellation_before_dispatch_sends_nothing(self):
        self.queue(); self.cancel()
        status = self.box.dispatch(self.nonce, self.receivers['alice'])
        self.assertEqual(status['state'], 'blocked'); self.assertEqual(status['attempts'], 0)
        self.assertEqual(self.receiver_count(), 0)

    def test_cancellation_after_received_stops_processing_but_preserves_receipt(self):
        self.queue(); self.box.dispatch(self.nonce, self.receivers['alice']); self.cancel()
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'received_blocked')
        self.assertEqual(self.receiver_count(), 1)
        self.assertEqual(self.session.view().audit, [])
        self.assertEqual(self.sender.owner_inbox('alice')[0]['state'], 'received')

    def test_cancellation_after_lost_ack_does_not_hide_actual_receipt(self):
        self.queue(); self.lose_ack(); self.cancel()
        self.assertEqual(self.box.dispatch(self.nonce, self.receivers['alice'])['state'], 'received')
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'received_blocked')
        self.assertEqual(self.box.status(self.nonce)['attempts'], 1)

    def test_cancellation_after_dispatch_commit_cannot_recall_inflight_attempt(self):
        self.queue(); receiver = self.receivers['alice']; cancel = self.cancel
        class CancelInGap:
            owner, registry = receiver.owner, receiver.registry
            def receipt(self, nonce): return receiver.receipt(nonce)
            def receive(self, packet):
                cancel()
                return receiver.receive(packet)
        self.assertEqual(self.box.dispatch(self.nonce, CancelInGap())['state'], 'received')
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'received_blocked')
        self.assertEqual(self.receiver_count(), 1)

    def test_unknown_outcome_remains_uncertain_after_expiry(self):
        self.queue(); receiver = self.receivers['alice']
        class FailBeforeReceive:
            owner, registry = receiver.owner, receiver.registry
            def receipt(self, nonce): return None
            def receive(self, packet): raise ConnectionError('synthetic uncertain boundary')
        with self.assertRaises(ConnectionError): self.box.dispatch(self.nonce, FailBeforeReceive())
        self.now[0] = 1400
        status = self.box.dispatch(self.nonce, FailBeforeReceive())
        self.assertEqual(status['state'], 'stopped_uncertain'); self.assertEqual(status['attempts'], 1)
        with self.assertRaises(Denied): self.box.enqueue(self.sign(self.message), self.message)

    def test_unreachable_reconciliation_does_not_trigger_another_send(self):
        self.queue(); self.lose_ack(); receiver = self.receivers['alice']
        class Unreachable:
            owner, registry = receiver.owner, receiver.registry
            def receipt(self, nonce): raise ConnectionError('receiver unavailable')
            def receive(self, packet): raise AssertionError('must not resend')
        with self.assertRaises(ConnectionError): self.box.dispatch(self.nonce, Unreachable())
        self.assertEqual(self.box.status(self.nonce)['attempts'], 1)

    def test_revoked_then_repaired_pair_does_not_revive_queued_send(self):
        self.queue()
        version = self.sender.contact_version('alice', 'bob', self.session.context)
        self.gateway.apply(self.authorities.control('alice', 'revoke', {'peer': 'bob', 'contact_version': version}, self.now[0]))
        self.gateway.apply(self.authorities.control('alice', 'pair', {'peer': 'bob', 'contact_version': version+1, 'ttl': 3600}, self.now[0]))
        self.assertEqual(self.box.dispatch(self.nonce, self.receivers['alice'])['state'], 'blocked')
        self.assertEqual(self.receiver_count(), 0)
        newer = self.sign(self.message)
        self.assertEqual(self.box.enqueue(newer, self.message)['state'], 'queued')

    def test_stale_scheduling_step_is_blocked_before_disclosure(self):
        self.queue()
        target = {'recipient': 'alice', 'envelope_digest': digest(self.message), 'pair_versions': self.gateway.contact_versions('bob','alice')}
        self.gateway.apply(self.authorities.control('bob', 'send', target, self.now[0]), self.message)
        status = self.box.dispatch(self.nonce, self.receivers['alice'])
        self.assertEqual(status['state'], 'blocked'); self.assertEqual(status['attempts'], 0)
        self.assertEqual(self.receiver_count(), 0)

    def test_missing_receiver_receipt_is_not_processed(self):
        self.queue()
        with self.assertRaises(Denied): self.box.process_received(self.nonce)
        self.assertEqual(self.box.reconcile(self.nonce, self.receivers['alice'])['state'], 'queued')
        self.assertEqual(self.receiver_count(), 0)

    def test_enqueue_log_failure_rolls_back_consumption_and_outbox(self):
        self.sender.db.execute("CREATE TRIGGER fail_log BEFORE INSERT ON owner_decisions BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.queue()
        self.assertEqual(self.sender.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0], 0)
        self.sender.db.execute('DROP TRIGGER fail_log'); self.queue()

    def test_receiver_commit_failure_keeps_uncertain_sender_until_retry(self):
        self.queue()
        db = self.receiver_stores['alice'].db
        db.execute("CREATE TRIGGER fail_receive BEFORE INSERT ON encrypted_inbox BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.box.dispatch(self.nonce, self.receivers['alice'])
        self.assertEqual(self.box.status(self.nonce)['state'], 'dispatched'); self.assertEqual(self.receiver_count(), 0)
        packet = self.box.packet(self.nonce)
        db.execute('DROP TRIGGER fail_receive')
        self.assertEqual(self.box.dispatch(self.nonce, self.receivers['alice'])['state'], 'received')
        self.assertEqual(self.box.packet(self.nonce), packet)
        self.assertEqual(self.box.status(self.nonce)['attempts'], 2)

    def test_sender_receipt_commit_failure_reconciles_without_redelivery(self):
        self.queue()
        self.sender.db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON deliveries BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.box.dispatch(self.nonce, self.receivers['alice'])
        self.assertEqual(self.receiver_count(), 1)
        self.assertEqual(self.box.status(self.nonce)['state'], 'dispatched')
        self.sender.db.execute('DROP TRIGGER fail_receipt')
        self.assertEqual(self.box.reconcile(self.nonce, self.receivers['alice'])['state'], 'received')
        self.assertEqual(self.box.status(self.nonce)['attempts'], 1)

    def test_processing_failure_rolls_back_transition_and_status(self):
        self.queue(); self.box.dispatch(self.nonce, self.receivers['alice'])
        self.sender.db.execute("CREATE TRIGGER fail_process BEFORE INSERT ON transitions BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.box.process_received(self.nonce)
        self.assertEqual(self.box.status(self.nonce)['state'], 'received')
        self.assertEqual(self.sender.owner_inbox('alice')[0]['state'], 'received')
        self.assertEqual(self.session.view().audit, [])
        self.sender.db.execute('DROP TRIGGER fail_process')
        self.assertEqual(self.box.process_received(self.nonce)['state'], 'processed')

    def test_forged_or_altered_receipt_is_rejected(self):
        self.queue(); self.lose_ack(); original = self.receivers['alice'].receipt(self.nonce)
        variants = []
        forged = copy.deepcopy(original); forged['signature'] = '0' * 128; variants.append(forged)
        for field, value in (('recipient','dana'),('wire_digest','0'*64),('delivery_id','1'*32),('domain','wrong')):
            altered = copy.deepcopy(original); altered['receipt'][field] = value; variants.append(altered)
        for receipt in variants:
            with self.subTest(receipt=receipt['receipt']['recipient']), self.assertRaises(Denied):
                self.box.record_receipt(self.nonce, receipt)
        self.assertEqual(self.sender.owner_inbox('alice'), [])

    def test_receiver_signed_future_receipt_is_rejected(self):
        self.queue(); self.lose_ack(); receipt = self.receivers['alice'].receipt(self.nonce)
        receipt['receipt']['received_at'] = self.now[0] + 10
        receipt['signature'] = crypto.sign(hashlib.sha256(signed_bytes(RECEIPT_DOMAIN,receipt['receipt'])).hexdigest(),
                                           self.authorities.transport_keys['alice'].privkey_hex)
        with self.assertRaises(Denied): self.box.record_receipt(self.nonce, receipt)

    def test_wrong_receiver_cannot_receive_or_reconcile(self):
        self.queue()
        with self.assertRaises(Denied): self.box.dispatch(self.nonce,self.receivers['dana'])
        with self.assertRaises(Denied): self.box.reconcile(self.nonce,self.receivers['dana'])
        with self.assertRaises(Denied): self.receivers['dana'].receive(self.box.packet(self.nonce))
        self.assertEqual(self.box.status(self.nonce)['attempts'],0)

    def test_identity_substitution_in_signed_decision_is_rejected(self):
        signed=copy.deepcopy(self.signed)
        signed['decision']['target']['recipient_binding']=self.authorities.registry.binding_digest('dana')
        signed['signature']=self.authorities.owner_keys['bob'].sign(signed_bytes(DELIVERY_DOMAIN,signed['decision'])).hex()
        with self.assertRaises(Denied): self.box.enqueue(signed,self.message)

    def test_receiver_rejects_resealed_ciphertext_under_same_delivery_id(self):
        self.queue();self.box.dispatch(self.nonce,self.receivers['alice'])
        packet=self.box.packet(self.nonce)
        packet['wire']=self.box.peers['bob'].seal(self.message,self.nonce,self.now[0]).model_dump()
        with self.assertRaises(Denied): self.receivers['alice'].receive(packet)
        self.assertEqual(self.receiver_count(),1)

    def test_duplicate_receiver_packet_after_expiry_only_returns_existing_receipt(self):
        self.queue();self.box.dispatch(self.nonce,self.receivers['alice'])
        receipt=self.receivers['alice'].receipt(self.nonce)
        self.now[0]=2000
        self.assertEqual(self.receivers['alice'].receive(self.box.packet(self.nonce)),receipt)
        self.assertEqual(self.receiver_count(),1)

    def test_new_pending_duplicate_scheduling_operation_is_rejected(self):
        self.queue()
        with self.assertRaises(Denied):self.box.enqueue(self.sign(self.message),self.message)
        self.assertEqual(self.sender.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],1)

    def test_expired_queued_decision_blocks_without_transmission(self):
        self.queue();self.now[0]=1400
        self.assertEqual(self.box.dispatch(self.nonce,self.receivers['alice'])['state'],'blocked')
        self.assertEqual(self.receiver_count(),0)

    def test_outbox_without_live_sender_key_cannot_create_new_ciphertext(self):
        self.reopen_sender()
        with self.assertRaises(Denied):self.queue()

    def test_record_bounds_fail_without_consuming_new_decision(self):
        self.sender.max_records=1
        with self.assertRaises(Denied):self.queue()
        self.assertEqual(self.sender.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)

    def test_full_meeting_through_encrypted_receipts(self):
        def deliver(message):
            signed=self.sign(message);nonce=signed['decision']['nonce']
            self.box.enqueue(signed,message)
            self.box.dispatch(nonce,self.receivers[message['recipient']])
            self.box.process_received(nonce)
        for agent in self.agents:deliver(agent.preview_availability(self.meeting))
        for agent in self.agents:
            deliver(self.session.view().preview_proposal(self.agents[0],agent.identity))
            deliver(self.session.view().preview_acceptance(agent))
        self.assertTrue(self.session.view().agreed)
        self.assertEqual(len(self.session.view().audit),12)
        self.assertEqual(sum(self.receiver_count(o) for o in self.receivers),12)

    def test_concurrent_queue_same_signed_decision_consumes_once(self):
        def queue(_):
            store=LocalDelivery(self.directory/'sender.sqlite3',clock=lambda:self.now[0])
            try:
                meeting,agents,_=fixture(); session=PersistentSession(store,agents,meeting)
                gateway=SignedOwnerGateway(session,self.authorities.owner_roots)
                box=DurableEncryptedOutbox(gateway,self.authorities.registry,self.authorities.transport_keys)
                return box.enqueue(self.signed,self.message)['state']
            finally:store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(set(pool.map(queue,range(8))),{'queued'})
        self.assertEqual(self.sender.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],1)

    def test_stale_dispatch_read_cannot_overwrite_processed_state(self):
        self.queue()
        original_row = self.box._row
        injected = [False]
        def stale_row(nonce):
            row = original_row(nonce)
            if not injected[0]:
                injected[0] = True
                self.box.dispatch(nonce, self.receivers['alice'])
                self.box.process_received(nonce)
            return row
        self.box._row = stale_row
        try: status = self.box.dispatch(self.nonce, self.receivers['alice'])
        finally: self.box._row = original_row
        self.assertEqual(status['state'], 'processed')
        self.assertEqual(self.box.status(self.nonce)['attempts'], 1)
        self.assertEqual(self.receiver_count(), 1)

    def test_late_receipt_failure_rolls_back_delivery_insert(self):
        self.queue(); self.lose_ack()
        self.sender.db.execute("CREATE TRIGGER abort_late_receipt BEFORE UPDATE ON encrypted_outbox BEGIN SELECT RAISE(ABORT,'late receipt failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.box.reconcile(self.nonce, self.receivers['alice'])
        self.assertEqual(self.sender.owner_inbox('alice'), [])
        self.assertEqual(self.box.status(self.nonce)['state'], 'dispatched')
        self.assertEqual(self.receiver_count(), 1)

    def test_late_processing_failure_rolls_back_all_prior_writes(self):
        self.queue(); self.box.dispatch(self.nonce, self.receivers['alice'])
        self.sender.db.execute("CREATE TRIGGER abort_late_processing BEFORE UPDATE ON encrypted_outbox BEGIN SELECT RAISE(ABORT,'late processing failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.box.process_received(self.nonce)
        self.assertEqual(self.session.view().audit, [])
        self.assertEqual(self.sender.owner_inbox('alice')[0]['state'], 'received')
        self.assertEqual(self.box.status(self.nonce)['state'], 'received')

    def test_stopped_uncertain_accepts_late_receipt_without_releasing_reservation(self):
        self.queue();receiver=self.receivers['alice']
        class UnconfirmedAttempt:
            owner,registry=receiver.owner,receiver.registry
            def receipt(self,nonce):return None
            def receive(self,packet):raise ConnectionError('synthetic in-flight outcome unknown')
        with self.assertRaises(ConnectionError):self.box.dispatch(self.nonce,UnconfirmedAttempt())
        self.cancel()
        self.assertEqual(self.box.dispatch(self.nonce,UnconfirmedAttempt())['state'],'stopped_uncertain')
        # The already-started attempt finally reaches the receiver. No new dispatch
        # happens after cancellation, and the receiver has no remote cancel channel.
        receiver.receive(self.box.packet(self.nonce))
        self.assertEqual(self.box.reconcile(self.nonce,receiver)['state'],'received')
        self.assertEqual(self.box.process_received(self.nonce)['state'],'received_blocked')
        self.assertEqual(self.box.status(self.nonce)['attempts'],1)

    def test_concurrent_processing_of_verified_receipt_applies_transition_once(self):
        self.queue();self.box.dispatch(self.nonce,self.receivers['alice'])
        def process(_):
            store=LocalDelivery(self.directory/'sender.sqlite3',clock=lambda:self.now[0])
            try:
                meeting,agents,_=fixture();session=PersistentSession(store,agents,meeting)
                gateway=SignedOwnerGateway(session,self.authorities.owner_roots)
                box=DurableEncryptedOutbox(gateway,self.authorities.registry)
                return box.process_received(self.nonce)['state']
            finally:store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(set(pool.map(process,range(8))),{'processed'})
        self.assertEqual(len(self.session.view().audit),1)

    def test_concurrent_dispatches_deduplicate_at_separate_receiver_store(self):
        self.queue()
        def dispatch(_):
            sender=LocalDelivery(self.directory/'sender.sqlite3',clock=lambda:self.now[0])
            receiver_store=LocalDelivery(self.directory/'alice.sqlite3',clock=lambda:self.now[0])
            try:
                meeting,agents,_=fixture();session=PersistentSession(sender,agents,meeting)
                gateway=SignedOwnerGateway(session,self.authorities.owner_roots)
                box=DurableEncryptedOutbox(gateway,self.authorities.registry)
                receiver=OfflineReceiver(receiver_store,self.authorities.registry,'alice',self.authorities.transport_keys['alice'])
                return box.dispatch(self.nonce,receiver)['state']
            finally:sender.close();receiver_store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(set(pool.map(dispatch,range(4))),{'received'})
        self.assertEqual(self.receiver_count(),1)
        self.assertEqual(len(self.sender.owner_inbox('alice')),1)
        self.box.process_received(self.nonce)
        self.assertEqual(len(self.session.view().audit),1)

    def test_receipt_reader_needs_no_private_key_and_cannot_retransmit(self):
        from encrypted_delivery import ReceiptReader
        self.queue()
        reader=ReceiptReader(self.receiver_stores['alice'],self.authorities.registry,'alice')
        self.assertFalse(hasattr(reader,'_private_key'))
        self.assertFalse(hasattr(reader,'receive'))
        with self.assertRaises(Denied):self.box.dispatch(self.nonce,reader)
        self.assertEqual(self.box.status(self.nonce)['attempts'],0)
        self.lose_ack()
        self.assertEqual(self.box.reconcile(self.nonce,reader)['state'],'received')
        self.assertEqual(self.box.process_received(self.nonce)['state'],'processed')
