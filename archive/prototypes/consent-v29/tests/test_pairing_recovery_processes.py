import unittest
from contextlib import ExitStack
from unittest.mock import patch
import test_owner_workflow_processes as process_fixture
import test_local_owner_app as ui_fixture
from network import Denied


class PairingRecoveryProcessTests(unittest.TestCase):
    def setUp(self):
        self.f=process_fixture.WorkflowProcessTests();self.f.setUp();self.f.pair_all()
        self.c=self.f.cmd('request_prepare',owner='bob',action='send',envelope=self.f.agents[1].preview_availability(self.f.meeting))
        for owner,peer in (('bob','alice'),('alice','bob')):
            revoke=self.f.cmd('request_prepare',owner=owner,action='revoke',peer=peer)
            self.f.resolve(revoke);self.f.cmd('request_submit',owner=owner,request_id=revoke['request_id'])
    def tearDown(self):self.f.tearDown()
    def current(self):return self.f.cmd('request_review',owner='bob',request_id=self.c['request_id'])
    def recover(self,c,direction):return self.f.cmd('request_pairing',owner='bob',request_id=c['request_id'],review_digest=c['review_digest'],direction_owner=direction)

    def test_closed_process_recovery_and_fresh_send_are_separate(self):
        original=self.current()
        for owner in ('bob','alice'):
            c=self.current();pair=self.recover(c,owner)
            self.assertEqual(pair['state'],'pending');self.assertEqual(pair['owner'],owner)
            self.assertEqual(self.f.cmd('summary')['receiver_receipts'],0)
            self.f.resolve(pair);self.f.cmd('request_submit',owner=owner,request_id=pair['request_id'])
            self.assertEqual(self.recover(c,owner)['request_id'],pair['request_id'])
        c=self.current();self.assertEqual(c['state'],'stale');self.assertTrue(c['can_replace'])
        old=self.f.worker.request({'method':'request_submit','owner':'bob','request_id':c['request_id']})
        self.assertFalse(old['ok'])
        fresh=self.f.cmd('request_replace',owner='bob',request_id=c['request_id'],review_digest=c['review_digest'])
        self.assertEqual(fresh['envelope'],original['envelope']);self.assertEqual(fresh['state'],'pending')
        self.f.resolve(fresh);self.f.cmd('request_submit',owner='bob',request_id=fresh['request_id'])
        self.assertEqual(self.f.cmd('delivery_view',owner='bob',request_id=fresh['request_id'])['attempts'],0)
        self.f.cmd('reopen_storage');self.assertEqual(self.recover(original,'bob')['state'],'submitted')

    def test_process_recovery_rejects_injected_scope_and_unrelated_owner(self):
        c=self.current();base={'method':'request_pairing','owner':'bob','request_id':c['request_id'],'review_digest':c['review_digest'],'direction_owner':'bob'}
        for extra in ({'peer':'dana'},{'envelope':{}},{'ttl':86400},{'approved':True}):
            self.assertFalse(self.f.worker.request({**base,**extra})['ok'])
        for direction in ('dana',None,[]):self.assertFalse(self.f.worker.request({**base,'direction_owner':direction})['ok'])
        self.assertEqual(self.current()['review_digest'],c['review_digest'])


class PairingRecoveryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.f=ui_fixture.UIServiceTests();self.f.setUp();self.f.ready();self.f.send_card()
        from demo import fixture
        meeting,agents,_=fixture()
        self.c=self.f.ui._command('request_prepare',owner='bob',action='send',envelope=agents[1].preview_availability(meeting))
        revoke=self.f.ui.action({'action':'revoke','owner':'bob','peer':'alice'})['card'];self.f.approve(revoke);self.f.submit(revoke)
        self.c=self.f.ui.review('bob',self.c['request_id'])
    def tearDown(self):self.f.tearDown()
    def action(self):return {'action':'review_pairing','owner':'bob','request_id':self.c['request_id'],
        'review_digest':self.c['review_digest'],'direction_owner':'bob','confirmation':'REVIEW PAIR bob'}

    def test_ui_open_pair_review_never_contacts_any_signer_or_approves(self):
        with ExitStack() as stack:
            for signer in self.f.ui.signers.values():stack.enter_context(patch.object(signer,'request',side_effect=AssertionError('must not sign')))
            wrong={**self.action(),'confirmation':'APPROVE bob'}
            with self.assertRaises(Denied):self.f.ui.action(wrong)
            pair=self.f.ui.action(self.action())['card']
            self.assertEqual(pair['state'],'pending');self.assertEqual(pair['owner'],'bob')
            self.assertEqual(self.f.ui.action(self.action())['card']['request_id'],pair['request_id'])
            with self.assertRaises(Denied):self.f.submit(pair)
        self.assertEqual(self.f.ui.state('bob')['summary']['receiver_receipts'],0)

    def test_ui_views_never_prepare_recovery_and_decline_stays_visible(self):
        before=self.f.ui.state('bob')['inbox']
        for _ in range(3):self.f.ui.review('bob',self.c['request_id']);self.f.ui.state('bob')
        self.assertEqual(self.f.ui.state('bob')['inbox'],before)
        pair=self.f.ui.action(self.action())['card']
        self.f.ui.action({'action':'decline','owner':'bob','request_id':pair['request_id'],'review_digest':pair['review_digest']})
        self.c=self.f.ui.review('bob',self.c['request_id'])
        self.assertEqual(self.f.ui.action(self.action())['card']['state'],'declined')
        with self.assertRaises(Denied):self.f.ui.action({**self.action(),'peer':'dana'})
