"""Local exact membership/fence tests. No sockets or browser."""
import copy
import json
import threading
import unittest
from unittest.mock import patch, Mock
from network import Denied, digest
from owner_workspace import OwnerWorkspace
from relationship_workspace import MAX_GROUPS, MAX_MEMBERS, AFTER_STOP_ACTIONS
from workspace_ui_service import WorkspaceUIService
from test_owner_workspace import WorkspaceTests
from test_workspace_ui import InProcessHTTP


class GroupContractTests(unittest.TestCase):
    def setUp(self):
        self.w = OwnerWorkspace()
        self.addCleanup(self.w.close)
        self.members = [{k:r[k] for k in ('selector','context')} for r in self.w.list_tasks()]

    def create(self, members=None, gid='group-friends'):
        p = self.w.relationship_preview({'operation':'create','spec':{'group_id':gid,'label':'Fictional friends','members':members or self.members[:1]}})
        return self.w.relationship_commit('create',p,'CREATE GROUP')

    def stop(self, gid='group-friends'):
        p = self.w.relationship_preview({'operation':'stop','group_id':gid})
        return self.w.relationship_commit('stop',p,'STOP GROUP')

    def test_preview_is_pure_detached_and_does_not_create_authority(self):
        before = self.w.list_tasks()
        p = self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-one','label':'Bob','members':self.members}})
        self.assertEqual(self.w.relationships(),[])
        self.assertEqual(before,self.w.list_tasks()); self.assertEqual(self.w._slots,{})
        group = self.w.relationship_commit('create',p,'CREATE GROUP')
        group['members'].clear(); p['members'].clear()
        self.assertEqual(len(self.w.relationships()[0]['members']),2)
        self.assertEqual([r['phase'] for r in before],[r['phase'] for r in self.w.list_tasks()])
        self.assertEqual(self.w._slots,{})

    def test_stale_membership_review_and_exact_stop_retry(self):
        self.create()
        stale = self.w.relationship_preview({'operation':'stop','group_id':'group-friends'})
        attach = self.w.relationship_preview({'operation':'attach','group_id':'group-friends','member':self.members[1]})
        self.w.relationship_commit('attach',attach,'ATTACH TASK')
        with self.assertRaises(Denied):self.w.relationship_commit('stop',stale,'STOP GROUP')
        p = self.w.relationship_preview({'operation':'stop','group_id':'group-friends'})
        stopped = self.w.relationship_commit('stop',p,'STOP GROUP')
        self.assertEqual(stopped,self.w.relationship_commit('stop',copy.deepcopy(p),'STOP GROUP'))
        self.assertEqual(p,self.w.relationship_preview({'operation':'stop','group_id':'group-friends'}))
        with self.assertRaises(Denied):self.w.relationship_commit('stop',stale,'STOP GROUP')
        with self.assertRaises(Denied):self.w.relationship_commit('attach',attach,'ATTACH TASK')
        self.assertTrue(all(r['local_work_stopped'] for r in self.w.list_tasks()))
        for m in self.members:
            with self.assertRaises(Denied):self.w.create(**m)
        with self.assertRaises(Denied):self.create(gid='group-another')

    def test_no_label_inference_overlap_fences_and_lifetime_tombstones(self):
        self.create()
        self.create(self.members,'group-overlap')
        self.stop()
        self.assertFalse(self.w.list_tasks()[1]['local_work_stopped'])
        self.w.create(**self.members[1])
        with self.assertRaises(Denied):self.create(gid='group-friends')
        self.w.close_task(**self.members[1])
        with self.assertRaises(Denied):self.w.create(**self.members[1])
        self.assertEqual(len(self.w.relationships()),2)

    def test_invalid_closed_schemas_and_review_types(self):
        bad = [None,[],{}, {'operation':'resume','group_id':'group-x'},
               {'operation':'stop','group_id':True},
               {'operation':'create','spec':{'group_id':'group-x','label':'x','members':[]}},
               {'operation':'create','spec':{'group_id':'group-x','label':'x','members':[dict(self.members[0],owner='bob')]}},
               {'operation':'create','spec':{'group_id':'group-x','label':'x','members':[self.members[0]]*2}},
               {'operation':'create','spec':{'group_id':'group-x','label':'x','members':[dict(self.members[0],context=self.members[1]['context'])]}}]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(Denied):self.w.relationship_preview(body)
        self.create()
        p = self.w.relationship_preview({'operation':'stop','group_id':'group-friends'})
        for patch_value in ({'revision':True},{'extra':1},{'review_digest':'0'*64},{'members':[]}):
            with self.assertRaises(Denied):self.w.relationship_commit('stop',dict(p,**patch_value),'STOP GROUP')
        for phrase in ('STOP',True,None,'STOP GROUP '):
            with self.assertRaises(Denied):self.w.relationship_commit('stop',p,phrase)
        self.assertFalse(self.w.relationships()[0]['stopped'])

    def test_capacity_and_stale_create_attach(self):
        request = {'operation':'create','spec':{'group_id':'group-stale','label':'x','members':self.members[:1]}}
        stale = self.w.relationship_preview(request)
        for i in range(MAX_GROUPS):self.create(gid='group-'+str(i))
        with self.assertRaises(Denied):self.w.relationship_commit('create',stale,'CREATE GROUP')
        with self.assertRaises(Denied):self.create(gid='group-extra')
        with self.assertRaises(Denied):self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-many','label':'x','members':self.members*(MAX_MEMBERS+1)}})

    def test_attach_capacity_and_stale_attach_are_exact(self):
        self.create()
        body={'operation':'attach','group_id':'group-friends','member':self.members[1]}
        p=self.w.relationship_preview(body)
        with patch('relationship_workspace.MAX_MEMBERS',1):
            with self.assertRaises(Denied):self.w.relationship_preview(body)
        self.w.relationship_commit('attach',p,'ATTACH TASK')
        with self.assertRaises(Denied):self.w.relationship_commit('attach',p,'ATTACH TASK')

    def test_custom_capabilities_keep_independent_identity_and_fence(self):
        from generic_capabilities import BOUNDED_TEXT
        for index, text in enumerate((False,True)):
            spec={'selector':'custom-group-'+str(index),'task_id':'task-group-'+str(index),
                  'conversation_id':'conversation-group-'+str(index),'requester':'alice',
                  'query':'A fictional question'}
            spec.update({'capability':BOUNDED_TEXT,'max_reply_chars':64} if text else {'max_items':1})
            p=self.w.task_preview(spec)
            row=self.w.compose(spec,p['review_digest'],'CREATE TASK')
            member={k:row[k] for k in ('selector','context')}
            service=self.w._slots[row['selector']]['service']
            roots=copy.deepcopy(service.roots)
            self.create([member],gid='group-custom-'+str(index))
            self.assertEqual(roots,service.roots);self.assertFalse(service.bindings)
            self.stop('group-custom-'+str(index))
            self.assertTrue(self.w.state(**member,owner='alice')['local_work_stopped'])
            with self.assertRaises(Denied):self.w.action(**member,request={'action':'next'})
            with self.assertRaises(Denied):self.w.compose(spec,p['review_digest'],'CREATE TASK')
            self.assertTrue(self.w.close_task(**member)['closed'])
            self.assertTrue(any(g['stopped'] for g in self.w.relationships() if member in g['members']))

    def test_tampering_fails_closed_but_cleanup_allowed(self):
        self.w.create(**self.members[0]); self.create()
        self.w._relationships._groups['group-friends']['members'].clear()
        for operation in (lambda:self.w.relationships(),lambda:self.w.action(**self.members[0],request={'action':'next'}),lambda:self.w.create(**self.members[1])):
            with self.assertRaises(Denied):operation()
        self.assertTrue(self.w.action(**self.members[0],request={'action':'close','confirmation':'DISCARD FIXTURE'})['closed'])

    def test_closed_http_contract(self):
        ui = WorkspaceUIService(); self.addCleanup(ui.close)
        http = InProcessHTTP(ui)
        body = {'operation':'create','spec':{'group_id':'group-http','label':'Offline','members':self.members}}
        code,_,data = http.call('POST','/api/relationship-preview',body)
        self.assertEqual(code,200); p=json.loads(data)
        code,_,_ = http.call('POST','/api/action',{'action':'relationship_create','review':p,'confirmation':'CREATE GROUP'})
        self.assertEqual(code,200)
        code,_,data = http.call('GET','/api/relationships')
        self.assertEqual(code,200);self.assertEqual(len(json.loads(data)),1)
        for body in ({'action':'relationship_stop','review':p,'confirmation':'STOP GROUP','owner':'alice'}, {'action':'relationship_resume','review':p,'confirmation':'RESUME'}):
            self.assertEqual(http.call('POST','/api/action',body)[0],400)


