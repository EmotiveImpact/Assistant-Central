import copy
import json
import os
import sqlite3
import tempfile
import unittest

from independent_peer.endpoint import Endpoint
from independent_peer.fixture import Experiment, PeerProcess, UncertainOutcome
from independent_peer.protocol import CAPABILITY, Rejected, digest, scope, token


def body_of(peer, table, message_id):
    # Test-only public application-state oracle. No private keys are stored here.
    with sqlite3.connect(peer.database) as db:
        return json.loads(db.execute(f'SELECT body FROM {table} WHERE id=?', (message_id,)).fetchone()[0])


def setup_request(experiment, deliver=True, process=False):
    alice, bob = experiment.alice, experiment.bob
    incoming = alice.owner('allow_receive')['grant']
    outgoing = bob.owner('allow_receive')['grant']
    request = alice.owner('approve_send', payload='Fictional question.', grant=outgoing)
    receipt = bob.peer('deliver', request['packet']) if deliver else None
    proof = bob.owner('process', id=request['id']) if process else None
    return incoming, outgoing, request, receipt, proof


class IndependentProcessTests(unittest.TestCase):
    def setUp(self):
        self.ex = Experiment()
        self.addCleanup(self.ex.close)
        self.a, self.b = self.ex.alice, self.ex.bob

    def test_distinct_processes_stores_and_keys(self):
        a, b = self.a.owner('inspect'), self.b.owner('inspect')
        self.assertNotEqual(a['pid'], b['pid'])
        self.assertNotIn(os.getpid(), (a['pid'], b['pid']))
        self.assertNotEqual(self.a.database, self.b.database)
        self.assertNotEqual(a['identity']['signing'], b['identity']['signing'])
        self.assertNotEqual(a['identity']['encryption'], b['identity']['encryption'])
        for peer in (self.a, self.b):
            with sqlite3.connect(peer.database) as db:
                stored = dict(db.execute('SELECT * FROM meta'))
            self.assertEqual(set(stored), {'identity', 'peer', 'task'})
            self.assertEqual(json.loads(stored['identity'])['actor'], peer.actor)
            self.assertNotIn('private', json.dumps(stored))

    def test_receipt_is_not_processing_and_result_reorders_evidence(self):
        grant, _, request, received, _ = setup_request(self.ex)
        self.a.peer('evidence', {'status': 'received', 'evidence': received['received']})
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])
        state = self.b.owner('inspect')
        self.assertEqual(state['processed_projection'], [])
        self.assertIsNone(state['incoming'][0]['payload'])
        proof = self.b.owner('process', id=request['id'])
        result = self.b.owner('approve_send', payload='Fictional answer.', grant=grant)
        received_result = self.a.peer('deliver', result['packet'])
        self.assertTrue(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])
        self.assertFalse(self.a.owner('inspect')['incoming'][0]['processed_evidence_present'])
        self.b.peer('evidence', {'status': 'received', 'evidence': received_result['received']})
        result_proof = self.a.owner('process', id=result['id'])
        self.b.peer('evidence', {'status': 'processed', 'evidence': result_proof['processed']})
        self.a.peer('evidence', {'status': 'processed', 'evidence': proof['processed']})
        self.assertEqual(self.a.owner('inspect')['processed_projection'][0]['payload'], 'Fictional answer.')

    def test_bob_cannot_send_before_own_processed_request(self):
        grant, _, request, _, _ = setup_request(self.ex)
        with self.assertRaisesRegex(Rejected, 'not locally processed'):
            self.b.owner('approve_send', payload='Too early.', grant=grant)
        self.assertEqual(self.b.owner('inspect')['outgoing'], [])
        self.b.owner('process', id=request['id'])
        self.b.owner('approve_send', payload='Now approved.', grant=grant)

    def test_owner_controls_are_not_peer_routes(self):
        before = self.b.owner('inspect')
        for op in ('allow_receive', 'approve_send', 'configure', 'cancel', 'process', 'describe', 'sign', 'forge'):
            with self.subTest(op=op), self.assertRaises(Rejected):
                self.b.peer(op, {})
        for command in ({'op': 'deliver', 'value': {}, 'actor': 'alice'},
                        {'op': 'cancel', 'operation_id': token()},
                        {'op': 'evidence', 'value': {}, 'context': 'owner'}):
            with self.assertRaises(Rejected):
                self.b.call('peer', command)
        self.assertEqual(before, self.b.owner('inspect'))

    def test_revoke_queued_packet_and_regrant_old_epoch(self):
        _, _, request, _, _ = setup_request(self.ex, deliver=False)
        self.b.owner('revoke_receive')
        with self.assertRaisesRegex(Rejected, 'not current'):
            self.b.peer('deliver', request['packet'])
        self.b.owner('allow_receive')
        with self.assertRaisesRegex(Rejected, 'not current'):
            self.b.peer('deliver', request['packet'])
        self.assertEqual(self.b.owner('inspect')['incoming'], [])

    def test_revoke_after_receipt_blocks_process_and_result(self):
        grant, _, request, received, _ = setup_request(self.ex)
        self.b.owner('revoke_receive')
        with self.assertRaises(Rejected):
            self.b.owner('process', id=request['id'])
        self.assertEqual(self.b.owner('inspect')['processed_projection'], [])
        replay = self.b.peer('deliver', request['packet'])
        self.assertTrue(replay['historical_replay'])
        self.assertEqual(replay['received'], received['received'])
        self.assertIsNone(replay['processed'])
        self.b.owner('allow_receive')
        with self.assertRaises(Rejected):
            self.b.owner('process', id=request['id'])
        with self.assertRaises(Rejected):
            self.b.owner('approve_send', payload='No.', grant=grant)

    def test_revoke_processed_request_blocks_new_result_disclosure(self):
        grant, _, request, _, _ = setup_request(self.ex, process=True)
        self.b.owner('revoke_receive')
        with self.assertRaises(Rejected):
            self.b.owner('approve_send', payload='No new disclosure.', grant=grant)
        # The owner can still inspect historical committed processing.
        self.assertTrue(self.b.owner('inspect')['incoming'][0]['processed_evidence_present'])

    def test_cancel_before_late_result_and_evidence_remains_historical(self):
        grant, _, request, received, proof = setup_request(self.ex, process=True)
        result = self.b.owner('approve_send', payload='Delayed.', grant=grant)
        self.a.owner('cancel')
        with self.assertRaisesRegex(Rejected, 'terminal'):
            self.a.peer('deliver', result['packet'])
        self.a.peer('evidence', {'status': 'processed', 'evidence': proof['processed']})
        self.a.peer('evidence', {'status': 'received', 'evidence': received['received']})
        state = self.a.owner('inspect')
        self.assertEqual(state['policy']['terminal'], 'cancel')
        self.assertTrue(state['outgoing'][0]['processed_evidence_present'])
        self.assertEqual(state['incoming'], [])
        with self.assertRaises(Rejected):
            self.a.owner('packet', id=request['id'])

    def test_sender_cancel_cannot_recall_already_released_request(self):
        _, _, request, _, _ = setup_request(self.ex, deliver=False)
        self.a.owner('cancel')
        # The fixture already possesses these bytes. Bob cannot know Alice cancelled.
        received = self.b.peer('deliver', request['packet'])
        self.assertFalse(received['historical_replay'])
        self.assertTrue(self.b.owner('inspect')['incoming'][0]['received_evidence_present'])
        self.assertEqual(self.a.owner('inspect')['policy']['terminal'], 'cancel')

    def test_refusal_is_terminal_and_does_not_inform_remote_automatically(self):
        _, _, request, _, _ = setup_request(self.ex, deliver=False)
        self.b.owner('refuse')
        with self.assertRaises(Rejected):
            self.b.peer('deliver', request['packet'])
        with self.assertRaises(Rejected):
            self.b.owner('allow_receive')
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['received_evidence_present'])

    def test_exact_replay_and_historical_evidence_after_cancel(self):
        _, _, request, received, proof = setup_request(self.ex, process=True)
        self.b.owner('cancel')
        replay = self.b.peer('deliver', request['packet'])
        self.assertTrue(replay['historical_replay'])
        self.assertEqual(replay['received'], received['received'])
        self.assertEqual(replay['processed'], proof['processed'])
        self.assertEqual(len(self.b.owner('inspect')['incoming']), 1)

    def test_lost_receipt_then_lost_processed_reply_explicit_reconciliation(self):
        _, _, request, receipt, _ = setup_request(self.ex)
        # Supervisor drops receipt rather than delivering it to Alice.
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['received_evidence_present'])
        replay = self.b.peer('deliver', request['packet'])  # Explicit test retry; fixture never retries.
        self.a.peer('evidence', {'status': 'received', 'evidence': replay['received']})
        self.b.owner('process', id=request['id'])  # Supervisor drops processing proof too.
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])
        replay = self.b.peer('deliver', request['packet'])
        self.a.peer('evidence', {'status': 'processed', 'evidence': replay['processed']})
        self.assertTrue(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])

    def test_exact_owner_operation_replay_and_collision(self):
        grant = self.b.owner('allow_receive')['grant']
        operation = token()
        sent = self.a.owner('approve_send', operation_id=operation, payload='One.', grant=grant)
        again = self.a.owner('approve_send', operation_id=operation, payload='One.', grant=grant)
        self.assertFalse(sent['historical_replay'])
        self.assertTrue(again['historical_replay'])
        self.assertEqual(sent['packet'], again['packet'])
        self.assertEqual(sent['id'], again['id'])
        with self.assertRaisesRegex(Rejected, 'collision'):
            self.a.owner('approve_send', operation_id=operation, payload='Two.', grant=grant)
        self.assertEqual(len(self.a.owner('inspect')['outgoing']), 1)

    def test_domain_swap_wrong_signature_and_wrong_grant(self):
        _, _, request, received, proof = setup_request(self.ex, process=True)
        with self.assertRaises(Rejected):
            self.a.peer('evidence', {'status': 'processed', 'evidence': received['received']})
        with self.assertRaises(Rejected):
            self.a.peer('evidence', {'status': 'received', 'evidence': proof['processed']})
        forged = copy.deepcopy(proof['processed'])
        forged['body']['id'] = token()
        with self.assertRaises(Rejected):
            self.a.peer('evidence', {'status': 'processed', 'evidence': forged})
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])

    def test_result_receipt_without_process_cannot_mark_bob_processed(self):
        grant, _, _, _, _ = setup_request(self.ex, process=True)
        result = self.b.owner('approve_send', payload='Answer.', grant=grant)
        receipt = self.a.peer('deliver', result['packet'])
        self.b.peer('evidence', {'status': 'received', 'evidence': receipt['received']})
        self.assertFalse(self.b.owner('inspect')['outgoing'][0]['processed_evidence_present'])

    def test_restart_existing_store_fails_closed(self):
        setup_request(self.ex)
        path = self.a.database
        self.a.close()
        replacement = PeerProcess('alice', self.ex.temp.name)
        try:
            with self.assertRaises(UncertainOutcome):
                replacement.owner('describe')
            replacement.process.wait(timeout=3)
            self.assertNotEqual(replacement.process.returncode, 0)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
        finally:
            replacement.close()


