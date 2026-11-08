"""Two real scripted child processes; synthetic owner decisions only."""
import copy
import inspect
import json
import os
import unittest
from unittest.mock import patch

from network import Denied
from offline_peer_demo import Demo, SPEC, simulate, tool_value, run
from owner_workspace import OwnerWorkspace
from workspace_console import interactive


class OfflinePeerDemoTests(unittest.TestCase):
    def setUp(self):
        self.workspace = OwnerWorkspace()
        self.addCleanup(self.workspace.close)
        self.demo = Demo(self.workspace)
        self.addCleanup(self.demo.close)

    def prepare(self):
        review = self.workspace.task_preview(SPEC)
        self.row = self.workspace.compose(SPEC,review['review_digest'],'CREATE TASK')
        self.route = self.row['selector'],self.row['context']
        for binding in self.workspace.state(*self.route,'alice')['bindings']:
            self.action(action='bind',owner=binding['owner'],binding_digest=binding['digest'],confirmation='BIND '+binding['owner'])
        self.demo.command('peers-start','',self.row)
        for actor in ('alice','bob'):
            self.demo.command('peer',actor+' discover',self.row)

    def action(self, **request):
        return self.workspace.action(*self.route,request)

    def call(self,actor,step):
        return tool_value(self.demo.command('peer',actor+' '+step,self.row))

    def pair(self):
        for _ in range(2):
            card = self.action(action='next')['card']
            self.assertEqual(card['decision']['action'],'pair')
            self.action(action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
            self.action(action='submit',owner=card['owner'],request_id=card['request_id'])

    def test_real_children_roundtrip_and_explicit_receipt_processing(self):
        lines = []
        simulate(self.workspace,self.demo,lines.append)
        pids = [p.pid for p in self.demo.peers.values()]
        self.assertEqual(len(set(pids)),2)
        self.assertNotIn(os.getpid(),pids)
        self.assertEqual(sum('DELIVERY RECEIPT' in line for line in lines),2)
        self.assertEqual(sum(line.startswith('PROCESSING ') for line in lines),2)
        for actor, expected in (('alice',self.demo.result),('bob',self.demo.request)):
            result = tool_value(self.demo.peers[actor].step('inbox'))
            self.assertEqual(result['messages'][0]['envelope'],expected)
        self.assertIsNone(self.workspace._continuity)
        peers = list(self.demo.peers.values())
        self.demo.close()
        self.demo.close()
        for peer in peers:
            self.assertIsNotNone(peer.process.returncode)
            self.assertEqual(peer.fds,[])
            self.assertTrue(peer.process.stdin.closed)
            self.assertTrue(peer.process.stdout.closed)

    def test_proposals_have_no_owner_authority_declined_retry_stays_declined(self):
        self.prepare()
        staged = self.call('alice','propose')
        self.assertEqual(staged['state'],'awaiting_owner_review')
        self.assertEqual(self.workspace.state(*self.route,'alice')['inbox'],[])
        self.assertEqual(self.call('bob','inbox')['messages'],[])
        with self.assertRaises(Denied):
            self.workspace.import_proposal(*self.route,'alice','peer-alice')
        self.pair()
        card = self.workspace.import_proposal(*self.route,'alice','peer-alice')
        self.action(action='decline',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'])
        for _ in range(2):
            self.assertEqual(self.call('alice','propose')['state'],'declined')
        self.assertEqual(self.call('bob','inbox')['messages'],[])
        with self.assertRaises(Denied):
            self.call('bob','status')

    def test_exact_selected_route_and_closed_steps(self):
        self.prepare()
        original = self.demo.route
        for row in (dict(self.row,selector='garden'),dict(self.row,context='0'*64)):
            with self.assertRaises(Denied):self.demo.command('peer','alice inbox',row)
        for command in ('alice approve','alice inbox bob','bob rebind','charlie inbox','alice inbox {"actor":"bob"}'):
            with self.assertRaises(Denied):self.demo.command('peer',command,self.row)
        with self.assertRaises(Denied):self.demo.command('peers-start','',self.row)
        self.assertEqual(self.demo.route,original)
        self.assertEqual(self.call('alice','inbox')['messages'],[])

    def test_result_before_processing_refused(self):
        self.prepare()
        with self.assertRaises(Denied):self.call('bob','propose')
        self.assertEqual(self.call('alice','inbox')['messages'],[])

    def test_stopped_group_fences_existing_child_other_task_usable(self):
        self.prepare()
        self.call('alice','propose')
        request = {'operation':'create','spec':{'group_id':'group-peer','label':'Fictional peers',
            'members':[{'selector':self.row['selector'],'context':self.row['context']}]}}
        review = self.workspace.relationship_preview(request)
        self.workspace.relationship_commit('create',review,'CREATE GROUP')
        review = self.workspace.relationship_preview({'operation':'stop','group_id':'group-peer'})
        self.workspace.relationship_commit('stop',review,'STOP GROUP')
        with self.assertRaises(Denied):self.call('alice','propose')
        self.assertEqual(self.call('bob','inbox')['messages'],[])
        garden = self.workspace.list_tasks()[0]
        self.workspace.create(garden['selector'],garden['context'])
        self.assertEqual(self.workspace.state(garden['selector'],garden['context'],'alice')['local_work_stopped'],False)
        self.assertFalse(self.demo.peers['alice'].closed)

    def test_console_extension_requires_selection_and_preserves_default(self):
        calls=[]
        commands=iter(['peer alice inbox','select garden','peer alice inbox','quit'])
        output=[]
        interactive(self.workspace,read=lambda _:next(commands),write=output.append,
                    command_handler=lambda verb,arg,row:calls.append((verb,arg,row)) or {'ok':True})
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][2]['selector'],'garden')
        self.assertTrue(any('Select an exact task first' in line for line in output))
        commands=iter(['select garden','peer alice inbox','quit'])
        output=[]
        interactive(self.workspace,read=lambda _:next(commands),write=output.append)
        self.assertTrue(any('Unknown command' in line for line in output))

    def test_default_quit_never_starts_children_or_owner_work(self):
        lines=[]
        with patch('offline_peer_demo.Peer') as spawn:
            run(read=lambda _:'quit',write=lines.append)
        spawn.assert_not_called()
        self.assertFalse(any('SIMULATED OWNER' in line for line in lines))


if __name__ == '__main__':unittest.main()
