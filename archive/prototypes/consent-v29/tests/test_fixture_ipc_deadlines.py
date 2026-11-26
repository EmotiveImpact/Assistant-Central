"""Linux pipe failure and deadline regressions, using owned dummy children."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import fixture_ipc
from fixture_ipc import JsonProcess
from ipc_test_support import child, output


class FixtureDeadlines(unittest.TestCase):
    def own(self, process):
        self.addCleanup(process.close)
        return process

    def failed(self, process, operation=None):
        started = time.monotonic()
        with patch('fixture_ipc._RESPONSE_TIMEOUT', .15):
            with self.assertRaisesRegex(RuntimeError, 'outcome may be unknown') as error:
                (operation or process.read)()
        self.assertLess(time.monotonic()-started, 2)
        self.assertIsNone(error.exception.__cause__)
        self.assertNotIn('SECRET', str(error.exception))
        self.assertIsNotNone(process.process.poll())
        for stream in (process.process.stdin, process.process.stdout, process.process.stderr):
            self.assertTrue(stream.closed)
        process.close(); process.close()

    def test_partial_frames_do_not_defeat_deadline(self):
        for frame in (b'{', b'{}', b'"\xf0\x90', b'"SECRET'):
            with self.subTest(frame=frame):
                p=self.own(child('import os,time; os.write(1,'+repr(frame)+'); time.sleep(60)'))
                self.failed(p)

    def test_invalid_utf8_json_and_nonfinite(self):
        for frame in (b'"\xff"\n', b'"\xf0\x90\n', b'NaN\n', b'Infinity\n', b'1e9999\n', b'{"x":1,"x":2}\n', b'{SECRET\n', b'\n'):
            self.failed(self.own(output(frame)))

    def test_frame_bound_counts_utf8_bytes(self):
        for limit in (16384,65536):
            valid='"'+'é'*((limit-4)//2)+'"\n'
            p=self.own(output(valid,limit))
            self.assertEqual(p.read(),json.loads(valid))
            self.failed(self.own(output(valid[:-2]+'éé"\n',limit)))

    def test_blocked_write_and_partial_write_timeout(self):
        import fcntl
        p=self.own(child('import time; time.sleep(60)'))
        fcntl.fcntl(p.process.stdin, fcntl.F_SETPIPE_SZ, 4096)
        self.failed(p,lambda:p.request('x'*16000))

    def test_short_writes_and_eagain(self):
        p=self.own(child('import sys; line=sys.stdin.buffer.readline(); sys.stdout.buffer.write(line); sys.stdout.buffer.flush()'))
        original=os.write
        calls=[]
        def short(fd, value):
            calls.append(len(value))
            if len(calls)%3==1:raise BlockingIOError()
            return original(fd,value[:7])
        with patch('fixture_ipc.os.write',side_effect=short):
            self.assertEqual(p.request({'value':'é'*80}),{'value':'é'*80})
        self.assertGreater(len(calls),5)

    def test_stderr_flood_can_finish_or_timeout_without_retention(self):
        p=self.own(child('import os; [os.write(2,b"SECRET"*600) for _ in range(200)]; os.write(1,b"{}\\n")'))
        self.assertEqual(p.read(),{})
        p=self.own(child('import os\nwhile True: os.write(2,b"SECRET"*600)'))
        self.failed(p)
        self.assertEqual(p._pending,b'')

    def test_timeout_does_not_imply_no_side_effect_or_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=os.path.join(directory,'committed')
            p=self.own(child('import sys,time,pathlib; sys.stdin.buffer.readline(); pathlib.Path('+repr(path)+').write_text("done"); time.sleep(60)'))
            self.failed(p,lambda:p.request({'commit':True}))
            self.assertEqual(Path(path).read_text(),'done')
            with self.assertRaisesRegex(RuntimeError,'outcome may be unknown'):
                p.request({'commit':True})

    def test_broken_streams_and_exit(self):
        for code in ('pass', 'import os,time; os.close(0); os.close(1); time.sleep(60)'):
            p=self.own(child(code));self.failed(p,lambda:p.request({}))
        p=self.own(child('import time; time.sleep(60)'))
        p.process.stdin.close()
        self.failed(p,lambda:p.request({}))

    def test_fragmented_utf8_and_buffered_frames(self):
        p=self.own(child('import os,time; os.write(1,b\'"\\xf0\\x90\'); time.sleep(.03); os.write(1,b\'\\x80\\x80"\\n{}\\n\')'))
        self.assertEqual(p.read(),'𐀀');self.assertEqual(p.read(),{})

    def test_close_kills_hung_child_and_reaps_already_exited_child(self):
        for code in ('import time; time.sleep(60)','pass'):
            p=self.own(child(code));p.close();p.close()
            self.assertIsNotNone(p.process.returncode)
            with self.assertRaises(ChildProcessError):os.waitpid(p.process.pid,os.WNOHANG)

    def test_write_and_read_share_one_deadline(self):
        p=self.own(child('import sys,time; sys.stdin.buffer.readline(); time.sleep(.20); print("{}",flush=True)'))
        original=os.write
        def slow_write(fd,value):
            time.sleep(.18)
            return original(fd,value)
        started=time.monotonic()
        with patch('fixture_ipc._RESPONSE_TIMEOUT',.30),patch('fixture_ipc.os.write',side_effect=slow_write):
            with self.assertRaisesRegex(RuntimeError,'outcome may be unknown'):
                p.request({})
        self.assertLess(time.monotonic()-started,.65)
        self.assertIsNotNone(p.process.poll())

    def test_external_kill_and_repeated_cleanup_leave_no_fds_or_threads(self):
        import threading
        before_fds=len(os.listdir('/proc/self/fd'))
        before_threads=threading.active_count()
        for _ in range(12):
            p=child('import time; time.sleep(60)')
            p.process.kill()
            self.failed(p)
        self.assertEqual(len(os.listdir('/proc/self/fd')),before_fds)
        self.assertEqual(threading.active_count(),before_threads)

    def test_exact_launch_surface_and_limits(self):
        real=fixture_ipc.subprocess.Popen
        launches=[]
        def launch(argv,**kwargs):
            launches.append((argv,kwargs))
            return real([fixture_ipc.sys.executable,'-c','pass'],**kwargs)
        with patch('fixture_ipc.subprocess.Popen',side_effect=launch):
            p=self.own(JsonProcess('owner_fixture_process.py','--owner','bob'))
        argv,kwargs=launches[0]
        self.assertEqual(argv,[fixture_ipc.sys.executable,str(fixture_ipc.ROOT/'owner_fixture_process.py'),'--fixture','--owner','bob'])
        self.assertEqual(kwargs['env'],{'PATH':os.environ.get('PATH',''),'PYTHONPATH':os.environ.get('PYTHONPATH',''),'PYTHONIOENCODING':'utf-8'})
        self.assertTrue(kwargs['close_fds'])
        with patch('fixture_ipc.subprocess.Popen') as launch:
            for name in ('x.py','../owner_fixture_process.py'):
                with self.assertRaises(ValueError):JsonProcess(name)
            launch.assert_not_called()

if __name__=='__main__':unittest.main()