class MaliciousSenderTests(unittest.TestCase):
    def setUp(self):
        self.ex = Experiment(bob_module='tests.malicious_worker')
        self.addCleanup(self.ex.close)
        self.a, self.b = self.ex.alice, self.ex.bob

    def forge(self, body):
        return self.b.call('owner', {'op': 'forge', 'body': body})

    def template(self, grant, request=None):
        return {'id': token(), 'scope': scope(self.ex.task, 'bob', 'alice', 'result'), 'grant': grant,
                'request': request, 'payload': 'Malicious but sender-signed fictional answer.'}

    def valid_result_body(self):
        grant, _, request, _, proof = setup_request(self.ex, process=True)
        body = self.template(grant, {'id': request['id'], 'digest': request['message_digest'], 'processed': proof['processed']})
        return body, request

    def test_valid_crypto_unsolicited_result_rejected_by_alice_itself(self):
        grant = self.a.owner('allow_receive')['grant']
        body = self.template(grant, {'id': token(), 'digest': '0' * 64, 'processed': {}})
        with self.assertRaisesRegex(Rejected, 'no locally authorized'):
            self.a.peer('deliver', self.forge(body))
        self.assertEqual(self.a.owner('inspect')['incoming'], [])

    def test_scope_linkage_and_payload_bounds_rejected_with_valid_sender_signature(self):
        base, _ = self.valid_result_body()
        mutations = [('task', token()), ('context', 'f' * 64), ('capability', 'fictional-answer/2'),
                     ('sender', 'alice'), ('recipient', 'bob'), ('kind', 'request')]
        for field, value in mutations:
            body = copy.deepcopy(base); body['scope'][field] = value
            with self.subTest(field=field), self.assertRaises(Rejected):
                self.a.peer('deliver', self.forge(body))
        for field, value in [('id', token()), ('digest', 'e' * 64), ('processed', {})]:
            body = copy.deepcopy(base); body['request'][field] = value
            with self.subTest(link=field), self.assertRaises(Rejected):
                self.a.peer('deliver', self.forge(body))
        for payload in ('', 'x' * 1025, '💙' * 257, ['not a string']):
            body = copy.deepcopy(base); body['payload'] = payload
            with self.subTest(payload=str(payload)[:10]), self.assertRaises(Rejected):
                self.a.peer('deliver', self.forge(body))
        self.assertEqual(self.a.owner('inspect')['incoming'], [])
        self.a.peer('deliver', self.forge(base))

    def test_positive_sender_versions_cannot_override_local_revocation(self):
        body, _ = self.valid_result_body()
        self.a.owner('revoke_receive')
        with self.assertRaisesRegex(Rejected, 'not current'):
            self.a.peer('deliver', self.forge(body))
        # Even an accurately signed old grant cannot survive recipient regrant.
        self.a.owner('allow_receive')
        with self.assertRaisesRegex(Rejected, 'not current'):
            self.a.peer('deliver', self.forge(body))
        fake_grant = copy.deepcopy(body)
        fake_grant['grant']['body']['epoch'] = 999
        with self.assertRaises(Rejected):
            self.a.peer('deliver', self.forge(fake_grant))

    def test_same_id_changed_body_and_reencrypted_packet_rejected(self):
        body, _ = self.valid_result_body()
        packet = self.forge(body)
        first = self.a.peer('deliver', packet)
        replay = self.a.peer('deliver', packet)
        self.assertEqual(first['received'], replay['received'])
        body['payload'] = 'Changed.'
        with self.assertRaisesRegex(Rejected, 'collision'):
            self.a.peer('deliver', self.forge(body))
        body['payload'] = 'Malicious but sender-signed fictional answer.'
        with self.assertRaisesRegex(Rejected, 'collision'):
            self.a.peer('deliver', self.forge(body))
        self.assertEqual(len(self.a.owner('inspect')['incoming']), 1)

    def test_peer_can_lie_about_own_processing_but_not_invent_alice_request(self):
        # Deliberate limitation: a key holder can attest a lie about its own state.
        grant, _, request, _, _ = setup_request(self.ex, process=False)
        request_body = body_of(self.a, 'outbox', request['id'])
        bob_public = self.b.owner('describe')['descriptor']
        claim = {'scope': request_body['scope'], 'id': request['id'], 'message_digest': digest(request_body),
                 'packet_digest': digest(request['packet']), 'grant_digest': digest(request_body['grant']),
                 'processor_binding': digest(bob_public), 'status': 'processed'}
        signed = self.b.call('owner', {'op': 'forge_evidence', 'domain': 'processed', 'body': claim})
        body = self.template(grant, {'id': request['id'], 'digest': digest(request_body), 'processed': signed})
        self.a.peer('deliver', self.forge(body))
        self.assertFalse(self.b.owner('inspect')['incoming'][0]['processed_evidence_present'])
        self.assertTrue(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])
        # It is an authenticated peer assertion, never proof of honest remote execution.

    def test_wrong_evidence_binding_validly_signed_by_peer_rejected(self):
        _, _, request, _, proof = setup_request(self.ex, process=True)
        for field, value in [('packet_digest', '0' * 64), ('message_digest', '1' * 64),
                             ('grant_digest', '2' * 64), ('processor_binding', '3' * 64), ('status', 'received')]:
            claim = copy.deepcopy(proof['processed']['body']); claim[field] = value
            signed = self.b.call('owner', {'op': 'forge_evidence', 'domain': 'processed', 'body': claim})
            with self.subTest(field=field), self.assertRaises(Rejected):
                self.a.peer('evidence', {'status': 'processed', 'evidence': signed})
        self.assertFalse(self.a.owner('inspect')['outgoing'][0]['processed_evidence_present'])


