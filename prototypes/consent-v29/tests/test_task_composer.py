"""Trusted custom composition stays exact across live disposable child processes."""
import copy
import json
import unittest
from unittest.mock import patch, MagicMock
from network import Denied, digest, canonical
from task_composer import preview, composed_fixture, parse_startup
from owner_workspace import OwnerWorkspace
from workspace_ui_service import WorkspaceUIService
from generic_protocol import task_envelope, task_context_digest


def spec(n='one', requester='bob'):
    return dict(selector='custom-'+n,task_id='task-'+n,conversation_id='conversation-'+n,
                requester=requester,query='Fictional resource examples',max_items=2)


class CompositionValidationTests(unittest.TestCase):
    def test_preview_pure_detached_exact_and_commits_every_field(self):
        original=spec(); expected=preview(original)
        with patch('owner_workspace.OwnerUIService',side_effect=AssertionError('allocated')):
            w=OwnerWorkspace(); self.assertEqual(w.task_preview(original),expected)
            self.assertEqual(len(w.list_tasks()),2); self.assertEqual(w._slots,{})
        expected['spec']['query']='changed';self.assertEqual(original,spec())
        for field,value in [('query','Other query'),('max_items',3),('selector','custom-two'),
                            ('task_id','task-two'),('conversation_id','conversation-two'),('requester','alice')]:
            changed={**original,field:value}
            self.assertNotEqual(preview(changed)['context'],preview(original)['context'])
            self.assertNotEqual(preview(changed)['review_digest'],preview(original)['review_digest'])

    def test_closed_types_bounds_and_fields(self):
        bad=[None,[],{}, {**spec(),'tool':'browse'}]
        for key, values in {'selector':['garden','custom-','custom-A',1], 'task_id':['', 'x'*65,True],
                            'conversation_id':['a/b',None], 'requester':['charlie',[],None],
                            'query':['',' spaced','x'*513,'a\nline','\ud800',False],
                            'max_items':[True,False,0,6,1.0,'2',None]}.items():
            bad.extend({**spec(),key:v} for v in values)
        for value in bad:
            with self.subTest(value=repr(value)), self.assertRaises(Denied):preview(value)
        for value in ['', 'x'*8193, '{"selector":"a","selector":"b"}', '[]']:
            with self.assertRaises(Denied):parse_startup(value)
        self.assertEqual(parse_startup(canonical(spec())),spec())
        unicode_spec={**spec(),'query':'😀'*512}
        self.assertEqual(parse_startup(canonical(unicode_spec)),unicode_spec)
        self.assertEqual(preview(unicode_spec)['spec'],unicode_spec)

    def test_response_bounds_remain_exact_and_fail_closed(self):
        from ipc_test_support import output
        for limit in (16384,65536):
            exact=json.dumps('x'*(limit-3))+'\n'
            child=output(exact,limit);self.addCleanup(child.close)
            self.assertEqual(len(child.read()),limit-3)
            for malformed in (exact[:-1],exact[:-1]+'x\n',''):
                child=output(malformed,limit);self.addCleanup(child.close)
                with self.assertRaises(RuntimeError):child.read()

    def test_review_confirmation_mutation_no_allocation(self):
        w=WorkspaceUIService(); self.addCleanup(w.close); p=preview(spec())
        body=dict(action='compose_task',spec=spec(),review_digest=p['review_digest'],confirmation='CREATE TASK')
        with patch('owner_workspace.OwnerUIService',side_effect=AssertionError('allocated')):
            for mutated in [{**body,'confirmation':'create task'},{**body,'review_digest':'0'*64},
                            {**body,'spec':{**spec(),'query':'different'}},{**body,'extra':1}]:
                with self.assertRaises(Denied):w.action(mutated)
        self.assertEqual(len(w.tasks()),2)

    def test_capacity_replay_closed_and_uncertain_tombstones(self):
        w=OwnerWorkspace()
        with patch('owner_workspace.OwnerUIService',return_value=MagicMock()):
            for i in range(8):
                value=spec(str(i));p=preview(value);w.compose(value,p['review_digest'],'CREATE TASK')
            with self.assertRaises(Denied):w.compose(spec('9'),preview(spec('9'))['review_digest'],'CREATE TASK')
            row=w.list_tasks()[2];w.close_task(row['selector'],row['context'])
            with self.assertRaises(Denied):w.compose(spec('0'),preview(spec('0'))['review_digest'],'CREATE TASK')
            w.close()
        w=OwnerWorkspace();p=preview(spec())
        with patch('owner_workspace.OwnerUIService',side_effect=RuntimeError('uncertain startup')):
            with self.assertRaises(RuntimeError):w.compose(spec(),p['review_digest'],'CREATE TASK')
        self.assertEqual(w.list_tasks()[-1]['phase'],'startup_failed_cleanup_uncertain')
        with self.assertRaises(Denied):w.compose(spec(),p['review_digest'],'CREATE TASK')
        with self.assertRaises(RuntimeError):w.close()

    def test_same_task_id_conflict_and_cleanup_uncertain(self):
        w=OwnerWorkspace();p=preview(spec())
        child=MagicMock()
        with patch('owner_workspace.OwnerUIService',return_value=child):w.compose(spec(),p['review_digest'],'CREATE TASK')
        conflicting={**spec('other'),'task_id':spec()['task_id']}
        with self.assertRaises(Denied):w.compose(conflicting,preview(conflicting)['review_digest'],'CREATE TASK')
        child.close.side_effect=RuntimeError('uncertain cleanup')
        with self.assertRaises(RuntimeError):w.close_task(p['selector'],p['context'])
        self.assertEqual(w.list_tasks()[-1]['phase'],'cleanup_uncertain')
        with self.assertRaises(Denied):w.state(p['selector'],p['context'],'bob')
        child.close.side_effect=None;w.close()


