"""Independent adversarial checks of the pilot's actual public boundaries.

No host/provider call or real owner is involved. These tests do not substitute
for review of a deployed identity/transport system.
"""
from contextlib import contextmanager
import copy
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import TransportDenied, canonical, digest, fingerprint, open_packet, seal
from pilot.transport import PeerExchange
from pilot.runtime import PilotRuntime, RuntimeDenied
from pilot.server import PilotHTTPServer, MAX_QUARANTINE, PEER_HEADER, peer_endpoint, RequestDenied
from pilot.provider import ResponsesAdapter, ProviderDenied, ProviderOutcomeUnknown


PASSWORD_A = 'fictional-owner-alpha-password'
PASSWORD_B = 'fictional-owner-beta-password'


class IndependentBoundaryReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pilot-independent-review-')
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.a_path = Path(self.temp.name) / 'a'
        self.b_path = Path(self.temp.name) / 'b'
        self.a = LocalOwnerAuth(self.a_path, clock=lambda: self.now)
        self.b = LocalOwnerAuth(self.b_path, clock=lambda: self.now)
        self.addCleanup(lambda: self.a.close())
        self.addCleanup(lambda: self.b.close())
        self.a.bootstrap('owner-a', 'assistant-a', PASSWORD_A)
        self.b.bootstrap('owner-b', 'assistant-b', PASSWORD_B)
        self.at = self.a.login(PASSWORD_A)
        self.bt = self.b.login(PASSWORD_B)
        self.adb = sqlite3.connect(Path(self.temp.name) / 'outbox.sqlite', isolation_level=None)
        self.bdb = sqlite3.connect(Path(self.temp.name) / 'inbox.sqlite', isolation_level=None)
        self.addCleanup(self.adb.close)
        self.addCleanup(self.bdb.close)
        self.ax = PeerExchange(self.adb, self.a.public_identity(), clock=lambda: self.now)
        self.bx = PeerExchange(self.bdb, self.b.public_identity(), clock=lambda: self.now)
        self.ax.enroll_peer(self.b.public_identity(), fingerprint(self.b.public_identity()))
        self.bx.enroll_peer(self.a.public_identity(), fingerprint(self.a.public_identity()))

    def packet(self, **changes):
        values = dict(message_id='original-message', context='context-a', artifact_id='artifact-a',
                      proposal_id='proposal-a', kind='proposal',
                      payload={'text': 'SYNTHETIC REVIEW TEXT'}, expires=1100, now=self.now)
        values.update(changes)
        return seal(self.a, self.at, self.b.public_identity(), **values)

    def test_session_from_another_owner_cannot_unlock_or_sign(self):
        for target, token in ((self.a, self.bt), (self.b, self.at)):
            with self.assertRaises(AuthError): target.authenticate(token)
            with self.assertRaises(AuthError): target.sign(token, b'exact fake release')
        self.assertNotEqual(fingerprint(self.a.public_identity()), fingerprint(self.b.public_identity()))

    def test_restart_locks_identity_and_invalidates_old_session_without_changing_keys(self):
        public = self.a.public_identity()
        self.a.close()
        self.a = LocalOwnerAuth(self.a_path, clock=lambda: self.now)
        self.assertEqual(self.a.public_identity(), public)
        self.assertFalse(self.a.status()['unlocked'])
        with self.assertRaises(AuthError): self.a.sign(self.at, b'after restart')
        self.at = self.a.login(PASSWORD_A)
        self.assertEqual(self.a.authenticate(self.at)['owner_id'], 'owner-a')
        with self.assertRaises(AuthError): self.a.bootstrap('other-owner', 'other-agent', PASSWORD_B)

    def test_password_and_raw_bearer_are_not_retained_in_database(self):
        encoded = (self.a_path / 'auth.sqlite').read_bytes()
        self.assertNotIn(PASSWORD_A.encode(), encoded)
        self.assertNotIn(self.at.encode(), encoded)
        self.assertEqual(os.stat(self.a_path).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.a_path / 'auth.sqlite').st_mode & 0o777, 0o600)

    def test_public_identity_pin_cannot_be_replaced_or_revived(self):
        replacement = self.b.public_identity()
        replacement['signing_key'] = self.a.public_identity()['signing_key']
        with self.assertRaises(TransportDenied):
            self.ax.enroll_peer(replacement, fingerprint(replacement))
        original = fingerprint(self.b.public_identity())
        self.ax.revoke_peer(original)
        with self.assertRaises(TransportDenied):
            self.ax.enroll_peer(self.b.public_identity(), original)

    def test_signature_binds_every_header_selector_and_ciphertext(self):
        packet = self.packet()
        for key, changed in (('context', 'context-b'), ('artifact_id', 'artifact-b'),
                             ('proposal_id', 'proposal-b'), ('message_id', 'message-b'),
                             ('kind', 'cancel'), ('expires', 1099), ('created', 999)):
            altered = copy.deepcopy(packet); altered['header'][key] = changed
            with self.subTest(field=key), self.assertRaises(TransportDenied):
                open_packet(self.b, self.bt, self.a.public_identity(), altered, now=self.now)
        altered = copy.deepcopy(packet)
        altered['ciphertext'] = ('A' if altered['ciphertext'][0] != 'A' else 'B') + altered['ciphertext'][1:]
        with self.assertRaises(TransportDenied):
            open_packet(self.b, self.bt, self.a.public_identity(), altered, now=self.now)

    def test_reflected_direction_cannot_be_decrypted_as_incoming(self):
        packet = self.packet()
        with self.assertRaises(TransportDenied):
            open_packet(self.a, self.at, self.b.public_identity(), packet, now=self.now)

    def test_unenrolled_sender_has_no_implicit_trust_from_owner_labels(self):
        adb = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(adb.close)
        unpaired = PeerExchange(adb, self.b.public_identity(), clock=lambda: self.now)
        with self.assertRaises(TransportDenied): unpaired.receive(self.packet(), self.b, self.bt)

    def test_same_message_id_cannot_replace_packet_even_with_valid_signature(self):
        original = self.packet()
        self.bx.receive(original, self.b, self.bt)
        changed = self.packet(payload={'text': 'DIFFERENT SYNTHETIC TEXT'})
        with self.assertRaises(TransportDenied): self.bx.receive(changed, self.b, self.bt)
        self.assertEqual(self.bdb.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 1)

    def test_queue_and_retry_preserve_exact_ciphertext_and_uncertainty(self):
        original = self.packet()
        self.ax.queue(original)
        first = self.ax.prepare_attempt('original-message')
        reopened = PeerExchange(self.adb, self.a.public_identity(), clock=lambda: self.now)
        second = reopened.prepare_attempt('original-message')
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(reopened.outbox_status('original-message')['state'], 'uncertain')
        self.assertNotIn('SYNTHETIC REVIEW TEXT', json.dumps(reopened.outbox_status('original-message')))

    def test_duplicate_receipt_has_no_payload_and_is_not_owner_acceptance(self):
        packet = self.packet()
        self.ax.queue(packet)
        self.ax.prepare_attempt('original-message')
        original = self.bx.receive(packet, self.b, self.bt)
        duplicate = self.bx.receive(packet, self.b, self.bt)
        self.assertFalse(original['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        self.assertIsNone(duplicate['envelope'])
        receipt = self.bx.receipt_for(self.b, self.bt, 'original-message')
        self.ax.receive(receipt, self.a, self.at)
        status = self.ax.outbox_status('original-message')
        self.assertEqual(status['state'], 'received')
        self.assertEqual(status['owner_acceptance'], 'not_established')
        self.assertEqual(status['work_execution'], 'not_established')

    def test_receipt_for_another_context_cannot_confirm_outbox(self):
        packet = self.packet()
        self.ax.queue(packet)
        self.bx.receive(packet, self.b, self.bt)
        forged = seal(self.b, self.bt, self.a.public_identity(), message_id='crossed-receipt',
                      context='different-context', artifact_id='artifact-a', proposal_id='proposal-a',
                      kind='receipt', expires=1100, now=self.now,
                      payload={'message_id': 'original-message', 'packet_digest': digest(packet),
                               'effect': 'durably_received_only'})
        with self.assertRaises(TransportDenied): self.ax.receive(forged, self.a, self.at)
        self.assertEqual(self.ax.outbox_status('original-message')['state'], 'queued')

    def test_cancel_then_late_receipt_preserves_cancellation_and_exposure(self):
        packet = self.packet()
        self.ax.queue(packet)
        self.ax.prepare_attempt('original-message')
        self.ax.cancel('original-message')
        self.bx.receive(packet, self.b, self.bt)
        self.ax.receive(self.bx.receipt_for(self.b, self.bt, 'original-message'), self.a, self.at)
        state = self.ax.outbox_status('original-message')
        self.assertEqual(state['state'], 'cancelled')
        self.assertIsNotNone(state['receipt_id'])
        with self.assertRaises(TransportDenied): self.ax.prepare_attempt('original-message')

    def test_expired_new_packet_cannot_be_admitted_after_restart(self):
        packet = self.packet()
        self.now = 1100
        reopened = PeerExchange(self.bdb, self.b.public_identity(), clock=lambda: self.now)
        with self.assertRaises(TransportDenied): reopened.receive(packet, self.b, self.bt)
        self.assertEqual(self.bdb.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)

    def test_outer_transaction_rollback_leaves_no_delivery_receipt(self):
        packet = self.packet()
        self.bdb.execute('BEGIN IMMEDIATE')
        self.bx.receive(packet, self.b, self.bt)
        self.bdb.execute('ROLLBACK')
        self.assertEqual(self.bdb.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)
        with self.assertRaises(TransportDenied): self.bx.receipt_for(self.b, self.bt, 'original-message')


class IndependentRuntimeReview(unittest.TestCase):
    def setUp(self):
        IndependentBoundaryReview.setUp(self)
        self.ar = PilotRuntime(self.a_path, self.a, clock=lambda: self.now)
        self.br = PilotRuntime(self.b_path, self.b, clock=lambda: self.now)
        self.addCleanup(self.ar.close)
        self.addCleanup(self.br.close)
        self.ar.enrol_peer(self.at, self.b.public_identity(), self.br.fingerprint)
        self.br.enrol_peer(self.bt, self.a.public_identity(), self.ar.fingerprint)

    def sent(self, task='one-task'):
        item = self.ar.propose(self.at, self.br.fingerprint, 'task', 'Synthetic review task',
                               'SYNTHETIC REVIEW INPUT', 'a' * 64, task, 1100)
        self.ar.release(self.at, item['id'], self.ar.review(self.at, item['id'])['review_digest'])
        packet = self.ar.prepare_delivery(self.at, 'proposal-' + item['id'])
        return item['id'], packet

    def rewrap(self, original, **changes):
        body = self.ar._row(original)[1]
        body.update(changes)
        return seal(self.a, self.at, self.b.public_identity(), message_id='alias-' + digest(body),
                    context=body['context'], artifact_id=body['artifact_digest'], proposal_id=digest(body),
                    kind='proposal', payload=body, expires=body['expires'], now=self.now)

    def test_untrusted_sender_cannot_rewrap_rejected_or_cancelled_logical_task(self):
        for action in ('reject', 'cancel'):
            item, packet = self.sent('task-' + action)
            self.br.receive(self.bt, packet)
            review = self.br.review(self.bt, item)['review_digest']
            if action == 'reject': self.br.decide(self.bt, item, review, 'reject')
            else: self.br.cancel(self.bt, item, review)
            alias = self.rewrap(item, created_at=1001, expires=1101)
            before = len(self.br.state(self.bt)['items'])
            with self.subTest(action=action), self.assertRaises(RuntimeDenied): self.br.receive(self.bt, alias)
            self.assertEqual(len(self.br.state(self.bt)['items']), before)

    def test_forged_upstream_permission_labels_are_rejected_even_when_signed(self):
        item, _ = self.sent()
        body = self.ar._row(item)[1]
        for change in ({'owner_fingerprint': 'f' * 64}, {'upstream': ['unverified-third-owner']},
                       {'return_policy': 'any-recipient'}):
            rights = dict(body['source_permissions']); rights.update(change)
            forged = self.rewrap(item, source_permissions=rights)
            with self.subTest(change=change), self.assertRaises(RuntimeDenied): self.br.receive(self.bt, forged)
        self.assertEqual(self.br.state(self.bt)['items'], [])
        self.assertEqual(self.br.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)

    def test_source_cancel_before_proposal_blocks_later_acceptance(self):
        item, original_packet = self.sent()
        self.ar.cancel(self.at, item, self.ar.review(self.at, item)['review_digest'])
        row = self.ar.db.execute('SELECT cancel_message_id FROM runtime_items WHERE id=?', (item,)).fetchone()
        cancelled = self.ar.prepare_delivery(self.at, row[0])
        self.br.receive(self.bt, cancelled)
        self.br.receive(self.bt, original_packet)
        self.assertEqual(self.br.status(self.bt, item)['state'], 'cancelled')
        with self.assertRaises(RuntimeDenied):
            self.br.decide(self.bt, item, self.br.review(self.bt, item)['review_digest'], 'accept')

    def test_late_cancel_preserves_historical_acceptance(self):
        item, packet = self.sent()
        self.br.receive(self.bt, packet)
        self.br.decide(self.bt, item, self.br.review(self.bt, item)['review_digest'], 'accept')
        self.ar.cancel(self.at, item, self.ar.review(self.at, item)['review_digest'])
        cancel_id = self.ar.db.execute('SELECT cancel_message_id FROM runtime_items WHERE id=?', (item,)).fetchone()[0]
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, cancel_id))
        status = self.br.status(self.bt, item)
        self.assertEqual(status['state'], 'cancelled')
        self.assertEqual(status['historical_state'], 'accepted')
        self.assertTrue(status['peer_cancellation_observed'])

    def test_enrolled_third_peer_cannot_forge_original_recipient_decision(self):
        item, _ = self.sent()
        c = LocalOwnerAuth(Path(self.temp.name) / 'third', clock=lambda: self.now)
        self.addCleanup(c.close)
        c.bootstrap('third-owner', 'third-assistant', 'fictional-third-password')
        ct = c.login('fictional-third-password')
        self.ar.enrol_peer(self.at, c.public_identity(), fingerprint(c.public_identity()))
        body = self.ar._row(item)[1]
        payload = {'domain': 'assistant-central-pilot-runtime/1/decision', 'item_id': item,
                   'review_digest': '0' * 64, 'decision': 'accept', 'recipient': self.br.fingerprint}
        forged = seal(c, ct, self.a.public_identity(), message_id='fake-third-decision',
                      context=body['context'], artifact_id=body['artifact_digest'], proposal_id=item,
                      kind='decision', payload=payload, expires=1100, now=self.now)
        with self.assertRaises(RuntimeDenied): self.ar.receive(self.at, forged)
        self.assertEqual(self.ar.status(self.at, item)['state'], 'released')

    def test_accepted_task_without_signed_provider_grant_cannot_be_used_for_model(self):
        item, packet = self.sent()
        self.br.receive(self.bt, packet)
        self.br.decide(self.bt, item, self.br.review(self.bt, item)['review_digest'], 'accept')
        binding = {'item_id': item, 'context': 'a' * 64,
                   'payload_digest': self.br.status(self.bt, item)['artifact_digest'],
                   'provider': 'openai', 'model': 'synthetic-model', 'max_output_tokens': 64}
        self.br.db.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(RuntimeDenied): self.br.authorise_provider(self.bt, binding)
        finally:
            self.br.db.execute('ROLLBACK')


class IndependentHTTPReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pilot-http-review-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owner'
        auth = LocalOwnerAuth(self.path)
        try: auth.bootstrap('http-owner', 'http-assistant', PASSWORD_A)
        finally: auth.close()
        self.server = PilotHTTPServer(self.path, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def request(self, method, path, value=None, *, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            body = raw if raw is not None else (json.dumps(value).encode() if value is not None else None)
            fields = {'Content-Type': 'application/json'} if body is not None else {}
            fields.update(headers or {})
            connection.request(method, path, body=body, headers=fields)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally: connection.close()

    def login(self):
        status, _, body = self.request('POST', '/api/session', {'password': PASSWORD_A})
        self.assertEqual(status, 200)
        return json.loads(body)['token']

    def test_wrong_host_and_cross_origin_cannot_log_in(self):
        for headers in ({'Host': 'attacker.invalid'}, {'Origin': 'https://attacker.invalid'},
                        {'Origin': 'null'}, {'Host': 'localhost:' + str(self.server.server_port)}):
            with self.subTest(headers=headers):
                status, _, body = self.request('POST', '/api/session', {'password': PASSWORD_A}, headers=headers)
                self.assertEqual(status, 400)
                self.assertNotIn(PASSWORD_A.encode(), body)
        self.login()

    def test_duplicate_json_and_non_json_writes_do_not_create_owner_sessions(self):
        raw = ('{"password":"' + PASSWORD_A + '","password":"' + PASSWORD_A + '"}').encode()
        self.assertEqual(self.request('POST', '/api/session', raw=raw)[0], 400)
        self.assertEqual(self.request('POST', '/api/session', {'password': PASSWORD_A},
                                      headers={'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('POST', '/api/session', {'password': PASSWORD_A, 'owner': 'another'})[0], 400)

    def test_bearer_is_required_and_cannot_be_supplied_in_url(self):
        token = self.login()
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.assertEqual(self.request('GET', '/api/state?token=' + token)[0], 400)
        self.assertEqual(self.request('GET', '/api/state', headers={'Authorization': 'Bearer ' + 'x' * 43})[0], 401)
        status, _, body = self.request('GET', '/api/state', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200)
        self.assertNotIn(token.encode(), body)
        self.assertNotIn(PASSWORD_A.encode(), body)

    def test_logout_revokes_token_at_http_boundary(self):
        token = self.login()
        headers = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.request('DELETE', '/api/session', {}, headers=headers)[0], 200)
        self.assertEqual(self.request('GET', '/api/state', headers=headers)[0], 401)

    def test_peer_mailbox_storage_is_not_authenticated_owner_acceptance(self):
        status, _, body = self.request('POST', '/peer/inbox', {'packet': {'not': 'an authenticated packet'}},
                                       headers={'X-Assistant-Central-Peer': PEER_HEADER})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)['authenticated_receipt'])
        self.assertEqual(self.request('POST', '/api/exchange', {})[0], 401)
        token = self.login()
        status, _, body = self.request('POST', '/api/exchange', {}, headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['rejected_packets'], 1)
        status, _, body = self.request('GET', '/api/state', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['items'], [])

    def test_mailbox_quota_preserves_existing_packets_and_deduplicates(self):
        headers = {'X-Assistant-Central-Peer': PEER_HEADER}
        for index in range(MAX_QUARANTINE):
            self.assertEqual(self.request('POST', '/peer/inbox', {'packet': {'synthetic': index}}, headers=headers)[0], 200)
        self.assertEqual(self.request('POST', '/peer/inbox', {'packet': {'synthetic': MAX_QUARANTINE}}, headers=headers)[0], 400)
        status, _, body = self.request('POST', '/peer/inbox', {'packet': {'synthetic': 0}}, headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['duplicate'])
        self.assertEqual(len(self.server.owner.mailbox.pending()), MAX_QUARANTINE)

    def test_static_ui_has_no_inline_execution_or_cross_origin_permission(self):
        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        policy = headers['Content-Security-Policy']
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.request('GET', '/app.mjs')[0], 200)
        self.assertEqual(self.request('GET', '/../../auth.sqlite')[0], 400)

    def test_peer_endpoint_cannot_target_remote_hosts_or_other_paths(self):
        for endpoint in ('https://example.com', 'http://localhost:8765', 'http://127.0.0.1:80',
                         'http://127.0.0.1:8765/api/session', 'http://127.0.0.1:8765?token=x',
                         'http://user:pass@127.0.0.1:8765', 'http://127.0.0.1:8765#x'):
            with self.subTest(endpoint=endpoint), self.assertRaises(RequestDenied): peer_endpoint(endpoint)


class IndependentProviderReview(unittest.TestCase):
    def setUp(self):
        IndependentRuntimeReview.setUp(self)
        grant = {'provider': 'openai', 'model': 'synthetic-model', 'max_output_tokens': 64}
        item = self.ar.propose(self.at, self.br.fingerprint, 'task', 'Synthetic model task',
                               'SYNTHETIC ONLY: Describe one fictional garden.', 'b' * 64, 'model-task', 1100,
                               provider_disclosure=grant)
        self.item = item['id']
        self.ar.release(self.at, self.item, self.ar.review(self.at, self.item)['review_digest'])
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, 'proposal-' + self.item))
        self.br.decide(self.bt, self.item, self.br.review(self.bt, self.item)['review_digest'], 'accept')
        self.binding = {'item_id': self.item, 'context': 'b' * 64,
                        'payload_digest': self.br.status(self.bt, self.item)['artifact_digest'], **grant}
        self.calls = []
        test = self
        class Fixture:
            synthetic_only = True
            def send(self, raw):
                test.calls.append(json.loads(raw))
                return 200, json.dumps({'object': 'response', 'id': 'fixture_response', 'status': 'completed',
                    'error': None, 'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'SYNTHETIC MODEL RESULT'}]}],
                    'usage': {'output_tokens': 5}}).encode()
        self.fixture = Fixture()
        self.adapter = ResponsesAdapter(self.br.db, self.br.authorise_provider, self.b.authenticate,
                                         transport=self.fixture, clock=lambda: self.now)
        review = self.adapter.prepare(self.bt, 'original-model-run', self.binding)
        self.adapter.approve(self.bt, 'original-model-run', review['review_digest'], expires=1090)

    def test_logout_before_claim_prevents_provider_dispatch(self):
        self.b.logout(self.bt)
        with self.assertRaises(ProviderDenied): self.adapter.dispatch(self.bt, 'original-model-run')
        self.assertEqual(self.calls, [])
        self.bt = self.b.login(PASSWORD_B)
        self.assertEqual(self.adapter.status(self.bt, 'original-model-run')['state'], 'approved')

    def test_session_revocation_cannot_interleave_before_claim_commit(self):
        begin, finished = threading.Event(), threading.Event()
        errors = []
        def revoke():
            begin.wait(5)
            try: self.b.logout(self.bt)
            except BaseException as exc: errors.append(exc)
            finally: finished.set()
        worker = threading.Thread(target=revoke)
        worker.start()
        request = self.adapter._request
        def pause_before_claim(*args):
            result = request(*args)
            begin.set()
            self.assertFalse(finished.wait(0.05), 'Logout passed while provider claim still held owner authority')
            return result
        original_send = self.fixture.send
        def after_commit(raw):
            self.assertTrue(finished.wait(5), 'Owner lock incorrectly held during external provider call')
            self.assertEqual(self.br.db.execute("SELECT state FROM pilot_provider_runs").fetchone()[0], 'uncertain')
            return original_send(raw)
        with patch.object(self.adapter, '_request', pause_before_claim), patch.object(self.fixture, 'send', after_commit):
            outcome = self.adapter.dispatch(self.bt, 'original-model-run')
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcome['state'], 'completed')
        self.assertEqual(len(self.calls), 1)

    def test_permission_expiring_during_request_construction_cannot_be_claimed(self):
        request = self.adapter._request
        def expired(*args):
            value = request(*args)
            self.now = 1100  # both approved provider request and signed source task are expired
            return value
        with patch.object(self.adapter, '_request', expired):
            with self.assertRaises(ProviderDenied): self.adapter.dispatch(self.bt, 'original-model-run')
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.br.db.execute('SELECT claimed_at FROM pilot_provider_runs').fetchone()[0])

    def test_source_deadline_is_rechecked_even_when_local_provider_approval_lasts_longer(self):
        grant = {'provider': 'openai', 'model': 'synthetic-model', 'max_output_tokens': 64}
        item = self.ar.propose(self.at, self.br.fingerprint, 'task', 'Short source permission',
                               'SYNTHETIC ONLY: Short-lived task.', 'c' * 64, 'short-source', 1010,
                               provider_disclosure=grant)
        self.ar.release(self.at, item['id'], self.ar.review(self.at, item['id'])['review_digest'])
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, 'proposal-' + item['id']))
        self.br.decide(self.bt, item['id'], self.br.review(self.bt, item['id'])['review_digest'], 'accept')
        binding = {'item_id': item['id'], 'context': 'c' * 64, 'payload_digest': item['artifact_digest'], **grant}
        review = self.adapter.prepare(self.bt, 'short-source-run', binding)
        self.adapter.approve(self.bt, 'short-source-run', review['review_digest'], expires=1090)
        request = self.adapter._request
        def expired(*args):
            value = request(*args)
            self.now = 1010
            return value
        with patch.object(self.adapter, '_request', expired):
            with self.assertRaises(ProviderDenied): self.adapter.dispatch(self.bt, 'short-source-run')
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.br.db.execute("SELECT claimed_at FROM pilot_provider_runs WHERE id='short-source-run'").fetchone()[0])

    def test_uncertain_provider_outcome_never_reissues_after_new_adapter(self):
        with patch.object(self.fixture, 'send', side_effect=TimeoutError('SECRET transport detail')):
            with self.assertRaises(ProviderOutcomeUnknown) as failure:
                self.adapter.dispatch(self.bt, 'original-model-run')
        self.assertNotIn('SECRET', str(failure.exception))
        reopened = ResponsesAdapter(self.br.db, self.br.authorise_provider, self.b.authenticate,
                                     transport=self.fixture, clock=lambda: self.now)
        with self.assertRaises(ProviderDenied): reopened.dispatch(self.bt, 'original-model-run')
        self.assertEqual(self.calls, [])
        self.assertEqual(reopened.status(self.bt, 'original-model-run')['state'], 'uncertain')

    def test_source_cancellation_blocks_new_provider_claim(self):
        self.ar.cancel(self.at, self.item, self.ar.review(self.at, self.item)['review_digest'])
        cancel_id = self.ar.db.execute('SELECT cancel_message_id FROM runtime_items WHERE id=?', (self.item,)).fetchone()[0]
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, cancel_id))
        with self.assertRaises(ProviderDenied): self.adapter.dispatch(self.bt, 'original-model-run')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
