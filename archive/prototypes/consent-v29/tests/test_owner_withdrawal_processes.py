import copy
import time
import unittest
from unittest.mock import patch
import test_owner_workflow_processes as process_fixture
import test_local_owner_app as ui_fixture
from network import Denied, digest


class WithdrawalProcessTests(unittest.TestCase):
    def setUp(self):self.f=process_fixture.WorkflowProcessTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def authorized(self,ttl=300):
        c=self.f.cmd('request_prepare',owner='bob',action='cancel',ttl=ttl)
        return self.f.resolve(c)
    def challenge(self,c):return self.f.cmd('withdrawal_prepare',owner=c['owner'],request_id=c['request_id'],review_digest=c['review_digest'])
    def signing_request(self,challenge):
        body=challenge['withdrawal']
        return {**challenge,'confirmation':f"WITHDRAW {body['owner']} {body['target']['request_id']} {digest(body)}"}
    def signed(self,challenge):
        result=self.f.signers['bob'].request(self.signing_request(challenge));self.assertTrue(result['ok'],result);return result['signed']

    def test_expired_authorization_withdraws_then_fresh_review_requires_new_approval(self):
        c=self.authorized(ttl=1);delay=c['decision']['expires_at']-time.time()
        if delay>0:time.sleep(delay+0.02)
        c=self.f.cmd('request_review',owner='bob',request_id=c['request_id']);self.assertTrue(c['can_withdraw'])
        challenge=self.challenge(c);signed=self.signed(challenge)
        withdrawn=self.f.cmd('withdrawal_commit',signed=signed);self.assertEqual(withdrawn['state'],'withdrawn')
        self.assertEqual(self.f.cmd('summary')['receiver_receipts'],0)
        self.f.cmd('reopen_storage');self.assertEqual(self.f.cmd('withdrawal_commit',signed=signed)['state'],'withdrawn')
        self.assertTrue(self.challenge(c)['already_withdrawn'])
        fresh=self.f.cmd('withdrawal_fresh',owner='bob',request_id=c['request_id'],review_digest=withdrawn['review_digest'])
        self.assertEqual(fresh['state'],'pending');self.assertNotEqual(fresh['request_id'],c['request_id'])
        self.assertFalse(self.f.worker.request({'method':'request_submit','owner':'bob','request_id':fresh['request_id']})['ok'])
        self.assertFalse(self.f.worker.request({'method':'request_submit','owner':'bob','request_id':c['request_id']})['ok'])

    def test_signer_rejects_wrong_phrase_owner_original_and_extra_fields(self):
        c=self.authorized();challenge=self.challenge(c);request=self.signing_request(challenge)
        self.assertFalse(self.f.signers['alice'].request(request)['ok'])
        cases=[{**request,'confirmation':'yes'},{**request,'approved':True}]
        bad=copy.deepcopy(request);bad['original']['decision']['target']['meeting']='other';cases.append(bad)
        bad=copy.deepcopy(request);bad['original']['envelope']={};cases.append(bad)
        bad=copy.deepcopy(request);bad['withdrawal']['target']['fingerprint']='0'*64;cases.append(bad)
        for item in cases:self.assertFalse(self.f.signers['bob'].request(item)['ok'])
        self.assertEqual(self.f.cmd('request_review',owner='bob',request_id=c['request_id'])['state'],'authorized')

    def test_closed_executor_commands_reject_scope_injection_and_unsigned_commit(self):
        c=self.authorized();challenge=self.challenge(c);signed=self.signed(challenge)
        for request in [
            {'method':'withdrawal_prepare','owner':'bob','request_id':c['request_id'],'review_digest':c['review_digest'],'peer':'dana'},
            {'method':'withdrawal_commit','signed':{'withdrawal':challenge['withdrawal'],'signature':'0'*128}},
            {'method':'withdrawal_commit','signed':signed,'owner':'bob'},
            {'method':'withdrawal_fresh','owner':'bob','request_id':c['request_id'],'review_digest':c['review_digest']}]:
            self.assertFalse(self.f.worker.request(request)['ok'])
        self.assertEqual(self.f.cmd('request_review',owner='bob',request_id=c['request_id'])['state'],'authorized')

    def test_zero_attempt_queued_delivery_cannot_be_withdrawn(self):
        c=self.f.pair_all();self.f.resolve(c);self.f.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])
        c=self.f.cmd('request_review',owner=c['owner'],request_id=c['request_id']);self.assertFalse(c['can_withdraw'])
        self.assertFalse(self.f.worker.request({'method':'withdrawal_prepare','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest']})['ok'])
        self.assertEqual(self.f.cmd('delivery_view',owner=c['owner'],request_id=c['request_id'])['attempts'],0)


class WithdrawalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.f=ui_fixture.UIServiceTests();self.f.setUp();self.f.ready()
        c=self.f.ui.action({'action':'cancel','owner':'bob'})['card'];self.c=self.f.approve(c)['card']
    def tearDown(self):self.f.tearDown()
    def action(self):return {'action':'withdraw_unused','owner':'bob','request_id':self.c['request_id'],'review_digest':self.c['review_digest'],'confirmation':'WITHDRAW bob'}

    def test_wrong_phrase_never_signs_and_exact_retry_never_resigns(self):
        with patch.object(self.f.ui.signers['bob'],'request',side_effect=AssertionError('must not sign')):
            with self.assertRaises(Denied):self.f.ui.action({**self.action(),'confirmation':'yes'})
        card=self.f.ui.action(self.action())['card'];self.assertEqual(card['state'],'withdrawn')
        with patch.object(self.f.ui.signers['bob'],'request',side_effect=AssertionError('must not resign')):
            self.assertEqual(self.f.ui.action(self.action())['card']['state'],'withdrawn')
        self.assertEqual(self.f.ui.state('bob')['summary']['receiver_receipts'],0)

    def test_lost_commit_reply_is_recovered_from_existing_tombstone(self):
        command=self.f.ui._command
        def lost(method,**fields):
            result=command(method,**fields)
            if method=='withdrawal_commit':raise ConnectionError('synthetic lost reply after commit')
            return result
        with patch.object(self.f.ui,'_command',side_effect=lost):
            with self.assertRaises(ConnectionError):self.f.ui.action(self.action())
        self.assertEqual(self.f.ui.review('bob',self.c['request_id'])['state'],'withdrawn')
        with patch.object(self.f.ui.signers['bob'],'request',side_effect=AssertionError('must not resign')):
            self.assertEqual(self.f.ui.action(self.action())['card']['state'],'withdrawn')

    def test_fresh_unsigned_review_is_separate_and_idempotent_after_decline(self):
        withdrawn=self.f.ui.action(self.action())['card']
        action={'action':'fresh_after_withdrawal','owner':'bob','request_id':self.c['request_id'],
                'review_digest':withdrawn['review_digest'],'confirmation':'REVIEW bob'}
        with patch.object(self.f.ui.signers['bob'],'request',side_effect=AssertionError('no fresh approval')):
            fresh=self.f.ui.action(action)['card'];self.assertEqual(fresh['state'],'pending')
            with self.assertRaises(Denied):self.f.submit(fresh)
        self.f.ui.action({'action':'decline','owner':'bob','request_id':fresh['request_id'],'review_digest':fresh['review_digest']})
        retry=self.f.ui.action(action)['card'];self.assertEqual(retry['request_id'],fresh['request_id']);self.assertEqual(retry['state'],'declined')
        self.assertEqual(self.f.ui.review('bob',self.c['request_id'])['state'],'withdrawn')

    def test_inspecting_authorization_or_withdrawal_never_creates_successor(self):
        for _ in range(3):self.assertTrue(self.f.ui.review('bob',self.c['request_id'])['can_withdraw'])
        self.assertEqual(len(self.f.ui.state('bob')['inbox']),1)
        self.f.ui.action(self.action())
        for _ in range(3):self.assertTrue(self.f.ui.review('bob',self.c['request_id'])['can_prepare_fresh'])
        self.assertEqual(len(self.f.ui.state('bob')['inbox']),1)
