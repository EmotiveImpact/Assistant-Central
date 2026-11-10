"""Actual owner HTTP checks for the synthetic task-to-result composition.

Each test uses separate processes/stores and fresh fictional identities. There
are no injected HTTP responses, live provider requests or shared owner sessions.
"""
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from urllib.parse import urlsplit

from pilot.demo import provision
from pilot.workflow_demo import TwoProcessWorkflow, response_status, run


class WorkflowHTTPTests(unittest.TestCase):
    def setUp(self):
        self.pilot = TwoProcessWorkflow()
        self.pilot.__enter__()
        self.addCleanup(self.pilot.__exit__, None, None, None)

    def denied(self, method, path, body=None, token=None, *, origin=None):
        pilot = self.pilot
        return response_status(pilot.receiver_url, method, path, body,
                               pilot.receiver_token if token is None else token, origin=origin)

    def completed(self, name='completed'):
        pilot = self.pilot
        task = pilot.create_task(name)
        run_id = pilot.prepare(task['id'])['run_id']
        digest = pilot.approve(run_id)
        outcome = pilot.workflow(run_id, 'run', {'review_digest': digest})
        self.assertEqual(outcome['state'], 'completed')
        return task, run_id, pilot.workflow(run_id, 'result')

    def test_workflow_routes_require_recipient_session_and_same_origin(self):
        pilot = self.pilot
        item_id = '0' * 64
        routes = [('POST', '/api/items/' + item_id + '/workflow', {}),
                  ('GET', '/api/workflows/work-' + item_id, None),
                  ('GET', '/api/workflows/work-' + item_id + '/result', None),
                  ('POST', '/api/workflows/work-' + item_id + '/cancel', {})]
        for method, path, body in routes:
            with self.subTest(path=path, auth='absent'):
                self.assertEqual(response_status(pilot.receiver_url, method, path, body), 401)
            with self.subTest(path=path, auth='other owner'):
                self.assertEqual(self.denied(method, path, body, pilot.sender_token), 401)
            with self.subTest(path=path, origin='foreign'):
                self.assertEqual(self.denied(method, path, body, origin='https://untrusted.invalid'), 400)
        self.assertEqual(pilot.state(True)['workflow']['runs'], [])

    def test_restart_binding_does_not_allow_a_second_active_pilot_listener(self):
        pilot = self.pilot
        other = pilot.root / 'other-owner'
        provision(other, 'fictional-other-owner', 'other-assistant')
        result = subprocess.run([sys.executable, '-B', '-m', 'pilot.server', 'serve',
            '--directory', str(other), '--port', str(urlsplit(pilot.receiver_url).port),
            '--synthetic-workflow'], cwd=Path(__file__).resolve().parents[2],
            env={'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8'},
            stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'Address already in use', result.stderr)
        self.assertEqual(pilot.state(True)['identity']['owner_id'], 'fictional-worker')

    def test_prepare_requires_accepted_task_and_exact_signed_source_grant(self):
        pilot = self.pilot
        pending = pilot.create_task('unaccepted', decision=None)
        pilot.settle()
        path = '/api/items/' + pending['id'] + '/workflow'
        self.assertEqual(self.denied('POST', path, {}), 400)
        pilot.item_action(pending['id'], 'decision', True, 'reject')
        self.assertEqual(self.denied('POST', path, {}), 400)
        no_grant = pilot.create_task('ungranted', grant=False)
        self.assertEqual(self.denied('POST', '/api/items/' + no_grant['id'] + '/workflow', {}), 400)
        self.assertEqual(pilot.state(True)['workflow']['runs'], [])

    def test_caller_cannot_supply_model_run_alias_or_content_to_prepare(self):
        pilot = self.pilot
        task = pilot.create_task('exact-binding')
        path = '/api/items/' + task['id'] + '/workflow'
        for body in ({'model': 'other-model'}, {'run_id': 'alias'}, {'text': 'replacement'},
                     {'recipient': pilot.sender_pin}, {'allow_live': True}):
            with self.subTest(fields=tuple(body)):
                self.assertEqual(self.denied('POST', path, body), 400)
        run_id = pilot.prepare(task['id'])['run_id']
        self.assertEqual(run_id, 'work-' + task['id'])
        self.assertEqual(pilot.prepare(task['id'])['run_id'], run_id)
        self.assertEqual(len(pilot.state(True)['workflow']['runs']), 1)

    def test_provider_approval_result_review_and_release_are_separate(self):
        pilot = self.pilot
        task = pilot.create_task('separate-authorities')
        run_id = pilot.prepare(task['id'])['run_id']
        base = '/api/workflows/' + run_id
        provider_review = pilot.workflow(run_id, 'review')
        exact = {'review_digest': provider_review['review_digest']}
        self.assertEqual(self.denied('POST', base + '/run', exact), 400)
        self.assertEqual(self.denied('POST', base + '/approve',
            {'review_digest': '0' * 64, 'expires': time.time() + 300}), 400)
        self.assertEqual(pilot.workflow(run_id)['state'], 'prepared')
        pilot.approve(run_id)
        self.assertEqual(self.denied('POST', base + '/run', {'review_digest': '0' * 64}), 400)
        completed = pilot.workflow(run_id, 'run', exact)
        self.assertEqual(completed['state'], 'completed')
        self.assertFalse(completed['retry_allowed'])
        self.assertEqual(self.denied('POST', base + '/run', exact), 400)
        reviewed = pilot.workflow(run_id, 'result')
        self.assertIn('SYNTHETIC', reviewed['content'])
        self.assertFalse(reviewed['authorises_publication'])
        self.assertEqual(self.denied('POST', base + '/stage', {'review_digest': provider_review['review_digest']}), 400)
        self.assertEqual(self.denied('POST', base + '/stage',
            {'review_digest': reviewed['review_digest'], 'text': 'substituted content'}), 400)
        staged = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})
        artifact_id = staged['artifact_id']
        self.assertEqual(pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})['artifact_id'], artifact_id)
        worker = {item['id']: item for item in pilot.state(True)['items']}
        self.assertEqual(worker[artifact_id]['state'], 'draft')
        self.assertEqual(worker[artifact_id]['artifact_digest'], completed['result_digest'])
        self.assertEqual(worker[artifact_id]['parent_id'], task['id'])
        self.assertNotIn(artifact_id, {item['id'] for item in pilot.state()['items']})

    def test_source_withdrawal_blocks_result_preview_and_staging(self):
        pilot = self.pilot
        task, run_id, reviewed = self.completed('source-withdrawal')
        pilot.item_action(task['id'], 'cancel')
        pilot.settle()
        self.assertEqual(self.denied('GET', '/api/workflows/' + run_id + '/result'), 400)
        self.assertEqual(self.denied('POST', '/api/workflows/' + run_id + '/stage',
            {'review_digest': reviewed['review_digest']}), 400)
        status = pilot.workflow(run_id)
        self.assertEqual(status['state'], 'completed')
        self.assertIsNone(status['artifact_id'])
        self.assertFalse(status['retry_allowed'])

    def test_cancel_stops_staged_draft_before_artifact_release(self):
        pilot = self.pilot
        _, run_id, reviewed = self.completed('cancel-staged')
        artifact_id = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})['artifact_id']
        cancelled = pilot.workflow(run_id, 'cancel', {})
        self.assertTrue(cancelled['cancel_requested'])
        self.assertFalse(cancelled['remote_cancel_confirmed'])
        item = next(item for item in pilot.state(True)['items'] if item['id'] == artifact_id)
        self.assertEqual(item['state'], 'cancelled')
        self.assertEqual(self.denied('POST', '/api/items/' + artifact_id + '/release',
            {'review_digest': pilot.item_review(artifact_id, True)['review_digest']}), 400)
        self.assertEqual(self.denied('GET', '/api/workflows/' + run_id + '/result'), 400)

    def test_observed_source_withdrawal_blocks_already_staged_artifact_release(self):
        pilot = self.pilot
        task, run_id, reviewed = self.completed('withdraw-before-release')
        artifact_id = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})['artifact_id']
        artifact_review = pilot.item_review(artifact_id, True)
        pilot.item_action(task['id'], 'cancel')
        pilot.settle()
        self.assertEqual(self.denied('POST', '/api/items/' + artifact_id + '/release',
            {'review_digest': artifact_review['review_digest']}), 400)
        self.assertNotIn(artifact_id, {item['id'] for item in pilot.state()['items']})
        worker_item = next(item for item in pilot.state(True)['items'] if item['id'] == artifact_id)
        self.assertIsNone(worker_item['message_id'])

    def test_requester_rejection_cannot_mint_replacement_result_or_return(self):
        pilot = self.pilot
        task, run_id, reviewed = self.completed('reject-returned-result')
        artifact_id = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})['artifact_id']
        pilot.item_action(artifact_id, 'release', True)
        pilot.settle()
        pilot.item_action(artifact_id, 'decision', decision='reject')
        pilot.settle()
        retained = pilot.workflow(run_id)
        self.assertEqual(retained['artifact_state'], 'rejected')
        self.assertEqual(pilot.prepare(task['id'])['run_id'], run_id)
        self.assertEqual(pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})['artifact_id'], artifact_id)
        self.assertEqual(pilot.workflow(run_id)['artifact_state'], 'rejected')
        self.assertEqual(self.denied('POST', '/api/workflows/' + run_id + '/run',
            {'review_digest': retained['review_digest']}), 400)
        self.assertEqual(len(pilot.state(True)['items']), 2)


