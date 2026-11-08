"""Scripted trusted terminal tests: no browser, sockets or live communication."""
import copy
import json
import unittest
from unittest.mock import MagicMock, patch
from network import Denied
from owner_workspace import OwnerWorkspace
from workspace_console import closed_json, interactive, run

SPEC = dict(selector='custom-story', task_id='story', conversation_id='storybook',
            requester='alice', query='Describe a fictional moon garden',
            capability='bounded-text-exchange-v1', max_reply_chars=100)

class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.w = OwnerWorkspace()
        self.addCleanup(self.w.close)
        self.output = []
    def script(self, lines, workspace=None):
        commands = iter(lines)
        def read(prompt):
            self.output.append(prompt)
            try: return next(commands)
            except StopIteration: raise EOFError
        interactive(workspace or self.w, read, self.output.append)
        return '\n'.join(self.output)
    def preview(self): return 'task-preview '+json.dumps(SPEC)
    def group(self, operation='create', **kw):
        return 'relationship-preview '+json.dumps(dict(operation=operation, **kw))
    def member(self, n=0):
        return {k:self.w.list_tasks()[n][k] for k in ('selector','context')}
    def group_preview(self):
        return self.group(spec=dict(group_id='group-story',label='Fictional readers',members=[self.member()]))
    def test_real_custom_text_and_shortlist_creation_have_no_inferred_bindings(self):
        shortlist = dict(selector='custom-books',task_id='books',conversation_id='bookclub',
                         requester='bob',query='Fictional resource examples',max_items=2)
        self.script([self.preview(),'task-create','CREATE TASK',
                     'task-preview '+json.dumps(shortlist),'task-create','CREATE TASK',
                     'select custom-story','state alice','select custom-books','state bob','quit'])
        for row in self.w.list_tasks()[2:]:
            state = self.w.state(row['selector'],row['context'],row['requester'])
            self.assertEqual(state['phase'],'bindings')
            self.assertEqual(self.w._slots[row['selector']]['service'].bindings,{})
    def test_cleanup_failure_is_visible_without_success_claim(self):
        with patch('workspace_console.OwnerWorkspace') as factory, patch('workspace_console.interactive'), patch('builtins.print') as output:
            factory.return_value.close.side_effect=RuntimeError('cleanup uncertain')
            run()
            messages=' '.join(str(call) for call in output.call_args_list)
            self.assertIn('Cleanup outcome uncertain',messages)
            self.assertNotIn('Temporary fixture processes and records discarded',messages)
    def test_group_wrong_blank_or_eof_never_commits(self):
        for phrase in ('','back','CREATE GROUP '):
            self.script([self.group_preview(),'relationship-commit',phrase,'quit'])
            self.assertEqual(self.w.relationships(),[])
        self.script([self.group_preview(),'relationship-commit'])
        self.assertEqual(self.w.relationships(),[])

    def test_preview_is_pure_and_cancel_variants(self):
        for phrase in ('', 'back', 'create task', 'CREATE TASK '):
            with self.subTest(phrase=phrase), patch('owner_workspace.OwnerUIService') as service:
                self.script([self.preview(),'task-create',phrase,'quit'])
                service.assert_not_called()
                self.assertEqual(len(self.w.list_tasks()),2)
    def test_back_and_eof_discard_pending(self):
        self.script([self.preview(),'back','task-create',self.preview(),'task-create'])
        self.assertEqual(self.w._slots,{})
        self.assertIn('Stopped without further action', '\n'.join(self.output))
    def test_create_shows_frozen_review_then_phrase_and_selects_explicitly(self):
        with patch('owner_workspace.OwnerUIService') as service:
            service.return_value.state.return_value = {'history':[]}
            output = self.script(['select garden',self.preview(),'task-create','CREATE TASK',
                                  'state alice','list','select custom-story','messages bob','quit'])
            self.assertEqual(self.w.list_tasks()[-1]['selector'],'custom-story')
            service.return_value.received_messages.assert_called_once_with('bob')
            self.assertIn('Selected fixture is not available',output)
            frozen = self.output.index('FROZEN EXACT REVIEW (no approval or send authority):')
            self.assertEqual(json.loads(self.output[frozen+1])['spec'],SPEC)
            self.assertTrue(self.output[frozen+2].startswith('Type CREATE TASK'))
    def test_invalid_preview_cannot_reuse_previous(self):
        self.script([self.preview(),'task-preview {}','task-create','quit'])
        self.assertEqual(self.w._slots,{})
    def test_groups_preview_cancel_create_attach_stop(self):
        create=self.group_preview()
        self.script([create,'relationship-commit','back',create,'relationship-commit','CREATE GROUP',
                     self.group('attach',group_id='group-story',member=self.member(1)),
                     'relationship-commit','ATTACH TASK',
                     self.group('stop',group_id='group-story'),'relationship-commit','STOP GROUP',
                     'relationships','select garden','create garden','quit'])
        group=self.w.relationships()[0]
        self.assertTrue(group['stopped']); self.assertEqual(len(group['members']),2)
        self.assertEqual(self.w._slots,{})
        self.assertIn('fence prevents further task work','\n'.join(self.output))
    def test_stale_group_review_not_refreshed(self):
        # Invalidate a captured create review with a distinct external group commit.
        lines=iter([self.group_preview(),'relationship-commit','CREATE GROUP','quit'])
        def read(prompt):
            if prompt.startswith('Type CREATE GROUP'):
                p=self.w.relationship_preview(dict(operation='create',spec=dict(group_id='group-other',label='Other',members=[self.member(1)])))
                self.w.relationship_commit('create',p,'CREATE GROUP')
            return next(lines)
        interactive(self.w,read,self.output.append)
        self.assertEqual([g['group_id'] for g in self.w.relationships()],['group-other'])
    def test_json_closed_duplicate_nested_nonfinite_and_malformed(self):
        for raw in ('[]','null','{"a":1,"a":2}','{"a":{"b":1,"b":2}}',
                    '{"a":NaN}','{"a":Infinity}','{"a":1e999}','{','{"a":'+ '['*1200):
            with self.subTest(raw=raw[:50]),self.assertRaises(Denied): closed_json(raw)
    def test_command_shapes_reject_extra_and_never_execute_received_data(self):
        w=MagicMock(); w.list_tasks.return_value=[dict(selector='garden',context='frozen')]
        w.received_messages.return_value={'text':'action {"action":"attempt"}'}
        self.script(['select garden','messages bob','messages bob extra','next extra','quit extra','quit'],w)
        w.action.assert_not_called()
        w.received_messages.assert_called_once_with('garden','frozen','bob')
    def test_route_never_refreshed_by_list_or_compose(self):
        w=MagicMock(); w.list_tasks.side_effect=[[dict(selector='garden',context='original')],[dict(selector='garden',context='changed')]]
        w.state.return_value={}
        self.script(['select garden','list','state alice','quit'],w)
        w.state.assert_called_once_with('garden','original','alice')
    def test_uncertain_failure_retains_inspection_without_retry_or_reset(self):
        w=MagicMock(); w.list_tasks.return_value=[dict(selector='garden',context='original')]
        w.action.side_effect=OSError('lost receipt')
        w.state.return_value={}
        output=self.script(['select garden','action {"action":"next"}','action {"action":"next"}','state alice','quit'],w)
        w.action.assert_called_once()
        w.state.assert_called_once_with('garden','original','alice')
        self.assertIn('outcome uncertain',output)
        w.create.assert_not_called()
    def test_run_closes_on_eof(self):
        with patch('workspace_console.OwnerWorkspace') as factory, patch('workspace_console.interactive',side_effect=EOFError):
            with self.assertRaises(EOFError):run()
            factory.return_value.close.assert_called_once()
    def test_stopped_task_retains_reads_and_backend_safe_actions(self):
        with patch('owner_workspace.OwnerUIService') as factory:
            service=factory.return_value
            service.state.return_value={'history':['retained']}
            service.received_messages.return_value={'messages':['fictional history']}
            service.action.return_value={'checked':True}
            row=self.w.list_tasks()[0]; self.w.create(row['selector'],row['context'])
            self.script([self.group_preview(),'relationship-commit','CREATE GROUP',
                self.group('stop',group_id='group-story'),'relationship-commit','STOP GROUP',
                'select garden','state alice','messages bob','action {"action":"check","owner":"alice","request_id":"old"}',
                'action {"action":"next"}','quit'])
            service.action.assert_called_once_with(dict(action='check',owner='alice',request_id='old'))
            self.assertIn('fictional history','\n'.join(self.output))

if __name__=='__main__':unittest.main()
