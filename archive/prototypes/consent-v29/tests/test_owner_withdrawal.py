"""Offline withdrawal security, transaction, replay and explicit-successor regressions."""
import copy
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch
import test_owner_workflow as workflow_fixture
from owner_withdrawal import DOMAIN, validate_withdrawal, withdrawal_bytes
from network import Denied, canonical, digest


class WithdrawalTests(unittest.TestCase):
    setUp=workflow_fixture.OwnerWorkflowTests.setUp
    tearDown=workflow_fixture.OwnerWorkflowTests.tearDown
    open=workflow_fixture.OwnerWorkflowTests.open
    prepare=workflow_fixture.OwnerWorkflowTests.prepare
    sign=workflow_fixture.OwnerWorkflowTests.sign
    resolve=workflow_fixture.OwnerWorkflowTests.resolve

    def authorized(self, action='send'):
        c=self.prepare() if action=='send' else self.flow.prepare('bob',action,peer='alice' if action in ('pair','revoke') else None)
        return self.resolve(c)

    def challenge(self,c):
        return self.flow.prepare_withdrawal(c['owner'],c['request_id'],c['review_digest'])

    def signed_withdrawal(self,challenge):
        b=copy.deepcopy(challenge['withdrawal'])
        return {'withdrawal':b,'signature':self.a.owner_keys[b['owner']].sign(withdrawal_bytes(b)).hex()}

    def withdraw(self,c):
        return self.flow.withdraw(self.signed_withdrawal(self.challenge(c)))

    def test_expired_unused_and_clock_rollback_reopen(self):
        c=self.authorized();signed=self.sign(c);self.now[0]=1301
        c=self.flow.review('bob',c['request_id']);self.assertEqual(c['state'],'expired');self.assertTrue(c['can_withdraw'])
        token=self.signed_withdrawal(self.challenge(c));w=self.flow.withdraw(token)
        self.assertEqual(w['state'],'withdrawn');self.assertEqual(w['stored_state'],'authorized')
        self.assertEqual(json.loads(self.flow._row('bob',c['request_id'])['signed']),signed)
        self.now[0]=2000;self.assertEqual(self.flow.withdraw(token)['state'],'withdrawn')
        self.assertTrue(self.challenge(c)['already_withdrawn'])
        self.store.close();self.open();self.now[0]=1000
        with self.assertRaisesRegex(Denied,'withdrawn'):self.box.enqueue(signed,c['envelope'])
        with self.assertRaisesRegex(Denied,'withdrawn'):self.flow.submit('bob',c['request_id'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0],0)

    def test_control_fence_valid_withdrawal_and_distinct_fresh_review(self):
        for action in ('pair','revoke','cancel'):
            c=self.authorized(action);signed=self.sign(c);w=self.withdraw(c)
            with self.assertRaisesRegex(Denied,'withdrawn'):self.gateway.apply(signed)
            self.assertTrue(w['can_prepare_fresh'])
            f=self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest'])
            self.assertEqual(f['state'],'pending');self.assertNotEqual(f['request_id'],c['request_id'])
            self.assertEqual(f['withdrawn_source'],c['request_id']);self.assertIsNone(self.flow._row('bob',f['request_id'])['signed'])
            source=self.flow.review('bob',c['request_id']);self.assertEqual(source['state'],'withdrawn')
            self.assertEqual(source['withdrawn_successor'],f['request_id'])
            self.resolve(f,'decline');self.now[0]+=601
            self.assertEqual(self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest'])['state'],'declined')
            with self.assertRaises(Denied):self.flow.prepare_after_withdrawal('bob',c['request_id'],source['review_digest'])

    def test_stale_contact_and_separate_fresh_permission_gate(self):
        c=self.authorized();self.store.owner_revoke('bob','alice',self.session.context)
        c=self.flow.review('bob',c['request_id']);self.assertEqual(c['state'],'stale')
        w=self.withdraw(c);self.assertFalse(w['can_prepare_fresh']);self.assertTrue(w['fresh_review_blocker'])
        with self.assertRaises(Denied):self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM owner_withdrawal_successors').fetchone()[0],0)
        with self.assertRaises(Denied):self.flow.replace_review('bob',c['request_id'],w['review_digest'])
        with self.assertRaises(Denied):self.flow.recover_pairing('bob',c['request_id'],w['review_digest'],'bob')

    def test_all_execution_evidence_blocks_even_zero_attempt_outbox(self):
        inserts=[('owner_decisions',lambda n:self.store.db.execute('INSERT INTO owner_decisions VALUES (?,?,?)',(n,'x','{}'))),
                 ('approvals',lambda n:self.store.db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,0)',(n,'bob','alice',self.session.context,'x',2000))),
                 ('deliveries',lambda n:self.store.db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,'received')",(n,'bob','alice',self.session.context,'{}'))),
                 ('transitions',lambda n:self.store.db.execute('INSERT INTO transitions(session_id,delivery_id,body) VALUES (?,?,?)',(self.meeting.id,n,'{}')))]
        for table,insert in inserts:
            c=self.authorized();token=self.signed_withdrawal(self.challenge(c));insert(c['request_id'])
            with self.assertRaisesRegex(Denied,'evidence'):self.challenge(c)
            with self.assertRaisesRegex(Denied,'evidence'):self.flow.withdraw(token)
            self.store.db.execute('DELETE FROM '+table+' WHERE '+('delivery_id' if table=='transitions' else 'nonce' if table=='owner_decisions' else 'id')+'=?',(c['request_id'],))
        c=self.authorized();token=self.signed_withdrawal(self.challenge(c));self.box.enqueue(self.sign(c),c['envelope'])
        self.store.db.execute('DELETE FROM owner_decisions WHERE nonce=?',(c['request_id'],))
        for state in ('queued','blocked'):
            self.store.db.execute('UPDATE encrypted_outbox SET state=? WHERE nonce=?',(state,c['request_id']))
            with self.assertRaisesRegex(Denied,'evidence'):self.flow.withdraw(token)

    def test_wrong_scope_fields_signature_and_changed_retry(self):
        c=self.authorized();ch=self.challenge(c);s=self.signed_withdrawal(ch)
        for field,value in [('owner','dana'),('context','a'*64),('nonce',c['request_id'])]:
            bad=copy.deepcopy(ch);bad['withdrawal'][field]=value
            with self.assertRaises(Denied):self.flow.withdraw(self.signed_withdrawal(bad))
        for field in ('fingerprint','review_digest'):
            bad=copy.deepcopy(ch);bad['withdrawal']['target'][field]='a'*64
            with self.assertRaises(Denied):self.flow.withdraw(self.signed_withdrawal(bad))
        bad=copy.deepcopy(s);bad['signature']='0'*128
        with self.assertRaises(Denied):self.flow.withdraw(bad)
        for where in ('outer','body','target'):
            bad=copy.deepcopy(s)
            (bad if where=='outer' else bad['withdrawal'] if where=='body' else bad['withdrawal']['target'])['extra']=1
            with self.assertRaises(Denied):self.flow.withdraw(bad)
        self.flow.withdraw(s)
        other=copy.deepcopy(ch);other['withdrawal']['nonce']='a'*32
        with self.assertRaises(Denied):self.flow.withdraw(self.signed_withdrawal(other))
        with self.assertRaises(Denied):self.flow.prepare_withdrawal('bob',c['request_id'],'a'*64)

    def test_unsigned_declined_deferred_submitted_cannot_withdraw(self):
        for choice in (None,'decline','defer','approve'):
            c=self.prepare()
            if choice:c=self.resolve(c,choice)
            if choice=='approve':c=self.flow.submit('bob',c['request_id'])
            with self.assertRaises(Denied):self.challenge(c)

    def test_transaction_fault_rolls_back_fence_and_successor(self):
        c=self.authorized();token=self.signed_withdrawal(self.challenge(c))
        real=self.flow._card
        with patch.object(self.flow,'_card',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.flow.withdraw(token)
        self.assertIsNone(self.flow._withdrawal(c['request_id']))
        w=self.flow.withdraw(token)
        before=self.store.db.execute('SELECT COUNT(*) FROM owner_requests').fetchone()[0]
        with patch.object(self.flow,'_card',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM owner_requests').fetchone()[0],before)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM owner_withdrawal_successors').fetchone()[0],0)

    def test_guide_skips_withdrawn_and_never_executes_old_signature(self):
        c=self.authorized();self.withdraw(c);step=self.flow.next_step()
        self.assertEqual(step['kind'],'request');self.assertNotEqual(step['card']['request_id'],c['request_id'])
        self.assertEqual(step['card']['state'],'pending')
        self.assertIsNone(self.store.db.execute('SELECT 1 FROM owner_decisions WHERE nonce=?',(c['request_id'],)).fetchone())

    def test_fresh_successor_retry_after_submission(self):
        c=self.authorized();w=self.withdraw(c)
        fresh=self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest']);self.resolve(fresh)
        self.flow.submit('bob',fresh['request_id']);self.now[0]=1301
        self.assertEqual(self.flow.prepare_after_withdrawal('bob',c['request_id'],w['review_digest'])['state'],'submitted')

    def test_expiry_and_closed_validator(self):
        c=self.authorized();ch=self.challenge(c);token=self.signed_withdrawal(ch)
        self.now[0]=1300
        with self.assertRaisesRegex(Denied,'expired'):self.flow.withdraw(token)
        for value in (True,-1,2**63):
            b=copy.deepcopy(ch['withdrawal']);b['issued_at']=value
            with self.assertRaises(Denied):validate_withdrawal(b)
        b=copy.deepcopy(ch['withdrawal']);b['expires_at']=b['issued_at']+601
        with self.assertRaises(Denied):validate_withdrawal(b)

    def test_cancelled_context_still_allows_non_granting_withdrawal(self):
        c=self.authorized();self.session.owner_cancel(self.session.registry['alice'])
        c=self.flow.review('bob',c['request_id']);w=self.withdraw(c)
        self.assertEqual(w['state'],'withdrawn');self.assertFalse(w['can_prepare_fresh'])

    def test_additive_schema_preserves_previous_authorization_and_ledgers(self):
        c=self.authorized();before=dict(self.flow._row('bob',c['request_id']))
        decisions=[tuple(r) for r in self.store.db.execute('SELECT * FROM owner_decisions')]
        self.store.db.execute('DROP TABLE owner_authorization_withdrawals')
        self.store.db.execute('DROP TABLE owner_withdrawal_successors')
        self.store.close();self.open()
        self.assertEqual(dict(self.flow._row('bob',c['request_id'])),before)
        self.assertEqual([tuple(r) for r in self.store.db.execute('SELECT * FROM owner_decisions')],decisions)
        self.assertEqual(self.flow.review('bob',c['request_id'])['state'],'authorized')
        self.assertEqual(self.withdraw(c)['state'],'withdrawn')

    def test_source_changes_require_review_again_before_withdrawal(self):
        c=self.authorized();token=self.signed_withdrawal(self.challenge(c))
        self.store.owner_pair('bob','alice',self.session.context)
        with self.assertRaisesRegex(Denied,'current review'):self.flow.withdraw(token)
        with self.assertRaisesRegex(Denied,'Review changed'):self.challenge(c)
        current=self.flow.review('bob',c['request_id'])
        self.assertEqual(self.withdraw(current)['state'],'withdrawn')

    def test_submission_withdrawal_two_connection_race(self):
        from durable import LocalDelivery
        from session import PersistentSession
        from owner_auth import SignedOwnerGateway
        from encrypted_delivery import DurableEncryptedOutbox
        from owner_workflow import OwnerWorkflow
        c=self.authorized();token=self.signed_withdrawal(self.challenge(c));barrier=threading.Barrier(2);results=[]
        def run(operation):
            store=LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
            session=PersistentSession(store,self.agents,self.meeting)
            gateway=SignedOwnerGateway(session,self.a.owner_roots)
            box=DurableEncryptedOutbox(gateway,self.a.registry,self.a.transport_keys);flow=OwnerWorkflow(gateway,box)
            barrier.wait()
            try:
                if operation=='submit':box.enqueue(self.sign(c),c['envelope'])
                else:flow.withdraw(token)
                results.append((operation,'ok'))
            except Denied:results.append((operation,'denied'))
            finally:store.close()
        threads=[threading.Thread(target=run,args=(op,)) for op in ('submit','withdraw')]
        for t in threads:t.start()
        for t in threads:t.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(sorted(r[1] for r in results),['denied','ok'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM owner_authorization_withdrawals WHERE source_nonce=?',(c['request_id'],)).fetchone()[0]+self.store.db.execute('SELECT COUNT(*) FROM encrypted_outbox WHERE nonce=?',(c['request_id'],)).fetchone()[0],1)

if __name__=='__main__':unittest.main()
