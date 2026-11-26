"""Trusted owner plumbing only: no sockets, browser or live provider."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import Mock, patch

import local_owner_app
import workspace_console
from local_owner_app import Handler
from network import Denied
from owner_workspace import OwnerWorkspace
from workspace_ui_service import WorkspaceUIService
from test_workspace_ui import InProcessHTTP


class ContinuityOwnerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.ui = WorkspaceUIService(continuity=True)
        self.addCleanup(self.ui.close)
        self.http = InProcessHTTP(self.ui)

    def call(self, path, body=None, method='POST', **kw):
        status, _, data = self.http.call(method, path, body, **kw)
        return status, json.loads(data)

    def preview(self, operation, **fields):
        status, review = self.call('/api/continuity-preview', dict(operation=operation, **fields))
        self.assertEqual(status, 200, review)
        return review

    def commit(self, operation, review):
        return self.call('/api/action', {'action': 'continuity_'+operation,
            'review': review, 'confirmation': operation.upper()+' CONTINUITY '+review['review_digest']})

    def enroll(self):
        review = self.preview('enroll', identity_id='fictional-one')
        self.assertEqual(self.commit('enroll', review)[0], 200)
        return review

    def associate(self):
        row = self.ui.tasks()[0]
        self.ui.workspace.create(row['selector'], row['context'])
        review = self.preview('associate', identity_id='fictional-one', association_id='proof-one',
                              selector=row['selector'], context=row['context'], actor='alice')
        status, result = self.commit('associate', review)
        self.assertEqual(status, 200, result)
        return row, review, result

    def test_disabled_default_has_no_registry_or_process_and_refuses_writes(self):
        with patch('continuity_workspace.JsonProcess') as process:
            ui = WorkspaceUIService()
            self.addCleanup(ui.close)
            http = InProcessHTTP(ui)
            self.assertEqual(json.loads(http.call('GET', '/api/continuity')[2]), {'enabled': False})
            self.assertIsNone(ui.workspace._continuity)
            self.assertEqual(http.call('POST', '/api/continuity-preview', {'operation':'enroll','identity_id':'one'})[0],400)
            self.assertEqual(http.call('POST', '/api/action', {'action':'continuity_enroll','review':{},'confirmation':'yes'})[0],400)
            process.assert_not_called()
        for value in (None, 1, 'true', []):
            with self.assertRaises(Denied): WorkspaceUIService(continuity=value)

    def test_opt_in_and_preview_do_not_start_any_signer_or_task(self):
        with patch('continuity_workspace.JsonProcess') as process:
            review = self.preview('enroll', identity_id='fictional-one')
            status, state = self.call('/api/continuity', method='GET')
            self.assertEqual(status, 200)
            self.assertEqual(set(state), {'enabled','incarnation','identities','associations'})
            self.assertEqual(state['identities'], [])
            self.assertFalse(self.ui.workspace._slots)
            process.assert_not_called()
            review['identity_id'] = 'changed'
            self.assertEqual(self.commit('enroll', review)[0], 400)

    def test_closed_schema_and_full_confirmation(self):
        review = self.preview('enroll', identity_id='fictional-one')
        valid = {'action':'continuity_enroll','review':review,'confirmation':'ENROLL CONTINUITY '+review['review_digest']}
        for body in ({}, [], {'operation':'enroll','identity_id':'fictional-one','extra':True},
                     {'operation':'unknown'}, {'operation':'enroll','identity_id':True}):
            self.assertEqual(self.call('/api/continuity-preview', json.dumps(body))[0], 400)
        for body in (dict(valid, extra=True), dict(valid, confirmation='ENROLL CONTINUITY'),
                     dict(valid, action='continuity_sign'), dict(valid, confirmation=True),
                     {'action':'continuity_enroll','review':review}):
            self.assertEqual(self.call('/api/action', body)[0], 400)
        self.assertEqual(self.ui.continuity_state()['identities'], [])

    def test_host_origin_json_and_body_guards_apply(self):
        request = {'operation':'enroll','identity_id':'fictional-one'}
        for headers in ([('Host','evil.invalid')], [('Origin','https://evil.invalid')],
                        [('Content-Type','text/plain')], [('Sec-Fetch-Site','cross-site')],
                        [('Transfer-Encoding','chunked')], [('Content-Length','2')]):
            self.assertEqual(self.call('/api/continuity-preview', request, headers=headers)[0],400)
        for raw in ('{"operation":"enroll","operation":"retire"}', 'x'*8193,
                    '{"operation":"enroll","identity_id":NaN}', '{"operation":"enroll","identity_id":1e999}'):
            self.assertEqual(self.call('/api/continuity-preview', raw)[0],400)
        self.assertEqual(self.ui.continuity_state()['identities'], [])

    def test_no_query_aliases_or_legacy_continuity_routes(self):
        for path in ('/api/continuity?x=1','/api/continuity/','/api/continuity?enabled=true'):
            self.assertEqual(self.call(path, method='GET')[0],404)
        for path in ('/api/continuity?x=1&x=2','/api/continuity?x='):
            self.assertEqual(self.call(path, method='GET')[0],400)
        legacy = InProcessHTTP(self.ui, Handler)
        self.assertEqual(legacy.call('GET','/api/continuity')[0],404)
        self.assertEqual(legacy.call('POST','/api/continuity-preview',{})[0],404)
        for path in ('/api/continuity-preview?x=1','/api/continuity-preview/','http://evil.invalid/api/continuity-preview'):
            self.assertEqual(self.call(path, {})[0],404)

    def test_enroll_associate_retire_is_detached_informational_history(self):
        enrollment = self.enroll()
        row, review, result = self.associate()
        self.assertEqual(result['status'], 'active')
        state_before = self.ui.state(row['selector'], row['context'], 'alice')
        retire = self.preview('retire', identity_id='fictional-one')
        self.assertEqual(self.commit('retire', retire)[0],200)
        self.assertEqual(self.ui.state(row['selector'], row['context'], 'alice'), state_before)
        with patch('continuity_workspace.JsonProcess') as process:
            status, history = self.commit('associate', review)
            self.assertEqual((status, history['status'], history['historical']), (200,'retired',True))
            self.assertFalse(history['active'])
            self.assertEqual(history['certificate'],result['certificate'])
            self.assertEqual(self.commit('enroll', enrollment)[0],200)
            process.assert_not_called()
        history['certificate']['body']['actor'] = 'changed'
        self.assertEqual(self.ui.continuity_state()['associations'][0]['certificate'], result['certificate'])
        state = self.ui.continuity_state()
        self.assertEqual(set(state['identities'][0]), {'anchor','phase','cleanup'})
        self.assertEqual(set(state['identities'][0]['anchor']), {'incarnation','identity_id','identity_version','continuity_root','fingerprint'})
        self.http.server.shutdown.assert_not_called()

    def test_expired_review_never_signs_and_expired_certificate_retry_keeps_history(self):
        self.enroll()
        row, review, result = self.associate()
        with patch('continuity_workspace.time.time', return_value=review['body']['certificate_expires_at']):
            status, history = self.commit('associate', review)
            self.assertEqual((status,history['status']), (200,'expired'))
            self.assertEqual(history['certificate'],result['certificate'])
        pending = self.preview('associate',identity_id='fictional-one',association_id='proof-two',selector=row['selector'],context=row['context'],actor='alice')
        with patch('continuity_workspace.time.time', return_value=pending['body']['review_expires_at']):
            self.assertEqual(self.commit('associate', pending)[0],400)
        self.assertEqual(len(self.ui.continuity_state()['associations']),1)

    def test_stopped_and_closed_tasks_fence_new_proofs_but_preserve_exact_retry(self):
        self.enroll()
        row, review, result = self.associate()
        group = self.ui.relationship_preview({'operation':'create','spec':{'group_id':'group-one','label':'One','members':[{k:row[k] for k in ('selector','context')}]}})
        self.ui.action({'action':'relationship_create','review':group,'confirmation':'CREATE GROUP'})
        stop = self.ui.relationship_preview({'operation':'stop','group_id':'group-one'})
        self.ui.action({'action':'relationship_stop','review':stop,'confirmation':'STOP GROUP'})
        self.assertEqual(self.commit('associate',review)[1]['status'],'stopped')
        request = {'operation':'associate','identity_id':'fictional-one','association_id':'proof-two','selector':row['selector'],'context':row['context'],'actor':'alice'}
        self.assertEqual(self.call('/api/continuity-preview', request)[0],400)
        self.ui.workspace.action(row['selector'],row['context'],{'action':'close','confirmation':'DISCARD FIXTURE'})
        self.assertEqual(self.commit('associate',review)[1]['status'],'closed')
        self.assertEqual(self.call('/api/continuity-preview', request)[0],400)

    def test_uncertain_enrollment_is_observable_and_exact_retry_never_restarts(self):
        review = self.preview('enroll', identity_id='fictional-one')
        with patch('continuity_workspace.JsonProcess', side_effect=RuntimeError('startup lost')) as process:
            self.assertEqual(self.commit('enroll',review)[0],503)
            self.assertEqual(self.ui.continuity_state()['identities'][0]['phase'],'uncertain')
            self.assertEqual(self.commit('enroll',review)[0],200)
            self.assertEqual(process.call_count,1)
        self.assertEqual(self.call('/api/continuity-preview',{'operation':'enroll','identity_id':'fictional-one'})[0],400)


    def test_uncertain_association_response_is_historical_and_never_resigned(self):
        self.enroll()
        row = self.ui.tasks()[0]
        self.ui.workspace.create(row['selector'],row['context'])
        review = self.preview('associate',identity_id='fictional-one',association_id='proof-failed',selector=row['selector'],context=row['context'],actor='alice')
        signer = self.ui.workspace._slots[row['selector']]['service'].signers['alice']
        with patch.object(signer, 'request', return_value={'ok':False}) as request:
            self.assertEqual(self.commit('associate',review)[0],400)
            status, history = self.commit('associate',review)
            self.assertEqual((status,history['status'],history['certificate']), (200,'uncertain',None))
            request.assert_called_once()
        self.assertEqual(self.ui.continuity_state()['associations'][0],history)

    def test_retirement_cleanup_uncertainty_does_not_reactivate_or_sign(self):
        self.enroll()
        review = self.preview('retire',identity_id='fictional-one')
        signer = self.ui.workspace._continuity.identities['fictional-one']['signer']
        with patch.object(signer,'close',side_effect=RuntimeError('disposal lost')) as close, patch.object(signer,'request') as request:
            self.assertEqual(self.commit('retire',review)[0],503)
            state = self.ui.continuity_state()['identities'][0]
            self.assertEqual((state['phase'],state['cleanup']),('retired','uncertain'))
            close.assert_called_once();request.assert_not_called()
        self.assertEqual(self.commit('retire',review)[0],200)
        self.assertEqual(self.ui.continuity_state()['identities'][0]['cleanup'],'disposed')

    def test_closed_workspace_state_and_exact_association_history_remain_readable(self):
        self.enroll()
        row, review, original = self.associate()
        self.ui.close()
        self.assertEqual(self.call('/api/continuity',method='GET')[0],200)
        status, history = self.commit('associate',review)
        self.assertEqual((status,history['status']), (200,'retired'))
        self.assertEqual(history['certificate'],original['certificate'])
        self.assertEqual(self.call('/api/continuity-preview',{'operation':'enroll','identity_id':'two'})[0],400)


class ContinuityConsoleTests(unittest.TestCase):
    def script(self, w, commands, enabled=True, hook=None):
        source = iter(commands); output=[]
        def read(prompt):
            output.append(prompt)
            if hook: hook(prompt)
            try:
                value=next(source)
                return value(prompt) if callable(value) else value
            except StopIteration: raise EOFError
        workspace_console.interactive(w,read,output.append,continuity=enabled)
        return '\n'.join(output)

    @staticmethod
    def phrase(prompt):
        return prompt.split('Type ',1)[1].split(' to commit;',1)[0]

    def test_default_disabled_commands_do_not_call_core(self):
        w=Mock()
        out=self.script(w,['continuity-state','continuity-preview {"operation":"enroll","identity_id":"one"}','continuity-commit','quit'],enabled=False)
        self.assertIn('"enabled": false',out)
        self.assertIn('not enabled',out)
        w.continuity_state.assert_not_called();w.continuity_preview.assert_not_called();w.continuity_commit.assert_not_called()

    def test_full_phrase_preview_freeze_and_no_implicit_retry(self):
        w=Mock()
        review={'operation':'enroll','identity_id':'one','review_digest':'original'}
        w.continuity_preview.return_value=review
        w.continuity_state.return_value={'identities':[],'associations':[]}
        w.continuity_commit.return_value={}
        def mutate(prompt):
            if prompt.startswith('Type '):review['identity_id']='mutated';review['review_digest']='mutated'
        out=self.script(w,['continuity-preview {"operation":"enroll","identity_id":"one"}','continuity-commit',self.phrase,'continuity-commit','quit'],hook=mutate)
        w.continuity_commit.assert_called_once_with('enroll',{'operation':'enroll','identity_id':'one','review_digest':'original'},'ENROLL CONTINUITY original')
        self.assertIn('Preview an exact continuity operation first',out)

    def test_back_invalid_preview_and_wrong_phrase_consume_review(self):
        for tail in (['back'], ['continuity-preview {"operation":"enroll","operation":"retire"}'], ['continuity-commit','ENROLL CONTINUITY']):
            w=Mock();w.continuity_preview.return_value={'operation':'enroll','review_digest':'abc'}
            out=self.script(w,['continuity-preview {"operation":"enroll","identity_id":"one"}',*tail,'continuity-commit','quit'])
            w.continuity_commit.assert_not_called()
            self.assertIn('Preview an exact continuity operation first',out)

    def test_uncertainty_preserves_only_continuity_state_inspection(self):
        for failure in (RuntimeError('lost'),Denied('proof uncertain')):
            w=Mock();w.continuity_preview.return_value={'review_digest':'abc'}
            w.continuity_commit.side_effect=failure
            w.continuity_state.return_value={'identities':[],'associations':[{'status':'uncertain'}]}
            out=self.script(w,['continuity-preview {"operation":"associate"}','continuity-commit',self.phrase,'continuity-preview {"operation":"associate"}','continuity-commit','continuity-state','quit'])
            self.assertEqual(w.continuity_preview.call_count,1)
            self.assertEqual(w.continuity_commit.call_count,1)
            self.assertEqual(w.continuity_state.call_count,2)
            self.assertIn('Inspection only',out)
            self.assertIn('read-only inspection',out)

    def test_scripted_real_enrollment_and_retirement_grant_no_task_authority(self):
        w=OwnerWorkspace(continuity=True);self.addCleanup(w.close)
        out=self.script(w,['continuity-preview {"operation":"enroll","identity_id":"one"}','continuity-commit',self.phrase,'continuity-state','continuity-preview {"operation":"retire","identity_id":"one"}','continuity-commit',self.phrase,'quit'])
        self.assertEqual(w.continuity_state()['identities'][0]['phase'],'retired')
        self.assertFalse(w._slots)
        self.assertIn('ENROLL CONTINUITY ',out);self.assertIn('RETIRE CONTINUITY ',out)

    def test_no_argument_commands_reject_extra_fields(self):
        w=Mock()
        self.script(w,['continuity-state extra','continuity-commit extra','quit'])
        w.continuity_state.assert_not_called();w.continuity_commit.assert_not_called()


class ContinuityLauncherTests(unittest.TestCase):
    def test_browser_requires_workspace_and_rejects_bad_flags_before_resources(self):
        for args in (['--continuity'], ['--continuity=true'], ['--continuity','--workspace','--unknown']):
            with patch('sys.argv',['local_owner_app.py',*args]), patch('local_owner_app.LoopbackServer') as server, patch('local_owner_app.OwnerUIService') as legacy, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:local_owner_app.main()
                self.assertEqual(exc.exception.code,2);server.assert_not_called();legacy.assert_not_called()

    def test_browser_explicit_flag_is_forwarded_and_default_is_false(self):
        for enabled in (False,True):
            argv=['local_owner_app.py','--workspace']+(['--continuity'] if enabled else [])
            with patch('sys.argv',argv), patch('local_owner_app.LoopbackServer') as server, patch('workspace_ui_service.WorkspaceUIService') as service, redirect_stdout(io.StringIO()):
                local_owner_app.main()
                service.assert_called_once_with(continuity=enabled)
                server.assert_called_once_with(service.return_value,0,workspace=True)
                service.return_value.close.assert_called_once()

    def test_console_bad_flags_exit_before_any_workspace(self):
        import runpy
        for flags in (['--continuity=true'], ['--workspace'], ['--unknown']):
            with patch('sys.argv',['workspace_console.py',*flags]), patch('owner_workspace.OwnerWorkspace') as workspace, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:runpy.run_module('workspace_console',run_name='__main__')
                self.assertEqual(exc.exception.code,2)
                workspace.assert_not_called()

    def test_console_cleanup_failure_does_not_claim_clean_discard(self):
        with patch('workspace_console.OwnerWorkspace') as workspace, patch('workspace_console.interactive'), redirect_stdout(io.StringIO()) as output:
            workspace.return_value.close.side_effect=RuntimeError('cleanup uncertain')
            workspace_console.run(continuity=True)
            self.assertIn('No automatic retry. No clean-discard claim.',output.getvalue())
            self.assertNotIn('processes and records discarded',output.getvalue())
            workspace.return_value.close.assert_called_once()

    def test_console_forwarding_and_cleanup(self):
        for enabled in (False,True):
            with patch('workspace_console.OwnerWorkspace') as workspace, patch('workspace_console.interactive') as loop, redirect_stdout(io.StringIO()):
                workspace_console.run(continuity=enabled)
                workspace.assert_called_once_with(continuity=enabled)
                if enabled: loop.assert_called_once_with(workspace.return_value,continuity=True)
                else: loop.assert_called_once_with(workspace.return_value)
                workspace.return_value.close.assert_called_once()


if __name__=='__main__':unittest.main()
