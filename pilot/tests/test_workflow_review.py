"""Independent adversarial review of the reviewed synthetic work loop.

The fixture establishes real local sessions and signed source proposals. It is
not a live model, external security audit or real-person consent exercise.
"""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth, AuthError
from pilot.crypto import digest
from pilot.runtime import PilotRuntime, RuntimeDenied, RuntimeOutcomeUnknown
from pilot.provider import ResponsesAdapter, ProviderDenied, ProviderOutcomeUnknown
from pilot.workflow import SyntheticWorkLoop, FIXTURE_MODEL


PASSWORD_A = 'fictional-independent-alpha-password'
PASSWORD_B = 'fictional-independent-beta-password'
DENIED = (ValueError, PermissionError)


class WorkLoopReview(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='reviewed-work-independent-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 1000
        self.ap = self.root / 'first'
        self.bp = self.root / 'second'
        self.a = LocalOwnerAuth(self.ap, clock=lambda: self.now)
        self.b = LocalOwnerAuth(self.bp, clock=lambda: self.now)
        self.addCleanup(lambda: self.a.close())
        self.addCleanup(lambda: self.b.close())
        self.a.bootstrap('fictional-first', 'first-assistant', PASSWORD_A)
        self.b.bootstrap('fictional-second', 'second-assistant', PASSWORD_B)
        self.at, self.bt = self.a.login(PASSWORD_A), self.b.login(PASSWORD_B)
        self.ar = PilotRuntime(self.ap, self.a, clock=lambda: self.now)
        self.br = PilotRuntime(self.bp, self.b, clock=lambda: self.now)
        self.addCleanup(lambda: self.ar.close())
        self.addCleanup(lambda: self.br.close())
        self.ar.enrol_peer(self.at, self.br.identity, self.br.fingerprint)
        self.br.enrol_peer(self.bt, self.ar.identity, self.ar.fingerprint)
        self.loop = SyntheticWorkLoop(self.br, enabled=True)
        self.item_id = self.accepted_task()

    def accepted_task(self, *, grant=True, accept=True, task='independent-task', context='a' * 64):
        provider = {'provider': 'openai', 'model': FIXTURE_MODEL, 'max_output_tokens': 128} if grant else None
        item = self.ar.propose(self.at, self.br.fingerprint, 'task', 'Independent fictional task',
            'SYNTHETIC ONLY: Review a fictional community garden plan.', context, task, 1100,
            provider_disclosure=provider)
        item_id = item['id']
        self.ar.release(self.at, item_id, self.ar.review(self.at, item_id)['review_digest'])
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, 'proposal-' + item_id))
        if accept:
            self.br.decide(self.bt, item_id, self.br.review(self.bt, item_id)['review_digest'], 'accept')
        return item_id

    def prepared(self, item_id=None):
        return self.loop.prepare(self.bt, item_id or self.item_id)

    def completed(self, item_id=None):
        prepared = self.prepared(item_id)
        run_id = prepared['run_id']
        review = self.loop.review(self.bt, run_id)
        self.loop.approve(self.bt, run_id, review['review_digest'], expires=1090)
        self.loop.dispatch(self.bt, run_id, review['review_digest'])
        return run_id

    def withdraw_source(self):
        self.ar.cancel(self.at, self.item_id, self.ar.review(self.at, self.item_id)['review_digest'])
        cancel = next(entry for entry in self.ar.state(self.at)['outbox'] if entry['message_id'].startswith('cancel-'))
        self.br.receive(self.bt, self.ar.prepare_delivery(self.at, cancel['message_id']))

    def artifact_rows(self):
        return self.br.db.execute("SELECT * FROM runtime_items WHERE direction='outgoing' AND kind='artifact'").fetchall()

    def stage(self, run_id):
        review = self.loop.review_result(self.bt, run_id)
        return self.loop.stage_result(self.bt, run_id, review['review_digest'])

    def test_local_enable_and_signed_source_grant_are_separate_requirements(self):
        disabled = SyntheticWorkLoop(self.br)
        with self.assertRaises(DENIED): disabled.prepare(self.bt, self.item_id)
        ungranted = self.accepted_task(grant=False, task='without-grant', context='b' * 64)
        with self.assertRaises(DENIED): self.loop.prepare(self.bt, ungranted)
        self.assertEqual(self.br.db.execute('SELECT COUNT(*) FROM pilot_provider_runs').fetchone()[0], 0)

    def test_pending_and_rejected_work_cannot_be_used_for_provider_work(self):
        pending = self.accepted_task(accept=False, task='pending-task', context='b' * 64)
        with self.assertRaises(DENIED): self.loop.prepare(self.bt, pending)
        self.br.decide(self.bt, pending, self.br.review(self.bt, pending)['review_digest'], 'reject')
        with self.assertRaises(DENIED): self.loop.prepare(self.bt, pending)

    def test_another_owners_token_cannot_read_or_stage_a_result(self):
        run_id = self.completed()
        for call in (lambda: self.loop.status(self.at, run_id),
                     lambda: self.loop.review_result(self.at, run_id),
                     lambda: self.loop.stage_result(self.at, run_id, 'a' * 64)):
            with self.assertRaises(DENIED): call()
        self.assertEqual(self.artifact_rows(), [])

    def test_review_and_dispatch_do_not_grant_artifact_release(self):
        run_id = self.completed()
        self.assertEqual(self.artifact_rows(), [])
        review = self.loop.review_result(self.bt, run_id)
        self.assertEqual(self.artifact_rows(), [])
        self.loop.stage_result(self.bt, run_id, review['review_digest'])
        rows = self.artifact_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], 'draft')
        self.assertIsNone(rows[0]['message_id'])
        self.assertFalse(any(entry['message_id'].startswith('proposal-') for entry in self.br.state(self.bt)['outbox']))

    def test_result_reviews_cannot_be_crossed_between_original_tasks(self):
        first = self.completed()
        other_item = self.accepted_task(task='other-task', context='b' * 64)
        other = self.completed(other_item)
        other_review = self.loop.review_result(self.bt, other)
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, first, other_review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])

    def test_observed_source_withdrawal_after_review_blocks_staging(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        self.withdraw_source()
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        with self.assertRaises(DENIED): self.loop.review_result(self.bt, run_id)
        self.assertEqual(self.artifact_rows(), [])

    def test_peer_revocation_after_review_blocks_staging(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        self.br.revoke_peer(self.bt, self.ar.fingerprint)
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])

    def test_session_logout_after_review_blocks_staging(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        self.b.logout(self.bt)
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])

    def test_expired_source_cannot_be_renewed_by_the_completed_result(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        self.now = 1100
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])

    def test_source_withdrawal_after_staging_still_blocks_release(self):
        run_id = self.completed()
        self.stage(run_id)
        row = self.artifact_rows()[0]
        review = self.br.review(self.bt, row['id'])
        self.withdraw_source()
        with self.assertRaises(DENIED): self.br.release(self.bt, row['id'], review['review_digest'])
        self.assertEqual(self.artifact_rows()[0]['state'], 'draft')

    def test_cancelled_workflow_cannot_release_its_already_staged_draft(self):
        run_id = self.completed()
        self.stage(run_id)
        row = self.artifact_rows()[0]
        review = self.br.review(self.bt, row['id'])
        self.loop.cancel(self.bt, run_id)
        with self.assertRaises(DENIED): self.br.release(self.bt, row['id'], review['review_digest'])
        self.assertIsNone(self.artifact_rows()[0]['message_id'])

    def test_original_result_text_corruption_cannot_reuse_its_digest(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        # Corrupt retained content without changing its committed result digest.
        # This is a storage-consistency fault, not an assertion of hostile-host isolation.
        self.br.db.execute('UPDATE pilot_provider_runs SET result=? WHERE id=?',
                           ('SYNTHETIC CORRUPTED RESULT', run_id))
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])

    def test_duplicate_stage_keeps_one_original_draft_and_returns_no_content(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        first = self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.now += 1
        again = self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(first['artifact_id'], again['artifact_id'])
        self.assertEqual(len(self.artifact_rows()), 1)
        self.assertNotIn(review['content'], json.dumps(again))
        self.assertNotIn(self.bt, json.dumps(again))

    def test_concurrent_connections_stage_one_original_draft(self):
        run_id = self.completed()
        reviewed = self.loop.review_result(self.bt, run_id)['review_digest']
        barrier = threading.Barrier(2)
        results, errors = [], []
        def worker():
            runtime = PilotRuntime(self.bp, self.b, clock=lambda: self.now)
            try:
                loop = SyntheticWorkLoop(runtime, enabled=True)
                barrier.wait(5)
                results.append(loop.stage_result(self.bt, run_id, reviewed))
            except BaseException as error:
                errors.append(error)
            finally:
                runtime.close()
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(8)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['artifact_id'], results[1]['artifact_id'])
        self.assertEqual(len(self.artifact_rows()), 1)

    @contextmanager
    def lost_commit_ack(self):
        original = self.br.db
        class Proxy:
            def __getattr__(self, key): return getattr(original, key)
            def execute(self, sql, *args):
                result = original.execute(sql, *args)
                if sql.strip().upper() == 'COMMIT':
                    raise sqlite3.OperationalError('SYNTHETIC private lost acknowledgement')
                return result
        self.br.db = Proxy()
        try: yield
        finally: self.br.db = original

    def test_lost_stage_commit_ack_is_recovered_without_a_second_draft(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        with self.lost_commit_ack():
            with self.assertRaises(RuntimeError) as error:
                self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertNotIn('private', str(error.exception))
        self.assertEqual(len(self.artifact_rows()), 1)
        recovered = self.loop.status(self.bt, run_id)
        self.assertEqual(recovered['artifact_id'], self.artifact_rows()[0]['id'])
        self.br.close()
        self.br = PilotRuntime(self.bp, self.b, clock=lambda: self.now)
        self.loop = SyntheticWorkLoop(self.br, enabled=True)
        again = self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(again['artifact_id'], recovered['artifact_id'])
        self.assertEqual(len(self.artifact_rows()), 1)

    def test_expiry_during_staging_rolls_back_draft_and_mapping_together(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        original = self.br._event
        def expire(*args, **kwargs):
            value = original(*args, **kwargs)
            self.now = 1100
            return value
        with patch.object(self.br, '_event', expire):
            with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])
        self.assertIsNone(self.loop.status(self.bt, run_id)['artifact_id'])

    def test_audit_failure_does_not_leave_an_unmapped_draft(self):
        run_id = self.completed()
        review = self.loop.review_result(self.bt, run_id)
        with patch.object(self.br, '_event', side_effect=RuntimeError('SYNTHETIC audit failure')):
            with self.assertRaises(RuntimeError): self.loop.stage_result(self.bt, run_id, review['review_digest'])
        self.assertEqual(self.artifact_rows(), [])
        self.assertIsNone(self.loop.status(self.bt, run_id)['artifact_id'])

    def test_uncertain_dispatch_survives_restart_without_result_staging_or_retry(self):
        prepared = self.prepared()
        run_id = prepared['run_id']
        self.loop.approve(self.bt, run_id, prepared['review_digest'], expires=1090)
        with patch.object(self.loop.adapter.transport, 'send', side_effect=TimeoutError('SYNTHETIC lost return')) as send:
            with self.assertRaises(ProviderOutcomeUnknown):
                self.loop.dispatch(self.bt, run_id, prepared['review_digest'])
            self.assertEqual(send.call_count, 1)
        self.br.close(); self.b.close()
        self.b = LocalOwnerAuth(self.bp, clock=lambda: self.now)
        self.br = PilotRuntime(self.bp, self.b, clock=lambda: self.now)
        self.loop = SyntheticWorkLoop(self.br, enabled=True)
        with self.assertRaises(DENIED): self.loop.status(self.bt, run_id)
        self.bt = self.b.login(PASSWORD_B)
        self.assertEqual(self.loop.status(self.bt, run_id)['state'], 'uncertain')
        with patch.object(self.loop.adapter.transport, 'send') as send:
            with self.assertRaises(DENIED): self.loop.dispatch(self.bt, run_id, prepared['review_digest'])
            self.assertFalse(send.called)
        with self.assertRaises(DENIED): self.loop.review_result(self.bt, run_id)
        with self.assertRaises(DENIED): self.loop.stage_result(self.bt, run_id, 'a' * 64)
        self.assertEqual(self.artifact_rows(), [])

    def test_cancel_rolls_back_run_artifact_and_signed_notice_together(self):
        run_id = self.completed()
        self.stage(run_id)
        artifact = self.artifact_rows()[0]['id']
        self.br.release(self.bt, artifact, self.br.review(self.bt, artifact)['review_digest'])
        event = self.br._event
        def fail_final_event(name, *args, **kwargs):
            if name == 'workflow_cancelled': raise RuntimeError('SYNTHETIC commit preparation failure')
            return event(name, *args, **kwargs)
        with patch.object(self.br, '_event', fail_final_event):
            with self.assertRaises(RuntimeError): self.loop.cancel(self.bt, run_id)
        self.assertFalse(self.loop.status(self.bt, run_id)['cancel_requested'])
        self.assertEqual(self.br.status(self.bt, artifact)['state'], 'released')
        self.assertFalse(any(entry['message_id'].startswith('cancel-') for entry in self.br.state(self.bt)['outbox']))
        self.loop.cancel(self.bt, run_id)
        self.assertTrue(self.loop.status(self.bt, run_id)['cancel_requested'])
        self.assertEqual(self.br.status(self.bt, artifact)['state'], 'cancelled')
        self.assertTrue(any(entry['message_id'].startswith('cancel-') for entry in self.br.state(self.bt)['outbox']))


