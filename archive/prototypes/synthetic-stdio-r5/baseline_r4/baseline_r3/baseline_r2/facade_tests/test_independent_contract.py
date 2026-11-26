"""Independent sequential application contract probes; no process or transport use."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from independent_peer.endpoint import Endpoint
from independent_peer.protocol import Rejected, digest, token
from facade_candidate.store import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher

class Contract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ep = {a: Endpoint(a, self.root / (a + '.db')) for a in ('alice', 'bob')}
        self.public = {a: e.identity.descriptor for a,e in self.ep.items()}
        self.task = {'id': token(), 'context': digest('review'), 'capability':'fictional-answer/1'}
        for a,e in self.ep.items():
            e.handle_owner({'op':'configure','operation_id':token(),'task':self.task,'peer':self.public['bob' if a=='alice' else 'alice']})
        self.path = self.root / 'proposals.db'
        self.open()
    def open(self):
        self.store = ProposalStore(self.path, actor='alice', task_value=self.task, public=self.public)
        self.api = AssistantFacade(self.store)
        self.owner = OwnerReview(self.store)
        self.publisher = SnapshotPublisher(self.store)
    def tearDown(self):
        self.store.close()
        for e in self.ep.values(): e.close()
        self.tmp.cleanup()
    def propose(self, text='Exact question'):
        return self.api.propose({'text':text})
    def prepare(self,p):
        grant = self.ep['bob'].handle_owner({'op':'allow_receive','operation_id':token()})['grant']
        return self.owner.prepare_approve_and_release(p['proposal_id'], reviewed_content_digest=p['content_digest'], reviewed_grant_digest=digest(grant),grant=grant)
    def test_durable_unknown_without_execution(self):
        p=self.propose(); command=self.prepare(p)
        self.assertEqual(self.ep['alice'].snapshot()['outgoing'],[])
        self.store.close(); self.open()
        self.assertEqual(self.propose()['state'],'unknown')
        self.assertEqual(self.propose()['command_digest'],digest(command))
        with self.assertRaises(Rejected): self.prepare(p)
    def test_failed_save_returns_no_command_and_no_unknown(self):
        p=self.propose()
        self.store._db.execute("CREATE TRIGGER reject_save BEFORE INSERT ON proposals BEGIN SELECT RAISE(ABORT, 'review injected persistence failure'); END")
        self.store._db.commit()
        with self.assertRaises(sqlite3.IntegrityError): self.prepare(p)
        self.assertEqual(self.propose()['state'],'pending')
        self.assertEqual(self.ep['alice'].snapshot()['outgoing'],[])
    def test_actual_release_is_not_delivery(self):
        p=self.propose(); c=self.prepare(p); response=self.ep['alice'].handle_owner(c)
        result=self.owner.record_response(p['proposal_id'],operation_id=c['operation_id'],command_digest=digest(c),response=response)
        self.assertEqual(result['state'],'released')
        self.assertIn('delivery unknown',result['evidence_basis'])
        self.assertEqual(self.ep['bob'].snapshot()['incoming'],[])
        self.store.close(); self.open()
        self.assertEqual(self.propose(),result)
    def test_unrecorded_release_reconciles_only_content(self):
        p=self.propose(); c=self.prepare(p); self.ep['alice'].handle_owner(c)
        out=self.owner.reconcile_snapshot(p['proposal_id'],self.ep['alice'].snapshot())
        self.assertEqual(out['state'],'committed_content_observed')
        self.assertIsNone(out['packet_digest'])
        self.assertIn('causation',out['evidence_basis'])
        with self.assertRaises(Rejected): self.prepare(p)
    def test_processed_only_real_endpoint_projection(self):
        p=self.propose(); c=self.prepare(p); response=self.ep['alice'].handle_owner(c)
        bobstore=ProposalStore(self.root/'bob-proposals.db',actor='bob',task_value=self.task,public=self.public)
        try:
            api=AssistantFacade(bobstore); publisher=SnapshotPublisher(bobstore)
            self.ep['bob'].handle_peer({'op':'deliver','value':response['packet']})
            publisher.publish(self.ep['bob'].snapshot())
            self.assertEqual(api.processed_inbox({})['items'],[])
            self.ep['bob'].handle_owner({'op':'process','operation_id':token(),'id':response['id']})
            publisher.publish(self.ep['bob'].snapshot())
            self.assertEqual(api.processed_inbox({})['items'][0]['payload'],'Exact question')
            self.ep['bob'].handle_owner({'op':'cancel','operation_id':token()})
            publisher.publish(self.ep['bob'].snapshot())
            self.assertEqual(len(api.processed_inbox({})['items']),1)
        finally: bobstore.close()
    def test_full_history_preserves_decline_and_unknown(self):
        declined=self.propose('declined'); self.owner.decline(declined['proposal_id'])
        unknown=self.propose('unknown'); self.prepare(unknown)
        for i in range(62): self.propose(str(i))
        with self.assertRaises(Rejected): self.propose('new')
        self.store.close(); self.open()
        self.assertEqual(self.propose('declined')['state'],'declined')
        self.assertEqual(self.propose('unknown')['state'],'unknown')
    def test_mixed_utf8_bound_and_unicode_identity(self):
        self.propose('😀'*255+'abcd')
        with self.assertRaises(Rejected): self.propose('😀'*255+'abcde')
        with self.assertRaises(Rejected): self.propose('\udfff')
        self.assertNotEqual(self.propose('é')['proposal_id'],self.propose('e\u0301')['proposal_id'])
    def test_changed_binding_context_and_peer_key_rejected(self):
        self.propose()
        for field in ('context','peer_key'):
            task=copy.deepcopy(self.task); public=copy.deepcopy(self.public)
            if field=='context': task['context']=digest('different')
            else: public['bob']['signing']=public['alice']['signing']
            with self.assertRaises(Rejected): ProposalStore(self.path,actor='alice',task_value=task,public=public)
    def test_wrong_response_correlation_leaves_unknown(self):
        p=self.propose(); c=self.prepare(p); response=self.ep['alice'].handle_owner(c)
        for op,cd in ((token(),digest(c)),(c['operation_id'],digest('wrong'))):
            with self.assertRaises(Rejected): self.owner.record_response(p['proposal_id'],operation_id=op,command_digest=cd,response=response)
        self.assertEqual(self.propose()['state'],'unknown')

    def test_foreign_header_response_rejected_before_recording(self):
        p=self.propose(); c=self.prepare(p); response=self.ep['alice'].handle_owner(c)
        response['packet']['header']['recipient_binding']=digest('foreign incarnation')
        with self.assertRaises(Rejected):
            self.owner.record_response(p['proposal_id'],operation_id=c['operation_id'],command_digest=digest(c),response=response)
        self.assertEqual(self.propose()['state'],'unknown')
    def test_content_observation_blocks_late_actual_response(self):
        p=self.propose(); c=self.prepare(p); response=self.ep['alice'].handle_owner(c)
        observed=self.owner.reconcile_snapshot(p['proposal_id'],self.ep['alice'].snapshot())
        with self.assertRaises(Rejected):
            self.owner.record_response(p['proposal_id'],operation_id=c['operation_id'],command_digest=digest(c),response=response)
        self.assertEqual(self.propose(),observed)
        self.assertEqual(observed['state'],'committed_content_observed')

if __name__=='__main__': unittest.main()
