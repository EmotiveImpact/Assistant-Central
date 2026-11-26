"""Trusted synchronous supervisor for closed fixed Python/Node offline scripted clients.

No sockets, background polling, reconnect, callback retry or owner operations.
Only an explicitly requested step services a pre-bound RestrictedHostSession.
Deadlines bound pipe waits, not trusted Python callbacks or OS scheduling.
"""
import json
import os
from pathlib import Path
import select
import shutil
import re
import stat
import subprocess
import sys
import time

from restricted_host_protocol import RestrictedHostSession, MAX_INPUT, MAX_OUTPUT

REPORT_LIMIT = 65536
STEP_LIMIT = 8


class PeerFailure(RuntimeError):
    """A terminated client; earlier mutations/replies may have occurred."""


def node_runtime():
    """Resolve from the trusted operator runtime PATH, never from current directory.

    PATH is a trusted launcher input, not peer configuration. Empty/relative
    entries and the checkpoint directory are excluded. No install or fallback.
    The executable and its parent directories must not be world-writable.
    """
    root = Path(__file__).resolve().parent
    directories = [p for p in os.get_exec_path() if Path(p).is_absolute()
                   and not Path(p).resolve().is_relative_to(root)]
    found = shutil.which('node', path=os.pathsep.join(directories))
    if not found:
        raise PeerFailure('Node 18+ runtime unavailable; no fallback or installation')
    executable = Path(found).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise PeerFailure('Node runtime is not a regular executable')
    if any(p.stat().st_mode & stat.S_IWOTH for p in (executable, *executable.parents)):
        raise PeerFailure('Node runtime path is world-writable')
    try:
        result = subprocess.run([str(executable), '--version'], env={},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            close_fds=True, timeout=3, check=False, cwd=str(root))
    except (OSError, subprocess.TimeoutExpired):
        raise PeerFailure('Node runtime version check failed') from None
    version = re.fullmatch(rb'v(\d+)\.\d+\.\d+\n?', result.stdout)
    if result.returncode or not version or int(version.group(1)) < 18:
        raise PeerFailure('Expected Node 18 or newer; no fallback or installation')
    return str(executable)


def write_deadline(fd, data, deadline):
    view = memoryview(data)
    while view:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
            raise PeerFailure('pipe_timeout; outcome may be unknown')
        try:
            count = os.write(fd, view)
        except BlockingIOError:
            continue
        if count <= 0:
            raise PeerFailure('output_failed; outcome may be unknown')
        view = view[count:]