class DisabledWorkflowReview(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='disabled-work-review-')
        self.addCleanup(self.temporary.cleanup)
        path = Path(self.temporary.name) / 'owner'
        self.auth = LocalOwnerAuth(path)
        self.auth.bootstrap('fictional-disabled', 'disabled-assistant', PASSWORD_B)
        self.addCleanup(self.auth.close)
        self.token = self.auth.login(PASSWORD_B)
        self.runtime = PilotRuntime(path, self.auth)
        self.addCleanup(self.runtime.close)

    def test_default_disabled_does_not_persist_a_provider_budget(self):
        loop = SyntheticWorkLoop(self.runtime)
        self.assertEqual(loop.list_runs(self.token), [])
        self.assertIsNone(self.runtime.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pilot_provider_meta'").fetchone())

    def test_default_disabled_can_open_an_existing_standalone_provider_store(self):
        ResponsesAdapter(self.runtime.db, self.runtime.authorise_provider, self.auth.authenticate)
        original = self.runtime.db.execute('SELECT version,budget FROM pilot_provider_meta').fetchone()
        loop = SyntheticWorkLoop(self.runtime)
        self.assertEqual(loop.list_runs(self.token), [])
        retained = self.runtime.db.execute('SELECT version,budget FROM pilot_provider_meta').fetchone()
        self.assertEqual(tuple(original), tuple(retained))
        with self.assertRaises(DENIED): loop.status(self.token, 'work-' + 'a' * 64)
        # Opting into a different budget remains an explicit incompatibility,
        # never an automatic increase of the immutable original allowance.
        with self.assertRaises(DENIED): SyntheticWorkLoop(self.runtime, enabled=True)
        self.assertEqual(tuple(original), tuple(self.runtime.db.execute('SELECT version,budget FROM pilot_provider_meta').fetchone()))


class WorkLoopHTTPReview(unittest.TestCase):
    def setUp(self):
        from pilot.server import PilotHTTPServer
        self.server_type = PilotHTTPServer
        self.temporary = tempfile.TemporaryDirectory(prefix='reviewed-work-http-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.path = root / 'recipient'
        a, b = LocalOwnerAuth(root / 'origin'), LocalOwnerAuth(self.path)
        ar = br = None
        try:
            a.bootstrap('fictional-origin', 'origin-assistant', PASSWORD_A)
            b.bootstrap('fictional-recipient', 'recipient-assistant', PASSWORD_B)
            at, bt = a.login(PASSWORD_A), b.login(PASSWORD_B)
            ar, br = PilotRuntime(root / 'origin', a), PilotRuntime(self.path, b)
            ar.enrol_peer(at, br.identity, br.fingerprint)
            br.enrol_peer(bt, ar.identity, ar.fingerprint)
            grant = {'provider': 'openai', 'model': FIXTURE_MODEL, 'max_output_tokens': 128}
            item = ar.propose(at, br.fingerprint, 'task', 'HTTP synthetic task',
                'SYNTHETIC ONLY: Review a fictional garden.', 'b' * 64, 'http-review-task',
                time.time() + 300, provider_disclosure=grant)
            self.item_id = item['id']
            ar.release(at, self.item_id, ar.review(at, self.item_id)['review_digest'])
            br.receive(bt, ar.prepare_delivery(at, 'proposal-' + self.item_id))
            br.decide(bt, self.item_id, br.review(bt, self.item_id)['review_digest'], 'accept')
        finally:
            if ar: ar.close()
            if br: br.close()
            a.close(); b.close()
        self.start_server(enabled=True)
        self.addCleanup(self.stop_server)
        self.token = self.login()

    def start_server(self, *, enabled):
        self.server = self.server_type(self.path, synthetic_workflow=enabled)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, method, path, body=None, *, token=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        request_headers = {'Origin': self.server.origin}
        if body is not None: request_headers['Content-Type'] = 'application/json'
        if token is not None: request_headers['Authorization'] = 'Bearer ' + token
        request_headers.update(headers or {})
        try:
            connection.request(method, path, json.dumps(body).encode() if body is not None else None, request_headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def login(self):
        status, result = self.request('POST', '/api/session', {'password': PASSWORD_B})
        self.assertEqual(status, 200)
        return result['token']

    def prepare(self):
        status, result = self.request('POST', '/api/items/' + self.item_id + '/workflow', {}, token=self.token)
        self.assertEqual(status, 200)
        return result

    def test_disabled_server_cannot_be_enabled_by_an_owner_request(self):
        self.stop_server()
        self.start_server(enabled=False)
        self.token = self.login()
        status, state = self.request('GET', '/api/state', token=self.token)
        self.assertEqual(status, 200)
        self.assertFalse(state['workflow']['enabled'])
        for body in ({}, {'enabled': True}, {'synthetic_workflow': True}, {'allow_live': True}):
            status, _ = self.request('POST', '/api/items/' + self.item_id + '/workflow', body, token=self.token)
            self.assertEqual(status, 400)
        _, state = self.request('GET', '/api/state', token=self.token)
        self.assertEqual(state['workflow']['runs'], [])

    def test_prepare_rejects_caller_supplied_route_output_or_run_identity(self):
        for body in ({'model': 'different-model'}, {'text': 'UNTRUSTED REPLACEMENT'},
                     {'run_id': 'alias'}, {'recipient': 'somebody-else'}, {'context': 'f' * 64}):
            with self.subTest(body=body):
                status, _ = self.request('POST', '/api/items/' + self.item_id + '/workflow', body, token=self.token)
                self.assertEqual(status, 400)
        _, state = self.request('GET', '/api/state', token=self.token)
        self.assertEqual(state['workflow']['runs'], [])

    def test_workflow_mutations_require_bearer_and_same_origin(self):
        path = '/api/items/' + self.item_id + '/workflow'
        self.assertEqual(self.request('POST', path, {})[0], 401)
        self.assertEqual(self.request('POST', path, {}, token=self.token, headers={'Origin': 'https://attacker.invalid'})[0], 400)
        prepared = self.prepare()
        base = '/api/workflows/' + prepared['run_id']
        for action, body in (('approve', {'review_digest': prepared['review_digest'], 'expires': time.time() + 30}),
                             ('run', {'review_digest': prepared['review_digest']}), ('stage', {'review_digest': '0' * 64}),
                             ('cancel', {})):
            self.assertEqual(self.request('POST', base + '/' + action, body)[0], 401)

    def test_http_work_loop_stages_only_an_inert_exact_draft(self):
        prepared = self.prepare()
        base = '/api/workflows/' + prepared['run_id']
        status, review = self.request('GET', base + '/review', token=self.token)
        self.assertEqual(status, 200)
        approved = {'review_digest': review['review_digest'], 'expires': time.time() + 60}
        self.assertEqual(self.request('POST', base + '/approve', approved, token=self.token)[0], 200)
        self.assertEqual(self.request('POST', base + '/run', {'review_digest': review['review_digest']}, token=self.token)[0], 200)
        status, result = self.request('GET', base + '/result', token=self.token)
        self.assertEqual(status, 200)
        self.assertIn('SYNTHETIC', result['content'])
        for extra in ({'text': 'REPLACED RESULT'}, {'recipient': 'other-owner'}, {'context': 'c' * 64}):
            body = {'review_digest': result['review_digest'], **extra}
            self.assertEqual(self.request('POST', base + '/stage', body, token=self.token)[0], 400)
        self.assertEqual(self.request('POST', base + '/stage', {'review_digest': '0' * 64}, token=self.token)[0], 400)
        status, staged = self.request('POST', base + '/stage', {'review_digest': result['review_digest']}, token=self.token)
        self.assertEqual(status, 200)
        _, state = self.request('GET', '/api/state', token=self.token)
        artifact = next(item for item in state['items'] if item['id'] == staged['artifact_id'])
        self.assertEqual(artifact['state'], 'draft')
        self.assertIsNone(artifact['message_id'])
        self.assertFalse(state['provider']['live_enabled'])
        self.assertNotIn(result['content'], json.dumps(state))

    def test_logout_before_run_prevents_dispatch(self):
        prepared = self.prepare()
        base = '/api/workflows/' + prepared['run_id']
        self.assertEqual(self.request('POST', base + '/approve',
            {'review_digest': prepared['review_digest'], 'expires': time.time() + 60}, token=self.token)[0], 200)
        self.assertEqual(self.request('DELETE', '/api/session', {}, token=self.token)[0], 200)
        self.assertEqual(self.request('POST', base + '/run', {'review_digest': prepared['review_digest']}, token=self.token)[0], 401)
        self.token = self.login()
        status, state = self.request('GET', base, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(state['state'], 'approved')
        self.assertIsNone(state['claimed_at'])


if __name__ == '__main__':
    unittest.main()
