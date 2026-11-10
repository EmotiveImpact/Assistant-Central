"""Real local authority and store composition, with an explicitly fake model."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.crypto import digest
from pilot.provider import ResponsesAdapter, ProviderDenied, ProviderOutcomeUnknown
from pilot.runtime import PilotRuntime, RuntimeDenied, RuntimeOutcomeUnknown
from pilot.workflow import SyntheticWorkLoop, WorkflowDenied, FIXTURE_GRANT


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.auths, self.runtimes, self.sessions = {}, {}, {}
        for name in ('source', 'recipient'):
            path = self.root / name
            path.mkdir(mode=0o700)
            auth = LocalOwnerAuth(path / 'auth', clock=lambda: self.now)
            auth.bootstrap(name, name + '-assistant', 'Fictional workflow password ' + name)
            self.auths[name] = auth
            self.sessions[name] = auth.login('Fictional workflow password ' + name)
            self.runtimes[name] = PilotRuntime(path / 'runtime', auth, clock=lambda: self.now)
        self.addCleanup(self.close)
        self.a, self.b = self.runtimes.values()
        for actor, peer in ((self.a, self.b), (self.b, self.a)):
            actor.enrol_peer(self.session(actor), peer.identity, peer.fingerprint)
        self.workflow = SyntheticWorkLoop(self.b, enabled=True)

    def close(self):
        for runtime in self.runtimes.values(): runtime.close()
        for auth in self.auths.values(): auth.close()

    def session(self, runtime):
        return self.sessions[runtime.identity['owner_id']]

    def accepted(self, *, name='garden', grant=FIXTURE_GRANT):
        item = self.a.propose(self.session(self.a), self.b.fingerprint, 'task', 'Fictional research',
            'SYNTHETIC ONLY: Compare imaginary community garden ideas.', digest({'name': name}), name,
            1600, provider_disclosure=grant)
        self.a.release(self.session(self.a), item['id'], self.a.review(self.session(self.a), item['id'])['review_digest'])
        incoming = self.b.receive(self.session(self.b), self.a.prepare_delivery(self.session(self.a), 'proposal-' + item['id']))
        self.b.decide(self.session(self.b), item['id'], self.b.review(self.session(self.b), item['id'])['review_digest'], 'accept')
        return item['id']

    def complete(self, name='garden'):
        item = self.accepted(name=name)
        prepared = self.workflow.prepare(self.session(self.b), item)
        self.workflow.approve(self.session(self.b), prepared['run_id'], prepared['review_digest'], 1500)
        return self.workflow.dispatch(self.session(self.b), prepared['run_id'], prepared['review_digest'])

    def stage(self, status):
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        return self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])

    def test_disabled_is_inspection_only_and_no_live_transport_is_selected(self):
        item = self.accepted()
        disabled = SyntheticWorkLoop(self.b)
        with self.assertRaises(WorkflowDenied): disabled.prepare(self.session(self.b), item)
        self.assertEqual(disabled.list_runs(self.session(self.b)), [])
        prepared = self.workflow.prepare(self.session(self.b), item)
        self.assertEqual(disabled.status(self.session(self.b), prepared['run_id'])['allowed_actions'], [])
        self.assertIsNone(disabled.adapter.transport)
        self.assertFalse(self.workflow.adapter.allow_live)
        self.assertIs(self.workflow.adapter.transport.synthetic_only, True)

    def test_default_disabled_does_not_reserve_any_provider_schema_or_budget(self):
        disabled = SyntheticWorkLoop(self.a)
        self.assertEqual(disabled.list_runs(self.session(self.a)), [])
        self.assertIsNone(disabled.adapter)
        names = [row[0] for row in self.a.db.execute('SELECT name FROM sqlite_master')]
        self.assertNotIn('pilot_provider_meta', names)
        self.assertNotIn('pilot_workflow_meta', names)

    def test_default_disabled_opens_legacy_provider_budget_without_migration(self):
        legacy = ResponsesAdapter(self.a.db, self.a.authorise_provider, self.a.auth.authenticate)
        budget = self.a.db.execute('SELECT budget FROM pilot_provider_meta').fetchone()[0]
        disabled = SyntheticWorkLoop(self.a)
        self.assertEqual(disabled.list_runs(self.session(self.a)), [])
        self.assertEqual(self.a.db.execute('SELECT budget FROM pilot_provider_meta').fetchone()[0], budget)
        self.assertIsNone(disabled.adapter)
        with self.assertRaises(ProviderDenied): SyntheticWorkLoop(self.a, enabled=True)

    def test_complete_task_result_draft_release_and_requester_acceptance(self):
        status = self.complete()
        self.assertEqual(status['state'], 'completed')
        self.assertIsNone(status['artifact_id'])
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        self.assertIn('No model or research was run', review['content'])
        self.assertEqual(review['review']['recipient'], self.a.identity)
        self.assertEqual(review['review']['parent_id'], status['item_id'])
        artifact = review['review']['artifact']
        self.assertEqual(artifact['text'], review['content'])
        self.assertEqual(digest(artifact), review['review']['artifact_id'])
        staged = self.stage(status)
        self.assertEqual(staged['artifact_state'], 'draft')
        self.assertEqual(staged['artifact_id'], review['review']['artifact_id'])
        self.assertIsNone(self.b.status(self.session(self.b), staged['artifact_id'])['message_id'])
        self.b.release(self.session(self.b), staged['artifact_id'], self.b.review(self.session(self.b), staged['artifact_id'])['review_digest'])
        received = self.a.receive(self.session(self.a), self.b.prepare_delivery(self.session(self.b), 'proposal-' + staged['artifact_id']))
        self.assertEqual(received['item']['state'], 'pending')
        decision = self.a.decide(self.session(self.a), staged['artifact_id'], self.a.review(self.session(self.a), staged['artifact_id'])['review_digest'], 'accept')
        self.assertEqual(decision['state'], 'accepted')

    def test_missing_or_other_provider_grant_never_prepares(self):
        for name, grant in (('none', None), ('other', {**FIXTURE_GRANT, 'model': 'another-model'})):
            item = self.accepted(name=name, grant=grant)
            with self.assertRaises(RuntimeDenied): self.workflow.prepare(self.session(self.b), item)
        self.assertEqual(self.workflow.list_runs(self.session(self.b)), [])

    def test_acceptance_does_not_approve_or_dispatch(self):
        item = self.accepted()
        status = self.workflow.prepare(self.session(self.b), item)
        self.assertEqual(status['state'], 'prepared')
        with self.assertRaises(ProviderDenied): self.workflow.dispatch(self.session(self.b), status['run_id'], status['review_digest'])
        with self.assertRaises(WorkflowDenied): self.workflow.review_result(self.session(self.b), status['run_id'])
        self.assertIsNone(self.workflow.status(self.session(self.b), status['run_id'])['claimed_at'])

    def test_exact_result_review_is_stable_and_duplicate_stage_returns_metadata(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        self.now += 10
        self.assertEqual(review, self.workflow.review_result(self.session(self.b), status['run_id']))
        first = self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        second = self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        self.assertEqual(first, second)
        self.assertNotIn('text', json.dumps(second))
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM pilot_workflow_artifacts').fetchone()[0], 1)
        self.assertEqual(self.b.db.execute("SELECT count(*) FROM runtime_audit WHERE event='workflow_result_staged'").fetchone()[0], 1)
        with self.assertRaises(WorkflowDenied): self.workflow.stage_result(self.session(self.b), status['run_id'], 'a' * 64)

    def test_stale_digest_and_corrupt_result_never_create_artifacts(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        with self.assertRaises(WorkflowDenied): self.workflow.stage_result(self.session(self.b), status['run_id'], 'b' * 64)
        self.b.db.execute('UPDATE pilot_provider_runs SET result=? WHERE id=?', ('changed original text', status['run_id']))
        with self.assertRaises(WorkflowDenied): self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        self.assertEqual(self.b.db.execute("SELECT count(*) FROM runtime_items WHERE kind='artifact'").fetchone()[0], 0)

    def test_source_withdrawal_blocks_result_and_staging(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        self.a.cancel(self.session(self.a), status['item_id'], self.a.review(self.session(self.a), status['item_id'])['review_digest'])
        message = self.a.status(self.session(self.a), status['item_id'])['cancel_message_id']
        self.b.receive(self.session(self.b), self.a.prepare_delivery(self.session(self.a), message))
        with self.assertRaises(WorkflowDenied): self.workflow.review_result(self.session(self.b), status['run_id'])
        with self.assertRaises(WorkflowDenied): self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        self.assertEqual(self.workflow.status(self.session(self.b), status['run_id'])['allowed_actions'], ['cancel'])

    def test_expiry_crossing_staging_rolls_back_draft_and_mapping(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        original = self.b._event
        def event(name, *args, **kwargs):
            original(name, *args, **kwargs)
            if name == 'workflow_result_staged': self.now = 1600
        with patch.object(self.b, '_event', event), self.assertRaises(WorkflowDenied):
            self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM pilot_workflow_artifacts').fetchone()[0], 0)
        self.assertEqual(self.b.db.execute("SELECT count(*) FROM runtime_items WHERE kind='artifact'").fetchone()[0], 0)

    def test_audit_failure_rolls_back_both_artifact_and_mapping(self):
        status = self.complete()
        self.b.db.execute("CREATE TRIGGER refuse_staging BEFORE INSERT ON runtime_audit WHEN NEW.event='workflow_result_staged' BEGIN SELECT RAISE(ABORT,'private failure'); END")
        with self.assertRaises(RuntimeOutcomeUnknown) as caught: self.stage(status)
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM pilot_workflow_artifacts').fetchone()[0], 0)
        self.assertEqual(self.b.db.execute("SELECT count(*) FROM runtime_items WHERE kind='artifact'").fetchone()[0], 0)

    def test_lost_commit_ack_is_inspectable_without_dispatch_or_new_artifact(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        original = self.b._transaction
        @contextmanager
        def lost(session):
            with original(session) as checks: yield checks
            raise RuntimeOutcomeUnknown('Lost acknowledgement')
        with patch.object(self.b, '_transaction', lost), self.assertRaises(RuntimeOutcomeUnknown):
            self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest'])
        recovered = self.workflow.status(self.session(self.b), status['run_id'])
        self.assertEqual(recovered['artifact_id'], review['review']['artifact_id'])
        self.assertEqual(self.workflow.stage_result(self.session(self.b), status['run_id'], review['review_digest']), recovered)
        with self.assertRaises(ProviderDenied): self.workflow.dispatch(self.session(self.b), status['run_id'], status['review_digest'])

    def test_cancel_staged_workflow_cancels_draft_atomically(self):
        status = self.stage(self.complete())
        self.workflow.cancel(self.session(self.b), status['run_id'])
        stopped = self.workflow.status(self.session(self.b), status['run_id'])
        self.assertTrue(stopped['cancel_requested'])
        self.assertEqual(stopped['artifact_state'], 'cancelled')
        with self.assertRaises(RuntimeDenied): self.b.release(self.session(self.b), stopped['artifact_id'], self.b.review(self.session(self.b), stopped['artifact_id'])['review_digest'])
        self.assertFalse(stopped['remote_cancel_confirmed'])

    def test_cancel_failure_keeps_original_run_and_draft_unchanged(self):
        status = self.stage(self.complete())
        self.b.db.execute("CREATE TRIGGER refuse_cancel BEFORE INSERT ON runtime_audit WHEN NEW.event='workflow_cancelled' BEGIN SELECT RAISE(ABORT,'refuse'); END")
        with self.assertRaises(RuntimeOutcomeUnknown): self.workflow.cancel(self.session(self.b), status['run_id'])
        retained = self.workflow.status(self.session(self.b), status['run_id'])
        self.assertFalse(retained['cancel_requested'])
        self.assertEqual(retained['artifact_state'], 'draft')

    def test_restart_retains_original_result_and_mapping(self):
        status = self.stage(self.complete())
        self.b.close()
        self.b = PilotRuntime(self.root/'recipient'/'runtime', self.auths['recipient'], clock=lambda: self.now)
        self.runtimes['recipient'] = self.b
        self.workflow = SyntheticWorkLoop(self.b, enabled=True)
        recovered = self.workflow.status(self.session(self.b), status['run_id'])
        self.assertEqual(recovered['artifact_id'], status['artifact_id'])
        self.assertEqual(recovered['result_digest'], status['result_digest'])
        self.assertEqual(self.stage(status)['artifact_id'], status['artifact_id'])

    def test_concurrent_connections_stage_one_original_draft(self):
        status = self.complete()
        review = self.workflow.review_result(self.session(self.b), status['run_id'])
        barrier = threading.Barrier(2)
        results, failures = [], []
        def worker():
            runtime = None
            try:
                runtime = PilotRuntime(self.root/'recipient'/'runtime', self.auths['recipient'], clock=lambda: self.now)
                workflow = SyntheticWorkLoop(runtime, enabled=True)
                barrier.wait(timeout=5)
                results.append(workflow.stage_result(self.sessions['recipient'], status['run_id'], review['review_digest']))
            except Exception as error: failures.append(error)
            finally:
                if runtime: runtime.close()
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertFalse(failures)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['artifact_id'], results[1]['artifact_id'])
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM pilot_workflow_artifacts').fetchone()[0], 1)

    def test_uncertain_dispatch_survives_reopen_and_cannot_stage(self):
        status = self.workflow.prepare(self.session(self.b), self.accepted())
        self.workflow.approve(self.session(self.b), status['run_id'], status['review_digest'], 1500)
        with patch.object(self.workflow.adapter.transport, 'send', side_effect=TimeoutError('private fixture error')):
            with self.assertRaises(ProviderOutcomeUnknown): self.workflow.dispatch(self.session(self.b), status['run_id'], status['review_digest'])
        self.workflow = SyntheticWorkLoop(self.b, enabled=True)
        recovered = self.workflow.status(self.session(self.b), status['run_id'])
        self.assertEqual(recovered['state'], 'uncertain')
        self.assertNotIn('run', recovered['allowed_actions'])
        with self.assertRaises(ProviderDenied): self.workflow.dispatch(self.session(self.b), status['run_id'], status['review_digest'])
        with self.assertRaises(WorkflowDenied): self.workflow.review_result(self.session(self.b), status['run_id'])


if __name__ == '__main__':
    unittest.main()
