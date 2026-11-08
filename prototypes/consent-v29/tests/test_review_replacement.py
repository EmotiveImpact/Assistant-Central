import copy
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
import test_owner_workflow as workflow_fixture
from durable import LocalDelivery
from session import PersistentSession
from owner_auth import SignedOwnerGateway
from encrypted_delivery import DurableEncryptedOutbox
from owner_workflow import OwnerWorkflow
from network import Denied


class ReviewReplacementTests(unittest.TestCase):
    def setUp(self):
        self.fixture=workflow_fixture.OwnerWorkflowTests();self.fixture.setUp()
        for name in ('flow','store','session','gateway','box','a','meeting','agents','message','now','path'):
            setattr(self,name,getattr(self.fixture,name))
    def tearDown(self):self.fixture.tearDown()
    def draft(self):return self.fixture.prepare()
    def expired(self):
        c=self.draft();self.now[0]=c['decision']['expires_at'];return self.flow.review('bob',c['request_id'])
    def replace(self,c):return self.flow.replace_review(c['owner'],c['request_id'],c['review_digest'])
    def count(self,table):return self.store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def test_expired_draft_can_explicitly_be_replaced_without_approval(self):
        old=self.expired();fresh=self.replace(old)
        self.assertNotEqual(old['request_id'],fresh['request_id']);self.assertEqual(fresh['state'],'pending')
        self.assertEqual(fresh['replaces'],old['request_id']);self.assertEqual(fresh['envelope'],old['envelope'])
        self.assertEqual(fresh['decision']['expires_at']-fresh['decision']['issued_at'],300)
        self.assertEqual(self.count('encrypted_outbox'),0)
        self.assertIsNone(self.store.db.execute('SELECT signed FROM owner_requests WHERE nonce=?',(fresh['request_id'],)).fetchone()[0])
        self.assertEqual(self.flow.next_step()['card']['request_id'],fresh['request_id'])

    def test_original_history_is_preserved_and_superseded(self):
        old=self.expired();saved=copy.deepcopy(old['decision']);fresh=self.replace(old)
        history=self.flow.review('bob',old['request_id'])
        self.assertEqual(history['decision'],saved);self.assertEqual(history['state'],'superseded')
        self.assertEqual(history['replaced_by'],fresh['request_id']);self.assertFalse(history['can_replace'])
        self.assertNotEqual(history['review_digest'],old['review_digest'])
        self.assertEqual(self.count('owner_requests'),2)

    def test_old_signature_and_fresh_ancestor_digest_cannot_revive_old_request(self):
        old=self.expired();signed=self.fixture.sign(old);self.replace(old)
        current=self.flow.review('bob',old['request_id'])
        for token in (old,current):
            for choice in ('approve','decline','defer'):
                with self.assertRaises(Denied):self.flow.resolve('bob',token['request_id'],token['review_digest'],choice,signed if choice=='approve' else None)
        with self.assertRaises(Denied):self.flow.submit('bob',old['request_id'])

    def test_same_token_retry_returns_same_successor_even_after_decline(self):
        old=self.expired();fresh=self.replace(old);again=self.replace(old)
        self.assertEqual(fresh['request_id'],again['request_id'])
        self.fixture.resolve(fresh,'decline')
        self.assertEqual(self.replace(old)['state'],'declined')
        self.assertEqual(self.count('owner_requests'),2);self.assertEqual(self.count('owner_request_replacements'),1)

    def test_retry_after_successor_expiry_never_renews_again_implicitly(self):
        old=self.expired();fresh=self.replace(old);self.now[0]+=301
        again=self.replace(old);self.assertEqual(again['request_id'],fresh['request_id']);self.assertEqual(again['state'],'expired')
        self.assertEqual(self.count('owner_requests'),2)
        newest=self.replace(again);self.assertNotEqual(newest['request_id'],fresh['request_id'])
        self.assertEqual(self.flow.next_step()['card']['request_id'],newest['request_id'])

    def test_unexpired_pending_or_deferred_cannot_be_replaced(self):
        c=self.draft()
        with self.assertRaises(Denied):self.replace(c)
        deferred=self.fixture.resolve(c,'defer')
        with self.assertRaises(Denied):self.replace(deferred)
        self.now[0]+=301;self.assertEqual(self.replace(self.flow.review('bob',c['request_id']))['state'],'pending')

    def test_declined_and_authorized_reviews_are_not_replaceable(self):
        c=self.draft();self.fixture.resolve(c,'decline');self.now[0]+=301
        with self.assertRaises(Denied):self.replace(self.flow.review('bob',c['request_id']))
        fresh=self.draft();self.fixture.resolve(fresh);self.now[0]+=301
        with self.assertRaises(Denied):self.replace(self.flow.review('bob',fresh['request_id']))
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_submitted_and_uncertain_delivery_cannot_be_replaced(self):
        c=self.draft();self.fixture.submit(c)
        class Unavailable:
            owner='alice';registry=self.a.registry
            def receipt(self,nonce):return None
            def receive(self,packet):raise ConnectionError('uncertain')
        with self.assertRaises(ConnectionError):self.box.dispatch(c['request_id'],Unavailable())
        self.now[0]+=301
        with self.assertRaises(Denied):self.replace(self.flow.review('bob',c['request_id']))
        self.assertEqual(self.box.status(c['request_id'])['attempts'],1)

    def test_stale_contact_versions_refresh_but_body_and_identity_do_not(self):
        old=self.draft();self.fixture.control('bob','revoke','alice');self.fixture.control('bob','pair','alice')
        old=self.flow.review('bob',old['request_id']);self.assertEqual(old['state'],'stale')
        fresh=self.replace(old)
        self.assertEqual(fresh['envelope'],old['envelope']);self.assertNotEqual(fresh['decision']['target']['pair_versions'],old['decision']['target']['pair_versions'])
        for key in ('sender_binding','recipient_binding','recipient','envelope_digest'):
            self.assertEqual(fresh['decision']['target'][key],old['decision']['target'][key])

    def test_missing_or_expired_pairing_remains_blocker_not_renewed_permission(self):
        old=self.draft();self.now[0]=4600
        current=self.flow.review('bob',old['request_id']);self.assertFalse(current['can_replace'])
        self.assertIn('Both owners',current['replacement_blocker'])
        with self.assertRaises(Denied):self.replace(current)
        self.assertEqual(self.count('owner_requests'),1)

    def test_cancellation_is_not_bypassed(self):
        old=self.expired();self.fixture.control('charlie','cancel')
        current=self.flow.review('bob',old['request_id']);self.assertFalse(current['can_replace'])
        with self.assertRaises(Denied):self.replace(current)
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_competing_live_delivery_blocks_replacement(self):
        old=self.expired()
        message=old['envelope'];signed=self.a.delivery(message,self.gateway.contact_versions('bob','alice'),self.now[0])
        self.box.enqueue(signed,message)
        current=self.flow.review('bob',old['request_id']);self.assertFalse(current['can_replace'])
        with self.assertRaises(Denied):self.replace(current)
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_wrong_owner_or_stale_review_token_is_refused(self):
        old=self.expired()
        with self.assertRaises(Denied):self.flow.replace_review('dana',old['request_id'],old['review_digest'])
        with self.assertRaises(Denied):self.flow.replace_review('bob',old['request_id'],'0'*64)
        self.fixture.control('dana','revoke','alice')
        with self.assertRaises(Denied):self.replace(old)
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_replacement_link_insert_fault_rolls_back_fresh_draft(self):
        old=self.expired()
        self.store.db.execute("CREATE TRIGGER fail_link BEFORE INSERT ON owner_request_replacements BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.replace(old)
        self.assertEqual(self.count('owner_requests'),1);self.assertEqual(self.count('owner_request_replacements'),0)
        self.assertEqual(self.flow.review('bob',old['request_id'])['review_digest'],old['review_digest'])

    def test_ancestor_revision_fault_rolls_back_link_and_successor(self):
        old=self.expired()
        self.store.db.execute("CREATE TRIGGER fail_revision BEFORE UPDATE ON owner_requests BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.replace(old)
        self.assertEqual(self.count('owner_requests'),1);self.assertEqual(self.count('owner_request_replacements'),0)

    def test_concurrent_replacements_converge_to_one_new_nonce(self):
        old=self.expired();barrier=threading.Barrier(2)
        def replace(_):
            store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
            session=PersistentSession(store,self.agents,self.meeting);gateway=SignedOwnerGateway(session,self.a.owner_roots)
            flow=OwnerWorkflow(gateway,DurableEncryptedOutbox(gateway,self.a.registry,self.a.transport_keys))
            try:barrier.wait();return flow.replace_review('bob',old['request_id'],old['review_digest'])['request_id']
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(replace,range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.count('owner_requests'),2)

    def test_reopen_preserves_replacement_and_consumed_history(self):
        old=self.expired();fresh=self.replace(old)
        self.store.close();self.fixture.open()
        self.store,self.flow=self.fixture.store,self.fixture.flow
        self.assertEqual(self.replace(old)['request_id'],fresh['request_id'])
        self.assertEqual(self.flow.next_step()['card']['request_id'],fresh['request_id'])

    def test_pair_request_duration_and_peer_are_preserved(self):
        c=self.flow.prepare('bob','pair',peer='alice',pair_ttl=120,ttl=20);self.now[0]+=21
        fresh=self.replace(self.flow.review('bob',c['request_id']))
        self.assertEqual(fresh['decision']['target']['ttl'],120)
        self.assertEqual(fresh['decision']['target']['peer'],'alice')
        self.assertEqual(fresh['decision']['expires_at']-fresh['decision']['issued_at'],20)

    def test_record_limit_does_not_delete_original_or_create_link(self):
        old=self.expired();self.store.max_records=1
        with self.assertRaises(Denied):self.replace(old)
        self.assertEqual(self.count('owner_requests'),1);self.assertEqual(self.count('owner_request_replacements'),0)

    def test_fresh_replacement_still_needs_separate_signature_submission_dispatch(self):
        old=self.expired();fresh=self.replace(old)
        with self.assertRaises(Denied):self.flow.submit('bob',fresh['request_id'])
        self.fixture.resolve(fresh);self.assertEqual(self.count('encrypted_outbox'),0)
        self.flow.submit('bob',fresh['request_id']);self.assertEqual(self.box.status(fresh['request_id'])['attempts'],0)

    def test_noop_review_and_guide_do_not_replace_expired_drafts(self):
        old=self.expired()
        for _ in range(3):
            current=self.flow.next_step()['card'];self.assertEqual(current['request_id'],old['request_id']);self.assertTrue(current['can_replace'])
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_expired_transport_identity_cannot_be_renewed_by_replacement(self):
        old=self.draft();self.now[0]=87400
        self.a.pair_all(self.gateway,self.now[0])
        current=self.flow.review('bob',old['request_id'])
        self.assertFalse(current['can_replace']);self.assertIn('identity binding',current['replacement_blocker'])
        with self.assertRaises(Denied):self.replace(current)
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_replacement_and_decline_race_has_one_terminal_winner(self):
        old=self.expired();barrier=threading.Barrier(2)
        def run(action):
            store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
            session=PersistentSession(store,self.agents,self.meeting);gateway=SignedOwnerGateway(session,self.a.owner_roots)
            flow=OwnerWorkflow(gateway,DurableEncryptedOutbox(gateway,self.a.registry,self.a.transport_keys))
            try:
                barrier.wait()
                try:
                    if action=='replace':flow.replace_review('bob',old['request_id'],old['review_digest'])
                    else:flow.resolve('bob',old['request_id'],old['review_digest'],'decline')
                    return action
                except Denied:return 'refused'
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,('replace','decline')))
        self.assertEqual(results.count('refused'),1)
        self.assertIn(self.flow.review('bob',old['request_id'])['state'],('declined','superseded'))

    def test_retry_after_successor_submitted_returns_history_without_execution(self):
        from unittest.mock import patch
        old=self.expired();fresh=self.replace(old);self.fixture.resolve(fresh);self.flow.submit('bob',fresh['request_id'])
        with patch.object(self.box,'enqueue',side_effect=AssertionError('no repeated execution')):
            again=self.replace(old)
        self.assertEqual(again['state'],'submitted');self.assertEqual(again['request_id'],fresh['request_id'])
        self.assertEqual(self.count('encrypted_outbox'),1);self.assertEqual(self.box.status(fresh['request_id'])['attempts'],0)

    def test_additive_schema_preserves_existing_unsigned_request(self):
        old=self.draft();self.store.db.execute('DROP TABLE owner_request_replacements')
        self.store.close();self.fixture.open();self.store,self.flow=self.fixture.store,self.fixture.flow
        current=self.flow.review('bob',old['request_id'])
        self.assertEqual(current['decision'],old['decision']);self.assertEqual(current['state'],'pending')
        self.assertEqual(self.count('owner_request_replacements'),0)

    def test_existing_decision_ledger_nonce_cannot_be_replaced(self):
        old=self.draft()
        self.gateway.apply(self.a.control('bob','revoke',{'peer':'alice','contact_version':self.store.contact_version('bob','alice',self.session.context)},self.now[0],nonce=old['request_id']))
        self.fixture.control('bob','pair','alice');self.now[0]+=301
        current=self.flow.review('bob',old['request_id'])
        with self.assertRaisesRegex(Denied,'committed or uncertain'):self.replace(current)
        self.assertEqual(self.count('owner_request_replacements'),0)
