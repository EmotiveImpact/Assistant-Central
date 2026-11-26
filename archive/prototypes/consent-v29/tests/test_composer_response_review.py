"""Independent local IPC framing and maximum composition lifecycle checks."""
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from fixture_ipc import JsonProcess
from task_composer import preview, composed_fixture
from owner_workspace import OwnerWorkspace
from generic_protocol import task_envelope
from network import digest


class IndependentResponseFraming(unittest.TestCase):
    def process(self,line,limit):
        from ipc_test_support import output
        process=output(line,limit)
        self.addCleanup(process.close)
        return process

    def test_exact_response_limit_and_one_over(self):
        for limit in (16384,65536):
            for length in (limit-1,limit,limit+1):
                line=json.dumps('x'*(length-3))+'\n'
                self.assertEqual(len(line),length)
                process=self.process(line,limit)
                with self.subTest(limit=limit,length=length):
                    if length<=limit:self.assertEqual(process.read(),'x'*(length-3))
                    else:
                        with self.assertRaises(RuntimeError):process.read()

    def test_missing_newline_empty_and_invalid_json_denied(self):
        for limit in (16384,65536):
            for line in ('','{}','x\n','{"x":\n'):
                process=self.process(line,limit)
                with self.subTest(limit=limit,line=line):
                    with self.assertRaises(RuntimeError):process.read()

    def test_timeout_kills_process(self):
        from ipc_test_support import child
        process=child('import time; time.sleep(60)')
        self.addCleanup(process.close)
        with patch('fixture_ipc._RESPONSE_TIMEOUT', .1):
            with self.assertRaises(RuntimeError):process.read()
        self.assertIsNotNone(process.process.poll())

    def test_custom_response_cap_does_not_expand_input_frame(self):
        process=self.process('{}\n',65536)
        with patch.object(process,'_run') as run:
            with self.assertRaises(ValueError):process.request({'value':'x'*16384})
            run.assert_not_called()

    def test_input_exact_limit_is_allowed_without_response_bound_leak(self):
        for limit in (16384,65536):
            process=self.process('{}\n',limit)
            with patch.object(process,'_run',return_value={}) as run:
                self.assertEqual(process.request('x'*(16384-3)),{})
            self.assertEqual(len(run.call_args.args[0]),16384)

    def test_constructor_rejects_unbounded_or_malformed_limit_before_launch(self):
        with patch('fixture_ipc.subprocess.Popen',side_effect=AssertionError('started')):
            for limit in (None,True,16384.0,65537,-1,'65536'):
                with self.subTest(limit=limit),self.assertRaises(ValueError):
                    JsonProcess('owner_fixture_process.py',max_response_bytes=limit)


class IndependentMaximumCompositionLifecycle(unittest.TestCase):
    def test_maximum_spec_roundtrip_with_explicit_empty_result(self):
        value=dict(selector='custom-'+'x'*48,task_id='t'*64,conversation_id='c'*64,
                   requester='bob',query='𐀀'*512,max_items=5)
        workspace=OwnerWorkspace();self.addCleanup(workspace.close)
        p=preview(value);workspace.compose(value,p['review_digest'],'CREATE TASK')
        service=workspace._slots[p['selector']]['service']
        def action(**request):return workspace.action(p['selector'],p['context'],request)
        def approve(card):
            action(action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
            action(action='submit',owner=card['owner'],request_id=card['request_id'])
        def send(card):
            approve(card)
            action(action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
            action(action='process',owner=card['owner'],request_id=card['request_id'])
        for owner,pending in service.requests.items():
            action(action='bind',owner=owner,binding_digest=digest(pending),confirmation='BIND '+owner)
        for _ in range(2):approve(action(action='next')['card'])
        card=action(action='next')['card'];self.assertEqual(card['envelope']['payload']['query'],value['query']);send(card)
        self.assertEqual(action(action='next')['kind'],'awaiting')
        task,_,request,_=composed_fixture(value)
        result=task_envelope(task,'result',{'items':[]},reply_to=digest(request))
        service._command('fixture_agent_call',actor='alice',command={'method':'propose','proposal_id':'max-response','envelope':result})
        card=workspace.import_proposal(p['selector'],p['context'],'alice','max-response');send(card)
        self.assertEqual(action(action='next')['kind'],'complete')

if __name__=='__main__':unittest.main()
