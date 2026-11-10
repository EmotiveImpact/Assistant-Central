"""Offline Responses wire/authority tests. The transport fixtures call no API."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.provider import (ResponsesAdapter, ProviderBudget, OpenAIResponsesHTTP,
                            ProviderDenied, ProviderOutcomeUnknown, ENDPOINT, MAX_RESPONSE_BYTES)


def response(text="SYNTHETIC ONLY: Three paper moons."):
    return {"object": "response", "id": "resp_fixture", "status": "completed", "error": None,
            "output": [{"type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "usage": {"input_tokens": 16, "output_tokens": 12, "total_tokens": 28}}


class FixtureTransport:
    synthetic_only = True

    def __init__(self, callback=None):
        self.calls, self.callback = [], callback

    def send(self, encoded):
        self.calls.append(encoded)
        if self.callback:
            return self.callback(encoded)
        return 200, json.dumps(response()).encode()


class FixtureAuth:
    def __init__(self):
        self.lock, self.active = threading.RLock(), True

    def authenticate(self, token):
        with self.lock:
            if not self.active or token != 'owner-session':
                raise PermissionError('SECRET must not escape')
            return {"owner_id": "owner", "agent_id": "assistant", "identity_fingerprint": "f" * 64}

    @contextmanager
    def authorised(self, token):
        with self.lock:
            yield self.authenticate(token)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'runtime.sqlite'
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(lambda: self.db.close())
        self.auth, self.transport = FixtureAuth(), FixtureTransport()
        self.now, self.source_allowed = 1000, True
        self.text = 'SYNTHETIC ONLY: Count three paper moons in a fictional garden.'
        self.binding = {"item_id": "message-one", "context": "a" * 64, "payload_digest": "b" * 64,
                        "provider": "openai", "model": "fixture-model", "max_output_tokens": 128}
        self.adapter = self.make_adapter()

    def authorise(self, token, binding):
        self.auth.authenticate(token)
        if not self.db.in_transaction or not self.source_allowed or binding != self.binding:
            raise PermissionError('SECRET source approval unavailable')
        return {"task_text": self.text, "context": binding['context'], "recipient": "assistant", "synthetic_only": True}

    def make_adapter(self, **kwargs):
        return ResponsesAdapter(self.db, self.authorise, self.auth.authenticate,
                                transport=self.transport, clock=lambda: self.now, **kwargs)

    def prepare(self):
        return self.adapter.prepare('owner-session', 'run-one', self.binding)

    def approved(self):
        result = self.prepare()
        return self.adapter.approve('owner-session', 'run-one', result['review_digest'], expires=1100)

    def test_defaults_never_contact_a_provider(self):
        self.adapter = ResponsesAdapter(self.db, self.authorise, self.auth.authenticate, clock=lambda: self.now)
        self.approved()
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'approved')
        self.assertEqual(self.transport.calls, [])

    def test_exact_review_and_single_fixture_dispatch(self):
        prepared = self.approved()
        review = self.adapter.review('owner-session', 'run-one')
        self.assertEqual(prepared['review_digest'], review['review_digest'])
        self.assertEqual(review['review']['binding'], self.binding)
        result = self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(result['state'], 'completed')
        self.assertFalse(result['live_provider_verified'])
        self.assertFalse(result['authorises_publication'])
        self.assertEqual(len(self.transport.calls), 1)
        request = json.loads(self.transport.calls[0])
        self.assertEqual(request['input'], self.text)
        self.assertEqual(request['tools'], [])
        self.assertEqual(request['tool_choice'], 'none')
        self.assertEqual(request['max_output_tokens'], 128)
        for field in ('store', 'stream', 'background'): self.assertIs(request[field], False)
        for field in ('owner', 'agent', 'context', 'payload_digest', 'item_id', 'api_key'):
            self.assertNotIn(field, request)
        self.assertIn('Three paper moons', self.adapter.result('owner-session', 'run-one')['text'])
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')

    def test_accepted_peer_input_does_not_substitute_for_provider_grant(self):
        self.source_allowed = False
        with self.assertRaises(ProviderDenied) as error: self.prepare()
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(self.db.execute('SELECT count(*) FROM pilot_provider_runs').fetchone()[0], 0)

    def test_source_revocation_after_approval_blocks_dispatch(self):
        self.approved(); self.source_allowed = False
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'approved')
        self.adapter.cancel('owner-session', 'run-one')

    def test_changed_task_text_cannot_reuse_review(self):
        prepared = self.prepare(); self.text += ' changed'
        with self.assertRaises(ProviderDenied): self.adapter.approve('owner-session', 'run-one', prepared['review_digest'], expires=1100)

    def test_wrong_context_model_digest_or_extra_scope_is_refused(self):
        for name, value in (('context', 'c' * 64), ('payload_digest', 'c' * 64), ('model', 'another-model'),
                            ('provider', 'elsewhere'), ('max_output_tokens', 4096), ('tools', ['shell'])):
            changed = deepcopy(self.binding); changed[name] = value
            with self.subTest(name=name), self.assertRaises(ProviderDenied): self.adapter.prepare('owner-session', 'run-one', changed)

    def test_no_run_alias_or_retargeting(self):
        self.prepare()
        with self.assertRaises(ProviderDenied): self.adapter.prepare('owner-session', 'run-alias', self.binding)
        changed = {**self.binding, 'model': 'other'}
        with self.assertRaises(ProviderDenied): self.adapter.prepare('owner-session', 'run-one', changed)

    def test_approval_expires_and_cannot_renew(self):
        prepared = self.prepare()
        for expires in (None, True, 1000, 4601, float('nan'), float('inf')):
            with self.subTest(expires=expires), self.assertRaises(ProviderDenied):
                self.adapter.approve('owner-session', 'run-one', prepared['review_digest'], expires=expires)
        self.adapter.approve('owner-session', 'run-one', prepared['review_digest'], expires=1100)
        self.now = 1100
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'expired')
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        with self.assertRaises(ProviderDenied): self.adapter.approve('owner-session', 'run-one', prepared['review_digest'], expires=1200)

    def test_wrong_owner_session_and_review_cannot_approve(self):
        self.prepare()
        with self.assertRaises(ProviderDenied): self.adapter.approve('owner-session', 'run-one', '0' * 64, expires=1100)
        with self.assertRaises(ProviderDenied): self.adapter.approve('another-session', 'run-one', '0' * 64, expires=1100)
        with self.assertRaises(ProviderDenied): self.adapter.status('another-session', 'run-one')

    def test_missing_revocation_guard_is_refused(self):
        with self.assertRaises(ProviderDenied): ResponsesAdapter(self.db, self.authorise, lambda token: self.auth.authenticate(token))

    def test_expired_session_before_commit_rolls_back_dispatch(self):
        self.approved()
        authorise = self.adapter._authorise
        def expire(token, binding):
            result = authorise(token, binding)
            self.auth.active = False
            return result
        self.adapter._authorise = expire
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.auth.active = True
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'approved')
        self.assertEqual(self.transport.calls, [])

    def test_request_budget_survives_restart_and_failed_transport(self):
        self.approved()
        def lost(encoded): raise TimeoutError('SECRET timeout')
        self.transport.callback = lost
        with self.assertRaises(ProviderOutcomeUnknown): self.adapter.dispatch('owner-session', 'run-one')
        self.db.close(); self.db = sqlite3.connect(self.path, isolation_level=None)
        self.adapter = self.make_adapter()
        self.binding = {**self.binding, 'item_id': 'message-two'}
        second = self.adapter.prepare('owner-session', 'run-two', self.binding)
        self.adapter.approve('owner-session', 'run-two', second['review_digest'], expires=1100)
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-two')
        self.assertEqual(len(self.transport.calls), 1)

    def test_budget_cannot_be_increased_on_reopen(self):
        for budget in (ProviderBudget(max_requests=2), ProviderBudget(max_output_tokens=512), ProviderBudget(max_input_bytes=16384)):
            with self.assertRaises(ProviderDenied): self.make_adapter(budget=budget)
        for kwargs in ({'max_requests': True}, {'max_requests': 100}, {'max_output_tokens': 0}, {'max_input_bytes': 0}):
            with self.assertRaises(ProviderDenied): ProviderBudget(**kwargs)

    def test_input_bound_is_utf8_and_no_silent_truncation(self):
        self.text = '🙂' * 2049
        with self.assertRaises(ProviderDenied): self.prepare()
        self.assertEqual(self.transport.calls, [])

    def test_cancel_before_dispatch_is_terminal_and_free_of_http(self):
        self.approved()
        result = self.adapter.cancel('owner-session', 'run-one')
        self.assertEqual(result['state'], 'cancelled')
        self.assertIsNone(result['claimed_at'])
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.prepare()['state'], 'cancelled')
        self.assertEqual(self.transport.calls, [])

    def test_cancel_after_claim_never_claims_remote_stop(self):
        self.approved()
        def during(encoded):
            status = self.adapter.cancel('owner-session', 'run-one')
            self.assertEqual(status['state'], 'uncertain')
            self.assertFalse(status['remote_cancel_confirmed'])
            return 200, json.dumps(response()).encode()
        self.transport.callback = during
        result = self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(result['state'], 'completed')
        self.assertTrue(result['cancel_requested'])
        with self.assertRaises(ProviderDenied): self.adapter.result('owner-session', 'run-one')

    def test_source_withdrawal_retains_late_result_without_exposing_it(self):
        self.approved()
        def during(encoded):
            self.source_allowed = False
            return 200, json.dumps(response()).encode()
        self.transport.callback = during
        self.assertEqual(self.adapter.dispatch('owner-session', 'run-one')['state'], 'completed')
        with self.assertRaises(ProviderDenied): self.adapter.result('owner-session', 'run-one')

    def test_uncertainty_is_durable_before_transport(self):
        self.approved()
        def inspect(encoded):
            db = sqlite3.connect(self.path)
            try:
                self.assertEqual(db.execute("SELECT state FROM pilot_provider_runs WHERE id='run-one'").fetchone()[0], 'uncertain')
            finally: db.close()
            raise OSError('SECRET lost connection')
        self.transport.callback = inspect
        with self.assertRaises(ProviderOutcomeUnknown) as error: self.adapter.dispatch('owner-session', 'run-one')
        self.assertNotIn('SECRET', str(error.exception))
        self.db.close(); self.db = sqlite3.connect(self.path, isolation_level=None); self.adapter = self.make_adapter()
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'uncertain')
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(len(self.transport.calls), 1)

    def test_lost_claim_commit_ack_does_not_send_or_reset(self):
        self.approved(); transaction = self.adapter._transaction
        @contextmanager
        def lost_ack(token=None, **kwargs):
            with transaction(token, **kwargs): yield
            raise sqlite3.OperationalError('SECRET commit ACK')
        with patch.object(self.adapter, '_transaction', lost_ack):
            with self.assertRaises(ProviderOutcomeUnknown): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'uncertain')

    def test_lost_result_commit_ack_retains_inspectable_completion(self):
        self.approved(); transaction = self.adapter._transaction
        @contextmanager
        def lost_ack(token=None, **kwargs):
            with transaction(token, **kwargs): yield
            if token is None: raise sqlite3.OperationalError('SECRET result ACK')
        with patch.object(self.adapter, '_transaction', lost_ack):
            with self.assertRaises(ProviderOutcomeUnknown): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'completed')
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')

    def test_http_failures_malformed_refusals_and_tool_calls_are_not_success(self):
        samples = [(429, b'private quota error'), (401, b'private auth error'), (302, b'redirect'),
                   (200, b'{'), (200, b'{}'), (200, b'x' * (MAX_RESPONSE_BYTES + 1)),
                   (200, b'{"status":"completed","status":"failed"}')]
        invalid = response(); invalid['output'][0]['content'][0] = {'type': 'refusal', 'refusal': 'No'}
        samples.append((200, json.dumps(invalid).encode()))
        invalid = response(); invalid['output'] = [{'type': 'function_call', 'name': 'shell'}]
        samples.append((200, json.dumps(invalid).encode()))
        invalid = response(); invalid['usage']['output_tokens'] = 129
        samples.append((200, json.dumps(invalid).encode()))
        for index, sample in enumerate(samples):
            with self.subTest(index=index):
                path = Path(self.tmp.name) / ('invalid-' + str(index) + '.sqlite')
                db = sqlite3.connect(path, isolation_level=None)
                def authority(token, binding):
                    return {'task_text': self.text, 'context': binding['context'], 'recipient': 'assistant', 'synthetic_only': True}
                fixture = FixtureTransport(lambda encoded: sample)
                adapter = ResponsesAdapter(db, authority, self.auth.authenticate, transport=fixture, clock=lambda: self.now)
                prepared = adapter.prepare('owner-session', 'run', self.binding)
                adapter.approve('owner-session', 'run', prepared['review_digest'], expires=1100)
                with self.assertRaises(ProviderOutcomeUnknown): adapter.dispatch('owner-session', 'run')
                self.assertEqual(adapter.status('owner-session', 'run')['state'], 'uncertain')
                self.assertEqual(len(fixture.calls), 1)
                db.close()

    def test_retained_binding_or_request_cannot_change_behind_review_digest(self):
        self.approved()
        self.db.execute("UPDATE pilot_provider_runs SET binding=? WHERE id='run-one'", (json.dumps({**self.binding, 'item_id':'other'}),))
        with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.transport.calls, [])

    def test_status_and_stored_rows_never_contain_session_or_provider_key(self):
        self.approved(); result = self.adapter.dispatch('owner-session', 'run-one')
        self.assertNotIn(self.text, json.dumps(result))
        self.assertNotIn('Three paper moons', json.dumps(result))
        for row in self.db.execute('SELECT * FROM pilot_provider_runs'):
            self.assertNotIn('owner-session', str(tuple(row)))

    def test_live_activation_requires_both_explicit_flags(self):
        supplied = []
        def key(): supplied.append(True); return 'sk-fixture-not-a-real-secret'
        for transport_enabled, adapter_enabled in ((False, False), (True, False), (False, True)):
            self.adapter = self.make_adapter(allow_live=adapter_enabled)
            self.adapter.transport = OpenAIResponsesHTTP(key, enabled=transport_enabled)
            self.approved() if self.db.execute('SELECT count(*) FROM pilot_provider_runs').fetchone()[0] == 0 else None
            with self.assertRaises(ProviderDenied): self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(supplied, [])

    def test_http_endpoint_is_fixed_no_redirect_and_secret_stays_in_header(self):
        captured = []
        class Reply:
            status = 200
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self, limit):
                self.limit = limit
                return json.dumps(response()).encode()
        class Opener:
            def open(self, request, timeout):
                captured.append(request)
                self.timeout = timeout
                return Reply()
        transport = OpenAIResponsesHTTP(lambda: 'sk-fixture-not-a-real-secret', enabled=True)
        with patch('pilot.provider.urllib.request.build_opener', return_value=Opener()) as build:
            status, _ = transport.send(b'{"synthetic":true}')
        self.assertEqual(status, 200)
        self.assertEqual(captured[0].full_url, ENDPOINT)
        self.assertEqual(captured[0].method, 'POST')
        self.assertEqual(captured[0].data, b'{"synthetic":true}')
        redirect = build.call_args.args[0]
        self.assertIsNone(redirect.redirect_request(None,None,302,'',{},'https://evil.invalid/'))
        self.assertNotIn('sk-fixture', repr(transport))

    def test_concurrent_dispatch_claims_one_request(self):
        self.approved(); barrier = threading.Barrier(2); results, errors = [], []
        fixture = FixtureTransport()
        def worker():
            db = sqlite3.connect(self.path, isolation_level=None)
            def authority(token, binding):
                self.auth.authenticate(token)
                return {'task_text': self.text, 'context': binding['context'], 'recipient':'assistant', 'synthetic_only':True}
            try:
                adapter = ResponsesAdapter(db, authority, self.auth.authenticate, transport=fixture, clock=lambda:self.now)
                barrier.wait(5)
                try: results.append(adapter.dispatch('owner-session', 'run-one')['state'])
                except ProviderDenied: results.append('denied')
            except BaseException as error: errors.append(error)
            finally: db.close()
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(8)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(results, ['completed', 'denied'])
        self.assertEqual(len(fixture.calls), 1)


class RuntimeProviderCompositionTests(unittest.TestCase):
    def test_signed_source_grant_and_authenticated_recipient_approval_are_separate(self):
        from pilot.auth import LocalOwnerAuth
        from pilot.runtime import PilotRuntime
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            alice = LocalOwnerAuth(path / 'alice-auth', clock=lambda: 1000)
            bob = LocalOwnerAuth(path / 'bob-auth', clock=lambda: 1000)
            runtimes = []
            try:
                alice.bootstrap('alice', 'alice-agent', 'fictional-local-password-alice')
                bob.bootstrap('bob', 'bob-agent', 'fictional-local-password-bob')
                a = alice.login('fictional-local-password-alice')
                b = bob.login('fictional-local-password-bob')
                sender = PilotRuntime(path / 'sender', alice, clock=lambda: 1000)
                receiver = PilotRuntime(path / 'receiver', bob, clock=lambda: 1000)
                runtimes.extend([sender, receiver])
                sender.enrol_peer(a, bob.public_identity(), receiver.fingerprint)
                receiver.enrol_peer(b, alice.public_identity(), sender.fingerprint)
                task = sender.propose(a, receiver.fingerprint, 'task', 'Synthetic task',
                                      'SYNTHETIC ONLY: Count three paper moons.', 'c' * 64, 'task-one', 1100,
                                      provider_disclosure={'provider':'openai','model':'fixture-model','max_output_tokens':128})
                item_id = task['id']
                released = sender.release(a, item_id, sender.review(a, item_id)['review_digest'])
                receiver.receive(b, sender.prepare_delivery(a, released['message_id']))
                binding = {'item_id':item_id, 'context':'c' * 64, 'payload_digest':task['artifact_digest'],
                           'provider':'openai','model':'fixture-model','max_output_tokens':128}
                fixture = FixtureTransport()
                adapter = ResponsesAdapter(receiver.db, receiver.authorise_provider, bob.authenticate,
                                           transport=fixture, clock=lambda:1000)
                with self.assertRaises(ProviderDenied): adapter.prepare(b, 'model-run', binding)
                receiver.decide(b, item_id, receiver.review(b, item_id)['review_digest'], 'accept')
                prepared = adapter.prepare(b, 'model-run', binding)
                with self.assertRaises(ProviderDenied): adapter.dispatch(b, 'model-run')
                adapter.approve(b, 'model-run', prepared['review_digest'], expires=1050)
                self.assertEqual(adapter.dispatch(b, 'model-run')['state'], 'completed')
                self.assertEqual(len(fixture.calls), 1)
                cancelled = sender.cancel(a, item_id, sender.review(a, item_id)['review_digest'])
                receiver.receive(b, sender.prepare_delivery(a, cancelled['cancel_message_id']))
                with self.assertRaises(ProviderDenied): adapter.result(b, 'model-run')
                self.assertEqual(adapter.status(b, 'model-run')['state'], 'completed')
            finally:
                for runtime in runtimes: runtime.close()
                alice.close(); bob.close()


if __name__ == '__main__':
    unittest.main()