class WorkflowHTTPDisabledAndRecoveryTests(unittest.TestCase):
    def test_host_flag_is_required_even_with_source_grant_and_acceptance(self):
        with TwoProcessWorkflow(enabled=False) as pilot:
            task = pilot.create_task('host-disabled')
            workflow = pilot.state(True)['workflow']
            self.assertFalse(workflow['enabled'])
            self.assertFalse(workflow['live_enabled'])
            self.assertEqual(response_status(pilot.receiver_url, 'POST',
                '/api/items/' + task['id'] + '/workflow', {}, pilot.receiver_token), 400)
            self.assertEqual(pilot.state(True)['workflow']['runs'], [])

    def test_two_process_demo_recovers_original_result_and_offline_delivery(self):
        evidence = run()
        self.assertTrue(evidence['separate_processes'])
        self.assertTrue(evidence['separate_private_stores'])
        self.assertEqual(evidence['fixture_dispatches'], 1)
        self.assertEqual(evidence['live_provider_calls'], 0)
        self.assertEqual(evidence['duplicate_stage'], 'original artifact identity retained')
        self.assertEqual(evidence['offline_delivery'], 'retained then delivered on original pinned endpoint')
        self.assertFalse(evidence['real_people_enrolled'])


if __name__ == '__main__':
    unittest.main()
