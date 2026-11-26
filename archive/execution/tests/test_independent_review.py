"""Independent regressions for the local-only execution boundary."""
import threading
import unittest

from execution.ledger import ExecutionLedger
from execution.bootstrap import Denied, TeamWorkflow
import test_ledger as fixture


class IndependentReviewTests(unittest.TestCase):
    setUp = fixture.LedgerTests.setUp
    tearDown = fixture.LedgerTests.tearDown
    open = fixture.LedgerTests.open
    reopen = fixture.LedgerTests.reopen
    start = fixture.LedgerTests.start
    prepare = fixture.LedgerTests.prepare
    claim = fixture.LedgerTests.claim
    result = fixture.LedgerTests.result
    revoke = fixture.LedgerTests.revoke

    def test_cancel_between_publish_check_and_submit(self):
        self.result()
        original = self.w._submit
        def cancel_then_submit(*args, **kwargs):
            # Separate connection models an owner action after the ledger check.
            other = TeamWorkflow(self.path, fixture.plan(), clock=lambda: 1000)
            try:
                other.revoke_task('bob', 'research', expected_context=other.context)
            finally:
                other.close()
            return original(*args, **kwargs)
        self.w._submit = cancel_then_submit
        with self.assertRaises(Denied):
            self.worker.publish('run-research')
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 0)
        self.assertEqual(self.worker.status('run-research')['state'], 'result_recorded')

    def test_bookkeeping_failure_after_submit_recovers_after_revocation(self):
        self.result()
        original = self.w._event
        def fail(event, **data):
            if event == 'execution_artifact_recorded':
                raise RuntimeError('simulated crash before bookkeeping commit')
            return original(event, **data)
        self.w._event = fail
        with self.assertRaises(RuntimeError):
            self.worker.publish('run-research')
        self.assertEqual(self.worker.status('run-research')['state'], 'result_recorded')
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 1)
        self.reopen()
        self.revoke()
        status = self.worker.publish('run-research')
        self.assertEqual((status['state'], status['task_state']), ('published', 'revoked'))
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 1)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='execution_artifact_recorded'").fetchone()[0], 1)

    def test_simultaneous_publish_is_one_artifact_and_one_receipt(self):
        self.result()
        barrier = threading.Barrier(2)
        outcomes = []
        def publish():
            other = TeamWorkflow(self.path, fixture.plan(), clock=lambda: 1000)
            try:
                worker = ExecutionLedger(other).facade('researcher')
                barrier.wait(timeout=5)
                outcomes.append(worker.publish('run-research')['state'])
            except BaseException as exc:
                outcomes.append(exc)
            finally:
                other.close()
        threads = [threading.Thread(target=publish) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(outcomes, ['published', 'published'])
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0], 1)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='execution_artifact_recorded'").fetchone()[0], 1)

    def test_conflicting_concurrent_result_cannot_replace_winner(self):
        claim = self.claim()
        barrier = threading.Barrier(2)
        outcomes = []
        def record(content):
            other = TeamWorkflow(self.path, fixture.plan(), clock=lambda: 1000)
            try:
                worker = ExecutionLedger(other).facade('researcher')
                barrier.wait(timeout=5)
                try:
                    worker.record_result('run-research', claim.digest, content)
                    outcomes.append(('recorded', content))
                except Denied:
                    outcomes.append(('denied', content))
            finally:
                other.close()
        threads = [threading.Thread(target=record, args=(content,)) for content in ('first', 'second')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual([state for state, _ in outcomes], ['recorded', 'denied'])
        winner = next(content for state, content in outcomes if state == 'recorded')
        self.worker.publish('run-research')
        self.assertEqual(self.w.facade('researcher').read_artifact('output-research')['artifact']['content'], winner)
