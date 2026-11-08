import copy
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
import test_owner_workflow as fixture
from durable import LocalDelivery
from session import PersistentSession
from owner_auth import SignedOwnerGateway
from encrypted_delivery import DurableEncryptedOutbox
from owner_workflow import OwnerWorkflow
from network import Denied, digest


class PairingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.OwnerWorkflowTests();self.f.setUp()
        for name in ('flow','store','session','gateway','box','a','meeting','agents','now','path','message'):
            setattr(self,name,getattr(self.f,name))
        self.source=self.f.prepare()
    def tearDown(self):self.f.tearDown()
    def review(self):return self.flow.review('bob',self.source['request_id'])
    def expire(self):self.now[0]=4600;return self.review()
    def recover(self,card=None,direction='bob'):
        card=card or self.review()
        return self.flow.recover_pairing('bob',card['request_id'],card['review_digest'],direction)
    def count(self,table):return self.store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    def new_flow(self):
        store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
        session=PersistentSession(store,self.agents,self.meeting);gateway=SignedOwnerGateway(session,self.a.owner_roots)
        return store,OwnerWorkflow(gateway,DurableEncryptedOutbox(gateway,self.a.registry,self.a.transport_keys))

    def test_bilateral_recovery_needs_two_owners_then_fresh_send_review(self):
        original=copy.deepcopy(self.source['decision']);card=self.expire()
        self.assertEqual([d['owner'] for d in card['pairing_reviews']],['bob','alice'])
        one=self.recover(card);self.assertEqual(one['owner'],'bob');self.assertEqual(one['decision']['target']['peer'],'alice')
        self.assertEqual(one['pairing_sources'],[{'owner':'bob','request_id':card['request_id']}])
        with self.assertRaises(Denied):self.store._paired('bob','alice',self.session.context)
        self.f.resolve(one)
        with self.assertRaises(Denied):self.store._paired('bob','alice',self.session.context)
        self.flow.submit('bob',one['request_id'])
        self.assertEqual([d['owner'] for d in self.review()['pairing_reviews']],['alice'])
        two=self.recover(direction='alice');self.f.submit(two)
        self.assertEqual(self.review()['pairing_reviews'],[]);self.assertEqual(self.count('encrypted_outbox'),0)
        with self.assertRaises(Denied):self.f.resolve(self.review(),signed=self.f.sign(self.source))
        self.assertEqual(self.review()['decision'],original)
        current=self.review();fresh=self.flow.replace_review('bob',current['request_id'],current['review_digest'])
        self.assertEqual(fresh['envelope'],self.source['envelope']);self.assertNotEqual(fresh['decision']['target']['pair_versions'],original['target']['pair_versions'])
        with self.assertRaises(Denied):self.flow.submit('bob',fresh['request_id'])
        self.f.submit(fresh);self.assertEqual(self.box.status(fresh['request_id'])['attempts'],0)

    def test_one_revoked_direction_does_not_extend_active_opposite_grant(self):
        self.f.control('bob','revoke','alice')
        before=dict(self.store.db.execute("SELECT * FROM contacts WHERE owner='alice' AND peer='bob'").fetchone())
        self.assertEqual([d['owner'] for d in self.review()['pairing_reviews']],['bob'])
        with self.assertRaises(Denied):self.recover(direction='alice')
        self.f.submit(self.recover())
        after=dict(self.store.db.execute("SELECT * FROM contacts WHERE owner='alice' AND peer='bob'").fetchone())
        self.assertEqual(before,after);self.assertEqual(self.count('encrypted_outbox'),0)

    def test_existing_pending_deferred_declined_authorized_pair_is_not_duplicated(self):
        for state in ('pending','deferred','declined','authorized'):
            with self.subTest(state=state):
                other=fixture.OwnerWorkflowTests();other.setUp()
                try:
                    source=other.prepare();other.control('bob','revoke','alice')
                    pair=other.flow.prepare('bob','pair',peer='alice')
                    if state!='pending':other.resolve(pair,{'deferred':'defer','declined':'decline','authorized':'approve'}[state])
                    source=other.flow.review('bob',source['request_id']);before=len(other.flow.inbox('bob'))
                    result=other.flow.recover_pairing('bob',source['request_id'],source['review_digest'],'bob')
                    self.assertEqual(result['request_id'],pair['request_id']);self.assertEqual(result['stored_state'],state)
                    self.assertEqual(len(other.flow.inbox('bob')),before)
                finally:other.tearDown()

    def test_expired_pair_returned_not_implicitly_replaced(self):
        self.f.control('bob','revoke','alice');pair=self.flow.prepare('bob','pair',peer='alice',ttl=10)
        self.now[0]+=11;result=self.recover()
        self.assertEqual(result['request_id'],pair['request_id']);self.assertEqual(result['state'],'expired')
        fresh=self.flow.replace_review('bob',result['request_id'],result['review_digest'])
        self.assertEqual(fresh['pairing_sources'],[{'owner':'bob','request_id':self.source['request_id']}])
        self.assertEqual(self.recover()['request_id'],fresh['request_id'])

    def test_declined_pair_stays_visible_even_after_contact_version_changes(self):
        pair=self.flow.prepare('bob','pair',peer='alice');self.f.resolve(pair,'decline')
        self.f.control('bob','revoke','alice');result=self.recover()
        self.assertEqual(result['state'],'declined');self.assertEqual(result['request_id'],pair['request_id'])

    def test_submitted_grant_does_not_hide_older_unsuperseded_review(self):
        for choice in ('defer','decline'):
            with self.subTest(choice=choice):
                other=fixture.OwnerWorkflowTests();other.setUp()
                try:
                    source=other.prepare();old=other.flow.prepare('bob','pair',peer='alice',ttl=10)
                    other.resolve(old,choice);other.now[0]+=11
                    newer=other.flow.prepare('bob','pair',peer='alice');other.submit(newer)
                    other.control('bob','revoke','alice')
                    source=other.flow.review('bob',source['request_id'])
                    pair=other.flow.recover_pairing('bob',source['request_id'],source['review_digest'],'bob')
                    self.assertEqual(pair['request_id'],old['request_id'])
                    self.assertEqual(pair['stored_state'],'deferred' if choice=='defer' else 'declined')
                finally:other.tearDown()

    def test_exact_retry_returns_historical_pair_after_replacement(self):
        source=self.expire();pair=self.recover(source);self.now[0]+=301
        current=self.flow.review('bob',pair['request_id']);fresh=self.flow.replace_review('bob',pair['request_id'],current['review_digest'])
        retry=self.recover(source)
        self.assertEqual(retry['request_id'],pair['request_id']);self.assertEqual(retry['state'],'superseded')
        self.assertEqual(retry['replaced_by'],fresh['request_id'])

    def test_retry_after_decline_submission_expiry_or_source_decline_never_creates(self):
        source=self.expire();pair=self.recover(source);self.f.resolve(pair,'decline')
        self.f.resolve(self.review(),'decline');self.now[0]+=301
        before=self.count('owner_requests');result=self.recover(source)
        self.assertEqual(result['request_id'],pair['request_id']);self.assertEqual(result['state'],'declined')
        self.assertEqual(self.count('owner_requests'),before)

    def test_new_revocation_allows_new_review_after_previously_submitted_grant(self):
        source=self.expire();pair=self.recover(source);self.f.submit(pair)
        self.f.control('bob','revoke','alice')
        self.assertEqual(self.recover(source)['request_id'],pair['request_id'])
        fresh=self.recover();self.assertNotEqual(fresh['request_id'],pair['request_id'])
        self.assertEqual(fresh['state'],'pending')

    def test_active_pairing_and_unrelated_direction_refused(self):
        with self.assertRaises(Denied):self.recover()
        source=self.expire()
        for owner in ('charlie','dana','nobody',None,[]):
            with self.assertRaises(Denied):self.recover(source,owner)
        self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_terminal_and_authorized_sources_cannot_initiate(self):
        self.f.resolve(self.source);self.now[0]=4600
        self.assertEqual(self.review()['pairing_reviews'],[])
        with self.assertRaises(Denied):self.recover()
        self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_submitted_uncertain_source_cannot_initiate(self):
        self.f.submit(self.source)
        class Lost:
            owner='alice';registry=self.a.registry
            def receipt(self,nonce):return None
            def receive(self,packet):raise ConnectionError('uncertain')
        with self.assertRaises(ConnectionError):self.box.dispatch(self.source['request_id'],Lost())
        self.now[0]=4600
        with self.assertRaises(Denied):self.recover()
        self.assertEqual(self.box.status(self.source['request_id'])['attempts'],1)

    def test_cancelled_or_expired_identity_suppresses_recovery(self):
        self.expire();self.f.control('charlie','cancel')
        self.assertEqual(self.review()['pairing_reviews'],[])
        with self.assertRaises(Denied):self.recover()

    def test_expired_identity_and_competing_delivery_fail_closed(self):
        self.now[0]=87400
        self.assertEqual(self.review()['pairing_reviews'],[])
        with self.assertRaises(Denied):self.recover()
        self.now[0]=1000
        signed=self.a.delivery(self.message,self.gateway.contact_versions('bob','alice'),1000)
        self.box.enqueue(signed,self.message);self.now[0]=4600
        self.assertEqual(self.review()['pairing_reviews'],[])
        with self.assertRaises(Denied):self.recover()

    def test_original_ledger_or_outbox_nonce_blocks_recovery_even_if_pending(self):
        signed=self.f.sign(self.source);self.box.enqueue(signed,self.source['envelope']);self.now[0]=4600
        with self.assertRaises(Denied):self.recover()
        self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_wrong_owner_stale_token_and_invalid_fields_refused(self):
        source=self.expire()
        with self.assertRaises(Denied):self.flow.recover_pairing('alice',source['request_id'],source['review_digest'],'bob')
        for token in (None,[],True,'0'*64):
            with self.assertRaises(Denied):self.flow.recover_pairing('bob',source['request_id'],token,'bob')
        self.recover(source)
        with self.assertRaises(Denied):self.recover(source,'alice')

    def test_preparation_failure_rolls_back_draft_link_and_revision(self):
        for target,operation in (('owner_pairing_reviews','INSERT'),('owner_requests','UPDATE')):
            source=self.expire();before=self.count('owner_requests')
            self.store.db.execute(f"CREATE TRIGGER fail_recovery BEFORE {operation} ON {target} BEGIN SELECT RAISE(ABORT,'fault'); END")
            with self.assertRaises(sqlite3.IntegrityError):self.recover(source)
            self.assertEqual(self.count('owner_requests'),before);self.assertEqual(self.count('owner_pairing_reviews'),0)
            self.assertEqual(self.review()['review_digest'],source['review_digest'])
            self.store.db.execute('DROP TRIGGER fail_recovery')

    def test_limits_fail_without_deleting_any_history(self):
        source=self.expire();self.store.max_records=1
        with self.assertRaises(Denied):self.recover(source)
        self.assertEqual(self.count('owner_requests'),1);self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_concurrent_same_source_converges_on_exact_one_pair(self):
        source=self.expire();barrier=threading.Barrier(2)
        def recover(_):
            store,flow=self.new_flow()
            try:
                barrier.wait();return flow.recover_pairing('bob',source['request_id'],source['review_digest'],'bob')['request_id']
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(recover,range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.count('owner_pairing_reviews'),1)
        self.assertEqual(self.count('owner_requests'),2)

    def test_concurrent_different_sources_share_one_direction_review(self):
        self.now[0]=1301;second=self.f.prepare();self.now[0]=4600
        sources=[self.review(),self.flow.review('bob',second['request_id'])];barrier=threading.Barrier(2)
        def recover(card):
            store,flow=self.new_flow()
            try:
                barrier.wait();return flow.recover_pairing('bob',card['request_id'],card['review_digest'],'bob')['request_id']
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(recover,sources))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.count('owner_requests'),3)
        self.assertEqual(self.count('owner_pairing_reviews'),2)
        self.assertEqual(len(self.flow.review('bob',results[0])['pairing_sources']),2)

    def test_recovery_vs_cancellation_never_restores_or_sends(self):
        source=self.expire();cancel=self.flow.prepare('charlie','cancel');signed=self.f.sign(cancel)
        barrier=threading.Barrier(2)
        def action(which):
            store,flow=self.new_flow()
            try:
                barrier.wait()
                if which=='cancel':flow.gateway.apply(signed);return 'cancelled'
                try:flow.recover_pairing('bob',source['request_id'],source['review_digest'],'bob');return 'prepared'
                except Denied:return 'refused'
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(action,('recover','cancel')))
        self.assertIn('cancelled',results);self.assertEqual(self.count('encrypted_outbox'),0)
        self.assertEqual(self.review()['pairing_reviews'],[])
        with self.assertRaises(Denied):self.store._paired('bob','alice',self.session.context)

    def test_superseded_source_cannot_request_new_pairing(self):
        self.now[0]=1301;old=self.review();fresh=self.flow.replace_review('bob',old['request_id'],old['review_digest'])
        self.now[0]=4600
        self.assertEqual(self.review()['state'],'superseded')
        with self.assertRaises(Denied):self.recover()
        self.assertEqual(len(self.flow.review('bob',fresh['request_id'])['pairing_reviews']),2)

    def test_coordinator_self_pairing_has_one_direction_not_duplicate(self):
        message=self.agents[0].preview_availability(self.meeting);source=self.flow.prepare('alice','send',envelope=message)
        self.now[0]=4600;source=self.flow.review('alice',source['request_id'])
        self.assertEqual(len(source['pairing_reviews']),1)
        pair=self.flow.recover_pairing('alice',source['request_id'],source['review_digest'],'alice')
        self.assertEqual(pair['decision']['target']['peer'],'alice');self.f.submit(pair)
        self.assertEqual(self.flow.review('alice',source['request_id'])['pairing_reviews'],[])

    def test_recovery_versus_decline_has_only_one_mutation_with_original_token(self):
        source=self.expire();barrier=threading.Barrier(2)
        def action(which):
            store,flow=self.new_flow()
            try:
                barrier.wait()
                try:
                    if which=='recover':flow.recover_pairing('bob',source['request_id'],source['review_digest'],'bob')
                    else:flow.resolve('bob',source['request_id'],source['review_digest'],'decline')
                    return which
                except Denied:return 'refused'
            finally:store.close()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(action,('recover','decline')))
        self.assertEqual(results.count('refused'),1)
        if 'decline' in results:self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_read_only_review_and_guide_never_create_recovery(self):
        self.expire();before=self.count('owner_requests')
        for _ in range(3):self.review();self.flow.inbox('bob');self.flow.next_step()
        self.assertEqual(self.count('owner_requests'),before);self.assertEqual(self.count('owner_pairing_reviews'),0)

    def test_reopen_and_additive_schema_preserve_exact_link(self):
        source=self.expire();pair=self.recover(source)
        self.store.close();self.f.open();self.store,self.flow=self.f.store,self.f.flow
        self.assertEqual(self.recover(source)['request_id'],pair['request_id'])
        self.assertEqual(self.review()['decision'],source['decision'])
