"""Independent uncertain submission and active capability lifecycle review."""
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from pilot.runtime import RuntimeDenied
from pilot.tests import test_owner_transfer as fixtures


class IndependentTransferReview(unittest.TestCase):
    setUp = fixtures.OwnerTransferTests.setUp
    tearDown = fixtures.OwnerTransferTests.tearDown
    review = fixtures.OwnerTransferTests.review
    send = fixtures.OwnerTransferTests.send

    def test_started_submission_without_returned_future_keeps_busy_fence(self):
        entered, release = threading.Event(), threading.Event()
        jobs = []
        original = self.first.worker.submit
        def slow(*args, **kwargs):
            entered.set()
            release.wait(5)
            return {'transport_acknowledged': True}
        def started_then_error(*args, **kwargs):
            jobs.append(original(*args, **kwargs))
            self.assertTrue(entered.wait(2))
            raise RuntimeError('Fictional interruption after dispatch began')
        try:
            with patch('pilot.https_exchange.send_file', side_effect=slow), \
                    patch.object(self.first.worker, 'submit', side_effect=started_then_error):
                with self.assertRaises(RuntimeError):
                    self.send()
                self.assertTrue(self.first.active())
                self.assertEqual(self.first.snapshot(self.a[1])['dispatch']['state'], 'in_flight')
                with self.assertRaises(RuntimeDenied):
                    self.send(self.review(), retry=True)
                self.assertEqual(self.review()['outbox']['attempts'], 1)
        finally:
            release.set()
            for job in jobs:
                job.result(timeout=3)
        self.assertFalse(self.first.active())
        self.assertEqual(self.review()['outbox']['attempts'], 1)

    def test_close_during_dispatch_does_not_delete_active_staging(self):
        prepared = self.first.exchange._prepare_send(self.a[1], self.message_id,
            'https://mailbox.invalid/v1/quarantine', self.b[2].fingerprint,
            retry=False, ca_file=None, receipt=False)
        entered, release = threading.Event(), threading.Event()
        paths = []
        results = []
        def slow(path, *args, **kwargs):
            paths.append(Path(path))
            entered.set()
            release.wait(5)
            self.assertTrue(Path(path).is_file())
            return {'transport_acknowledged': True}
        with patch('pilot.https_exchange.send_file', side_effect=slow):
            worker = threading.Thread(target=lambda: results.append(prepared.dispatch()))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                prepared.close()
                self.assertTrue(paths[0].is_file())
                with self.assertRaises(RuntimeDenied):
                    prepared.dispatch()
            finally:
                release.set()
                worker.join(timeout=3)
        self.assertEqual(len(results), 1)
        self.assertFalse(paths[0].exists())
