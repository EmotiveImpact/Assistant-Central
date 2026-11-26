"""Independent owner-surface boundary regressions; in-process only."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import local_owner_app
import workspace_console
from workspace_ui_service import WorkspaceUIService
from test_workspace_ui import InProcessHTTP


class IndependentContinuitySurfaceReview(unittest.TestCase):
    def scripted(self, workspace, commands):
        output = []
        source = iter(commands)
        def read(prompt):
            output.append(prompt)
            try: value = next(source)
            except StopIteration: raise EOFError
            return value(prompt) if callable(value) else value
        workspace_console.interactive(workspace, read, output.append, continuity=True)
        return '\n'.join(output)

    @staticmethod
    def confirm(prompt):
        return prompt.split('Type ', 1)[1].split(' to commit;', 1)[0]

    def workspace_mock(self):
        w = Mock()
        w.continuity_preview.return_value = {'review_digest': 'a'*64}
        w.continuity_commit.return_value = {}
        w.continuity_state.return_value = {'identities': [], 'associations': []}
        return w

    def test_malformed_commit_attempt_discards_pending_review(self):
        w = self.workspace_mock()
        self.scripted(w, ['continuity-preview {"operation":"enroll","identity_id":"one"}',
                          'continuity-commit extra', 'continuity-commit',
                          lambda p: self.confirm(p) if p.startswith('Type ') else 'quit', 'quit'])
        w.continuity_commit.assert_not_called()

    def test_selected_route_survives_continuity_and_back(self):
        w = self.workspace_mock()
        w.list_tasks.return_value = [{'selector':'garden','context':'frozen'}]
        w.state.return_value = {'phase':'unchanged'}
        self.scripted(w, ['select garden', 'continuity-preview {"operation":"enroll","identity_id":"one"}',
                          'continuity-commit', self.confirm, 'back', 'state alice', 'quit'])
        w.state.assert_called_once_with('garden','frozen','alice')
        w.create.assert_not_called(); w.compose.assert_not_called(); w.action.assert_not_called()

    def test_transport_uncertainty_discards_all_pending_effects(self):
        w = self.workspace_mock()
        w.task_preview.return_value = {'spec':{},'review_digest':'task'}
        w.relationship_preview.return_value = {'operation':'create'}
        w.list_tasks.side_effect = RuntimeError('read transport uncertain')
        out = self.scripted(w, ['task-preview {}','relationship-preview {}',
            'continuity-preview {"operation":"enroll","identity_id":"one"}', 'list',
            'task-create','relationship-commit','continuity-commit','continuity-preview {}',
            'continuity-state','quit'])
        w.compose.assert_not_called(); w.relationship_commit.assert_not_called()
        w.continuity_commit.assert_not_called(); self.assertEqual(w.continuity_preview.call_count,1)
        w.continuity_state.assert_called_once(); self.assertIn('inspection',out)

    def test_nested_ambiguous_json_never_reaches_service(self):
        service = Mock(); http = InProcessHTTP(service)
        for path in ('/api/continuity-preview','/api/action'):
            for raw in ('{"review":{"a":1,"a":2}}', '{"review":{"value":-Infinity}}',
                        '{"review":{"value":1e9999}}', '{"review":', '['*1500):
                with self.subTest(path=path,raw=raw[:50]):
                    self.assertEqual(http.call('POST',path,raw)[0],400)
        service.continuity_preview.assert_not_called(); service.action.assert_not_called()

    def test_missing_security_headers_and_incomplete_body_never_dispatch(self):
        service=Mock(); http=InProcessHTTP(service)
        base=[('Host',http.server.expected_host),('Origin',http.server.origin),
              ('Content-Type','application/json'),('X-Owner-Fixture','v7'),('Content-Length','2')]
        for path in ('/api/continuity-preview','/api/action'):
            for omit in range(len(base)):
                self.assertEqual(http.call('POST',path,'{}',headers=base[:omit]+base[omit+1:],defaults=False)[0],400)
            self.assertEqual(http.call('POST',path,'{',headers=base,defaults=False)[0],400)
        service.continuity_preview.assert_not_called();service.action.assert_not_called()

    def test_read_guards_and_extra_queries_do_not_disclose_state(self):
        service=Mock();http=InProcessHTTP(service)
        for path,headers in (('/api/continuity',[('Host',http.server.expected_host)]),
                             ('/api/continuity',[('Origin','https://other.invalid')]),
                             ('/api/continuity?x=1',[]),('/api/continuity?x=1&x=2',[])):
            self.assertIn(http.call('GET',path,headers=headers)[0],(400,404))
        service.continuity_state.assert_not_called()

    def test_disabled_actions_do_not_create_task_or_registry(self):
        ui=WorkspaceUIService();self.addCleanup(ui.close);http=InProcessHTTP(ui)
        for op in ('enroll','associate','retire'):
            self.assertEqual(http.call('POST','/api/action',{'action':'continuity_'+op,'review':{},'confirmation':op.upper()+' CONTINUITY fake'})[0],400)
        self.assertIsNone(ui.workspace._continuity);self.assertFalse(ui.workspace._slots)
        self.assertEqual(json.loads(http.call('GET','/api/continuity')[2]),{'enabled':False})

    def test_api_does_not_translate_uncertain_result_into_active_success(self):
        ui=WorkspaceUIService(continuity=True);self.addCleanup(ui.close)
        history={'status':'uncertain','active':False,'historical':True,'certificate':None}
        with patch.object(ui.workspace,'continuity_commit',return_value=history) as commit:
            status,_,data=InProcessHTTP(ui).call('POST','/api/action',{'action':'continuity_associate','review':{},'confirmation':'exact'})
        self.assertEqual(status,200);self.assertEqual(json.loads(data),history)
        commit.assert_called_once_with('associate',{},'exact')

    def test_launcher_cleanup_failure_does_not_claim_discard(self):
        with patch('sys.argv',['local_owner_app.py','--workspace','--continuity']), patch('workspace_ui_service.WorkspaceUIService') as factory, patch('local_owner_app.LoopbackServer') as server, redirect_stdout(io.StringIO()) as output:
            factory.return_value.close.side_effect=RuntimeError('cleanup lost')
            with self.assertRaises(RuntimeError):local_owner_app.main()
            factory.return_value.close.assert_called_once();server.return_value.server_close.assert_called_once()
        self.assertNotIn('keys discarded',output.getvalue())

if __name__=='__main__':unittest.main()
