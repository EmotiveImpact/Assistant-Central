"""Owner response composer: pure previews, durable history and explicit delivery."""
import copy
import concurrent.futures
import sqlite3
import pathlib
import unittest
from network import Denied, digest
from tests import test_task_composer as helpers
from workspace_ui_service import WorkspaceUIService


class OwnerResponseTests(unittest.TestCase):
    setUp = helpers.ComposedProcessTests.setUp
    action = helpers.ComposedProcessTests.action
    bind = helpers.ComposedProcessTests.bind
    pair = helpers.ComposedProcessTests.pair
    approve_submit = helpers.ComposedProcessTests.approve_submit
    send_process = helpers.ComposedProcessTests.send_process

    def ready(self):
        self.bind(); self.pair()
        card=self.action(action='next')['card'];self.send_process(card)
        return self.w.response_context(self.p['selector'],self.p['context'],'alice')

    def preview(self, payload=None):
        ctx=self.w.response_context(self.p['selector'],self.p['context'],'alice')
        return self.action(action='preview_response',owner='alice',request_digest=ctx['request_digest'],payload=payload or {'items':[]})

    def prepare(self, p):
        return self.action(**self.prepare_body(p))['card']

    def prepare_body(self, p):
        return dict(action='prepare_response',owner='alice',request_digest=p['request_digest'],payload=p['envelope']['payload'],preview_digest=p['preview_digest'],confirmation='REVIEW RESPONSE alice')

    def counts(self):
        result={}
        for path in pathlib.Path(self.service.directory.name).glob('*.sqlite*'):
            if path.suffix != '.sqlite3': continue
            with sqlite3.connect(path) as db:
                for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                    result[(path.name,table)]=db.execute('SELECT * FROM '+table).fetchall()
        return result

    def test_full_lifecycle_and_lost_result_terminal_replay(self):
        ctx=self.ready();p=self.preview();self.assertEqual(p['incoming_request'],ctx['incoming_request'])
        self.assertEqual(p['envelope']['reply_to'],ctx['request_digest'])
        self.assertTrue(self.service.state('alice')['response_composer'])
        card=self.prepare(p);self.assertEqual(card['state'],'pending')
        with self.assertRaises(Denied):self.action(action='submit',owner='alice',request_id=card['request_id'])
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'complete')
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        with self.assertRaises(Denied):self.preview()
        with self.assertRaises(Denied):self.w.response_context(self.p['selector'],self.p['context'],'alice')
        changed=copy.deepcopy(p);changed['envelope']['payload']['items']=[self.item()]
        with self.assertRaises(Denied):self.prepare(changed)

    def item(self):return {'title':'Example','url':'https://example.invalid','summary':'Inert fictional reference'}

    def test_only_processed_request_and_exact_scope_disclose(self):
        self.bind();self.pair()
        for owner in ('alice','bob','other',None,[]):
            with self.assertRaises(Denied):self.w.response_context(self.p['selector'],self.p['context'],owner)
        card=self.action(action='next')['card'];self.approve_submit(card)
        self.action(action='attempt',owner='bob',request_id=card['request_id'],confirmation='SEND bob')
        with self.assertRaises(Denied):self.w.response_context(self.p['selector'],self.p['context'],'alice')
        self.action(action='process',owner='bob',request_id=card['request_id'])
        self.assertEqual(self.preview()['owner'],'alice')
        with self.assertRaises(Denied):self.w.response_context(self.p['selector'],'0'*64,'alice')
        with self.assertRaises(Denied):self.w.response_context(self.p['selector'],self.p['context'],'bob')

    def test_preview_pure_detached_and_no_authority(self):
        self.ready();before=self.counts();p=self.preview({'items':[self.item()]})
        self.assertEqual(before,self.counts())
        self.assertEqual(self.action(action='next')['kind'],'awaiting')
        p['incoming_request']['payload']['query']='changed';p['envelope']['payload']['items'][0]['title']='changed'
        self.assertEqual(self.preview({'items':[self.item()]})['envelope']['payload']['items'][0]['title'],'Example')
        with self.assertRaises(Denied):self.prepare(p)
        self.assertEqual(before,self.counts())

    def test_closed_schema_types_unicode_and_bounds(self):
        ctx=self.ready();base=dict(action='preview_response',owner='alice',request_digest=ctx['request_digest'],payload={'items':[]})
        bad=[{**base,'extra':1},{**base,'owner':'bob'},{**base,'request_digest':'0'*64},{**base,'request_digest':[]},
             {**base,'payload':[]},{**base,'payload':{'items':[],'url':'x'}},{**base,'payload':{'items':{}}},
             {**base,'payload':{'items':[self.item()]*3}}]
        for field,value in [('title','\ud800'),('title','x'*129),('summary',None),('url','http://example.invalid')]:
            bad.append({**base,'payload':{'items':[{**self.item(),field:value}]}})
        for request in bad:
            with self.subTest(request=repr(request)),self.assertRaises(Denied):self.action(**request)
        p=self.preview();body=self.prepare_body(p)
        for request in ({**body,'confirmation':'APPROVE alice'},{**body,'preview_digest':None},{**body,'extra':1},{**body,'request_digest':'0'*64}):
            with self.assertRaises(Denied):self.action(**request)
        unicode_item={**self.item(),'title':'😀'*128,'summary':'😀'*512}
        card=self.prepare(self.preview({'items':[unicode_item]}));self.send_process(card)

    def test_transport_bounds_leave_process_alive(self):
        self.ready()
        large={**self.item(),'title':'😀'*128,'url':'https://'+'😀'*248,'summary':'😀'*512}
        with self.assertRaises(Denied):self.preview({'items':[large,large]})
        # The canonical 8192-byte envelope check remains independent of frame
        # protection. No oversized request should kill or desynchronize a child.
        self.assertEqual(self.preview()['envelope']['payload'],{'items':[]})
        with self.assertRaises(Denied):self.preview({'items':[large]})
        p=self.preview({'items':[{**large,'url':'https://example.invalid'}]})
        card=self.prepare(p)
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'complete')

    def test_repeat_decline_defer_and_changed_content(self):
        self.ready();p=self.preview();card=self.prepare(p)
        for choice in ('defer','decline'):
            card=self.action(action=choice,owner='alice',request_id=card['request_id'],review_digest=card['review_digest'])['card']
            self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assertEqual(self.prepare(p)['state'],'declined')
        self.assertNotEqual(self.prepare(self.preview({'items':[self.item()]}))['request_id'],card['request_id'])

    def test_authorized_withdrawn_history_and_reopen(self):
        self.ready();p=self.preview();card=self.prepare(p)
        card=self.action(action='approve',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE alice')['card']
        self.assertEqual(self.prepare(p)['state'],'authorized')
        card=self.action(action='withdraw_unused',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'],confirmation='WITHDRAW alice')['card']
        self.assertEqual(self.prepare(p)['state'],'withdrawn')
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])

    def test_agent_import_history_cannot_be_bypassed(self):
        self.ready();p=self.preview()
        self.service._command('fixture_agent_call',actor='alice',command={'method':'propose','proposal_id':'owner-response','envelope':p['envelope']})
        card=self.w.import_proposal(self.p['selector'],self.p['context'],'alice','owner-response')
        self.action(action='decline',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'])
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        self.assertEqual(self.prepare(p)['state'],'declined')
        for method in ('response_context','preview_response','prepare_response'):
            with self.assertRaises(Denied):self.service._command('fixture_agent_call',actor='alice',command={'method':method})

    def test_concurrent_repeated_prepare_returns_one_review(self):
        self.ready();p=self.preview()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            cards=list(pool.map(lambda _:self.prepare(p),range(10)))
        self.assertEqual(len({card['request_id'] for card in cards}),1)

    def test_cancel_blocks_new_content_but_not_original_history(self):
        self.ready();p=self.preview();card=self.prepare(p)
        other=self.preview({'items':[self.item()]})
        cancel=self.action(action='cancel',owner='bob')['card'];self.approve_submit(cancel)
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        with self.assertRaises(Denied):self.prepare(other)
        with self.assertRaises(Denied):self.preview()

    def test_workspace_wrapper_and_catalog_denial(self):
        self.ready();service=WorkspaceUIService();service.workspace=self.w
        ctx=service.response_context(self.p['selector'],self.p['context'],'alice')
        p=service.action({'selector':self.p['selector'],'context':self.p['context'],'request':dict(action='preview_response',owner='alice',request_digest=ctx['request_digest'],payload={'items':[]})})
        self.assertEqual(p['owner'],'alice')
        catalog=self.w.list_tasks()[0];self.w.create(catalog['selector'],catalog['context'])
        child=self.w._slots[catalog['selector']]['service']
        for owner,pending in child.requests.items():child.action(dict(action='bind',owner=owner,binding_digest=digest(pending),confirmation='BIND '+owner))
        self.assertNotIn('response_composer',child.state('alice'))
        with self.assertRaises(Denied):service.response_context(catalog['selector'],catalog['context'],'alice')
