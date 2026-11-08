"""Run offline mapping tests, blocking network I/O and child processes."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def guard(event, arguments):
    # Asyncio's local wakeup pair is needed by the in-memory byte-stream tests.
    if event == 'socket.__new__' and tuple(arguments[1:]) == (1, 1, 0):
        return
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('Offline integration forbids networking and child processes')


if __name__ == '__main__':
    sys.addaudithook(guard)
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.discover(str(ROOT / 'integration' / 'tests')))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun else 1)
