"""Read-only processed inbound contents, never authorization or agent authority."""
import json
import unittest
from network import Denied, digest
from owner_ui_service import OwnerUIService
from workspace_ui_service import WorkspaceUIService
from tests import test_owner_responses as response_helpers
from tests import test_owner_workspace as workspace_helpers


class OwnerMessageTests(unittest.TestCase):
    setUp = response_helpers.OwnerResponseTests.setUp
    action = response_helpers.OwnerResponseTests.action
    bind = response_helpers.OwnerResponseTests.bind
    pair = response_helpers.OwnerResponseTests.pair
    approve_submit = response_helpers.OwnerResponseTests.approve_submit
    send_process = response_helpers.OwnerResponseTests.send_process
    counts = response_helpers.OwnerResponseTests.counts
    preview = response_helpers.OwnerResponseTests.preview
    prepare = response_helpers.OwnerResponseTests.prepare
    prepare_body = response_helpers.OwnerResponseTests.prepare_body

    def received(self, owner):
        return self.w.received_messages(self.p['selector'], self.p['context'], owner)

    def assert_message(self, owner, card, state):
        view = self.received(owner)
        self.assertEqual(set(view), {'owner','task','context','task_state','messages','payload_trust','fictional','temporary'})
        self.assertEqual(view['owner'], owner)
        self.assertEqual(view['task'], self.service.meeting.id)
        self.assertEqual(view['context'], self.p['context'])
        self.assertEqual(view['task_state'], state)
        self.assertEqual(view['payload_trust'], 'untrusted_inert')
        self.assertIs(view['fictional'], True); self.assertIs(view['temporary'], True)
        self.assertEqual(view['messages'], [{'envelope_digest':digest(card['envelope']),
            'envelope':card['envelope'], 'sender_binding':card['decision']['target']['sender_binding']}])
        serialized=json.dumps(view)
        for secret in ('signature','private_key','request_id','nonce','owner_roots','authorization',card['request_id']):
            self.assertNotIn(secret, serialized)
        return view

    def test_request_and_response_only_after_processing_detached_and_reopened(self):
        self.bind(); self.pair()
        request=self.action(action='next')['card']
        for owner in ('alice','bob'):self.assertEqual(self.received(owner)['messages'], [])
        self.approve_submit(request)
        self.assertEqual(self.received('alice')['messages'], [])
        self.action(action='attempt', owner='bob', request_id=request['request_id'], confirmation='SEND bob')
        self.assertEqual(self.received('alice')['messages'], [])
        self.action(action='process', owner='bob', request_id=request['request_id'])
        v=self.assert_message('alice',request,'requested')
        self.assertEqual(self.received('bob')['messages'], [])
        v['messages'][0]['envelope']['payload']['query']='modified copy'
        self.assert_message('alice',request,'requested')
        result=self.prepare(self.preview())
        self.approve_submit(result)
        self.assertEqual(self.received('bob')['messages'], [])
        self.action(action='attempt',owner='alice',request_id=result['request_id'],confirmation='SEND alice')
        self.assertEqual(self.received('bob')['messages'], [])
        self.action(action='process',owner='alice',request_id=result['request_id'])
        self.assert_message('bob',result,'completed'); self.assert_message('alice',request,'completed')
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assert_message('bob',result,'completed'); self.assert_message('alice',request,'completed')

    def test_no_durable_mutation_or_proposal_tables_on_any_read(self):
        self.bind()
        before=self.counts()
        for _ in range(3):
            for owner in ('alice','bob'):self.received(owner)
        self.assertEqual(before,self.counts())
        self.assertFalse(any(table.startswith('agent_proposal') for _,table in before))
        self.pair(); card=self.action(action='next')['card'];self.send_process(card)
        before=self.counts()
        for _ in range(3):self.assert_message('alice',card,'requested')
        self.assertEqual(before,self.counts())

    def test_corrupted_scope_and_protocol_history_fail_closed(self):
        import pathlib
        import sqlite3
        self.bind();self.pair();card=self.action(action='next')['card'];self.send_process(card)
        for path in pathlib.Path(self.service.directory.name).glob('*.sqlite3'):
            with sqlite3.connect(path) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone():
                    original=db.execute('SELECT context FROM sessions').fetchone()[0]
                    db.execute("UPDATE sessions SET context=?", ('0'*64,));db.commit()
                    with self.assertRaises(Denied):self.received('alice')
                    db.execute('UPDATE sessions SET context=?',(original,));db.commit()
                    body=db.execute('SELECT body FROM transitions').fetchone()[0]
                    mutated=json.loads(body);mutated['recipient']='bob'
                    db.execute('UPDATE transitions SET body=?',(json.dumps(mutated),));db.commit()
                    with self.assertRaises(Denied):self.received('alice')
                    mutated=json.loads(body);mutated['payload']['query']='Different composed question'
                    db.execute('UPDATE transitions SET body=?',(json.dumps(mutated),));db.commit()
                    with self.assertRaises(Denied):self.received('alice')
                    db.execute('UPDATE transitions SET body=?',(body,));db.commit()
                    self.assert_message('alice',card,'requested')
                    break
        else:self.fail('No task projection store found')

    def test_cancellation_preserves_processed_history(self):
        self.bind();self.pair();card=self.action(action='next')['card'];self.send_process(card)
        cancel=self.action(action='cancel',owner='bob')['card'];self.approve_submit(cancel)
        self.assert_message('alice',card,'cancelled')
        self.assertEqual(self.received('bob')['messages'], [])
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assert_message('alice',card,'cancelled')

    def test_uncertain_dispatch_and_unprocessed_lost_receipt_are_hidden(self):
        self.bind();self.pair();card=self.action(action='next')['card'];self.approve_submit(card)
        self.service._command('fixture_lose_ack',owner='bob',request_id=card['request_id'])
        self.assertEqual(self.received('alice')['messages'], [])
        self.service._command('delivery_check',owner='bob',request_id=card['request_id'])
        self.assertEqual(self.received('alice')['messages'], [])
        self.service._command('delivery_process',owner='bob',request_id=card['request_id'])
        self.assert_message('alice',card,'requested')

    def test_blocked_received_after_cancel_and_stopped_uncertain_hidden(self):
        self.bind();self.pair();card=self.action(action='next')['card'];self.approve_submit(card)
        self.service._command('fixture_lose_ack',owner='bob',request_id=card['request_id'])
        cancel=self.action(action='cancel',owner='bob')['card'];self.approve_submit(cancel)
        self.service._command('delivery_check',owner='bob',request_id=card['request_id'])
        result=self.service._command('delivery_process',owner='bob',request_id=card['request_id'])
        self.assertEqual(result['state'],'received_blocked')
        self.assertEqual(self.received('alice')['messages'], [])

    def test_failed_before_receipt_uncertain_hidden(self):
        self.bind();self.pair();card=self.action(action='next')['card'];self.approve_submit(card)
        self.service._command('fixture_fail_before_receipt',owner='bob',request_id=card['request_id'])
        self.assertEqual(self.received('alice')['messages'], [])
        cancel=self.action(action='cancel',owner='bob')['card'];self.approve_submit(cancel)
        self.service._command('delivery_check',owner='bob',request_id=card['request_id'])
        self.assertEqual(self.received('alice')['messages'], [])

    def test_scope_readiness_closed_uncertain_and_trusted_pipe_schema(self):
        with self.assertRaises(Denied):self.received('alice')
        self.bind()
        for owner in ('other',None,[],True):
            with self.assertRaises(Denied):self.received(owner)
        for selector, context in ((self.p['selector'],'0'*64),('garden',self.p['context']),('other',self.p['context'])):
            with self.assertRaises(Denied):self.w.received_messages(selector,context,'alice')
        for command in ({'method':'received_messages'}, {'method':'received_messages','owner':'alice','context':self.p['context']}, {'method':'received_messages','owner':'alice','task':self.service.meeting.id}):
            self.assertFalse(self.service.executor.request(command)['ok'])
        with self.assertRaises(Denied):
            self.service._command('fixture_agent_call',actor='alice',command={'method':'received_messages','owner':'bob'})
        ui=WorkspaceUIService();ui.workspace.close();ui.workspace=self.w
        self.assertEqual(ui.received_messages(self.p['selector'],self.p['context'],'alice'),self.received('alice'))
        self.service.phase='cleanup_uncertain'
        with self.assertRaises(Denied):self.received('alice')
        self.service.phase='ready'
        self.w._slots[self.p['selector']]['phase']='cleanup_uncertain'
        with self.assertRaises(Denied):self.received('alice')
        self.w._slots[self.p['selector']]['phase']='open'
        self.w.close_task(self.p['selector'],self.p['context'])
        with self.assertRaises(Denied):self.received('alice')