class Peer:
    def __init__(self, session, envelope, proposal_id, *, timeout=3.0, client="python"):
        if type(session) is not RestrictedHostSession:
            raise TypeError('Expected an immutable restricted session')
        if not 0 < timeout <= 30:
            raise ValueError('Expected a bounded step timeout')
        if client not in ("python", "node"):
            raise ValueError("Expected fixed python or node client")
        self.session, self.timeout = session, timeout
        self.client = client
        self.process = None
        self.closed = False
        self.cleanup_uncertain = False
        self.fds = []
        self.buffers = {}
        reply_read = report_write = None
        try:
            command = ([sys.executable, "-I", str(Path(__file__).with_name("offline_peer_client.py"))]
                       if client == "python" else
                       [node_runtime(), str(Path(__file__).with_name("offline_peer_client.cjs"))])
            reply_read, self.reply_write = os.pipe()
            self.fds = [self.reply_write]
            self.report_read, report_write = os.pipe()
            self.fds.append(self.report_read)
            self.process = subprocess.Popen(command + [str(reply_read), str(report_write)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, close_fds=True, pass_fds=(reply_read, report_write),
                    env={}, cwd=str(Path(__file__).parent))
            for fd in (self.reply_write, self.report_read, self.process.stdin.fileno(), self.process.stdout.fileno()):
                os.set_blocking(fd, False)
            self.buffers = {self.process.stdout.fileno():bytearray(), self.report_read:bytearray()}
            config = json.dumps({'envelope':envelope, 'proposal_id':proposal_id}, ensure_ascii=True).encode()+b'\n'
            if len(config) > REPORT_LIMIT:
                raise PeerFailure('configuration_too_large')
            write_deadline(self.process.stdin.fileno(), config, time.monotonic()+timeout)
        except BaseException:
            self.close()
            raise
        finally:
            for fd in (reply_read, report_write):
                if fd is not None:
                    os.close(fd)

    @property
    def pid(self):
        return self.process.pid

    def step(self, name):
        if self.closed:
            raise PeerFailure('client_closed; no restart or replay')
        if name not in ('discover','propose','status','inbox'):
            raise ValueError('Unknown fixed client step')
        deadline = time.monotonic()+self.timeout
        frames = 0
        last_response = None
        try:
            write_deadline(self.process.stdin.fileno(), json.dumps({'step':name}).encode()+b'\n', deadline)
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise PeerFailure('pipe_timeout; outcome may be unknown')
                ready = select.select(list(self.buffers), [], [], remaining)[0]
                if not ready:
                    raise PeerFailure('pipe_timeout; outcome may be unknown')
                # Consume protocol input before reports if both are available.
                for fd in sorted(ready, key=lambda item:item == self.report_read):
                    pending = self.buffers[fd]
                    limit = REPORT_LIMIT if fd == self.report_read else MAX_INPUT
                    chunk = os.read(fd, min(4096, limit+1-len(pending)))
                    if not chunk:
                        raise PeerFailure(('partial_eof' if pending else 'client_eof')+'; outcome may be unknown')
                    pending.extend(chunk)
                    while b'\n' in pending:
                        frame, _, tail = pending.partition(b'\n')
                        pending[:] = tail
                        if len(frame) > limit:
                            raise PeerFailure('oversize_frame; outcome may be unknown')
                        frames += 1
                        if frames > STEP_LIMIT:
                            raise PeerFailure('step_budget; outcome may be unknown')
                        if fd == self.report_read:
                            def pairs(items):
                                value = {}
                                for key, item in items:
                                    if key in value:
                                        raise PeerFailure('duplicate_report_field; outcome may be unknown')
                                    value[key] = item
                                return value
                            def constant(value):
                                raise PeerFailure('nonfinite_report; outcome may be unknown')
                            report = json.loads(frame, object_pairs_hook=pairs, parse_constant=constant)
                            if type(report) is not dict or set(report) != {'pid','response'} or report['pid'] != self.pid:
                                raise PeerFailure('invalid_report; outcome may be unknown')
                            if (last_response is None or
                                    json.dumps(report['response'], sort_keys=True, allow_nan=False) !=
                                    json.dumps(last_response, sort_keys=True, allow_nan=False) or
                                    any(self.buffers.values())):
                                raise PeerFailure('uncorrelated_report; outcome may be unknown')
                            # Correlation is local evidence only, never an owner decision.
                            return report
                        response = self.session.handle(bytes(frame))
                        if response is not None:
                            if type(response) is not bytes or len(response) > MAX_OUTPUT or b'\n' in response:
                                raise PeerFailure('invalid_response; outcome may be unknown')
                            last_response = json.loads(response)
                            write_deadline(self.reply_write, response+b'\n', deadline)
                    if len(pending) > limit:
                        raise PeerFailure('oversize_frame; outcome may be unknown')
        except BaseException as exc:
            self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, PeerFailure):
                raise
            raise PeerFailure('client_io_failed; outcome may be unknown; no replay') from None

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        try:
            self.session.close()
        except Exception as exc:
            errors.append(exc)
        if self.process is not None:
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception as exc:
                        errors.append(exc)
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError as exc:
                errors.append(exc)
        self.fds.clear()
        if self.process is not None:
            reaped = False
            for signal, timeout in ((None, 0.2), ('terminate', 0.5), ('kill', 1)):
                if signal is not None:
                    try:
                        getattr(self.process, signal)()
                    except ProcessLookupError:
                        pass  # Still wait to reap a process that has already exited.
                    except Exception as exc:
                        errors.append(exc)
                try:
                    self.process.wait(timeout=timeout)
                    reaped = True
                    break
                except subprocess.TimeoutExpired:
                    pass
                except Exception as exc:
                    errors.append(exc)
            if not reaped:
                errors.append(RuntimeError('Reaping could not be confirmed'))
        if errors:
            self.cleanup_uncertain = True
            raise PeerFailure('cleanup_uncertain; no clean-discard claim')
