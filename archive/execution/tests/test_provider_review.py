"""Independent adversarial tests of the synthetic provider-disclosure gate.

Owner controls are trusted harness calls, not authentication. No provider I/O.
"""
import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import unittest

from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied, digest
from execution.ledger import ExecutionLedger
from execution.provider_gate import ProviderGate, ProviderRoute


def review_plan():
    return TeamPlan('provider-independent', 'lead', (
        AgentRef('lead', 'alice', 'synthetic-a', 'coordination'),
        AgentRef('source', 'bob', 'synthetic-b', 'research'),
        AgentRef('other', 'dave', 'synthetic-d', 'research'),
        AgentRef('target', 'carol', 'synthetic-c', 'copy'),
        AgentRef('sibling', 'carol', 'synthetic-c', 'copy'),
    ), (
        TaskSpec('source-task', 'source', 'SOURCE OBJECTIVE', 'research'),
        TaskSpec('other-task', 'other', 'OTHER OBJECTIVE', 'research'),
        TaskSpec('target-task', 'target', 'CAROL PRIVATE TASK TEXT', 'copy',
                 ('source-task', 'other-task')),
    ))


class ProviderIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'provider.sqlite'
        self.now = 1000
        self.open()
        self.w.accept_lead('alice', expected_context=self.w.context)
        for actor, owner, content in (('source', 'bob', 'BOB PRIVATE INPUT'),
                                      ('other', 'dave', 'DAVE PRIVATE INPUT')):
            task, artifact = actor + '-task', actor + '-output'
            self.start(task)
            self.w.facade(actor).submit(task, artifact, content)
            self.disclose(owner, artifact, 'lead')
            self.w.facade('lead').review_output(task, artifact, 'accept')
            self.disclose(owner, artifact, 'target', 'target-task')
        self.start('target-task')
        self.ledger.facade('target').prepare('target-task', 'run', 'target-output')
        self.route = ProviderRoute('synthetic-c', 'account-one', 'model-one', 'No retention, synthetic fixture')
        self.worker.propose('run', self.route)

    def open(self):
        self.w = TeamWorkflow(self.path, review_plan(), clock=lambda: self.now)
        self.ledger = ExecutionLedger(self.w)
        self.gate = ProviderGate(self.ledger)
        self.worker = self.gate.facade('target')

    def reopen(self):
        self.w.close()
        self.open()

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def start(self, task):
        actor = self.w.tasks[task].assignee
        request = self.w.facade(actor).propose_start(task, 'proposal-' + task)
        self.w.decide_start(self.w.agents[actor].owner, request['request_id'], request['review_digest'],
                            'approve', expected_context=self.w.context, expires=1100)
        self.w.facade(actor).start(request['request_id'])

    def disclose(self, owner, artifact, recipient, task=None):
        review = self.w.disclosure_review(owner, artifact, recipient, task, expected_context=self.w.context)
        self.w.approve_disclosure(owner, artifact, recipient, review['review_digest'], task,
                                  expected_context=self.w.context)

    def review(self, owner):
        return self.gate.owner_review(owner, 'run', expected_context=self.w.context)

    def decide(self, owner, decision='approve', expires=1100):
        return self.gate.decide(owner, 'run', self.review(owner)['review_digest'], decision,
                                expected_context=self.w.context,
                                expires=expires if decision == 'approve' else None)

    def approve_all(self):
        for owner in ('bob', 'carol', 'dave'):
            self.decide(owner)

    def reads(self):
        return [r[0] for r in self.w.db.execute(
            "SELECT reads FROM disclosures WHERE recipient='target' ORDER BY artifact_id")]

    def test_three_owners_preview_only_their_exact_data(self):
        expected = {'bob': 'BOB PRIVATE INPUT', 'dave': 'DAVE PRIVATE INPUT',
                    'carol': 'CAROL PRIVATE TASK TEXT'}
        commitments = set()
        for owner, secret in expected.items():
            review = self.review(owner)
            encoded = json.dumps(review)
            self.assertIn(secret, encoded)
            for other, text in expected.items():
                if other != owner:
                    self.assertNotIn(text, encoded)
            commitments.add(review['review']['request_digest'])
            self.assertEqual(review['review_digest'], digest(review['review']))
            self.assertEqual(review['review']['common_metadata']['recipient'], self.route.to_dict())
            self.assertFalse(review['review']['human_authentication'])
            self.assertFalse(review['review']['live_provider_permission'])
        self.assertEqual(len(commitments), 1)
        self.assertEqual(self.reads(), [0, 0])
        for owner in ('alice', 'nobody'):
            with self.assertRaises(Denied):
                self.review(owner)

    def test_task_and_each_input_owner_are_independently_required(self):
        for owner in ('carol', 'bob'):
            self.decide(owner)
            with self.assertRaises(Denied):
                self.worker.release('run')
            self.assertEqual(self.worker.status('run')['execution']['state'], 'prepared')
            self.assertEqual(self.reads(), [0, 0])
        self.decide('dave')
        release = self.worker.release('run')
        self.assertEqual(release.digest, digest(release.to_dict()))
        payload = release.to_dict()['payload']
        self.assertEqual(payload['task_text'], 'CAROL PRIVATE TASK TEXT')
        self.assertEqual({i['content'] for i in payload['inputs']}, {'BOB PRIVATE INPUT', 'DAVE PRIVATE INPUT'})
        self.assertEqual(payload['tool_permissions'], [])
        self.assertEqual(payload['spend_limit'], 0)
        self.assertFalse(payload['external_actions_allowed'])
        self.assertEqual(self.reads(), [1, 1])
        self.assertEqual(self.worker.status('run')['execution']['state'], 'uncertain')

    def test_owner_digest_context_and_facade_cannot_be_substituted(self):
        with self.assertRaises(Denied):
            self.gate.decide('bob', 'run', self.review('carol')['review_digest'], 'approve',
                             expected_context=self.w.context, expires=1100)
        with self.assertRaises(Denied):
            self.gate.owner_review('bob', 'run', expected_context='wrong')
        for actor in ('lead', 'sibling', 'source'):
            bound = self.gate.facade(actor)
            for operation in (lambda: bound.status('run'), lambda: bound.release('run'),
                              lambda: bound.propose('run', self.route),
                              lambda: bound.record_result('run', 'wrong', 'result')):
                with self.assertRaises(Denied):
                    operation()
        self.assertTrue(all(d['state'] == 'pending' for d in self.worker.status('run')['decisions']))

    def test_every_route_field_is_immutable_even_before_release(self):
        for key, replacement in (('provider', 'different'), ('account_ref', 'account-two'),
                                 ('model_ref', 'model-two'), ('data_policy', 'Keep forever')):
            with self.subTest(key=key), self.assertRaises(Denied):
                self.worker.propose('run', dataclasses.replace(self.route, **{key: replacement}))
        self.assertEqual(self.worker.propose('run', self.route)['state'], 'pending')

    def test_refusal_and_preapproval_revocation_are_terminal(self):
        self.decide('bob', 'refuse')
        self.gate.revoke('dave', 'run', expected_context=self.w.context)
        self.decide('carol')
        for owner in ('bob', 'dave'):
            with self.assertRaises(Denied):
                self.decide(owner)
        with self.assertRaises(Denied):
            self.worker.release('run')
        self.reopen()
        with self.assertRaises(Denied):
            self.worker.release('run')
        self.assertEqual(self.reads(), [0, 0])

    def test_expiry_is_inclusive_and_cannot_be_renewed(self):
        self.approve_all()
        self.now = 1100
        self.assertEqual({d['state'] for d in self.worker.status('run')['decisions']}, {'expired'})
        with self.assertRaises(Denied):
            self.worker.release('run')
        with self.assertRaises(Denied):
            self.decide('bob', expires=1200)
        self.assertEqual(self.reads(), [0, 0])

    def test_invalid_expiries_leave_permission_pending(self):
        for expires in (None, True, float('nan'), float('inf'), 999, 1000, 4601, '1100'):
            with self.subTest(expires=expires), self.assertRaises(Denied):
                self.decide('bob', expires=expires)
            self.assertEqual(self.review('bob')['state'], 'pending')

    def test_release_rechecks_original_team_disclosure(self):
        self.approve_all()
        self.w.revoke_disclosure('bob', 'source-output', 'target', 'target-task',
                                  expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.release('run')
        self.assertEqual(self.reads(), [0, 0])
        self.assertEqual(self.worker.status('run')['execution']['state'], 'prepared')

    def test_release_rechecks_task_owner_and_lead_withdrawal(self):
        self.approve_all()
        self.w.revoke_task('carol', 'target-task', expected_context=self.w.context)
        self.w.withdraw_lead('alice', expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.release('run')
        self.assertEqual(self.reads(), [0, 0])

    def test_failure_at_either_commit_event_rolls_back_both_fences_and_reads(self):
        self.approve_all()
        original = self.w._event
        for failing_event in ('execution_claimed', 'provider_payload_released_locally'):
            def fail(event, **data):
                if event == failing_event:
                    raise RuntimeError('Synthetic audit failure')
                return original(event, **data)
            self.w._event = fail
            try:
                with self.assertRaises(RuntimeError):
                    self.worker.release('run')
            finally:
                self.w._event = original
            status = self.worker.status('run')
            self.assertEqual((status['state'], status['execution']['state']), ('pending', 'prepared'))
            self.assertIsNone(status['release_digest'])
            self.assertIsNone(status['execution']['claim_digest'])
            self.assertEqual(self.reads(), [0, 0])
        self.worker.release('run')
        self.assertEqual(self.reads(), [1, 1])

    def test_lost_release_restart_revocation_and_late_original_receipt(self):
        self.approve_all()
        release = self.worker.release('run')
        self.reopen()
        self.gate.revoke('bob', 'run', expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.release('run')
        with self.assertRaises(Denied):
            self.worker.record_result('run', release.to_dict()['claim_digest'], 'wrong receipt')
        status = self.worker.record_result('run', release.digest, 'ORIGINAL RESULT')
        self.assertEqual(status['state'], 'result_recorded')
        self.assertEqual(self.worker.record_result('run', release.digest, 'ORIGINAL RESULT'), status)
        with self.assertRaises(Denied):
            self.worker.record_result('run', release.digest, 'REPLACEMENT')
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts WHERE id='target-output'").fetchone()[0], 0)
        self.assertEqual(self.reads(), [1, 1])

    def test_audit_and_status_omit_content_and_route_policy(self):
        self.approve_all()
        release = self.worker.release('run')
        self.worker.record_result('run', release.digest, 'PRIVATE RESULT')
        encoded = json.dumps(self.worker.status('run')) + json.dumps(
            [dict(r) for r in self.w.db.execute("SELECT * FROM audit WHERE event LIKE 'provider_%'")])
        for secret in ('BOB PRIVATE INPUT', 'DAVE PRIVATE INPUT', 'CAROL PRIVATE TASK TEXT',
                       'PRIVATE RESULT', self.route.data_policy):
            self.assertNotIn(secret, encoded)

    def test_two_connections_can_release_only_once(self):
        self.approve_all()
        barrier = threading.Barrier(2)
        outcomes = []
        def compete():
            other = TeamWorkflow(self.path, review_plan(), clock=lambda: 1000)
            try:
                worker = ProviderGate(ExecutionLedger(other)).facade('target')
                barrier.wait(timeout=5)
                try:
                    worker.release('run')
                    outcomes.append('released')
                except Denied:
                    outcomes.append('denied')
            except BaseException as exc:
                outcomes.append(exc)
            finally:
                other.close()
        threads = [threading.Thread(target=compete) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertCountEqual(outcomes, ['released', 'denied'])
        self.assertEqual(self.reads(), [1, 1])
        for event in ('execution_claimed', 'provider_payload_released_locally'):
            self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM audit WHERE event=?', (event,)).fetchone()[0], 1)

    def test_release_competing_with_owner_revocation_is_serialized(self):
        self.approve_all()
        barrier = threading.Barrier(2)
        outcomes = []
        def compete(revoking):
            other = TeamWorkflow(self.path, review_plan(), clock=lambda: 1000)
            try:
                gate = ProviderGate(ExecutionLedger(other))
                barrier.wait(timeout=5)
                if revoking:
                    gate.revoke('bob', 'run', expected_context=other.context)
                    outcomes.append('revoked')
                else:
                    try:
                        gate.facade('target').release('run')
                        outcomes.append('released')
                    except Denied:
                        outcomes.append('denied')
            except BaseException as exc:
                outcomes.append(exc)
            finally:
                other.close()
        threads = [threading.Thread(target=compete, args=(revoking,)) for revoking in (False, True)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertIn('revoked', outcomes)
        self.assertEqual(len(outcomes), 2)
        self.assertTrue('released' in outcomes or 'denied' in outcomes, outcomes)
        self.assertEqual(self.review('bob')['state'], 'revoked')
        with self.assertRaises(Denied):
            self.worker.release('run')
        status = self.worker.status('run')
        if 'released' in outcomes:
            self.assertEqual((status['state'], status['execution']['state']), ('released', 'uncertain'))
            self.assertEqual(self.reads(), [1, 1])
        else:
            self.assertEqual((status['state'], status['execution']['state']), ('pending', 'prepared'))
            self.assertEqual(self.reads(), [0, 0])
