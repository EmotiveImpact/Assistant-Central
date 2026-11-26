"""In-process HTTP parser/handler and real disposable-workspace tests.

No sockets, browser, remote provider, or installed browser dependency is used.
"""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from local_owner_app import Handler, WorkspaceHandler, MAX_BODY, CSP
from network import Denied
from task_fixtures import fixture
from workspace_ui_service import WorkspaceUIService


class MemoryConnection:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()
    def makefile(self, *args):return self.input
    def settimeout(self, timeout):self.timeout = timeout
    def sendall(self, data):self.output.write(data)


class InProcessHTTP:
    def __init__(self, service, handler=WorkspaceHandler):
        self.server = SimpleNamespace(service=service, expected_host='127.0.0.1:49123',
                                      origin='http://127.0.0.1:49123', shutdown=Mock())
        self.handler = handler

    def call(self, method, path, body=None, headers=None, defaults=True):
        if isinstance(body, dict):body = json.dumps(body).encode()
        elif isinstance(body, str):body = body.encode()
        body = body or b''
        lines = [('Host', self.server.expected_host)] if defaults else []
        if defaults and method == 'POST':
            lines += [('Origin', self.server.origin), ('Content-Type', 'application/json'),
                      ('X-Owner-Fixture', 'v7'), ('Content-Length', str(len(body)))]
        lines += headers or []
        request = (method+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in lines)+'\r\n').encode()+body
        connection = MemoryConnection(request)
        self.handler(connection, ('127.0.0.1', 12345), self.server)
        raw = connection.output.getvalue()
        head, data = raw.split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        response_headers = dict(line.split(': ', 1) for line in lines[1:])
        return int(lines[0].split()[1]), response_headers, data


class WorkspaceHandlerTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.tasks.return_value = []
        self.service.state.return_value = {'phase':'bindings'}
        self.service.review.return_value = {'state':'pending'}
        self.service.delivery.return_value = {'state':'uncertain'}
        self.service.proposals.return_value = []
        self.service.action.return_value = {'task_closed':True}
        self.http = InProcessHTTP(self.service)
        self.scope = {'selector':'garden','context':'a'*64,'owner':'alice'}

    def test_scoped_reads_route_exact_immutable_arguments(self):
        for endpoint in ('state','review','delivery','proposals'):
            fields = dict(self.scope)
            if endpoint in ('review','delivery'):fields['id'] = 'request-1'
            status, _, _ = self.http.call('GET','/api/'+endpoint+'?'+urlencode(fields))
            self.assertEqual(status,200)
            args = ('garden','a'*64,'alice') + (('request-1',) if 'id' in fields else ())
            getattr(self.service,endpoint).assert_called_once_with(*args)
        self.service.action.assert_not_called()

    def test_metadata_read_does_not_create_or_select(self):
        self.assertEqual(self.http.call('GET','/api/tasks')[0],200)
        self.service.tasks.assert_called_once_with()
        self.service.action.assert_not_called()
        self.assertEqual(self.http.call('GET','/api/tasks?selector=garden')[0],404)

    def test_missing_duplicate_blank_extra_scope_fields_do_not_route(self):
        for endpoint in ('state','review','delivery','proposals'):
            valid = dict(self.scope)
            if endpoint in ('review','delivery'):valid['id']='r'
            for key in valid:
                missing = dict(valid);missing.pop(key)
                blank = dict(valid);blank[key]=''
                for query in (urlencode(missing),urlencode(blank),urlencode(valid)+'&'+key+'=other',urlencode(valid)+'&'+key+'='):
                    with self.subTest(endpoint=endpoint,query=query):
                        self.assertNotEqual(self.http.call('GET','/api/'+endpoint+'?'+query)[0],200)
            self.assertNotEqual(self.http.call('GET','/api/'+endpoint+'?'+urlencode(valid)+'&extra=1')[0],200)
            getattr(self.service,endpoint).assert_not_called()

    def test_explicit_post_routes_wrapper_and_never_shuts_down_workspace(self):
        body={'selector':'garden','context':'a'*64,'request':{'action':'close','confirmation':'DISCARD FIXTURE'}}
        self.assertEqual(self.http.call('POST','/api/action',body)[0],200)
        self.service.action.assert_called_once_with(body)
        self.http.server.shutdown.assert_not_called()

    def test_security_headers_and_static_allowlist_are_inherited(self):
        with TemporaryDirectory() as directory:
            for file in ('index.html','app.js','style.css'):(Path(directory)/file).write_text('workspace fixture')
            with patch.object(WorkspaceHandler,'static_root',Path(directory)):
                for path in ('/','/app.js','/style.css'):
                    status,headers,data=self.http.call('GET',path)
                    self.assertEqual(status,200);self.assertEqual(data,b'workspace fixture')
                    self.assertEqual(headers['Content-Security-Policy'],CSP)
                    self.assertEqual(headers['Cache-Control'],'no-store')
                    self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
                    self.assertEqual(headers['X-Frame-Options'],'DENY')
                    self.assertEqual(headers['Cross-Origin-Resource-Policy'],'same-origin')
                    self.assertNotIn('Access-Control-Allow-Origin',headers)
                for path in ('/../workspace_ui_service.py','/%2e%2e/workspace_ui_service.py','/style.css?extra=1','/owner_ui/app.js'):
                    self.assertNotEqual(self.http.call('GET',path)[0],200)

    def test_absolute_urls_wrong_hosts_and_duplicate_hosts_fail(self):
        for host in ('evil.example','localhost:49123','127.0.0.1:49123.evil','127.0.0.1:49123@evil'):
            self.assertEqual(self.http.call('GET','/api/tasks',headers=[('Host',host)],defaults=False)[0],400)
        self.assertEqual(self.http.call('GET','http://evil.example/api/tasks')[0],400)
        self.assertEqual(self.http.call('GET','/api/tasks',headers=[('Host',self.http.server.expected_host)])[0],400)
        self.service.tasks.assert_not_called()

    def test_origin_fetch_site_and_json_header_protections(self):
        base=[('Host',self.http.server.expected_host),('Origin',self.http.server.origin),
              ('Content-Type','application/json'),('X-Owner-Fixture','v7'),('Content-Length','2')]
        for field,value in [('Origin','null'),('Origin','http://evil.example'),('Content-Type','text/plain'),
                            ('Content-Type','application/json; charset=utf-8'),('X-Owner-Fixture','v17')]:
            headers=[(k,v if k!=field else value) for k,v in base]
            self.assertEqual(self.http.call('POST','/api/action','{}',headers,False)[0],400)
        for key in ('Host','Origin','Content-Type','X-Owner-Fixture','Content-Length'):
            self.assertEqual(self.http.call('POST','/api/action','{}',[(k,v) for k,v in base if k!=key],False)[0],400)
            duplicate=next(pair for pair in base if pair[0]==key)
            self.assertEqual(self.http.call('POST','/api/action','{}',base+[duplicate],False)[0],400)
        for extra in [('Sec-Fetch-Site','cross-site'),('Transfer-Encoding','chunked')]:
            self.assertEqual(self.http.call('POST','/api/action','{}',base+[extra],False)[0],400)
        self.service.action.assert_not_called()

    def test_body_limits_duplicates_nonfinite_and_truncation_fail(self):
        for body in ('{"request":{"action":"create","action":"next"}}','{"selector":NaN}','not json','x'*(MAX_BODY+1)):
            self.assertEqual(self.http.call('POST','/api/action',body)[0],400)
        headers=[('Host',self.http.server.expected_host),('Origin',self.http.server.origin),
                 ('Content-Type','application/json'),('X-Owner-Fixture','v7')]
        for length in ('0','-1','invalid',str(MAX_BODY+1),'100'):
            self.assertEqual(self.http.call('POST','/api/action','{}',headers+[('Content-Length',length)],False)[0],400)
        self.service.action.assert_not_called()

    def test_unknown_methods_and_routes_do_not_mutate(self):
        for method in ('PUT','DELETE','OPTIONS'):
            self.assertEqual(self.http.call(method,'/api/action')[0],405)
        self.assertEqual(self.http.call('POST','/api/action?selector=garden','{}')[0],404)
        self.assertEqual(self.http.call('POST','http://evil.example/api/action','{}')[0],404)
        self.service.action.assert_not_called()

    def test_cleanup_and_lost_response_errors_are_uncertain_and_not_retried(self):
        self.service.action.side_effect=RuntimeError('internal details')
        status,_,body=self.http.call('POST','/api/action','{}')
        self.assertEqual(status,503);self.assertIn('uncertain',body.decode())
        self.assertNotIn('internal details',body.decode());self.service.action.assert_called_once()
        self.http.server.shutdown.assert_not_called()

    def test_legacy_handler_routes_unchanged_and_does_not_accept_workspace_scope(self):
        legacy=InProcessHTTP(self.service,Handler)
        self.assertEqual(legacy.call('GET','/api/state?owner=alice')[0],200)
        self.service.state.assert_called_once_with('alice')
        self.assertEqual(legacy.call('GET','/api/tasks')[0],404)
        self.assertEqual(legacy.call('GET','/api/state?'+urlencode(self.scope))[0],404)
        self.assertEqual(Handler.static_root.name,'owner_ui')
        self.assertEqual(WorkspaceHandler.static_root.name,'workspace_ui')


class WorkspaceUIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.ui=WorkspaceUIService();self.addCleanup(self.ui.close)
        self.rows={row['selector']:row for row in self.ui.tasks()}
        self.http=InProcessHTTP(self.ui)
    def action(self,key,**request):
        return self.ui.action({'selector':key,'context':self.rows[key]['context'],'request':request})
    def create(self,key):self.action(key,action='create')
    def state(self,key,owner=None):
        row=self.rows[key];return self.ui.state(key,row['context'],owner or row['requester'])
    def ready(self,key):
        self.create(key)
        for b in self.state(key)['bindings']:
            self.action(key,action='bind',owner=b['owner'],binding_digest=b['digest'],confirmation='BIND '+b['owner'])
    def approve_submit(self,key,card):
        self.action(key,action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
        self.action(key,action='submit',owner=card['owner'],request_id=card['request_id'])

    def test_initial_metadata_and_reads_never_create_services(self):
        self.assertEqual([r['phase'] for r in self.ui.tasks()],['not_created','not_created'])
        self.assertFalse(self.ui.workspace._slots)
        for endpoint in ('state','review','delivery','proposals'):
            row=self.rows['garden'];fields={k:row[k] for k in ('selector','context')};fields['owner']='alice'
            if endpoint in ('review','delivery'):fields['id']='r'
            self.assertEqual(self.http.call('GET','/api/'+endpoint+'?'+urlencode(fields))[0],400)
        self.assertFalse(self.ui.workspace._slots)

    def test_explicit_create_starts_only_selected_service_without_bindings(self):
        self.create('astronomy')
        self.assertEqual(set(self.ui.workspace._slots),{'astronomy'})
        self.assertEqual(self.state('astronomy')['phase'],'bindings')
        self.assertFalse(any(b['approved'] for b in self.state('astronomy')['bindings']))
        with self.assertRaises(Denied):self.create('astronomy')

    def test_closed_action_wrapper_schema_and_context_reject_without_effect(self):
        valid={'selector':'garden','context':self.rows['garden']['context'],'request':{'action':'create'}}
        invalid=[[],{},dict(valid,extra=True),dict(valid,context=self.rows['astronomy']['context']),
                 dict(valid,selector=[]),dict(valid,request=[]),dict(valid,request={'action':'create','approve':True}),
                 dict(valid,request={'action':'import_proposal','owner':'alice','proposal_id':'x','execute':True})]
        for field in valid:
            bad=dict(valid);bad.pop(field);invalid.append(bad)
        for body in invalid:
            with self.assertRaises(Denied):self.ui.action(body)
        self.assertFalse(self.ui.workspace._slots)

    def test_startup_failure_is_an_occupied_uncertain_slot_not_success(self):
        with patch('owner_workspace.OwnerUIService',side_effect=RuntimeError('startup failed')):
            with self.assertRaises(RuntimeError):self.create('garden')
        self.assertEqual(self.ui.tasks()[0]['phase'],'startup_failed_cleanup_uncertain')
        with self.assertRaises(Denied):self.create('garden')
        with self.assertRaises(Denied):self.state('garden')
        self.create('astronomy');self.assertEqual(self.state('astronomy')['phase'],'bindings')
        # There was deliberately no child constructor in this injected fault.
        # Clear just the test tombstone so normal tearDown can clean the other task.
        self.ui.workspace._slots.pop('garden')

    def test_untrusted_adapter_and_raw_process_commands_not_exposed(self):
        self.ready('garden')
        for action in ('adapter','fixture_agent_call','sign','request_resolve','enqueue','propose','reopen_storage'):
            with self.assertRaises(Denied):self.action('garden',action=action)
        self.assertEqual(self.state('garden')['inbox'],[])
        self.assertEqual(self.state('garden')['summary']['transitions'],0)

    def test_cross_task_reads_and_review_mutations_are_refused(self):
        for key in self.rows:self.ready(key)
        card=self.action('garden',action='next')['card']
        ctx=self.rows['astronomy']['context']
        with self.assertRaises(Denied):self.ui.review('astronomy',ctx,card['owner'],card['request_id'])
        with self.assertRaises(Denied):self.action('astronomy',action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
        with self.assertRaises(Denied):self.ui.state('garden',ctx,'alice')
        self.assertEqual(self.state('astronomy')['inbox'],[])
        self.assertEqual(self.ui.review('garden',self.rows['garden']['context'],card['owner'],card['request_id'])['state'],'pending')

    def test_in_process_http_close_is_confirmed_isolated_and_tombstoned(self):
        for key in self.rows:self.create(key)
        row=self.rows['garden']
        request={'selector':'garden','context':row['context'],'request':{'action':'close','confirmation':'yes'}}
        self.assertEqual(self.http.call('POST','/api/action',request)[0],400)
        request['request']['confirmation']='DISCARD FIXTURE'
        status,_,data=self.http.call('POST','/api/action',request)
        self.assertEqual(status,200);self.assertTrue(json.loads(data)['task_closed'])
        self.http.server.shutdown.assert_not_called()
        self.assertEqual(self.state('astronomy')['phase'],'bindings')
        self.assertEqual(self.ui.tasks()[0]['phase'],'closed')
        with self.assertRaises(Denied):self.create('garden')
        with self.assertRaises(Denied):self.action('garden',action='next')

    def test_cleanup_uncertainty_is_visible_and_blocks_only_affected_task(self):
        for key in self.rows:self.create(key)
        service=self.ui.workspace._slots['garden']['service']
        with patch.object(service,'close',side_effect=RuntimeError('cleanup failed')):
            with self.assertRaises(RuntimeError):self.action('garden',action='close',confirmation='DISCARD FIXTURE')
        self.assertEqual(self.ui.tasks()[0]['phase'],'cleanup_uncertain')
        with self.assertRaises(Denied):self.state('garden')
        with self.assertRaises(Denied):self.action('garden',action='next')
        self.assertEqual(self.state('astronomy')['phase'],'bindings')

    def test_proposal_discovery_and_import_preserve_unsigned_and_declined_history(self):
        key='garden';self.ready(key)
        for _ in range(2):self.approve_submit(key,self.action(key,action='next')['card'])
        row=self.rows[key];service=self.ui.workspace._slots[key]['service']
        service._command('fixture_agent_call',actor='alice',command={'method':'propose','proposal_id':'ui-proposal','envelope':fixture(key)[2]})
        proposals=self.ui.proposals(key,row['context'],'alice')
        self.assertEqual(proposals[0]['proposal_id'],'ui-proposal')
        card=self.action(key,action='import_proposal',owner='alice',proposal_id='ui-proposal')['card']
        self.assertEqual(card['state'],'pending')
        self.action(key,action='decline',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'])
        again=self.action(key,action='import_proposal',owner='alice',proposal_id='ui-proposal')['card']
        self.assertEqual(again['request_id'],card['request_id']);self.assertEqual(again['state'],'declined')
        self.assertEqual(self.state(key)['summary']['transitions'],0)

    def test_complete_both_tasks_through_in_process_http_handler(self):
        for key in self.rows:
            def act(**request):
                body={'selector':key,'context':self.rows[key]['context'],'request':request}
                status,_,data=self.http.call('POST','/api/action',body)
                self.assertEqual(status,200,data);return json.loads(data)
            act(action='create')
            for b in self.state(key)['bindings']:
                act(action='bind',owner=b['owner'],binding_digest=b['digest'],confirmation='BIND '+b['owner'])
            for _ in range(30):
                step=act(action='next')
                if step['kind']=='complete':break
                if step['kind']=='request':
                    c=step['card'];act(action='approve',owner=c['owner'],request_id=c['request_id'],review_digest=c['review_digest'],confirmation='APPROVE '+c['owner'])
                    act(action='submit',owner=c['owner'],request_id=c['request_id'])
                elif step['state']=='queued':act(action='attempt',owner=step['owner'],request_id=step['delivery_id'],confirmation='SEND '+step['owner'])
                else:act(action='process',owner=step['owner'],request_id=step['delivery_id'])
            else:self.fail('Guide did not complete')
            self.assertEqual(self.state(key)['summary']['task_state'],'completed')
            self.assertEqual(self.state(key)['summary']['transitions'],2)
            self.assertEqual(self.state(key)['summary']['receiver_receipts'],2)


if __name__=='__main__':unittest.main()
