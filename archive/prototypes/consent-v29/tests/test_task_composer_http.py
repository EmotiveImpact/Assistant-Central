"""In-process HTTP coverage for the pure composer preview and explicit create.

No sockets or browser acceptance are implied by these handler-level tests.
"""
import copy
import json
import unittest
from unittest.mock import Mock
from local_owner_app import Handler
from workspace_ui_service import WorkspaceUIService
from test_workspace_ui import InProcessHTTP

SPEC = {'selector':'custom-library','task_id':'library-task','conversation_id':'fictional-library',
        'requester':'bob','query':'Fictional public library resources','max_items':2}


class ComposerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.ui=WorkspaceUIService();self.addCleanup(self.ui.close)
        self.http=InProcessHTTP(self.ui)
    def call(self,path,body):
        status,_,data=self.http.call('POST',path,body)
        return status,json.loads(data)
    def preview(self):
        status,result=self.call('/api/task-preview',{'spec':SPEC})
        self.assertEqual(status,200,result)
        return result
    def test_preview_read_only_and_exact_create_has_no_approved_binding(self):
        preview=self.preview()
        self.assertEqual(preview['spec'],SPEC)
        self.assertEqual(preview['selector'],SPEC['selector'])
        self.assertFalse(self.ui.workspace._slots)
        self.assertEqual(len(self.ui.tasks()),2)
        body={'action':'compose_task','spec':SPEC,'review_digest':preview['review_digest'],'confirmation':'CREATE TASK'}
        status,row=self.call('/api/action',body)
        self.assertEqual(status,200,row)
        self.assertEqual(row['phase'],'open')
        self.assertEqual(row['context'],preview['context'])
        self.assertEqual((row['requester'],row['responder']),('bob','alice'))
        state=self.ui.state(row['selector'],row['context'],'bob')
        self.assertEqual(state['phase'],'bindings')
        self.assertFalse(any(b['approved'] for b in state['bindings']))
        self.http.server.shutdown.assert_not_called()
    def test_preview_strict_wrapper_and_scope_shape(self):
        for body in ({},[],{'spec':SPEC,'confirmation':'CREATE TASK'},{'selector':'garden','context':'a'*64,'request':{'action':'preview'}}, {'spec':dict(SPEC,extra=True)}):
            with self.subTest(body=body):self.assertEqual(self.call('/api/task-preview',body)[0],400)
        self.assertFalse(self.ui.workspace._slots)
    def test_changed_spec_wrong_confirmation_and_extra_fields_never_create(self):
        preview=self.preview()
        valid={'action':'compose_task','spec':SPEC,'review_digest':preview['review_digest'],'confirmation':'CREATE TASK'}
        bodies=[dict(valid,confirmation='yes'),dict(valid,review_digest='0'*64),dict(valid,approve=True)]
        for field,value in [('query','Different exact query'),('requester','alice'),('max_items',3),('task_id','other-task'),('selector','custom-other'),('conversation_id','other-conversation')]:
            bodies.append(dict(valid,spec={**SPEC,field:value}))
        for body in bodies:
            with self.subTest(body=body):self.assertEqual(self.call('/api/action',body)[0],400)
        self.assertFalse(self.ui.workspace._slots)
    def test_preview_header_origin_limits_and_duplicate_json_are_preserved(self):
        for headers in ([('Origin','https://evil.invalid')],[('Sec-Fetch-Site','cross-site')],[('Content-Type','text/plain')]):
            self.assertEqual(self.http.call('POST','/api/task-preview',{'spec':SPEC},headers)[0],400)
        body='{"spec":'+json.dumps(SPEC)+',"spec":'+json.dumps(SPEC)+'}'
        self.assertEqual(self.call('/api/task-preview',body)[0],400)
        self.assertEqual(self.call('/api/task-preview','x'*8193)[0],400)
        self.assertEqual(self.call('/api/task-preview',{'spec':dict(SPEC,max_items=float('inf'))})[0],400)
        self.assertFalse(self.ui.workspace._slots)
    def test_legacy_and_other_routes_do_not_expose_composer(self):
        legacy=InProcessHTTP(self.ui,Handler)
        self.assertEqual(legacy.call('POST','/api/task-preview',{'spec':SPEC})[0],404)
        for path in ('/api/task-preview?extra=1','http://evil.invalid/api/task-preview','/api/task-preview/','/api/compose'):
            self.assertEqual(self.call(path,{'spec':SPEC})[0],404)
        self.assertFalse(self.ui.workspace._slots)
    def test_duplicate_exact_creation_is_refused_not_recreated(self):
        preview=self.preview()
        body={'action':'compose_task','spec':SPEC,'review_digest':preview['review_digest'],'confirmation':'CREATE TASK'}
        self.assertEqual(self.call('/api/action',body)[0],200)
        original=self.ui.workspace._slots[SPEC['selector']]['service']
        roots=copy.deepcopy(original.roots)
        self.assertEqual(self.call('/api/action',body)[0],400)
        self.assertIs(self.ui.workspace._slots[SPEC['selector']]['service'],original)
        self.assertEqual(original.roots,roots)

if __name__=='__main__':unittest.main()
