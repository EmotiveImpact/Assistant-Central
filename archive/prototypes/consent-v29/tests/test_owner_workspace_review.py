"""Independent v15 review: fail-closed routing, races and owned-resource cleanup."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from fixture_ipc import JsonProcess
from generic_protocol import task_context_digest
from network import Denied, digest
from owner_ui_service import OwnerUIService
from owner_workspace import OwnerWorkspace
from task_fixtures import exact_fixture, fixture


class IndependentWorkspaceReview(unittest.TestCase):
    def context(self, selector):
        return task_context_digest(fixture(selector)[0])

    def bind(self, workspace, selector):
        service = workspace._slots[selector]['service']
        for owner, request in service.requests.items():
            workspace.action(selector, self.context(selector), {
                'action': 'bind', 'owner': owner, 'binding_digest': digest(request),
                'confirmation': 'BIND ' + owner})
        return service

    def test_every_router_checks_context_before_service_access(self):
        workspace = OwnerWorkspace()
        context = self.context('garden')
        calls = [lambda s,c: workspace.create(s,c),
                 lambda s,c: workspace.state(s,c,'alice'),
                 lambda s,c: workspace.review(s,c,'alice','id'),
                 lambda s,c: workspace.delivery(s,c,'alice','id'),
                 lambda s,c: workspace.action(s,c,{'action':'next'}),
                 lambda s,c: workspace.proposals(s,c,'alice'),
                 lambda s,c: workspace.import_proposal(s,c,'alice','id'),
                 lambda s,c: workspace.adapter(s,c,'alice'),
                 lambda s,c: workspace.reopen_storage(s,c),
                 lambda s,c: workspace.close_task(s,c)]
        with patch('owner_workspace.OwnerUIService') as constructor:
            for call in calls:
                for selector in ('../garden', '', 'GARDEN', None, [], {}, True, 1):
                    with self.subTest(call=call, selector=selector):
                        with self.assertRaises(Denied): call(selector,context)
                for wrong in (self.context('astronomy'), '', None, [], True):
                    with self.assertRaises(Denied): call('garden',wrong)
            constructor.assert_not_called()
        self.assertEqual(workspace._slots,{})
        workspace.close()

    def test_concurrent_creation_has_single_incarnation(self):
        workspace = OwnerWorkspace()
        self.addCleanup(workspace.close)
        barrier = threading.Barrier(6)
        def create():
            barrier.wait()
            try: return workspace.create('garden', self.context('garden'))['phase']
            except Denied: return 'denied'
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(lambda _: create(),range(6)))
        self.assertEqual(outcomes.count('open'),1)
        self.assertEqual(outcomes.count('denied'),5)
        service=workspace._slots['garden']['service']
        self.assertEqual(len(service.signers),2)
        self.assertFalse(service.bindings)

    def test_constructor_cleans_children_after_signer_read_failure(self):
        children=[]; directories=[]
        from tempfile import TemporaryDirectory
        def directory(*args,**kwargs):
            result=TemporaryDirectory(*args,**kwargs);directories.append(result.name);return result
        def child(*args):
            result=JsonProcess(*args);children.append(result)
            if len(children)==2:
                result.read=lambda: (_ for _ in ()).throw(RuntimeError('injected signer read'))
            return result
        with patch('owner_ui_service.JsonProcess',side_effect=child), patch('owner_ui_service.tempfile.TemporaryDirectory',side_effect=directory):
            with self.assertRaisesRegex(RuntimeError,'injected signer read'):
                OwnerUIService('generic',task_fixture='astronomy')
        self.assertEqual(len(children),2)
        self.assertTrue(all(c.process.poll() is not None for c in children))
        self.assertTrue(all(not Path(p).exists() for p in directories))

    def test_constructor_cleans_children_after_executor_bootstrap_failure(self):
        children=[]
        def child(*args):
            result=JsonProcess(*args);children.append(result)
            if args[0]=='encrypted_executor_process.py':
                result.request=lambda value: {'ready_for_bindings':False}
            return result
        with patch('owner_ui_service.JsonProcess',side_effect=child):
            with self.assertRaises(Denied):OwnerUIService('generic',task_fixture='garden')
        self.assertEqual(len(children),3)
        self.assertTrue(all(c.process.poll() is not None for c in children))

    def test_signer_shutdown_failure_does_not_strand_other_children(self):
        service=OwnerUIService('generic',task_fixture='garden')
        self.addCleanup(service.close)
        children=[service.executor,*service.signers.values()]
        with patch.object(service.executor,'close',side_effect=OSError('broken pipe')):
            service.close()
        self.assertTrue(service.closed)
        self.assertEqual(service.phase,'closed')
        self.assertTrue(all(c.process.poll() is not None for c in children))
        self.assertFalse(Path(service.directory.name).exists())

    def test_adapter_callback_after_close_never_touches_executor(self):
        workspace=OwnerWorkspace();self.addCleanup(workspace.close)
        workspace.create('garden',self.context('garden'))
        service=self.bind(workspace,'garden')
        adapter=workspace.adapter('garden',self.context('garden'),'alice')
        def rpc(value):return json.loads(adapter.handle(json.dumps(value).encode()))
        rpc({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'review','version':'1'}}})
        adapter.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        workspace.close()
        with patch.object(service,'_command') as command:
            result=rpc({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'inbox','arguments':{}}})
            self.assertTrue(result['result']['isError'])
            command.assert_not_called()
        with self.assertRaises(Denied):workspace.create('astronomy',self.context('astronomy'))
        with self.assertRaises(Denied):workspace.adapter('garden',self.context('garden'),'alice')

    def test_catalog_matching_includes_all_identity_metadata(self):
        task=fixture('garden')[0]
        identity=task.conversation.identities[0]
        for field in ('provider','display_name'):
            modified=replace(identity,**{field:'different'})
            candidate=replace(task,conversation=replace(task.conversation,identities=(modified,*task.conversation.identities[1:])))
            with self.assertRaises(Denied):exact_fixture(candidate)

    def test_close_failure_preserves_tombstone_and_other_task(self):
        workspace=OwnerWorkspace();self.addCleanup(workspace.close)
        for selector in ('garden','astronomy'):workspace.create(selector,self.context(selector))
        service=workspace._slots['garden']['service']
        with patch.object(service,'close',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):workspace.close_task('garden',self.context('garden'))
            with self.assertRaises(Denied):workspace.state('garden',self.context('garden'),'alice')
            with self.assertRaises(Denied):workspace.create('garden',self.context('garden'))
            self.assertEqual(workspace.state('astronomy',self.context('astronomy'),'bob')['phase'],'bindings')
        workspace.close_task('garden',self.context('garden'))
        with self.assertRaises(Denied):workspace.create('garden',self.context('garden'))
