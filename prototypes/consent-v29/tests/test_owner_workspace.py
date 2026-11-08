"""Independent task stores/processes and exact trusted routing, all offline."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from network import Denied, digest
from task_fixtures import fixture, exact_fixture
from generic_protocol import task_context_digest
from owner_workspace import OwnerWorkspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.w=OwnerWorkspace();self.addCleanup(self.w.close)
        self.ctx={r['selector']:r['context'] for r in self.w.list_tasks()}
        for key in self.ctx:self.w.create(key,self.ctx[key])
    def service(self,key):return self.w._slots[key]['service']
    def action(self,key,**fields):return self.w.action(key,self.ctx[key],fields)
    def bind(self,key):
        for owner,pending in self.service(key).requests.items():
            self.action(key,action='bind',owner=owner,binding_digest=digest(pending),confirmation='BIND '+owner)
    def resolve(self,key,card,choice='approve'):
        fields=dict(action=choice,owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'])
        if choice=='approve':fields['confirmation']='APPROVE '+card['owner']
        return self.action(key,**fields)['card']
    def submit(self,key,card):return self.action(key,action='submit',owner=card['owner'],request_id=card['request_id'])['card']
    def pair(self,key):
        for _ in range(2):self.submit(key,self.resolve(key,self.action(key,action='next')['card']))
    def request(self,key):return self.action(key,action='next')['card']
    def summary(self,key):return self.service(key)._command('summary')
    def finish(self,key,card):
        self.submit(key,self.resolve(key,card))
        self.action(key,action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
        self.action(key,action='process',owner=card['owner'],request_id=card['request_id'])
    def rpc(self,adapter,method,args=None):
        self.counter+=1
        response=json.loads(adapter.handle(json.dumps({'jsonrpc':'2.0','id':self.counter,'method':'tools/call','params':{'name':method,'arguments':args or {}}}).encode()))
        return response
    def adapter(self,key,actor):
        self.counter=getattr(self,'counter',0)
        adapter=self.w.adapter(key,self.ctx[key],actor)
        adapter.handle(json.dumps({'jsonrpc':'2.0','id':'init','method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}}).encode())
        adapter.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        return adapter
    def test_creation_has_no_authority_and_isolated_processes_keys_directories(self):
        a,b=self.service('garden'),self.service('astronomy')
        self.assertNotEqual(a.directory.name,b.directory.name)
        self.assertNotEqual(a.roots,b.roots)
        self.assertNotEqual(a.executor.process.pid,b.executor.process.pid)
        for owner in ('alice','bob'):
            self.assertNotEqual(a.signers[owner].process.pid,b.signers[owner].process.pid)
            self.assertNotEqual(a.requests[owner]['binding']['transport_pubkey'],b.requests[owner]['binding']['transport_pubkey'])
        self.assertFalse(a.bindings);self.assertFalse(b.bindings)
        self.bind('garden');self.pair('garden')
        self.assertEqual(b.phase,'bindings');self.assertFalse(b.bindings)
        self.bind('astronomy')
        self.assertEqual(self.service('astronomy').state('bob')['inbox'],[])
        self.assertEqual(self.summary('astronomy')['transitions'],0)
    def test_interleaved_adapters_same_ids_and_explicit_approvals(self):
        adapters={}
        for key in self.ctx:
            self.bind(key);self.pair(key)
            adapters[key]={actor:self.adapter(key,actor) for actor in ('alice','bob')}
        for index in (2,3):
            cards={}
            for key in self.ctx:
                envelope=fixture(key)[index];actor=envelope['sender']
                answer=self.rpc(adapters[key][actor],'propose',{'proposal_id':'same-id','envelope':envelope})
                self.assertFalse(answer['result'].get('isError',False),answer)
                cards[key]=self.w.import_proposal(key,self.ctx[key],actor,'same-id')
                with self.assertRaises(Denied):self.submit(key,cards[key])
            for key in self.ctx:self.finish(key,cards[key])
        for key in self.ctx:
            self.assertEqual(self.summary(key)['task_state'],'completed')
            before=self.service(key).roots.copy()
            self.assertTrue(self.w.reopen_storage(key,self.ctx[key])['transport_keys_remained_in_live_fixture'])
            self.assertEqual(before,self.service(key).roots)
            self.assertEqual(self.summary(key)['transitions'],2)
    def test_cross_context_actions_envelopes_ids_and_signatures_fail(self):
        for key in self.ctx:self.bind(key);self.pair(key)
        a=self.request('garden');b=self.request('astronomy');before=self.summary('astronomy')
        with self.assertRaises(Denied):self.w.action('astronomy',self.ctx['garden'],{'action':'next'})
        with self.assertRaises(Denied):self.w.review('astronomy',self.ctx['astronomy'],a['owner'],a['request_id'])
        with self.assertRaises(Denied):self.service('astronomy')._command('request_prepare',owner='alice',action='send',envelope=a['envelope'])
        signed=self.service('garden').signers['alice'].request({'decision':a['decision'],'envelope':a['envelope'],'confirmation':'APPROVE alice send '+a['request_id']})['signed']
        with self.assertRaises(Denied):self.service('astronomy')._command('request_resolve',owner=b['owner'],request_id=b['request_id'],review_digest=b['review_digest'],choice='approve',signed=signed)
        pending=self.service('garden').requests['alice']
        response=self.service('astronomy').signers['alice'].request({'binding_request':pending,'confirmation':'BIND alice '+digest(pending)})
        self.assertFalse(response['ok']);self.assertEqual(before,self.summary('astronomy'))
    def test_cross_task_receipt_rejected_without_mutation(self):
        from bound_identity import IdentityRegistry
        from encrypted_delivery import verify_receipt
        for key in self.ctx:self.bind(key);self.pair(key)
        cards={}
        for key in self.ctx:
            card=self.resolve(key,self.request(key));self.submit(key,card);cards[key]=card
            self.action(key,action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
        rows={}
        for key in self.ctx:
            with sqlite3.connect(Path(self.service(key).directory.name)/'sender.sqlite3') as db:
                db.row_factory=sqlite3.Row
                rows[key]=dict(db.execute('SELECT * FROM encrypted_outbox').fetchone())
        b=self.service('astronomy');registry=IdentityRegistry(fixture('astronomy')[0],b.roots,b.bindings)
        before=self.summary('astronomy')
        with self.assertRaises(Denied):verify_receipt(registry,json.loads(rows['garden']['receipt']),rows['astronomy'])
        self.assertEqual(before,self.summary('astronomy'))

    def test_adapter_cannot_list_switch_or_follow_navigation(self):
        for key in self.ctx:self.bind(key)
        adapter=self.adapter('garden','alice')
        for method in ('create','list_tasks','switch_task','request_prepare','close'):
            self.assertIn('error',self.rpc(adapter,method))
        result=self.rpc(adapter,'propose',{'proposal_id':'one','envelope':fixture('astronomy')[2]})
        self.assertTrue('error' in result or result['result'].get('isError'))
        self.w.state('astronomy',self.ctx['astronomy'],'bob')
        self.assertFalse(self.rpc(adapter,'propose',{'proposal_id':'one','envelope':fixture('garden')[2]})['result'].get('isError',False))
        self.w.close_task('garden',self.ctx['garden'])
        self.assertTrue(self.rpc(adapter,'inbox')['result']['isError'])
        with self.assertRaises(Denied):self.w.create('garden',self.ctx['garden'])
        self.assertEqual(self.service('astronomy').phase,'ready')
    def test_controls_decline_withdraw_uncertainty_leave_other_task_operational(self):
        for key in self.ctx:self.bind(key);self.pair(key)
        a=self.request('garden');self.resolve('garden',a,'decline')
        self.finish('astronomy',self.request('astronomy'))
        self.assertEqual(self.summary('garden')['transitions'],0)
        self.assertEqual(self.summary('astronomy')['transitions'],1)
        for action in ('revoke','cancel'):
            fields={'action':action,'owner':'alice'}
            if action=='revoke':fields['peer']='bob'
            card=self.action('garden',**fields)['card'];self.submit('garden',self.resolve('garden',card))
        self.finish('astronomy',self.request('astronomy'))
        self.assertEqual(self.summary('astronomy')['task_state'],'completed')
    def test_withdrawal_cross_task_rejected_and_b_continues(self):
        for key in self.ctx:self.bind(key);self.pair(key)
        a=self.resolve('garden',self.request('garden'))
        prepared=self.service('garden')._command('withdrawal_prepare',owner=a['owner'],request_id=a['request_id'],review_digest=a['review_digest'])
        body=prepared['withdrawal'];signed=self.service('garden').signers['alice'].request({'withdrawal':body,'original':prepared['original'],'confirmation':f"WITHDRAW alice {a['request_id']} {digest(body)}"})['signed']
        with self.assertRaises(Denied):self.service('astronomy')._command('withdrawal_commit',signed=signed)
        self.service('garden')._command('withdrawal_commit',signed=signed)
        with self.assertRaises(Denied):self.submit('garden',a)
        self.finish('astronomy',self.request('astronomy'))
    def test_uncertain_a_reopen_no_retry_b_completes(self):
        for key in self.ctx:self.bind(key);self.pair(key)
        a=self.resolve('garden',self.request('garden'));self.submit('garden',a)
        self.service('garden')._command('fixture_fail_before_receipt',owner=a['owner'],request_id=a['request_id'])
        self.w.reopen_storage('garden',self.ctx['garden'])
        self.finish('astronomy',self.request('astronomy'));self.finish('astronomy',self.request('astronomy'))
        status=self.w.delivery('garden',self.ctx['garden'],a['owner'],a['request_id'])
        self.assertEqual(status['attempts'],1);self.assertEqual(status['state'],'dispatched')
        with self.assertRaises(Denied):self.action('garden',action='process',owner=a['owner'],request_id=a['request_id'])
        self.assertEqual(self.summary('astronomy')['task_state'],'completed')
    def test_cleanup_failure_attempts_every_service_and_stays_fenced(self):
        a,b=self.service('garden'),self.service('astronomy');original=a.close
        with patch.object(a,'close',side_effect=RuntimeError('injected')),patch.object(b,'close',wraps=b.close) as close_b:
            with self.assertRaisesRegex(RuntimeError,'cleanup uncertain'):self.w.close()
            close_b.assert_called_once()
            self.assertEqual(self.w.list_tasks()[0]['phase'],'cleanup_uncertain')
            with self.assertRaises(Denied):self.w.state('garden',self.ctx['garden'],'alice')
        original();self.w.close()
        self.assertFalse(Path(a.directory.name).exists());self.assertFalse(Path(b.directory.name).exists())
    def test_console_discovers_imports_proposal_without_approval(self):
        import contextlib
        import io
        import workspace_console
        for key in self.ctx:self.bind(key);self.pair(key)
        adapter=self.adapter('astronomy','bob')
        self.rpc(adapter,'propose',{'proposal_id':'staged','envelope':fixture('astronomy')[2]})
        output=io.StringIO()
        commands=iter(['select garden','select astronomy','proposals bob','import bob staged','quit'])
        # Keep the existing real child services available for assertions after
        # the interactive frontend exits; its normal close call is still checked.
        with patch.object(workspace_console,'OwnerWorkspace',return_value=self.w), patch('builtins.input',side_effect=lambda _:next(commands)), patch.object(self.w,'close') as close, contextlib.redirect_stdout(output):
            workspace_console.run(False)
            close.assert_called_once()
        self.assertIn('Any new review is unsigned',output.getvalue())
        rows=self.w.proposals('astronomy',self.ctx['astronomy'],'bob')
        self.assertEqual(rows[0]['state'],'pending')
        self.assertEqual(self.w.proposals('garden',self.ctx['garden'],'bob'),[])
        self.assertEqual(self.summary('astronomy')['receiver_receipts'],0)
        card=self.w.import_proposal('astronomy',self.ctx['astronomy'],'bob','staged')
        with self.assertRaises(Denied):self.submit('astronomy',card)

    def test_capacity_a_does_not_consume_b(self):
        for key in self.ctx:self.bind(key)
        a=self.adapter('garden','alice');b=self.adapter('astronomy','bob')
        for index in range(20):
            envelope=fixture('garden')[2];envelope['payload']['query']=str(index)
            result=self.rpc(a,'propose',{'proposal_id':'p'+str(index),'envelope':envelope})
            self.assertFalse(result['result'].get('isError',False))
        # Trusted fault fixture fills only A's bounded ID ledger, not runtime keys.
        with sqlite3.connect(Path(self.service('garden').directory.name)/'sender.sqlite3') as db:
            fingerprint=db.execute('SELECT fingerprint FROM agent_proposals LIMIT 1').fetchone()[0]
            db.executemany('INSERT INTO agent_proposal_ids VALUES (?,?,?,?)',
                [(self.ctx['garden'],'alice','fill'+str(i),fingerprint) for i in range(9980)])
        envelope=fixture('garden')[2];envelope['payload']['query']='over capacity'
        self.assertTrue(self.rpc(a,'propose',{'proposal_id':'overflow','envelope':envelope})['result']['isError'])
        self.assertFalse(self.rpc(b,'propose',{'proposal_id':'overflow','envelope':fixture('astronomy')[2]})['result'].get('isError',False))


class CatalogTests(unittest.TestCase):
    def test_exact_full_task_and_detached_payloads(self):
        from generic_demo import fixture as legacy
        self.assertEqual(legacy(),fixture('garden'))
        # Golden digests read from the frozen v14 extraction, not this wrapper.
        self.assertEqual(task_context_digest(fixture()[0]),'9bd7990b6e24f9ee82bf19cab1c34ce8be9e23d1038c8948d00f50b1879c6fcc')
        self.assertEqual(digest(fixture()[2]),'67ada8a2aacc2279c406763a2cf44228eae6fac1a101bf8bc986db953c44c4ef')
        self.assertEqual(digest(fixture()[3]),'5630615cb6390c55e02fbcfe0548f63aa8915e45919b1079d49df8794d9091c8')
        for key in ('garden','astronomy'):
            task=fixture(key)[0]
            self.assertEqual(exact_fixture(task)[0],task)
            with self.assertRaises(Denied):exact_fixture(replace(task,operation='different'))
            with self.assertRaises(Denied):exact_fixture(replace(task,conversation=replace(task.conversation,id='different')))
        with self.assertRaises(Denied):fixture({})
        a=fixture();a[2]['payload']['query']='changed';self.assertNotEqual(a,fixture())
    def test_startup_failure_tombstones_slot(self):
        w=OwnerWorkspace();context=task_context_digest(fixture()[0])
        with patch('owner_workspace.OwnerUIService',side_effect=RuntimeError('startup')):
            with self.assertRaises(RuntimeError):w.create('garden',context)
        with self.assertRaises(Denied):w.create('garden',context)
        with self.assertRaisesRegex(RuntimeError,'cleanup uncertain'):w.close()
    def test_console_demo_and_quit(self):
        for args,text in ((['--simulate'],None),([], 'create garden\nselect garden\nstate alice\nquit\n')):
            result=subprocess.run([sys.executable,'workspace_console.py',*args],input=text,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            if args:self.assertEqual(result.stdout.count('"task_state": "completed"'),2)
            else:self.assertNotIn('ACTION approve',result.stdout)
