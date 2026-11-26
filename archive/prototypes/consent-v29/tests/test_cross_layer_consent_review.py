"""Independent cross-layer consent combinations; fictional local subprocesses."""
import json
from network import Denied
from task_fixtures import fixture
from test_owner_workspace import WorkspaceTests as Base

class CrossLayerReview(Base):
    def setUp(self):
        super().setUp()
        self.bind('garden'); self.pair('garden')
        self.sender = self.adapter('garden', 'alice')
        self.recipient = self.adapter('garden', 'bob')
        self.envelope = fixture('garden')[2]
        self.assertFalse(self.rpc(self.sender, 'propose', {'proposal_id':'original','envelope':self.envelope})['result']['isError'])
        self.card = self.w.import_proposal('garden',self.ctx['garden'],'alice','original')

    def stop(self):
        review=self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-cross-review','label':'Fictional','members':[{'selector':'garden','context':self.ctx['garden']}]}})
        self.w.relationship_commit('create',review,'CREATE GROUP')
        review=self.w.relationship_preview({'operation':'stop','group_id':'group-cross-review'})
        self.w.relationship_commit('stop',review,'STOP GROUP')

    def result(self, host, method, arguments=None):
        reply=self.rpc(host,method,arguments)
        self.assertFalse(reply['result']['isError'],reply)
        return json.loads(reply['result']['content'][0]['text'])

    def test_lost_receipt_then_stop_allows_evidence_not_disclosure_or_alias(self):
        card=self.resolve('garden',self.card); self.submit('garden',card)
        self.service('garden')._command('fixture_lose_ack',owner='alice',request_id=card['request_id'])
        self.w.reopen_storage('garden',self.ctx['garden'])
        self.stop()
        for _ in range(2):
            self.action('garden',action='check',owner='alice',request_id=card['request_id'])
            self.action('garden',action='recover',owner='alice',request_id=card['request_id'])
            self.assertEqual([],self.result(self.recipient,'inbox')['messages'])
            self.assertEqual([],self.w.received_messages('garden',self.ctx['garden'],'bob')['messages'])
        status=self.result(self.sender,'proposal_status',{'proposal_id':'original'})
        self.assertEqual('received',status['delivery_state'])
        self.assertTrue(self.rpc(self.sender,'propose',{'proposal_id':'alias','envelope':self.envelope})['result']['isError'])
        for action in ('process','attempt','submit'):
            fields=dict(action=action,owner='alice',request_id=card['request_id'])
            if action=='attempt': fields['confirmation']='SEND alice'
            with self.assertRaises(Denied): self.action('garden',**fields)
        self.assertEqual(1,self.w.delivery('garden',self.ctx['garden'],'alice',card['request_id'])['attempts'])
        self.assertEqual(0,self.summary('garden')['transitions'])

    def test_owner_successor_sends_but_agent_alias_preserves_withdrawn_original(self):
        card=self.resolve('garden',self.card)
        withdrawn=self.action('garden',action='withdraw_unused',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'],confirmation='WITHDRAW alice')['card']
        successor=self.action('garden',action='fresh_after_withdrawal',owner='alice',request_id=card['request_id'],review_digest=withdrawn['review_digest'],confirmation='REVIEW alice')['card']
        self.finish('garden',successor)
        self.w.reopen_storage('garden',self.ctx['garden'])
        for alias in ('original','fresh-alias'):
            state=self.result(self.sender,'propose',{'proposal_id':alias,'envelope':self.envelope})
            self.assertEqual('withdrawn',state['state'])
            self.assertIsNone(state['delivery_state'])
            self.assertEqual(card['request_id'],self.w.import_proposal('garden',self.ctx['garden'],'alice',alias)['request_id'])
        self.assertEqual([self.envelope],[m['envelope'] for m in self.result(self.recipient,'inbox')['messages']])
        self.assertEqual(1,self.summary('garden')['transitions'])
        with self.assertRaises(Denied): self.submit('garden',card)

    def test_committed_enqueue_lost_ipc_response_kills_child_and_never_replays(self):
        from unittest.mock import patch
        import sqlite3
        from pathlib import Path
        card=self.resolve('garden',self.card)
        service=self.service('garden'); process=service.executor
        original=process._exchange
        def lose_after_commit(payload, deadline):
            original(payload,deadline)
            raise TimeoutError()
        with patch.object(process,'_exchange',side_effect=lose_after_commit):
            with self.assertRaisesRegex(RuntimeError,'outcome may be unknown'):
                self.submit('garden',card)
        self.assertIsNotNone(process.process.poll())
        with sqlite3.connect(Path(service.directory.name)/'sender.sqlite3') as db:
            self.assertEqual([('queued',0)],db.execute('SELECT state,attempts FROM encrypted_outbox').fetchall())
            self.assertEqual(0,db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0])
        for method,args in (('proposal_status',{'proposal_id':'original'}),('propose',{'proposal_id':'after-failure','envelope':self.envelope}),('inbox',{})):
            reply=self.rpc(self.sender,method,args)
            self.assertIn('error',reply)
        self.stop()
        with self.assertRaises(Denied): self.submit('garden',card)
        self.assertTrue(self.w.list_tasks()[0]['local_work_stopped'])
        self.bind('astronomy'); self.pair('astronomy')
        self.finish('astronomy',self.request('astronomy'))
        self.assertEqual(1,self.summary('astronomy')['transitions'])

    def test_stop_allows_withdrawal_but_fences_successor_and_old_unsigned_approval(self):
        card=self.resolve('garden',self.card)
        self.stop()
        withdrawn=self.action('garden',action='withdraw_unused',owner='alice',request_id=card['request_id'],review_digest=card['review_digest'],confirmation='WITHDRAW alice')['card']
        self.assertEqual('withdrawn',self.result(self.sender,'proposal_status',{'proposal_id':'original'})['state'])
        with self.assertRaises(Denied):
            self.action('garden',action='fresh_after_withdrawal',owner='alice',request_id=card['request_id'],review_digest=withdrawn['review_digest'],confirmation='REVIEW alice')
        with self.assertRaises(Denied): self.resolve('garden',self.card)
        self.assertEqual([],self.result(self.recipient,'inbox')['messages'])
        self.assertEqual(0,self.summary('garden')['transitions'])

for name in vars(Base):
    if name.startswith('test_') and name not in vars(CrossLayerReview): setattr(CrossLayerReview,name,None)
del Base
