"""Independent relationship fence review; offline processes and in-memory HTTP."""
import copy
import json
import unittest
from unittest.mock import patch

from network import Denied
from owner_workspace import OwnerWorkspace
from workspace_ui_service import WorkspaceUIService
from test_workspace_ui import InProcessHTTP
from test_owner_workspace import WorkspaceTests as _WorkspaceTests


class RelationshipBoundaryReview(unittest.TestCase):
    def setUp(self):
        self.w = OwnerWorkspace()
        self.addCleanup(self.w.close)
        self.members = [{k: row[k] for k in ('selector', 'context')}
                        for row in self.w.list_tasks()]

    def create(self, gid, members):
        review = self.w.relationship_preview({'operation': 'create', 'spec': {
            'group_id': gid, 'label': 'Same label', 'members': members}})
        return self.w.relationship_commit('create', review, 'CREATE GROUP')

    def stop(self, gid):
        review = self.w.relationship_preview({'operation': 'stop', 'group_id': gid})
        return self.w.relationship_commit('stop', review, 'STOP GROUP')

    def test_overlap_stops_union_and_preserves_exact_retry_after_other_changes(self):
        self.create('group-a', self.members[:1])
        self.create('group-b', self.members)
        original = self.stop('group-a')
        self.assertEqual([True, False], [r['local_work_stopped'] for r in self.w.list_tasks()])
        self.stop('group-b')
        self.assertEqual([True, True], [r['local_work_stopped'] for r in self.w.list_tasks()])
        self.assertEqual(original, self.w.relationship_commit('stop', original['stop_review'], 'STOP GROUP'))
        self.assertEqual({}, self.w._slots)
        with patch('owner_workspace.OwnerUIService', side_effect=AssertionError('allocated service')):
            for member in self.members:
                with self.assertRaises(Denied):
                    self.w.create(**member)
                wrong = dict(member, selector=self.members[1 if member == self.members[0] else 0]['selector'])
                with self.assertRaises(Denied):
                    self.w.create(**wrong)

    def test_stale_create_cannot_import_stopped_member_under_new_label(self):
        request = {'operation': 'create', 'spec': {'group_id': 'group-later',
                   'label': 'Unrelated label', 'members': self.members}}
        stale = self.w.relationship_preview(request)
        self.create('group-first', self.members[:1])
        self.stop('group-first')
        with self.assertRaises(Denied):
            self.w.relationship_commit('create', stale, 'CREATE GROUP')
        with self.assertRaises(Denied):
            self.w.relationship_preview(request)
        self.assertEqual(1, len(self.w.relationships()))

    def test_nested_snapshots_cannot_clear_stop_or_mutate_other_snapshots(self):
        self.create('group-a', self.members)
        self.stop('group-a')
        expected = copy.deepcopy(self.w.relationships())
        rows = self.w.list_tasks()
        rows[0]['relationship_groups'][0]['stop_review']['members'].clear()
        rows[0]['relationship_groups'][0]['members'].clear()
        rows[0]['relationship_groups'][0]['stopped'] = False
        self.assertEqual(expected, rows[1]['relationship_groups'])
        returned = self.w.relationships()
        returned[0]['stop_review']['members'][0]['context'] = 'forged'
        self.assertEqual(expected, self.w.relationships())
        self.assertTrue(all(r['local_work_stopped'] for r in self.w.list_tasks()))

    def test_stop_set_corruption_fails_closed_for_allowlisted_actions(self):
        self.create('group-a', self.members)
        self.stop('group-a')
        self.w._relationships._stopped = frozenset()
        for action in ('check', 'recover', 'decline', 'defer', 'withdraw_unused', 'next'):
            with self.subTest(action=action), self.assertRaises(Denied):
                self.w.action(**self.members[0], request={'action': action})
        with self.assertRaises(Denied):
            self.w.relationships()
        with patch('owner_workspace.OwnerUIService', side_effect=AssertionError('allocated service')):
            with self.assertRaises(Denied):
                self.w.create(**self.members[0])

    def test_http_closed_preview_and_duplicate_keys_never_commit(self):
        ui = WorkspaceUIService()
        self.addCleanup(ui.close)
        http = InProcessHTTP(ui)
        valid = {'operation': 'create', 'spec': {'group_id': 'group-http',
                 'label': 'Local', 'members': self.members}}
        for bad in (dict(valid, owner='alice'), dict(valid, confirmation='CREATE GROUP'),
                    dict(valid, spec=dict(valid['spec'], stopped=False)),
                    dict(valid, spec=dict(valid['spec'], members=[dict(self.members[0], owner='alice')]))):
            self.assertEqual(400, http.call('POST', '/api/relationship-preview', bad)[0])
        duplicate = '{"operation":"stop","operation":"create","spec":' + json.dumps(valid['spec']) + '}'
        self.assertEqual(400, http.call('POST', '/api/relationship-preview', duplicate)[0])
        self.assertNotEqual(200, http.call('GET', '/api/relationships?owner=alice')[0])
        self.assertEqual([], ui.relationships())
        self.assertEqual({}, ui.workspace._slots)


class RelationshipRecoveryReview(_WorkspaceTests):
    def stop(self):
        member = {'selector': 'garden', 'context': self.ctx['garden']}
        review = self.w.relationship_preview({'operation': 'create', 'spec': {
            'group_id': 'group-garden', 'label': 'Local', 'members': [member]}})
        self.w.relationship_commit('create', review, 'CREATE GROUP')
        review = self.w.relationship_preview({'operation': 'stop', 'group_id': 'group-garden'})
        self.w.relationship_commit('stop', review, 'STOP GROUP')

    def test_recover_authorized_pairing_never_submits_or_signs(self):
        self.bind('garden')
        card = self.resolve('garden', self.request('garden'))
        self.stop()
        before = self.summary('garden')
        service = self.service('garden')
        with patch.object(service.signers[card['owner']], 'request', side_effect=AssertionError('signer entered')):
            for _ in range(2):
                result = self.action('garden', action='recover', owner=card['owner'], request_id=card['request_id'])
                self.assertEqual('authorized', result['card']['state'])
            with self.assertRaises(Denied):
                self.submit('garden', card)
        self.assertEqual(before, self.summary('garden'))

    def test_queued_delivery_check_and_recover_cannot_dispatch(self):
        self.bind('garden'); self.pair('garden')
        card = self.resolve('garden', self.request('garden'))
        self.submit('garden', card)
        self.stop()
        before = self.w.delivery('garden', self.ctx['garden'], card['owner'], card['request_id'])
        for action in ('check', 'recover', 'check'):
            self.action('garden', action=action, owner=card['owner'], request_id=card['request_id'])
        after = self.w.delivery('garden', self.ctx['garden'], card['owner'], card['request_id'])
        self.assertEqual('queued', after['state'])
        self.assertEqual(before['attempts'], after['attempts'])
        self.assertFalse(after['can_start_attempt']); self.assertFalse(after['can_process'])
        self.assertEqual(0, self.summary('garden')['transitions'])
        self.assertEqual([], self.w.received_messages('garden', self.ctx['garden'], 'bob')['messages'])
        state = self.w.state('garden', self.ctx['garden'], 'alice')
        state['relationship_groups'][0]['stop_review']['members'].clear()
        self.assertTrue(self.w.state('garden', self.ctx['garden'], 'alice')['relationship_groups'][0]['stop_review']['members'])


for _name in vars(_WorkspaceTests):
    if _name.startswith('test_') and _name not in vars(RelationshipRecoveryReview):
        setattr(RelationshipRecoveryReview, _name, None)
del _WorkspaceTests
