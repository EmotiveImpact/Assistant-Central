import copy
import tempfile
import unittest
import sqlite3
from unittest.mock import patch
from pathlib import Path
from independent_peer.protocol import Identity, Rejected, digest, scope, token, seal, b64
from facade_candidate import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher


class FacadeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'alice.sqlite'
        self.identities = {name: Identity(name) for name in ('alice', 'bob')}
        self.public = {name: identity.descriptor for name, identity in self.identities.items()}
        self.task = {'id': token(), 'context': digest('fixed task'), 'capability': 'fictional-answer/1'}
        self.open()

    def open(self):
        self.store = ProposalStore(self.path, actor='alice', task_value=self.task, public=self.public)
        self.api = AssistantFacade(self.store)
        self.owner = OwnerReview(self.store)
        self.publisher = SnapshotPublisher(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def proposal(self, text='Question?'):
        return self.api.propose({'text': text})

    def grant(self):
        return self.identities['bob'].sign('grant', {
            'scope': scope(self.task, 'alice', 'bob', 'request'), 'nonce': token(), 'epoch': 1,
            'sender_binding': digest(self.public['alice']), 'recipient_binding': digest(self.public['bob'])})

    def prepare(self, proposal):
        grant = self.grant()
        review = self.owner.review(proposal['proposal_id'], grant=grant)
        return self.owner.prepare_approve_and_release(proposal['proposal_id'],
            reviewed_content_digest=review['status']['content_digest'],
            reviewed_grant_digest=review['selected_grant_digest'], grant=review['selected_grant'])

    def snapshot(self):
        return {'actor': 'alice', 'identity': copy.deepcopy(self.public['alice']), 'pid': 123,
                'configured': True, 'policy': {'terminal': None}, 'incoming': [], 'outgoing': [],
                'processed_projection': [], 'owner_operation_count': 0}

    def item(self, payload='Answer', kind='result'):
        return {'id': token(), 'kind': kind, 'message_digest': digest(payload),
                'received_evidence_present': True, 'processed_evidence_present': True, 'payload': payload}

    def test_three_exact_methods(self):
        self.assertEqual({n for n in dir(self.api) if not n.startswith('_')}, {'propose', 'status', 'processed_inbox'})
        for data in ({}, {'text': 'x', 'actor': 'bob'}, {'text': 'x', 'task': 'x'}, {'text': 'x', 'owner': 'approve_send'}, {'text': 'x', 'proposal_id': token()}):
            with self.assertRaises(Rejected): self.api.propose(data)
        with self.assertRaises(Rejected): self.api.status({'proposal_id': self.proposal()['proposal_id'], 'actor':'bob'})
        with self.assertRaises(Rejected): self.api.processed_inbox({'raw':True})

    def test_strict_scalar_and_utf8_bounds(self):
        for bad in ('', None, 1, True, {}, [], '\ud800', 'x'*1025, '😀'*257):
            with self.assertRaises(Rejected): self.proposal(bad)
        self.proposal('😀'*256)
        self.proposal('x'*1024)

    def test_no_normalization_or_trimming(self):
        values = ['é', 'e\u0301', ' x', 'x ', 'x', ' ']
        self.assertEqual(len({self.proposal(v)['proposal_id'] for v in values}), len(values))

    def test_identity_repeat_decline_reopen(self):
        p = self.proposal()
        self.owner.decline(p['proposal_id'])
        self.store.close(); self.open()
        repeat = self.proposal()
        self.assertEqual(repeat['proposal_id'], p['proposal_id'])
        self.assertEqual(repeat['state'], 'declined')
        with self.assertRaises(Rejected): self.prepare(repeat)

    def test_unknown_before_command_return_survives_exception_reopen(self):
        p = self.proposal(); command = self.prepare(p)
        self.assertEqual(self.proposal()['state'], 'unknown')
        # Simulated caller exception; no transport fault construction or audit.
        try: raise RuntimeError('caller failed before observing execution')
        except RuntimeError: pass
        self.store.close(); self.open()
        self.assertEqual(self.proposal()['operation_id'], command['operation_id'])
        with self.assertRaises(Rejected): self.prepare(p)
        with self.assertRaises(Rejected): self.owner.decline(p['proposal_id'])

    def test_binding_task_actor_and_both_incarnations(self):
        for field in ('task', 'actor', 'alice', 'bob'):
            task = copy.deepcopy(self.task); public = copy.deepcopy(self.public); actor = 'alice'
            if field == 'task': task['id'] = token()
            elif field == 'actor': actor = 'bob'
            else: public[field]['incarnation'] = token()
            with self.assertRaises(Rejected): ProposalStore(self.path, actor=actor, task_value=task, public=public)

    def test_other_actor_cannot_read_local_proposal(self):
        p = self.proposal()
        bob = ProposalStore(Path(self.tmp.name) / 'bob.sqlite', actor='bob', task_value=self.task, public=self.public)
        try:
            api = AssistantFacade(bob)
            with self.assertRaises(Rejected): api.status({'proposal_id': p['proposal_id']})
            self.assertNotEqual(api.propose({'text': 'Question?'})['proposal_id'], p['proposal_id'])
        finally:
            bob.close()

    def test_detached_inputs_outputs(self):
        p = self.proposal(); original = copy.deepcopy(p)
        p['state'] = 'released'; self.task['context'] = digest('mutated')
        self.public['bob']['incarnation'] = token()
        self.assertEqual(self.proposal(), original)
        review = self.owner.review(original['proposal_id']); review['binding']['actor'] = 'bob'
        self.assertEqual(self.owner.review(original['proposal_id'])['binding']['actor'], 'alice')

    def test_finite_history_no_eviction(self):
        for i in range(64): self.proposal(str(i))
        with self.assertRaises(Rejected): self.proposal('overflow')
        self.assertEqual(self.proposal('0')['state'], 'pending')

    def test_review_digest_and_grant_must_match(self):
        p = self.proposal(); grant = self.grant()
        for cd, gd in [('bad', digest(grant)), (p['content_digest'], 'bad')]:
            with self.assertRaises(Rejected):
                self.owner.prepare_approve_and_release(p['proposal_id'], reviewed_content_digest=cd,
                    reviewed_grant_digest=gd, grant=grant)
        self.assertEqual(self.proposal()['state'], 'pending')

    def test_grant_signature_and_scope_validation(self):
        p = self.proposal(); grant = self.grant(); grant['body']['epoch'] = 9
        with self.assertRaises(Rejected):
            self.owner.prepare_approve_and_release(p['proposal_id'], reviewed_content_digest=p['content_digest'],
                reviewed_grant_digest=digest(grant), grant=grant)
        self.assertEqual(self.proposal()['state'], 'pending')

    def test_command_mutation_does_not_change_stored_commitment(self):
        p = self.proposal(); command = self.prepare(p); original_digest = digest(command)
        command['payload'] = 'altered'; command['grant'].clear()
        self.assertEqual(self.proposal()['command_digest'], original_digest)
        self.assertEqual(self.owner.review(p['proposal_id'])['text'], 'Question?')

    def test_known_rejection_never_retry(self):
        p = self.proposal(); command = self.prepare(p)
        args = dict(operation_id=command['operation_id'], command_digest=digest(command))
        with self.assertRaises(Rejected): self.owner.record_rejection(p['proposal_id'], **args, rejection=RuntimeError())
        self.assertEqual(self.proposal()['state'], 'unknown')
        self.owner.record_rejection(p['proposal_id'], **args, rejection=Rejected('actual endpoint rejection'))
        self.assertEqual(self.proposal()['state'], 'rejected')
        with self.assertRaises(Rejected): self.prepare(p)

    def test_actual_response_narrow_and_correlated(self):
        p = self.proposal(); command = self.prepare(p)
        response = {'id': token(), 'message_digest': digest('message'), 'packet': seal(self.identities['alice'], self.public['bob'], {'synthetic':'opaque body'}),
                    'release':'approved_and_released', 'historical_replay':False}
        with self.assertRaises(Rejected):
            self.owner.record_response(p['proposal_id'], operation_id=token(), command_digest=digest(command), response=response)
        out = self.owner.record_response(p['proposal_id'], operation_id=command['operation_id'], command_digest=digest(command), response=response)
        self.assertEqual(out['state'], 'released')
        self.assertNotIn('packet', out); self.assertNotIn('grant', out)
        self.assertIn('delivery unknown', out['evidence_basis'])
        self.assertEqual(out['packet_digest'], digest(response['packet']))

    def test_release_packet_shape_and_binding_rejections(self):
        p = self.proposal(); command = self.prepare(p)
        valid = seal(self.identities['alice'], self.public['bob'], {'synthetic':'opaque body'})
        invalid = []
        for key, value in [('protocol', 'other/1'), ('sender', 'bob'), ('recipient', 'alice'),
                           ('sender_binding', digest('another incarnation')),
                           ('recipient_binding', digest('another incarnation')),
                           ('ephemeral', b64(b'x'*31)), ('nonce', b64(b'x'*11))]:
            packet = copy.deepcopy(valid); packet['header'][key] = value; invalid.append(packet)
        invalid.extend([{}, {'header':valid['header'], 'ciphertext':b64(b'x'*15)},
                        {'header':valid['header'], 'ciphertext':'not-base64'},
                        {**valid, 'unexpected':'value'},
                        seal(self.identities['bob'], self.public['alice'], {'synthetic':'swapped'})])
        for packet in invalid:
            response = {'id': token(), 'message_digest': digest('message'), 'packet': packet,
                        'release':'approved_and_released', 'historical_replay':False}
            with self.assertRaises(Rejected):
                self.owner.record_response(p['proposal_id'], operation_id=command['operation_id'],
                    command_digest=digest(command), response=response)
            self.assertEqual(self.proposal()['state'], 'unknown')

    def test_constructor_binding_failure_closes_local_connection(self):
        connection = sqlite3.connect(self.path)
        wrong_task = {**self.task, 'id': token()}
        with patch('facade_candidate.store.sqlite3.connect', return_value=connection):
            with self.assertRaises(Rejected):
                ProposalStore(self.path, actor='alice', task_value=wrong_task, public=self.public)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def test_bad_response_remains_unknown(self):
        p = self.proposal(); command = self.prepare(p)
        with self.assertRaises(Rejected):
            self.owner.record_response(p['proposal_id'], operation_id=command['operation_id'], command_digest=digest(command), response={})
        self.assertEqual(self.proposal()['state'], 'unknown')

    def test_snapshot_absence_cannot_clear_unknown_after_cancel(self):
        p = self.proposal(); self.prepare(p); snapshot = self.snapshot()
        snapshot['policy']['terminal'] = 'cancelled'
        self.assertEqual(self.owner.reconcile_snapshot(p['proposal_id'], snapshot)['state'], 'unknown')
        self.assertEqual(self.proposal()['state'], 'unknown')

    def test_snapshot_commit_not_release(self):
        p = self.proposal(); self.prepare(p); snapshot = self.snapshot()
        snapshot['outgoing'] = [self.item('Question?', kind='request')]
        out = self.owner.reconcile_snapshot(p['proposal_id'], snapshot)
        self.assertEqual(out['state'], 'committed_content_observed')
        self.assertIsNone(out['packet_digest'])
        self.assertIn('operation causation and release/delivery unknown', out['evidence_basis'])
        with self.assertRaises(Rejected): self.prepare(p)

    def test_snapshot_bound_identity_and_actor(self):
        for field in ('actor', 'identity'):
            snapshot = self.snapshot()
            if field == 'actor': snapshot[field] = 'bob'
            else: snapshot[field]['incarnation'] = token()
            with self.assertRaises(Rejected): self.publisher.publish(snapshot)

    def test_only_processed_projection_exposed(self):
        snapshot = self.snapshot(); snapshot['incoming'] = [{'payload':'SECRET RAW'}]
        self.assertEqual(self.api.processed_inbox({})['publication'], 0)
        self.publisher.publish(snapshot)
        view = self.api.processed_inbox({})
        self.assertEqual(view['publication'], 1); self.assertEqual(view['items'], [])
        snapshot['processed_projection'] = [self.item()]
        self.publisher.publish(snapshot)
        snapshot['processed_projection'][0]['payload'] = 'mutated'
        self.assertEqual(self.api.processed_inbox({})['items'][0]['payload'], 'Answer')
        self.assertIn('not fresh network truth', self.api.processed_inbox({})['knowledge'])

    def test_unprocessed_or_extra_fields_rejected(self):
        snapshot = self.snapshot(); item = self.item(); snapshot['processed_projection'] = [item]
        item['processed_evidence_present'] = False
        with self.assertRaises(Rejected): self.publisher.publish(snapshot)
        item['processed_evidence_present'] = True; item['raw'] = 'leak'
        with self.assertRaises(Rejected): self.publisher.publish(snapshot)

    def test_cancel_and_reopen_preserves_publication(self):
        snapshot = self.snapshot(); snapshot['processed_projection'] = [self.item()]
        self.publisher.publish(snapshot); snapshot['policy']['terminal'] = 'cancelled'
        self.publisher.publish(snapshot)
        self.store.close(); self.open()
        self.assertEqual(self.api.processed_inbox({})['publication'], 2)
        snapshot['processed_projection'] = []
        with self.assertRaises(Rejected): self.publisher.publish(snapshot)
        self.assertEqual(len(self.api.processed_inbox({})['items']), 1)

    def test_proposal_has_no_endpoint_or_callbacks(self):
        self.assertEqual(set(vars(self.api)), {'_store'})
        before = self.snapshot(); self.proposal()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(set(vars(self.store)), {'_binding', '_db'})


class SequentialDemoTests(unittest.TestCase):
    def test_normal_two_process_roundtrip(self):
        from facade_candidate.demo import run
        out = run()
        self.assertEqual(len(set(out['distinct_endpoint_pids'])), 2)
        self.assertEqual(out['request_status']['state'], 'released')
        self.assertEqual(out['result_status']['state'], 'released')
        self.assertEqual(out['alice_processed_inbox']['items'][0]['payload'], 'A moonberry (fictional).')
        self.assertEqual(out['bob_processed_inbox']['items'][0]['payload'], 'Name one imaginary blue fruit.')


if __name__ == '__main__': unittest.main()
