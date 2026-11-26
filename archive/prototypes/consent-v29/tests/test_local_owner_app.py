import copy
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from owner_ui_service import OwnerUIService
from local_owner_app import LoopbackServer, MAX_BODY
from network import Denied


class UIServiceTests(unittest.TestCase):
    def setUp(self):self.ui=OwnerUIService()
    def tearDown(self):self.ui.close()
    def ready(self):
        state=self.ui.state('alice')
        for b in state['bindings']:
            self.ui.action({'action':'bind','owner':b['owner'],'binding_digest':b['digest'],'confirmation':'BIND '+b['owner']})
    def approve(self,c):return self.ui.action({'action':'approve','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest'],'confirmation':'APPROVE '+c['owner']})
    def submit(self,c):return self.ui.action({'action':'submit','owner':c['owner'],'request_id':c['request_id']})
    def send_card(self):
        while True:
            step=self.ui.action({'action':'next'});c=step['card']
            if c['action']=='send':return c
            self.approve(c);self.submit(c)

    def test_setup_state_is_public_and_requires_exact_binding_consent(self):
        state=self.ui.state('alice');self.assertEqual(state['phase'],'bindings')
        self.assertNotIn('private',json.dumps(state))
        b=state['bindings'][0]
        for digest,phrase in [('0'*64,'BIND '+b['owner']),(b['digest'],'yes')]:
            with self.assertRaises(Denied):self.ui.action({'action':'bind','owner':b['owner'],'binding_digest':digest,'confirmation':phrase})
        self.assertFalse(any(b['approved'] for b in self.ui.state('alice')['bindings']))
        with self.assertRaises(Denied):self.ui.action({'action':'next'})

    def test_get_views_never_prepare_approve_or_send(self):
        self.ready()
        for _ in range(3):self.assertEqual(self.ui.state('alice')['inbox'],[])
        self.assertEqual(self.ui.state('alice')['summary']['receiver_receipts'],0)

    def test_view_review_and_exact_approval_are_separate_from_execution(self):
        self.ready();c=self.ui.action({'action':'next'})['card']
        with self.assertRaises(Denied):self.ui.action({'action':'approve','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest'],'confirmation':'yes'})
        self.assertEqual(self.ui.review(c['owner'],c['request_id'])['state'],'pending')
        self.assertEqual(self.approve(c)['card']['state'],'authorized')
        self.assertEqual(self.submit(c)['card']['state'],'submitted')
        self.assertEqual(self.ui.state('alice')['summary']['receiver_receipts'],0)

    def test_defer_invalidates_other_tab_review_and_decline_is_terminal(self):
        self.ready();c=self.ui.action({'action':'next'})['card']
        self.ui.action({'action':'defer','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest']})
        with self.assertRaisesRegex(Denied,'changed'):self.approve(c)
        fresh=self.ui.review(c['owner'],c['request_id'])
        self.ui.action({'action':'decline','owner':c['owner'],'request_id':c['request_id'],'review_digest':fresh['review_digest']})
        with self.assertRaises(Denied):self.approve(self.ui.review(c['owner'],c['request_id']))
        self.assertEqual(self.ui.action({'action':'next'})['card']['state'],'declined')

    def test_wrong_owner_and_raw_command_surfaces_are_refused(self):
        self.ready();c=self.ui.action({'action':'next'})['card']
        with self.assertRaises(Denied):self.ui.review('dana',c['request_id'])
        for request in ({'action':'enqueue'},{'action':'control'},{'action':'sign'},{'action':'next','approved':True},{'action':[]},[]):
            with self.assertRaises(Denied):self.ui.action(request)

    def test_full_http_adapter_workflow_preserves_twelve_messages(self):
        self.ready()
        while True:
            step=self.ui.action({'action':'next'})
            if step['kind']=='complete':break
            if step['kind']=='request':
                c=step['card'];self.approve(c);self.submit(c)
            else:
                owner,nonce=step['owner'],step['delivery_id']
                if step['state']=='queued':
                    self.ui.action({'action':'attempt','owner':owner,'request_id':nonce,'confirmation':'SEND '+owner})
                else:self.ui.action({'action':'process','owner':owner,'request_id':nonce})
        self.assertEqual(self.ui.state('alice')['summary'],{'agreed':True,'receiver_receipts':12,'transitions':12})

    def test_delivery_check_does_not_attempt_or_process(self):
        self.ready();c=self.send_card();self.approve(c);self.submit(c)
        kwargs={'owner':c['owner'],'request_id':c['request_id']}
        self.ui._command('fixture_lose_ack',**kwargs)
        for _ in range(2):
            result=self.ui.action({'action':'check',**kwargs});self.assertEqual(result['state'],'received');self.assertEqual(result['attempts'],1)
        self.assertEqual(self.ui.state('alice')['summary']['transitions'],0)

    def test_uncertain_outcome_stays_uncertain_and_cancellation_preserves_receipt(self):
        self.ready();c=self.send_card();self.approve(c);self.submit(c)
        kwargs={'owner':c['owner'],'request_id':c['request_id']}
        self.ui._command('fixture_lose_ack',**kwargs)
        cancel=self.ui.action({'action':'cancel','owner':'charlie'})['card'];self.approve(cancel);self.submit(cancel)
        with self.assertRaises(Denied):self.ui.action({'action':'attempt',**kwargs,'confirmation':'SEND '+c['owner']})
        self.assertEqual(self.ui.action({'action':'check',**kwargs})['state'],'received')
        self.assertEqual(self.ui.action({'action':'process',**kwargs})['state'],'received_blocked')
        self.assertEqual(self.ui.state('alice')['summary']['receiver_receipts'],1)

    def test_repeated_concurrent_approval_never_executes_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        self.ready();c=self.ui.action({'action':'next'})['card']
        def approve(_):
            try:return self.approve(c)['card']['state']
            except Denied:return 'refused'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(approve,range(2)))
        self.assertEqual(sorted(results),['authorized','refused'])
        self.assertEqual(self.ui.state('alice')['summary']['transitions'],0)

    def test_close_discards_temporary_records_and_stops_all_processes(self):
        directory=Path(self.ui.directory.name);processes=[s.process for s in self.ui.signers.values()]+[self.ui.executor.process]
        with self.assertRaises(Denied):self.ui.action({'action':'close','confirmation':'yes'})
        self.assertTrue(directory.exists())
        self.ui.action({'action':'close','confirmation':'DISCARD FIXTURE'})
        self.assertFalse(directory.exists());self.assertTrue(all(p.poll() is not None for p in processes))
        self.ui.close()
        with self.assertRaises(Denied):self.ui.action({'action':'next'})


class LoopbackHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui=OwnerUIService();cls.server=LoopbackServer(cls.ui)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.ui.close();cls.thread.join(timeout=2)
    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        conn.request(method,path,body=body,headers=headers or {})
        result=conn.getresponse();status=result.status;h=dict(result.getheaders());data=result.read();conn.close()
        return status,h,data
    def headers(self):return {'Origin':self.server.origin,'Content-Type':'application/json','X-Owner-Fixture':'v7'}
    def raw(self,headers,body=b'{"action":"next"}'):
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        conn.putrequest('POST','/api/action',skip_host=True,skip_accept_encoding=True)
        for k,v in headers:conn.putheader(k,v)
        conn.endheaders(body);r=conn.getresponse();result=(r.status,r.read());conn.close();return result

    def test_loopback_binding_static_allowlist_and_security_headers(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        for path in ('/','/app.js','/style.css'):
            status,headers,body=self.request('GET',path);self.assertEqual(status,200)
            self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Frame-Options'],'DENY')
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy']);self.assertNotIn('Access-Control-Allow-Origin',headers)
            self.assertTrue(body)
        for path in ('/../owner_ui_service.py','/owner_ui_service.py','/api/action','/style.css?x=1'):
            self.assertNotEqual(self.request('GET',path)[0],200)

    def test_state_is_read_only_and_queries_are_closed(self):
        for _ in range(2):self.assertEqual(self.request('GET','/api/state?owner=alice')[0],200)
        self.assertEqual(self.ui.phase,'bindings');self.assertEqual(self.ui.bindings,{})
        for path in ('/api/state','/api/state?owner=alice&owner=bob','/api/state?owner=alice&extra=yes','/api/state?owner=nobody'):
            self.assertNotEqual(self.request('GET',path)[0],200)

    def test_wrong_host_rebinding_and_absolute_url_refused(self):
        for host in ('localhost:'+str(self.server.server_address[1]),'127.0.0.1.evil','evil.example',self.server.expected_host+'@evil'):
            self.assertEqual(self.request('GET','/',headers={'Host':host})[0],400)
        self.assertEqual(self.request('GET','http://evil.example/')[0],400)

    def test_cross_origin_missing_origin_and_cross_site_posts_refused(self):
        for origin in (None,'null','https://evil.example',self.server.origin+'.evil'):
            headers=self.headers()
            if origin is None:headers.pop('Origin')
            else:headers['Origin']=origin
            self.assertEqual(self.request('POST','/api/action','{"action":"next"}',headers)[0],400)
        headers=self.headers();headers['Sec-Fetch-Site']='cross-site'
        self.assertEqual(self.request('POST','/api/action','{"action":"next"}',headers)[0],400)

    def test_form_content_preflight_and_unknown_methods_refused(self):
        for kind in ('text/plain','application/x-www-form-urlencoded','multipart/form-data','application/json; charset=utf-8'):
            h=self.headers();h['Content-Type']=kind
            self.assertEqual(self.request('POST','/api/action','{"action":"next"}',h)[0],400)
        h=self.headers();h.pop('X-Owner-Fixture')
        self.assertEqual(self.request('POST','/api/action','{"action":"next"}',h)[0],400)
        self.assertEqual(self.request('OPTIONS','/api/action')[0],405)
        self.assertEqual(self.request('PUT','/api/action')[0],405)

    def test_duplicate_critical_headers_and_transfer_encoding_refused(self):
        base=[('Host',self.server.expected_host),('Origin',self.server.origin),('Content-Type','application/json'),('X-Owner-Fixture','v7'),('Content-Length','17')]
        for name,value in base:
            self.assertEqual(self.raw(base+[(name,value)])[0],400)
        self.assertEqual(self.raw(base+[('Transfer-Encoding','chunked')])[0],400)
        for value in ('-1','999999','invalid'):
            headers=[(k,v) for k,v in base if k!='Content-Length']+[('Content-Length',value)]
            self.assertEqual(self.raw(headers)[0],400)

    def test_duplicate_nonfinite_invalid_and_oversized_json_refused(self):
        for body in ('{"action":"next","action":"close"}','{"action":NaN}','[]','not-json','{"action":"next","execute":true}','x'*(MAX_BODY+1)):
            self.assertEqual(self.request('POST','/api/action',body,self.headers())[0],400)
        self.assertEqual(self.ui.bindings,{})

    def test_valid_request_reaches_only_exact_binding_action(self):
        # Wrong confirmation is an application denial, not a CSRF/transport denial.
        b=self.ui.state('alice')['bindings'][0]
        body=json.dumps({'action':'bind','owner':b['owner'],'binding_digest':b['digest'],'confirmation':'wrong'})
        status,_,data=self.request('POST','/api/action',body,self.headers())
        self.assertEqual(status,400);self.assertIn('displayed owner phrase',data.decode())
        self.assertEqual(self.ui.bindings,{})


class UIShutdownFaultTests(unittest.TestCase):
    def test_cleanup_failure_does_not_skip_signers_or_directory_and_can_retry(self):
        calls=[]
        class Failing:
            def close(self):calls.append('executor');raise BrokenPipeError('fixture fault')
        class Signer:
            def close(self):calls.append('signer')
        class Directory:
            def cleanup(self):calls.append('directory')
        ui=OwnerUIService.__new__(OwnerUIService)
        ui.lock=threading.RLock();ui.closed=False;ui.phase='ready'
        ui.executor=Failing();ui.signers={'alice':Signer()};ui.directory=Directory()
        with self.assertRaisesRegex(RuntimeError,'cleanup'):ui.close()
        self.assertEqual(calls,['executor','signer','directory'])
        self.assertTrue(ui.closed);self.assertEqual(ui.phase,'cleanup_uncertain')
        ui.executor=Signer();self.assertEqual(ui.action({'action':'close','confirmation':'DISCARD FIXTURE'}),{'closed':True});self.assertEqual(ui.phase,'closed')
        self.assertEqual(calls[-3:],['signer','signer','directory'])


class HTTPEndToEndTests(unittest.TestCase):
    def test_complete_loopback_http_flow_and_explicit_shutdown(self):
        ui=OwnerUIService();server=LoopbackServer(ui);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        directory=Path(ui.directory.name)
        def call(method,path,body=None,origin=None):
            connection=http.client.HTTPConnection(*server.server_address,timeout=5)
            headers={'Origin':origin or server.origin,'Content-Type':'application/json','X-Owner-Fixture':'v7'} if method=='POST' else {}
            connection.request(method,path,json.dumps(body) if body is not None else None,headers)
            response=connection.getresponse();status=response.status;data=json.loads(response.read());connection.close()
            return status,data
        def action(body):
            status,data=call('POST','/api/action',body);self.assertEqual(status,200,data);return data
        try:
            _,state=call('GET','/api/state?owner=alice')
            for b in state['bindings']:action({'action':'bind','owner':b['owner'],'binding_digest':b['digest'],'confirmation':'BIND '+b['owner']})
            while True:
                step=action({'action':'next'})
                if step['kind']=='complete':break
                if step['kind']=='request':
                    c=step['card'];body={'action':'approve','owner':c['owner'],'request_id':c['request_id'],'review_digest':c['review_digest'],'confirmation':'APPROVE '+c['owner']}
                    self.assertEqual(call('POST','/api/action',body,origin='https://other.example')[0],400)
                    action(body);action({'action':'submit','owner':c['owner'],'request_id':c['request_id']})
                elif step['state']=='queued':action({'action':'attempt','owner':step['owner'],'request_id':step['delivery_id'],'confirmation':'SEND '+step['owner']})
                else:action({'action':'process','owner':step['owner'],'request_id':step['delivery_id']})
            status,state=call('GET','/api/state?owner=alice');self.assertEqual(status,200)
            self.assertEqual(state['summary'],{'agreed':True,'receiver_receipts':12,'transitions':12})
            self.assertEqual(action({'action':'close','confirmation':'DISCARD FIXTURE'}),{'closed':True})
            thread.join(timeout=3);self.assertFalse(thread.is_alive());self.assertFalse(directory.exists())
        finally:
            if thread.is_alive():server.shutdown();thread.join(timeout=2)
            server.server_close();ui.close()


class HTTPConcurrencyBoundTests(unittest.TestCase):
    def test_handler_capacity_is_bounded_without_executing_extra_requests(self):
        from unittest.mock import Mock
        service=Mock();server=LoopbackServer(service)
        try:
            for _ in range(8):self.assertTrue(server.handler_slots.acquire(blocking=False))
            request=Mock();server.process_request(request,('127.0.0.1',12345))
            request.close.assert_called_once();service.action.assert_not_called()
            for _ in range(8):server.handler_slots.release()
        finally:server.server_close()
