import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from demo import fixture
from fixture_ipc import JsonProcess
from network import digest

ROOT=Path(__file__).resolve().parent.parent


class WorkflowProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.meeting, self.agents,_=fixture()
        self.signers={};roots={};bindings={}
        for owner in self.meeting.participants:
            signer=JsonProcess('owner_fixture_process.py','--owner',owner)
            self.signers[owner]=signer;roots[owner]=signer.read()['public_key']
        self.worker=JsonProcess('encrypted_executor_process.py','--state-directory',self.tmp.name,'--owner-workflow')
        setup=self.worker.request({'owner_roots':roots})
        for owner,pending in setup['requests'].items():
            result=self.signers[owner].request({'binding_request':pending,'confirmation':f'BIND {owner} {digest(pending)}'})
            self.assertTrue(result['ok']);bindings[owner]=result['binding']
        self.assertTrue(self.worker.request({'bindings':bindings})['ready'])
        for signer in self.signers.values():
            self.assertTrue(signer.request({'registry':{'owner_roots':roots,'bindings':bindings}})['registry_verified'])

    def tearDown(self):
        self.worker.close()
        for signer in self.signers.values():signer.close()
        self.tmp.cleanup()

    def cmd(self,method,**kwargs):
        result=self.worker.request({'method':method,**kwargs});self.assertTrue(result['ok'],result);return result['result']

    def sign(self,c):
        d=c['decision'];result=self.signers[c['owner']].request({'decision':d,'envelope':c['envelope'],
            'confirmation':f"APPROVE {c['owner']} {c['action']} {c['request_id']}"})
        self.assertTrue(result['ok']);return result['signed']

    def resolve(self,c,choice='approve'):
        kwargs={'owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest'],'choice':choice}
        if choice=='approve':kwargs['signed']=self.sign(c)
        return self.cmd('request_resolve',**kwargs)

    def pair_all(self):
        while True:
            step=self.cmd('workflow_next');c=step['card']
            if c['action']=='send':return c
            self.resolve(c);self.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])

    def test_workflow_mode_rejects_every_raw_bypass_even_with_signed_approval(self):
        c=self.pair_all();signed=self.sign(c);self.resolve(c,'decline')
        for method,kwargs in [('enqueue',{'signed':signed,'envelope':c['envelope']}),('control',{'signed':signed}),
                              ('dispatch',{'delivery_id':c['request_id']}),('process',{'delivery_id':c['request_id']}),
                              ('reconcile',{'delivery_id':c['request_id']}),('status',{'delivery_id':c['request_id']})]:
            with self.subTest(method=method):
                result=self.worker.request({'method':method,**kwargs});self.assertFalse(result['ok']);self.assertIn('bypasses',result['error'])
        self.assertEqual(self.cmd('summary')['receiver_receipts'],0)
        result=self.worker.request({'method':'request_submit','owner':c['owner'],'request_id':c['request_id']})
        self.assertFalse(result['ok'])

    def test_owner_scoped_review_and_resolution_and_delivery(self):
        c=self.pair_all()
        for method in ('request_review','request_submit','request_recover','delivery_view','delivery_check','delivery_attempt','delivery_process'):
            result=self.worker.request({'method':method,'owner':'dana','request_id':c['request_id']});self.assertFalse(result['ok'])
        self.resolve(c);self.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])
        self.assertEqual(self.cmd('delivery_view',owner=c['owner'],request_id=c['request_id'])['attempts'],0)

    def test_storage_reopen_retains_defer_revision_and_requires_new_review(self):
        c=self.pair_all();signed=self.sign(c);self.resolve(c,'defer');self.cmd('reopen_storage')
        result=self.worker.request({'method':'request_resolve','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest'],'choice':'approve','signed':signed})
        self.assertFalse(result['ok']);self.assertIn('Review changed',result['error'])
        current=self.cmd('request_review',owner=c['owner'],request_id=c['request_id'])
        self.assertEqual(current['state'],'deferred');self.resolve(current)
        self.assertEqual(self.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])['state'],'submitted')

    def test_lost_ack_check_is_not_send_or_processing(self):
        c=self.pair_all();self.resolve(c);self.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])
        kwargs={'owner':c['owner'],'request_id':c['request_id']}
        result=self.cmd('fixture_lose_ack',**kwargs);self.assertEqual(result['state'],'dispatched')
        self.assertIn('uncertain',result['label'])
        self.cmd('reopen_storage')
        recovered=self.cmd('delivery_check',**kwargs);self.assertEqual(recovered['state'],'received');self.assertEqual(recovered['attempts'],1)
        self.assertEqual(self.cmd('summary')['transitions'],0)
        self.assertEqual(self.cmd('delivery_process',**kwargs)['state'],'processed')

    def test_unknown_outcome_stays_uncertain_on_repeated_checks(self):
        c=self.pair_all();self.resolve(c);self.cmd('request_submit',owner=c['owner'],request_id=c['request_id'])
        kwargs={'owner':c['owner'],'request_id':c['request_id']}
        self.cmd('fixture_fail_before_receipt',**kwargs)
        for _ in range(3):
            s=self.cmd('delivery_check',**kwargs);self.assertEqual(s['state'],'dispatched');self.assertEqual(s['attempts'],1)
        self.assertEqual(self.cmd('summary')['receiver_receipts'],0)

    def test_compact_inbox_remains_inside_ipc_frame_limit(self):
        for _ in range(30):
            c=self.cmd('request_prepare',owner='bob',action='cancel');self.resolve(c,'decline')
        items=self.cmd('request_list',owner='bob')
        self.assertEqual(len(items),20);self.assertLess(len(json.dumps(items)),12000)
        self.assertNotIn('decision',items[0]);self.assertNotIn('review',items[0])

    def test_malformed_commands_are_nonfatal(self):
        for request in [{'method':[]},{'method':'request_prepare','owner':'bob','action':[]},
                        {'method':'request_review','owner':[],'request_id':'a'*32},
                        {'method':'request_prepare','owner':'bob','action':'cancel','allow_all':True},
                        {'method':'request_resolve','owner':'bob','request_id':{},'review_digest':None,'choice':{}},
                        {'method':'delivery_attempt','owner':'bob','request_id':[]}]:
            result=self.worker.request(request);self.assertFalse(result['ok'])
        self.assertEqual(self.cmd('summary')['transitions'],0)

    def test_guide_does_not_replace_declined_request(self):
        step=self.cmd('workflow_next');c=step['card'];self.resolve(c,'decline')
        for _ in range(3):
            current=self.cmd('workflow_next')['card'];self.assertEqual(current['request_id'],c['request_id']);self.assertEqual(current['state'],'declined')


