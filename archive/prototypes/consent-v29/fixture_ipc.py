"""Trusted Linux fixture IPC, not an agent execution surface or OS sandbox.

Calls are sequential (one owner per instance). Deadlines cover pipe writes and
reads, not OS process creation or caller-side JSON serialization. No retries.
"""
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
_RESPONSE_TIMEOUT = 10.0
_CLEANUP_TIMEOUT = 5.0
_FAILURE = ('Fixture subprocess communication failed; command outcome may be '
            'unknown. Do not automatically resend.')


def _reject_constant(value):
    raise ValueError('Non-finite JSON value')


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite JSON value')
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class JsonProcess:
    def __init__(self, script, *args, max_response_bytes=16384):
        if type(max_response_bytes) is not int or max_response_bytes not in (16384, 65536):
            raise ValueError('Unknown fixture response bound')
        if script not in ('owner_fixture_process.py', 'executor_fixture_process.py', 'encrypted_executor_process.py', 'continuity_fixture_process.py'):
            raise ValueError('Unknown fixture subprocess')
        self.max_response_bytes = max_response_bytes
        self._pending = bytearray()
        self._closed = False
        env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
               'PYTHONIOENCODING': 'utf-8'}
        self.process = subprocess.Popen([sys.executable, str(ROOT / script), '--fixture', *args],
                                        cwd=ROOT, env=env, close_fds=True, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        try:
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
        except Exception:
            self.close()
            raise RuntimeError(_FAILURE) from None

    def _exchange(self, payload, deadline):
        if self._closed:
            raise RuntimeError(_FAILURE)
        offset = 0
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(self.process.stderr, selectors.EVENT_READ, 'stderr')
            if payload:
                selector.register(self.process.stdin, selectors.EVENT_WRITE, 'stdin')
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                newline = self._pending.find(b'\n')
                if newline >= 0:
                    if newline + 1 > self.max_response_bytes:
                        raise ValueError()
                    if offset == len(payload):
                        frame = bytes(self._pending[:newline + 1])
                        del self._pending[:newline + 1]
                        result = json.loads(frame.decode('utf-8', errors='strict'),
                                            parse_constant=_reject_constant,
                                            parse_float=_finite_float,
                                            object_pairs_hook=_unique_object)
                        if time.monotonic() >= deadline:
                            raise TimeoutError()
                        return result
                elif len(self._pending) >= self.max_response_bytes:
                    raise ValueError()
                events = selector.select(remaining)
                for key, _ in events:
                    if time.monotonic() >= deadline:
                        raise TimeoutError()
                    try:
                        if key.data == 'stdin':
                            written = os.write(key.fd, payload[offset:])
                            if written <= 0:
                                raise BrokenPipeError()
                            offset += written
                            if offset == len(payload):
                                selector.unregister(key.fileobj)
                        elif key.data == 'stderr':
                            # Discard one bounded chunk per turn. Never collect diagnostics
                            # (which may contain keys), or let a flood starve the deadline.
                            if not os.read(key.fd, 4096):
                                selector.unregister(key.fileobj)
                        else:
                            chunk = os.read(key.fd, min(4096, self.max_response_bytes + 1 - len(self._pending)))
                            if not chunk:
                                raise EOFError()
                            self._pending.extend(chunk)
                    except BlockingIOError:
                        continue

    def _run(self, payload):
        deadline = time.monotonic() + _RESPONSE_TIMEOUT
        try:
            return self._exchange(payload, deadline)
        except Exception:
            self.close()
            # Fixed, conservative error for even partially submitted requests.
            # Suppress decoder/OS diagnostics and their potentially secret contents.
            raise RuntimeError(_FAILURE) from None

    def read(self):
        """Read one startup/unsolicited frame within a single absolute deadline."""
        return self._run(b'')

    def request(self, value):
        # Preflight errors do not submit anything or invalidate the child.
        line = (json.dumps(value, allow_nan=False) + '\n').encode('utf-8')
        if len(line) > 16384:
            raise ValueError('Fixture request exceeds frame limit')
        return self._run(line)

    def close(self):
        """Close pipes and kill/reap this owned child; safe to call repeatedly.

        Does not promise process-tree containment. Fixture scripts are trusted,
        and no descendant execution surface is added here.
        """
        self._closed = True
        self._pending.clear()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if self.process.poll() is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
        try:
            self.process.wait(timeout=_CLEANUP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            # Preserve a fixed uncertainty-bearing error if the OS cannot reap.
            raise RuntimeError(_FAILURE) from None