class GroupIntegrationTests(WorkspaceTests):
    # Reuse the existing process-backed workspace helpers, not inherited tests.
    def group(self, key='garden'):
        members = [{'selector':key,'context':self.ctx[key]}]
        p=self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-'+key,'label':'Fictional','members':members}})
        return self.w.relationship_commit('create',p,'CREATE GROUP')
    def stop(self,key='garden'):
        p=self.w.relationship_preview({'operation':'stop','group_id':'group-'+key})
        return self.w.relationship_commit('stop',p,'STOP GROUP')

    def test_grouping_no_authority_keys_or_state_change(self):
        s=self.service('garden');before=(copy.deepcopy(s.bindings),copy.deepcopy(s.roots),s.phase)
        self.group()
        self.assertEqual(before,(s.bindings,s.roots,s.phase))
        self.assertFalse(self.service('astronomy').bindings)

    def test_every_mutation_fenced_before_service_even_old_adapter(self):
        self.bind('garden');adapter=self.adapter('garden','alice')
        from task_fixtures import fixture
        self.rpc(adapter,'propose',{'proposal_id':'early','envelope':fixture('garden')[2]})
        self.group();self.stop()
        s=self.service('garden')
        denied = ['bind','preview_response','prepare_response','next','approve','replace_review','review_pairing','fresh_after_withdrawal','submit','attempt','process','cancel','revoke','unknown']
        with patch.object(s,'action',side_effect=AssertionError('service entered')):
            for action in denied:
                with self.subTest(action=action),self.assertRaises(Denied):self.action('garden',action=action)
        for call in (lambda:self.w.import_proposal('garden',self.ctx['garden'],'alice','id'),lambda:self.w.adapter('garden',self.ctx['garden'],'alice'),lambda:self.w.reopen_storage('garden',self.ctx['garden'])):
            with self.assertRaises(Denied):call()
        from task_fixtures import fixture
        self.assertTrue(self.rpc(adapter,'propose',{'proposal_id':'late','envelope':fixture('garden')[2]})['result']['isError'])
        self.assertFalse(self.rpc(adapter,'inbox')['result']['isError'])
        self.assertFalse(self.rpc(adapter,'proposal_status',{'proposal_id':'early'})['result']['isError'])
        self.bind('astronomy');self.pair('astronomy');self.finish('astronomy',self.request('astronomy'))

    def test_received_history_receipt_reconcile_no_processing(self):
        self.bind('garden');self.pair('garden');card=self.request('garden');self.finish('garden',card)
        prior=self.w.received_messages('garden',self.ctx['garden'],'bob')
        reply=self.resolve('garden',self.request('garden'));self.submit('garden',reply)
        self.service('garden')._command('fixture_lose_ack',owner=reply['owner'],request_id=reply['request_id'])
        self.group();self.stop()
        self.assertEqual(prior,self.w.received_messages('garden',self.ctx['garden'],'bob'))
        before=self.w.delivery('garden',self.ctx['garden'],reply['owner'],reply['request_id'])
        self.assertFalse(before['can_process']);self.assertFalse(before['can_start_attempt'])
        self.assertEqual(before['state'],'dispatched')
        checked=self.action('garden',action='check',owner=reply['owner'],request_id=reply['request_id'])
        self.assertEqual(checked['state'],'received');self.assertFalse(checked['can_process'])
        self.assertEqual(checked['attempts'],before['attempts'])
        self.action('garden',action='recover',owner=reply['owner'],request_id=reply['request_id'])
        self.assertEqual(self.summary('garden')['transitions'],1)
        with self.assertRaises(Denied):self.action('garden',action='process',owner=reply['owner'],request_id=reply['request_id'])
        self.assertTrue(self.w.review('garden',self.ctx['garden'],reply['owner'],reply['request_id']))
        self.assertIsInstance(self.w.proposals('garden',self.ctx['garden'],'alice'),list)

    def test_reducing_actions_allowed_no_fresh_authority(self):
        for key, choice in [('garden','defer'),('astronomy','decline')]:
            self.bind(key);self.pair(key);card=self.request(key);self.group(key);self.stop(key)
            self.assertEqual(self.resolve(key,card,choice)['state'], 'deferred' if choice=='defer' else 'declined')
            self.assertEqual(self.summary(key)['transitions'],0)
        self.assertEqual(AFTER_STOP_ACTIONS,{'check','recover','decline','defer','withdraw_unused'})
        for action in AFTER_STOP_ACTIONS:
            with self.assertRaises(Denied):self.action('garden',action=action,owner='alice',request_id='x',effectful_extra=True)

    def test_withdraw_after_stop_without_send_or_replacement(self):
        self.bind('garden');self.pair('garden');card=self.resolve('garden',self.request('garden'))
        self.group();self.stop()
        result=self.action('garden',action='withdraw_unused',owner=card['owner'],request_id=card['request_id'],review_digest=card['review_digest'],confirmation='WITHDRAW '+card['owner'])
        self.assertEqual(result['card']['state'],'withdrawn');self.assertEqual(self.summary('garden')['transitions'],0)
        with self.assertRaises(Denied):self.submit('garden',card)

    def test_inflight_operation_can_finish_stop_fences_next(self):
        self.bind('garden');self.pair('garden');card=self.resolve('garden',self.request('garden'));self.submit('garden',card);self.group()
        entered=threading.Event();release=threading.Event();stopped=threading.Event();errors=[]
        original=self.service('garden').action
        def slow(request):
            entered.set()
            if not release.wait(5):raise RuntimeError('test synchronization timeout')
            return original(request)
        def send():
            try:self.action('garden',action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
            except BaseException as exc:errors.append(exc)
        def stop():
            try:self.stop();stopped.set()
            except BaseException as exc:errors.append(exc)
        with patch.object(self.service('garden'),'action',side_effect=slow):
            a=threading.Thread(target=send);a.start();self.assertTrue(entered.wait(5))
            b=threading.Thread(target=stop);b.start();self.assertFalse(stopped.wait(.05));release.set();a.join(5);b.join(5)
        self.assertFalse(errors);self.assertTrue(stopped.is_set())
        self.assertEqual(self.w.delivery('garden',self.ctx['garden'],card['owner'],card['request_id'])['state'],'received')
        with self.assertRaises(Denied):self.action('garden',action='process',owner=card['owner'],request_id=card['request_id'])

# Prevent inherited baseline tests from being discovered twice in this class.
for _name in tuple(vars(WorkspaceTests)):
    if _name.startswith('test_') and _name not in vars(GroupIntegrationTests):
        setattr(GroupIntegrationTests,_name,None)
# Imported TestCase helpers otherwise also get discovered by unittest.
del WorkspaceTests
