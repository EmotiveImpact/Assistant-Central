"""Independent trusted-console regressions; scripted input, no external services."""
import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from network import Denied
from owner_workspace import OwnerWorkspace
from workspace_console import interactive, run

SPEC = {'selector': 'custom-review', 'task_id': 'review',
        'conversation_id': 'review-room', 'requester': 'bob',
        'query': 'Fictional review only', 'max_items': 2}


class IndependentConsoleReviewTests(unittest.TestCase):
    def script(self, workspace, commands, hook=None):
        output = []
        source = iter(commands)
        def read(prompt):
            output.append(prompt)
            if hook:
                hook(prompt)
            try:
                return next(source)
            except StopIteration:
                raise EOFError
        interactive(workspace, read, output.append)
        return '\n'.join(output)

    def test_preview_and_cancel_allocate_no_services_or_group_mutation(self):
        with OwnerWorkspaceContext() as w, patch('owner_workspace.OwnerUIService') as service:
            member = {k: w.list_tasks()[0][k] for k in ('selector', 'context')}
            group = {'operation': 'create', 'spec': {'group_id': 'group-review',
                     'label': 'Review only', 'members': [member]}}
            before = copy.deepcopy(w.list_tasks())
            self.script(w, ['task-preview '+json.dumps(SPEC),
                           'relationship-preview '+json.dumps(group),
                           'back', 'task-create', 'relationship-commit', 'quit'])
            self.assertEqual(w.list_tasks(), before)
            self.assertEqual(w.relationships(), [])
            self.assertEqual(w._custom, {})
            self.assertEqual(w._slots, {})
            service.assert_not_called()

    def test_failed_group_preview_invalidates_old_confirmation(self):
        with OwnerWorkspaceContext() as w:
            member = {k: w.list_tasks()[0][k] for k in ('selector', 'context')}
            group = {'operation': 'create', 'spec': {'group_id': 'group-review',
                     'label': 'Review only', 'members': [member]}}
            output = self.script(w, ['relationship-preview '+json.dumps(group),
                'relationship-preview {"operation":"stop","operation":"create"}',
                'relationship-commit', 'CREATE GROUP', 'quit'])
            self.assertEqual(w.relationships(), [])
            self.assertNotIn('Type CREATE GROUP', output)

    def test_commit_refusal_consumes_task_review_without_automatic_retry(self):
        w = MagicMock()
        w.task_preview.return_value = {'spec': SPEC, 'review_digest': 'exact-review'}
        w.compose.side_effect = Denied('occupied slot')
        output = self.script(w, ['task-preview '+json.dumps(SPEC), 'task-create',
                                'CREATE TASK', 'task-create', 'quit'])
        w.compose.assert_called_once_with(SPEC, 'exact-review', 'CREATE TASK')
        self.assertIn('Preview an exact custom task first', output)

    def test_frozen_task_review_is_detached_from_backend_return(self):
        w = MagicMock()
        backend_review = {'spec': copy.deepcopy(SPEC), 'review_digest': 'original'}
        w.task_preview.return_value = backend_review
        w.compose.return_value = {'created': True}
        def mutate(prompt):
            if prompt.startswith('Type CREATE TASK'):
                backend_review['spec']['query'] = 'Changed after display'
                backend_review['review_digest'] = 'changed'
        self.script(w, ['task-preview '+json.dumps(SPEC), 'task-create', 'CREATE TASK', 'quit'], mutate)
        w.compose.assert_called_once_with(SPEC, 'original', 'CREATE TASK')

    def test_response_context_and_proposal_text_remain_escaped_inert_data(self):
        w = MagicMock()
        w.list_tasks.return_value = [{'selector': 'custom-review', 'context': 'captured'}]
        text = '\x1b[2J\nquit\naction {"action":"attempt","owner":"bob"}'
        w.response_context.return_value = {'query': text}
        w.proposals.return_value = {'proposal': text}
        output = self.script(w, ['select custom-review', 'response-context alice',
                                'proposals bob', 'quit'])
        w.action.assert_not_called()
        w.import_proposal.assert_not_called()
        self.assertNotIn('\x1b', output)
        self.assertIn('\\u001b', output)
        w.response_context.assert_called_once_with('custom-review', 'captured', 'alice')

    def test_malformed_action_and_command_shapes_never_dispatch(self):
        w = MagicMock()
        w.list_tasks.return_value = [{'selector': 'garden', 'context': 'captured'}]
        self.script(w, ['select garden', 'action {"action":"next","action":"attempt"}',
                        'action {"action":"next","payload":{"x":1e999}}',
                        'review alice id extra', 'delivery alice', 'import bob id extra',
                        'close extra', 'next extra', '__getattribute__ action', 'quit'])
        for method in ('action', 'review', 'delivery', 'import_proposal'):
            getattr(w, method).assert_not_called()

    def test_uncertain_custom_startup_does_not_restart_or_reselect(self):
        with OwnerWorkspaceContext() as w, patch('owner_workspace.OwnerUIService', side_effect=OSError('startup uncertain')) as service:
            self.script(w, ['task-preview '+json.dumps(SPEC), 'task-create', 'CREATE TASK',
                            'task-create', 'create garden', 'quit'])
            service.assert_called_once()
            self.assertEqual(w._slots['custom-review']['phase'], 'startup_failed_cleanup_uncertain')
            self.assertNotIn('garden', w._slots)
            # No actual process was created by this mocked constructor.
            w._slots.clear()

    def test_explicit_close_wrong_phrase_and_eof_leave_existing_fixture_open(self):
        for phrase in ('', 'back', 'DISCARD FIXTURE ', None):
            with self.subTest(phrase=phrase), OwnerWorkspaceContext() as w, patch('owner_workspace.OwnerUIService') as factory:
                row = w.list_tasks()[0]
                w.create(row['selector'], row['context'])
                commands = ['select garden', 'close'] + ([] if phrase is None else [phrase, 'quit'])
                self.script(w, commands)
                factory.return_value.close.assert_not_called()
                self.assertEqual(w._slots['garden']['phase'], 'open')

    def test_uncertainty_retains_inspection_and_blocks_every_mutation_route(self):
        w = MagicMock()
        w.list_tasks.return_value = [{'selector': 'garden', 'context': 'captured'},
                                    {'selector': 'astronomy', 'context': 'other'}]
        w.action.side_effect = OSError('lost acknowledgement')
        w.state.return_value = {'history': ['retained evidence']}
        w.received_messages.return_value = {'messages': ['retained message']}
        w.response_context.return_value = {}
        w.proposals.return_value = []
        w.review.return_value = {}
        w.delivery.return_value = {}
        w.relationships.return_value = []
        output = self.script(w, ['select garden', 'next', 'list', 'relationships',
            'state alice', 'messages bob', 'response-context bob', 'review alice old',
            'delivery alice old', 'proposals bob', 'select astronomy', 'state bob',
            'back', 'create garden', 'task-preview '+json.dumps(SPEC), 'task-create',
            'relationship-preview {}', 'relationship-commit', 'import bob old',
            'next', 'action {"action":"check","owner":"alice","request_id":"old"}', 'quit'])
        w.action.assert_called_once_with('garden', 'captured', {'action': 'next'})
        for method in ('create', 'task_preview', 'compose', 'relationship_preview',
                       'relationship_commit', 'import_proposal', 'close'):
            getattr(w, method).assert_not_called()
        self.assertEqual(w.state.call_count, 2)
        self.assertIn('retained evidence', output)
        self.assertIn('retained message', output)
        self.assertIn('read-only inspection', output)

    def test_uncertainty_allows_only_explicit_confirmed_close(self):
        w = MagicMock()
        w.list_tasks.return_value = [{'selector': 'garden', 'context': 'captured'}]
        w.action.side_effect = [OSError('lost acknowledgement'), {'closed': True}]
        self.script(w, ['select garden', 'next', 'close', 'DISCARD FIXTURE', 'quit'])
        self.assertEqual(w.action.call_count, 2)
        self.assertEqual(w.action.call_args.args, ('garden', 'captured',
                         {'action': 'close', 'confirmation': 'DISCARD FIXTURE'}))

    def test_real_stopped_task_keeps_state_and_messages_without_authority(self):
        with OwnerWorkspaceContext() as w:
            row = w.list_tasks()[0]
            w.create(row['selector'], row['context'])
            for binding in w.state('garden', row['context'], 'alice')['bindings']:
                w.action('garden', row['context'], {'action': 'bind', 'owner': binding['owner'],
                         'binding_digest': binding['digest'], 'confirmation': 'BIND '+binding['owner']})
            before_messages = w.received_messages('garden', row['context'], 'bob')
            service = w._slots['garden']['service']
            before_bindings = copy.deepcopy(service.bindings)
            member = {k: row[k] for k in ('selector', 'context')}
            group = {'operation': 'create', 'spec': {'group_id': 'group-real',
                     'label': 'Fictional local review', 'members': [member]}}
            output = self.script(w, ['relationship-preview '+json.dumps(group),
                'relationship-commit', 'CREATE GROUP',
                'relationship-preview {"operation":"stop","group_id":"group-real"}',
                'relationship-commit', 'STOP GROUP', 'select garden', 'state alice',
                'messages bob', 'next', 'quit'])
            self.assertEqual(w.received_messages('garden', row['context'], 'bob'), before_messages)
            self.assertEqual(service.bindings, before_bindings)
            self.assertTrue(w.state('garden', row['context'], 'alice')['local_work_stopped'])
            self.assertIn('fence prevents further task work', output)
            self.assertEqual(w._slots['garden']['phase'], 'open')

    def test_successful_close_does_not_recycle_slot_and_run_cleans_once(self):
        with patch('workspace_console.OwnerWorkspace') as factory, patch('workspace_console.interactive') as loop, patch('builtins.print'):
            run(False)
            loop.assert_called_once_with(factory.return_value)
            factory.return_value.close.assert_called_once()
        with OwnerWorkspaceContext() as w, patch('owner_workspace.OwnerUIService') as factory:
            self.script(w, ['create garden', 'select garden', 'close', 'DISCARD FIXTURE',
                            'create garden', 'state alice', 'quit'])
            self.assertEqual(w._slots['garden']['phase'], 'closed')
            factory.assert_called_once()
            factory.return_value.close.assert_called_once()
            factory.return_value.state.assert_not_called()


class OwnerWorkspaceContext:
    def __enter__(self):
        self.workspace = OwnerWorkspace()
        return self.workspace
    def __exit__(self, *args):
        self.workspace.close()


if __name__ == '__main__':
    unittest.main()