class TransactionTests(unittest.TestCase):
    def test_owner_rollback_has_no_partial_authority_or_idempotency_record(self):
        with tempfile.TemporaryDirectory() as directory:
            endpoint = Endpoint('alice', directory + '/alice.sqlite')
            bob = Endpoint('bob', directory + '/bob.sqlite')
            self.addCleanup(endpoint.close); self.addCleanup(bob.close)
            command = {'op': 'configure', 'operation_id': token(),
                       'task': {'id': token(), 'context': '0' * 64, 'capability': CAPABILITY},
                       'peer': bob.identity.descriptor}
            def fail():
                raise RuntimeError('injected before commit')
            endpoint.before_commit = fail
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                endpoint.handle_owner(command)
            self.assertIsNone(endpoint.task)
            self.assertEqual(endpoint.snapshot()['owner_operation_count'], 0)
            self.assertIsNone(endpoint.db.execute("SELECT value FROM meta WHERE key='task'").fetchone())
            endpoint.before_commit = lambda: None
            endpoint.handle_owner(command)
            allow = {'op': 'allow_receive', 'operation_id': token()}
            endpoint.before_commit = fail
            with self.assertRaises(RuntimeError):
                endpoint.handle_owner(allow)
            self.assertFalse(endpoint.snapshot()['policy']['active'])
            self.assertEqual(endpoint.snapshot()['policy']['epoch'], 0)
            self.assertEqual(endpoint.snapshot()['owner_operation_count'], 1)

    def test_send_and_processing_rollback_do_not_leave_partial_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            a = Endpoint('alice', directory + '/a.sqlite'); b = Endpoint('bob', directory + '/b.sqlite')
            try:
                context = {'id': token(), 'context': '0' * 64, 'capability': CAPABILITY}
                for own, other in [(a, b), (b, a)]:
                    own.handle_owner({'op': 'configure', 'operation_id': token(), 'task': context, 'peer': other.identity.descriptor})
                grant = b.handle_owner({'op': 'allow_receive', 'operation_id': token()})['grant']
                command = {'op': 'approve_send', 'operation_id': token(), 'grant': grant, 'payload': 'Fiction.'}
                def fail():
                    raise RuntimeError('before commit')
                a.before_commit = fail
                with self.assertRaises(RuntimeError):
                    a.handle_owner(command)
                self.assertEqual(a.snapshot()['outgoing'], [])
                self.assertEqual(a.snapshot()['owner_operation_count'], 1)
                a.before_commit = lambda: None
                sent = a.handle_owner(command)
                b.handle_peer({'op': 'deliver', 'value': sent['packet']})
                b.before_commit = fail
                with self.assertRaises(RuntimeError):
                    b.handle_owner({'op': 'process', 'operation_id': token(), 'id': sent['id']})
                self.assertEqual(b.snapshot()['processed_projection'], [])
                self.assertFalse(b.snapshot()['incoming'][0]['processed_evidence_present'])
            finally:
                a.close(); b.close()

    def test_peer_inbox_rollback_on_sql_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            a = Endpoint('alice', directory + '/a.sqlite'); b = Endpoint('bob', directory + '/b.sqlite')
            try:
                context = {'id': token(), 'context': '0' * 64, 'capability': CAPABILITY}
                for own, other in [(a, b), (b, a)]:
                    own.handle_owner({'op': 'configure', 'operation_id': token(), 'task': context, 'peer': other.identity.descriptor})
                grant = b.handle_owner({'op': 'allow_receive', 'operation_id': token()})['grant']
                request = a.handle_owner({'op': 'approve_send', 'operation_id': token(), 'grant': grant, 'payload': 'Fiction.'})
                b.db.execute("CREATE TRIGGER fault BEFORE INSERT ON inbox BEGIN SELECT RAISE(ABORT, 'injected'); END")
                with self.assertRaises(sqlite3.IntegrityError):
                    b.handle_peer({'op': 'deliver', 'value': request['packet']})
                self.assertEqual(b.snapshot()['incoming'], [])
                b.db.execute('DROP TRIGGER fault')
                b.handle_peer({'op': 'deliver', 'value': request['packet']})
                self.assertEqual(len(b.snapshot()['incoming']), 1)
            finally:
                a.close(); b.close()


if __name__ == '__main__':
    unittest.main()