class OwnerConsoleTests(unittest.TestCase):
    def run_console(self,*args,input=None):
        return subprocess.run([sys.executable,'owner_console.py',*args],cwd=ROOT,input=input,text=True,capture_output=True,timeout=25,check=True).stdout

    def test_complete_owner_workflow(self):
        out=self.run_console('--simulate')
        self.assertIn('"agreed": true, "receiver_receipts": 12, "transitions": 12',out)
        self.assertIn('This alone did not execute or dispatch anything',out)

    def test_decline_stops_before_first_disclosure(self):
        out=self.run_console('--simulate','--scenario','decline')
        self.assertIn('will not replace it or ask again',out)
        self.assertIn('"receiver_receipts": 0, "transitions": 0',out)

    def test_deferral_reopens_fresh_review_without_implicit_approval(self):
        out=self.run_console('--simulate','--scenario','defer')
        self.assertIn('Previous review token invalidated',out)
        self.assertIn('"agreed": true',out)

    def test_lost_ack_recovery_checks_receipt_before_progress(self):
        out=self.run_console('--simulate','--scenario','lost-receipt')
        self.assertIn('Receipt check only: Recipient receipt verified; not processed | attempts: 1',out)
        self.assertIn('"agreed": true',out)

    def test_unconfirmed_attempt_is_not_retried_automatically(self):
        out=self.run_console('--simulate','--scenario','uncertain')
        self.assertIn('Still uncertain. No automatic retry',out)
        self.assertIn('"receiver_receipts": 0, "transitions": 0',out)

    def test_manual_denial_of_binding_leaves_no_workflow_actions(self):
        out=self.run_console(input='NO\n')
        self.assertIn('Stopped safely:',out);self.assertNotIn('Owner signature saved',out)
        self.assertIn('Fixture processes stopped',out)

    def test_manual_back_defer_resume_decline_never_grants_approval(self):
        import contextlib,io,re
        from unittest.mock import patch
        from owner_console import run
        choices=iter(('back','defer','decline'));paused=iter(('back','resume'))
        def answer(prompt):
            if prompt.startswith("Type 'BIND "):return re.match("Type '([^']+)'",prompt).group(1)
            if prompt.startswith('Approve /'):return next(choices)
            if prompt.startswith('Owner to list'):return 'bob'
            if prompt.startswith('Request paused'):return next(paused)
            raise AssertionError('Unexpected prompt '+prompt)
        output=io.StringIO()
        with patch('builtins.input',side_effect=answer),contextlib.redirect_stdout(output):run()
        text=output.getvalue()
        self.assertIn('Returned to inbox. No decision or send occurred.',text)
        self.assertIn('Request remains deferred. No approval or send occurred.',text)
        self.assertIn('Explicitly resumed deferred review. No approval inferred.',text)
        self.assertNotIn('Owner signature saved',text)
        self.assertIn('"receiver_receipts": 0, "transitions": 0',text)
        self.assertIn('no later inbox resume',text)

    def test_manual_cancellation_keeps_received_evidence_visible_until_checked(self):
        import contextlib,io,re
        from unittest.mock import patch
        from owner_console import run
        delivery_choices=iter(('process','send','cancel','process'))
        def answer(prompt):
            if prompt.startswith("Type '"):return re.match("Type '([^']+)'",prompt).group(1)
            if prompt.startswith('Approve /'):return 'approve'
            if prompt.startswith('Submit approved'):return 'submit'
            if prompt.startswith('Send attempt'):return next(delivery_choices)
            raise AssertionError('Unexpected prompt '+prompt)
        output=io.StringIO()
        with patch('builtins.input',side_effect=answer),contextlib.redirect_stdout(output):run()
        text=output.getvalue()
        self.assertIn('Cannot process without a verified unprocessed receipt. Nothing changed.',text)
        self.assertIn('Meeting cancelled. Existing receipt checks may still establish what arrived',text)
        self.assertIn('"receiver_receipts": 1, "transitions": 0',text)
        self.assertIn('No unresolved attempted deliveries remain',text)