class CatalogMessageTests(unittest.TestCase):
    setUp=workspace_helpers.WorkspaceTests.setUp
    service=workspace_helpers.WorkspaceTests.service
    action=workspace_helpers.WorkspaceTests.action
    bind=workspace_helpers.WorkspaceTests.bind
    resolve=workspace_helpers.WorkspaceTests.resolve
    submit=workspace_helpers.WorkspaceTests.submit
    pair=workspace_helpers.WorkspaceTests.pair
    finish=workspace_helpers.WorkspaceTests.finish

    def test_catalog_request_result_and_cross_task_isolation(self):
        for key in self.ctx:self.bind(key);self.pair(key)
        card=self.action('garden',action='next')['card'];self.finish('garden',card)
        owner=card['envelope']['recipient']
        self.assertEqual(self.w.received_messages('garden',self.ctx['garden'],owner)['messages'][0]['envelope'],card['envelope'])
        self.assertEqual(self.w.received_messages('astronomy',self.ctx['astronomy'],owner)['messages'],[])
        result=self.action('garden',action='next')['card'];self.finish('garden',result)
        self.assertEqual(self.w.received_messages('garden',self.ctx['garden'],result['envelope']['recipient'])['messages'][0]['envelope'],result['envelope'])

    def test_legacy_meeting_interface_unchanged(self):
        service=OwnerUIService();self.addCleanup(service.close)
        with self.assertRaises(Denied):service.received_messages('alice')
        for owner,pending in service.requests.items():
            service.action({'action':'bind','owner':owner,'binding_digest':digest(pending),'confirmation':'BIND '+owner})
        with self.assertRaises(Denied):service.received_messages('alice')
        with self.assertRaises(Denied):service._command('received_messages',owner='alice')
        self.assertIn('meeting',service.state('alice'))

if __name__=='__main__':unittest.main()
