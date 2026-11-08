import time
import unittest
import test_owner_workflow_processes as workflow_process_fixture
import test_local_owner_app as ui_fixture


def after_expiry(card):
    delay=card['decision']['expires_at']-time.time()
    if delay>0:time.sleep(delay+0.02)


class ReviewReplacementProcessTests(unittest.TestCase):
    def setUp(self):self.f=workflow_process_fixture.WorkflowProcessTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()

    def test_expired_pair_review_replaces_through_closed_process_command(self):
        old=self.f.cmd('request_prepare',owner='bob',action='pair',peer='alice',ttl=1)
        signed=self.f.sign(old);after_expiry(old)
        fresh=self.f.cmd('request_replace',owner='bob',request_id=old['request_id'],review_digest=old['review_digest'])
        self.assertNotEqual(fresh['request_id'],old['request_id']);self.assertEqual(fresh['state'],'pending')
        history=self.f.cmd('request_review',owner='bob',request_id=old['request_id'])
        self.assertEqual(history['state'],'superseded')
        denied=self.f.worker.request({'method':'request_resolve','owner':'bob','request_id':old['request_id'],
                                     'review_digest':history['review_digest'],'choice':'approve','signed':signed})
        self.assertFalse(denied['ok'])
        repeated=self.f.cmd('request_replace',owner='bob',request_id=old['request_id'],review_digest=old['review_digest'])
        self.assertEqual(repeated['request_id'],fresh['request_id'])
        self.assertEqual(self.f.cmd('summary')['receiver_receipts'],0)

    def test_process_replacement_rejects_wrong_owner_extra_fields_and_invalid_ttl(self):
        old=self.f.cmd('request_prepare',owner='bob',action='pair',peer='alice')
        for request in [
            {'method':'request_replace','owner':'dana','request_id':old['request_id'],'review_digest':old['review_digest']},
            {'method':'request_replace','owner':'bob','request_id':old['request_id'],'review_digest':old['review_digest'],'approved':True},
            {'method':'request_replace','owner':'bob','request_id':[],'review_digest':None}]:
            self.assertFalse(self.f.worker.request(request)['ok'])
        for ttl in (True,0,601,[],None):
            self.assertFalse(self.f.worker.request({'method':'request_prepare','owner':'dana','action':'cancel','ttl':ttl})['ok'])
        self.assertEqual(self.f.cmd('request_review',owner='bob',request_id=old['request_id'])['state'],'pending')


class ReviewReplacementAdapterTests(unittest.TestCase):
    def setUp(self):self.f=ui_fixture.UIServiceTests();self.f.setUp();self.f.ready()
    def tearDown(self):self.f.tearDown()

    def test_ui_replacement_needs_explicit_phrase_and_never_signs_or_executes(self):
        from network import Denied
        old=self.f.ui._command('request_prepare',owner='bob',action='cancel',ttl=1);after_expiry(old)
        action={'action':'replace_review','owner':'bob','request_id':old['request_id'],
                'review_digest':old['review_digest'],'confirmation':'yes'}
        with self.assertRaises(Denied):self.f.ui.action(action)
        action['confirmation']='REVIEW bob';fresh=self.f.ui.action(action)['card']
        self.assertEqual(fresh['state'],'pending');self.assertNotEqual(fresh['request_id'],old['request_id'])
        self.assertEqual(self.f.ui.review('bob',old['request_id'])['state'],'superseded')
        self.assertEqual(self.f.ui.state('bob')['summary']['transitions'],0)
        with self.assertRaises(Denied):self.f.ui.action({'action':'submit','owner':'bob','request_id':fresh['request_id']})
        self.assertEqual(self.f.ui.action(action)['card']['request_id'],fresh['request_id'])

    def test_get_view_never_replaces_or_renews_expired_draft(self):
        old=self.f.ui._command('request_prepare',owner='bob',action='cancel',ttl=1);after_expiry(old)
        for _ in range(3):
            card=self.f.ui.review('bob',old['request_id']);self.assertEqual(card['state'],'expired');self.assertTrue(card['can_replace'])
        inbox=self.f.ui.state('bob')['inbox'];self.assertEqual(len(inbox),1)
        self.assertEqual(inbox[0]['request_id'],old['request_id'])
