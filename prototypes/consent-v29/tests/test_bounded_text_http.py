"""Text exchange through actual HTTP handlers and child processes, no sockets/browser."""
import json
import unittest
from urllib.parse import urlencode
from workspace_ui_service import WorkspaceUIService
from test_workspace_ui import InProcessHTTP
from test_bounded_text_exchange import spec

class TextHTTPTests(unittest.TestCase):
    def setUp(self):
        self.ui=WorkspaceUIService();self.addCleanup(self.ui.close);self.http=InProcessHTTP(self.ui)
    def post(self,path,body,status=200):
        code,_,data=self.http.call('POST',path,body);result=json.loads(data)
        self.assertEqual(code,status,result);return result
    def test_exact_composition_response_delivery_and_received_history(self):
        value=spec('alice',512,'😀'*512)
        p=self.post('/api/task-preview',{'spec':value})
        create={'action':'compose_task','spec':value,'review_digest':p['review_digest'],'confirmation':'CREATE TASK'}
        from test_task_composer import spec as old_spec
        self.post('/api/action',{**create,'spec':old_spec()},400)
        row=self.post('/api/action',create)
        def action(**request):return self.post('/api/action',{'selector':row['selector'],'context':row['context'],'request':request})
        def send(card):
            action(action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
            action(action='submit',owner=card['owner'],request_id=card['request_id'])
        state=self.ui.state(row['selector'],row['context'],'alice')
        for b in state['bindings']:action(action='bind',owner=b['owner'],binding_digest=b['digest'],confirmation='BIND '+b['owner'])
        for _ in range(2):send(action(action='next')['card'])
        card=action(action='next')['card'];send(card)
        action(action='attempt',owner='alice',request_id=card['request_id'],confirmation='SEND alice')
        action(action='process',owner='alice',request_id=card['request_id'])
        fields={'selector':row['selector'],'context':row['context'],'owner':'bob'}
        code,_,data=self.http.call('GET','/api/response-context?'+urlencode(fields));self.assertEqual(code,200)
        ctx=json.loads(data);self.assertEqual(ctx['incoming_request']['payload']['prompt'],'😀'*512)
        p=action(action='preview_response',owner='bob',request_digest=ctx['request_digest'],payload={'text':'😀'*512})
        body=dict(action='prepare_response',owner='bob',request_digest=p['request_digest'],payload=p['envelope']['payload'],preview_digest=p['preview_digest'],confirmation='REVIEW RESPONSE bob')
        self.post('/api/action',{'selector':row['selector'],'context':row['context'],'request':{**body,'payload':{'text':'changed'}}},400)
        card=action(**body)['card'];self.assertEqual(card['state'],'pending');send(card)
        action(action='attempt',owner='bob',request_id=card['request_id'],confirmation='SEND bob')
        action(action='process',owner='bob',request_id=card['request_id'])
        fields['owner']='alice';code,_,data=self.http.call('GET','/api/messages?'+urlencode(fields));self.assertEqual(code,200)
        messages=json.loads(data)['messages'];self.assertEqual(messages[0]['envelope']['payload'],{'text':'😀'*512})
        self.assertEqual(action(**body)['card']['request_id'],card['request_id'])
        summary=self.ui.state(row['selector'],row['context'],'alice')['summary']
        self.assertEqual(summary['executed_tools'],0);self.assertEqual(summary['live_provider_calls'],0)
