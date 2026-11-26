"""Independent Linux real-pipe regressions for bounded fixture transport."""
import fcntl
import os
import time
import unittest
from unittest.mock import patch

from ipc_test_support import child, output


class IndependentFixtureIPCReview(unittest.TestCase):
    def own(self, process):
        self.addCleanup(process.close)
        return process

    def assert_failed(self, process, operation):
        with self.assertRaisesRegex(RuntimeError, 'outcome may be unknown'):
            operation()
        self.assertIsNotNone(process.process.poll())
        self.assertTrue(all(s.closed for s in
                            (process.process.stdin, process.process.stdout, process.process.stderr)))

    def test_exact_ascii_frame_bounds_include_newline(self):
        for cap in (16384, 65536):
            with self.subTest(cap=cap):
                frame = b'"' + b'x' * (cap - 3) + b'"\n'
                p = self.own(output(frame, cap))
                self.assertEqual(p.read(), 'x' * (cap - 3))
                p = self.own(output(frame[:-2] + b'x"\n', cap))
                self.assert_failed(p, p.read)

    def test_continuous_stdout_progress_cannot_extend_deadline(self):
        p = self.own(child('import os,time\nos.write(1,b\'"\')\nwhile True:\n os.write(1,b"x"); time.sleep(.01)'))
        start = time.monotonic()
        with patch('fixture_ipc._RESPONSE_TIMEOUT', .20):
            self.assert_failed(p, p.read)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_real_pipe_backpressure_and_response_share_deadline(self):
        p = self.own(child('import sys,time; time.sleep(.20); sys.stdin.buffer.readline(); time.sleep(.20); print("{}",flush=True)'))
        fcntl.fcntl(p.process.stdin, fcntl.F_SETPIPE_SZ, 4096)
        start = time.monotonic()
        with patch('fixture_ipc._RESPONSE_TIMEOUT', .32):
            self.assert_failed(p, lambda: p.request('x' * 16000))
        self.assertLess(time.monotonic() - start, 1.5)

    def test_early_response_does_not_skip_blocked_request_write(self):
        p = self.own(child('import os,time; os.write(1,b"{}\\n"); time.sleep(60)'))
        fcntl.fcntl(p.process.stdin, fcntl.F_SETPIPE_SZ, 4096)
        with patch('fixture_ipc._RESPONSE_TIMEOUT', .20):
            self.assert_failed(p, lambda: p.request('x' * 16000))

    def test_preflight_rejections_do_not_submit_or_close_child(self):
        p = self.own(child('import sys\nfor line in sys.stdin.buffer:\n sys.stdout.buffer.write(line); sys.stdout.buffer.flush()'))
        for value in ('x' * 16384, float('nan'), {'unsupported': object()}):
            with self.assertRaises((ValueError, TypeError)):
                p.request(value)
            self.assertIsNone(p.process.poll())
        self.assertEqual(p.request({'only_submitted_request': True}),
                         {'only_submitted_request': True})

    def test_closed_stderr_does_not_disrupt_multiple_requests(self):
        p = self.own(child('import os,sys; os.close(2)\nfor line in sys.stdin.buffer:\n sys.stdout.buffer.write(line); sys.stdout.buffer.flush()'))
        for i in range(30):
            self.assertEqual(p.request({'sequence': i}), {'sequence': i})
        self.assertEqual(p._pending, b'')

    def test_cleanup_reap_timeout_is_reported_and_retryable(self):
        import subprocess
        p = self.own(child('import time; time.sleep(60)'))
        with patch.object(p.process, 'wait', side_effect=subprocess.TimeoutExpired('fixture', 5)):
            with self.assertRaisesRegex(RuntimeError, 'outcome may be unknown'):
                p.close()
        p.close()
        self.assertIsNotNone(p.process.returncode)
        with self.assertRaises(ChildProcessError):
            os.waitpid(p.process.pid, os.WNOHANG)


if __name__ == '__main__':
    unittest.main()
