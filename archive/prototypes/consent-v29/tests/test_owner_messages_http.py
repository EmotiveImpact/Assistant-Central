"""Read-only received content through exact owner-scoped in-process handlers."""
import json
import unittest
from urllib.parse import urlencode
import test_owner_response_http as response_http
from test_workspace_ui import InProcessHTTP
from local_owner_app import Handler


class OwnerMessagesHTTPTests(unittest.TestCase):
    setUp=response_http.OwnerResponseHTTPTests.setUp
    action=response_http.OwnerResponseHTTPTests.action
    context=response_http.OwnerResponseHTTPTests.context
    approve_submit=response_http.OwnerResponseHTTPTests.approve_submit
    receive=response_http.OwnerResponseHTTPTests.receive
    process_request=response_http.OwnerResponseHTTPTests.process_request
    preview=response_http.OwnerResponseHTTPTests.preview
    prepared=response_http.OwnerResponseHTTPTests.prepared

    def messages(self,owner='bob',**overrides):
        fields={k:self.row[k] for k in ('selector','context')};fields['owner']=owner;fields.update(overrides)
        status,_,data=self.http.call('GET','/api/messages?'+urlencode(fields))
        return status,json.loads(data)
    def test_receipt_is_hidden_then_processed_request_only_to_recipient(self):
        self.assertEqual(self.messages()[1]['messages'],[])
        card=self.receive()
        self.assertEqual(self.messages()[1]['messages'],[])
        self.action(action='process',owner='alice',request_id=card['request_id'])
        status,received=self.messages();self.assertEqual(status,200)
        self.assertEqual(received['messages'][0]['envelope'],card['envelope'])
        self.assertEqual(self.messages('alice')[1]['messages'],[])
        self.assertEqual(received['messages'][0]['sender_binding'],card['decision']['target']['sender_binding'])
        self.assertNotIn(card['request_id'],json.dumps(received))
    def test_completed_response_visible_only_after_its_processing(self):
        ctx=self.process_request();preview=self.preview(ctx)
        card=self.action(**self.prepared(preview))[1]['card'];self.approve_submit(card)
        self.assertEqual(self.messages('alice')[1]['messages'],[])
        self.action(action='attempt',owner='bob',request_id=card['request_id'],confirmation='SEND bob')
        self.assertEqual(self.messages('alice')[1]['messages'],[])
        self.action(action='process',owner='bob',request_id=card['request_id'])
        status,received=self.messages('alice');self.assertEqual(status,200)
        self.assertEqual(received['task_state'],'completed')
        self.assertEqual(received['messages'][0]['envelope']['payload'],self.payload)
        self.assertEqual(self.messages('bob')[1]['messages'][0]['envelope']['type'],'request')
    def test_wrong_scope_unknown_owner_and_malformed_fields_fail_without_content(self):
        self.process_request()
        for overrides in ({'context':'0'*64},{'selector':'astronomy'},{'owner':'charlie'}):
            status,data=self.messages(**overrides);self.assertEqual(status,400)
            self.assertNotIn(self.spec['query'],json.dumps(data))
        fields={k:self.row[k] for k in ('selector','context')};fields['owner']='bob'
        for key in fields:
            missing=dict(fields);missing.pop(key)
            self.assertNotEqual(self.http.call('GET','/api/messages?'+urlencode(missing))[0],200)
            self.assertNotEqual(self.http.call('GET','/api/messages?'+urlencode(fields)+'&'+key+'=')[0],200)
        self.assertNotEqual(self.http.call('GET','/api/messages?'+urlencode(fields)+'&id=anything')[0],200)
    def test_legacy_post_and_bad_origin_do_not_expose_messages(self):
        self.process_request()
        fields={k:self.row[k] for k in ('selector','context')};fields['owner']='bob'
        url='/api/messages?'+urlencode(fields)
        self.assertEqual(InProcessHTTP(self.ui,Handler).call('GET',url)[0],404)
        self.assertEqual(self.http.call('POST','/api/messages',fields)[0],404)
        self.assertEqual(self.http.call('GET',url,headers=[('Origin','https://evil.invalid')])[0],400)
        self.assertEqual(self.action(action='received_messages',owner='bob')[0],400)
    def test_cancellation_keeps_processed_history_but_close_fences_reads(self):
        self.process_request();original=self.messages()[1]['messages']
        card=self.action(action='cancel',owner='alice')[1]['card'];self.approve_submit(card)
        status,received=self.messages();self.assertEqual(status,200)
        self.assertEqual(received['task_state'],'cancelled');self.assertEqual(received['messages'],original)
        self.assertEqual(self.action(action='close',confirmation='DISCARD FIXTURE')[0],200)
        self.assertEqual(self.messages()[0],400)
        self.http.server.shutdown.assert_not_called()

if __name__=='__main__':unittest.main()