class ComposedProcessTests(unittest.TestCase):
    def setUp(self):
        self.w=OwnerWorkspace();self.addCleanup(self.w.close)
        self.spec=spec();self.p=preview(self.spec)
        self.w.compose(self.spec,self.p['review_digest'],'CREATE TASK')
        self.service=self.w._slots[self.p['selector']]['service']
    def action(self,**request):return self.w.action(self.p['selector'],self.p['context'],request)
    def bind(self):
        for owner,pending in self.service.requests.items():
            self.action(action='bind',owner=owner,binding_digest=digest(pending),confirmation='BIND '+owner)
    def approve_submit(self,card):
        self.action(action='approve',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+card['owner'])
        self.action(action='submit',owner=card['owner'],request_id=card['request_id'])
    def send_process(self,card):
        self.approve_submit(card)
        self.action(action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
        self.action(action='process',owner=card['owner'],request_id=card['request_id'])
    def pair(self):
        for _ in range(2):self.approve_submit(self.action(action='next')['card'])

    def test_explicit_response_completes_and_reopen_preserves_composition(self):
        self.assertEqual(self.service.phase,'bindings');self.bind();self.pair()
        card=self.action(action='next')['card'];task,_,request,_=composed_fixture(self.spec)
        self.assertEqual(card['envelope'],request);self.assertEqual(card['owner'],'bob')
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'awaiting')
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assertEqual(self.action(action='next')['kind'],'awaiting')
        result=task_envelope(task,'result',{'items':[]},reply_to=digest(request))
        staged=self.service._command('fixture_agent_call',actor='alice',command={'method':'propose','proposal_id':'response-one','envelope':result})
        self.assertNotIn('signature',canonical(staged))
        self.assertEqual(self.action(action='next')['kind'],'awaiting')
        card=self.w.import_proposal(self.p['selector'],self.p['context'],'alice','response-one')
        with self.assertRaises(Denied):self.action(action='submit',owner='alice',request_id=card['request_id'])
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'complete')

    def test_mutated_request_denied_and_adapter_cannot_compose(self):
        self.bind();self.pair();task,_,request,_=composed_fixture(self.spec)
        mutated=copy.deepcopy(request);mutated['payload']['query']='Changed after owner composition'
        with self.assertRaises(Denied):self.service._command('request_prepare',owner='bob',action='send',envelope=mutated)
        with self.assertRaises(Denied):
            self.service._command('fixture_agent_call',actor='bob',command={'method':'compose_task','spec':spec('evil')})
        with self.assertRaises(Denied):
            self.service._command('fixture_agent_call',actor='bob',command={'method':'propose','proposal_id':'mutated','envelope':mutated})
        card=self.action(action='next')['card']
        decision=copy.deepcopy(card['decision']);decision['target']['envelope_digest']=digest(mutated)
        response=self.service.signers['bob'].request({'decision':decision,'envelope':mutated,'confirmation':'APPROVE bob send '+card['request_id']})
        self.assertFalse(response['ok']);self.assertIn('composition',response['error'])
        self.assertEqual(len(self.w.list_tasks()),3)
        with self.assertRaises(Denied):self.w.state(self.p['selector'],preview(spec('other'))['context'],'bob')

    def test_maximum_unicode_query_real_process_review_and_delivery(self):
        value={**spec('unicode','alice'),'query':'😀'*512};p=preview(value)
        self.w.compose(value,p['review_digest'],'CREATE TASK')
        self.spec,self.p=value,p;self.service=self.w._slots[p['selector']]['service']
        self.bind();self.pair()
        card=self.action(action='next')['card']
        self.assertEqual(card['envelope']['payload']['query'],value['query'])
        self.assertGreater(len(json.dumps({'ok':True,'result':{'kind':'request','card':card}})),16384)
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'awaiting')
        task,_,request,_=composed_fixture(value)
        response=task_envelope(task,'result',{'items':[{'title':'😀'*128,'url':'https://example.invalid/resource','summary':'😀'*512}]},reply_to=digest(request))
        self.service._command('fixture_agent_call',actor='bob',command={'method':'propose','proposal_id':'unicode-result','envelope':response})
        result_card=self.w.import_proposal(p['selector'],p['context'],'bob','unicode-result')
        size=len(json.dumps({'ok':True,'result':{'kind':'request','card':result_card}}))
        self.assertGreater(size,16384);self.assertLess(size,65536)
        self.send_process(result_card)
        self.assertEqual(self.action(action='next')['kind'],'complete')

    def test_custom_instances_isolated_and_no_slot_reuse(self):
        second=spec('two','alice');p=preview(second);self.w.compose(second,p['review_digest'],'CREATE TASK')
        other=self.w._slots[p['selector']]['service']
        self.assertNotEqual(other.roots,self.service.roots);self.assertNotEqual(other.directory.name,self.service.directory.name)
        self.bind();self.pair();self.assertEqual(other.phase,'bindings')
        self.w.close_task(self.p['selector'],self.p['context'])
        with self.assertRaises(Denied):self.w.create(self.p['selector'],self.p['context'])
        with self.assertRaises(Denied):self.w.compose(self.spec,self.p['review_digest'],'CREATE TASK')

if __name__=='__main__':unittest.main()
