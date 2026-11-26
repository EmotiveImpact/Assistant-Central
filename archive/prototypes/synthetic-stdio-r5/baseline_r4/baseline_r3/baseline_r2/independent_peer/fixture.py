"""Trusted synthetic supervisor. Holds public artifacts, never endpoint private keys."""
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time

from .pipes import frame
from .protocol import CAPABILITY, MAX_FRAME, Rejected, digest, exact, need, parse, token

ROOT = Path(__file__).resolve().parent.parent


class UncertainOutcome(RuntimeError):
    """No automatic retry, replacement, or assertion of non-execution is safe."""


class CleanupUncertain(RuntimeError):
    """All cleanup steps were attempted, but at least one failed."""


class PeerProcess:
    def __init__(self, actor, directory, worker_module='independent_peer.worker'):
        self.actor = actor
        self.database = str(Path(directory) / (actor + '.sqlite'))
        self.broken = False
        self._lane_locks = {name: threading.Lock() for name in ('owner', 'peer')}
        self.process = None
        for name in ('owner_w', 'owner_r', 'peer_w', 'peer_r'):
            setattr(self, name, None)
        fds = []
        try:
            owner_r, self.owner_w = os.pipe(); fds += [owner_r, self.owner_w]
            self.owner_r, owner_w = os.pipe(); fds += [self.owner_r, owner_w]
            peer_r, self.peer_w = os.pipe(); fds += [peer_r, self.peer_w]
            self.peer_r, peer_w = os.pipe(); fds += [self.peer_r, peer_w]
            children = (owner_r, owner_w, peer_r, peer_w)
            self.process = subprocess.Popen(
                [sys.executable, '-m', worker_module, '--actor', actor, '--database', self.database,
                 '--owner-read', str(owner_r), '--owner-write', str(owner_w),
                 '--peer-read', str(peer_r), '--peer-write', str(peer_w)],
                cwd=ROOT, pass_fds=children, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, close_fds=True,
                env={'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'})
            for fd in children:
                os.close(fd)
                fds.remove(fd)
            for fd in fds:
                os.set_blocking(fd, False)
        except Exception as exc:
            # Close all acquired descriptors, including partially built lanes.
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            for name in ('owner_w', 'owner_r', 'peer_w', 'peer_r'):
                setattr(self, name, None)
            try:
                self.close()
            except CleanupUncertain:
                exc.add_note('Child cleanup was attempted but could not be fully confirmed.')
            raise

    def _io(self, read_fd, write_fd, command, timeout):
        deadline = time.monotonic() + timeout
        output = bytearray(frame(command))
        incoming = bytearray()
        size = None
        while output or size is None or len(incoming) < size + 4:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('fixture I/O deadline')
            readable, writable, _ = select.select([read_fd] if not output else [], [write_fd] if output else [], [], remaining)
            if writable:
                count = os.write(write_fd, output[:4096])
                del output[:count]
            if readable:
                want = 4 - len(incoming) if size is None else size + 4 - len(incoming)
                data = os.read(read_fd, min(4096, want))
                if not data:
                    raise EOFError('endpoint closed')
                incoming.extend(data)
                if size is None and len(incoming) == 4:
                    size = struct.unpack('!I', incoming)[0]
                    need(0 < size <= MAX_FRAME, 'response frame size')
        return parse(bytes(incoming[4:]))

    def call(self, lane, command, timeout=3):
        need(lane in ('owner', 'peer'), 'unknown fixture lane')
        lock = self._lane_locks[lane]
        need(lock.acquire(blocking=False), 'same-lane concurrent calls are unsupported')
        try:
            if self.broken:
                raise UncertainOutcome('session poisoned: outcome unresolved; do not retry automatically')
            # Validate locally before beginning I/O; these failures are known not submitted.
            frame(command)
            try:
                response = self._io(getattr(self, lane + '_r'), getattr(self, lane + '_w'), command, timeout)
                need(type(response) is dict and type(response.get('ok')) is bool, 'malformed response')
                if response['ok']:
                    exact(response, 'ok value')
                else:
                    exact(response, 'ok error')
                    need(type(response['error']) is str and len(response['error']) <= 200, 'malformed error response')
            except Exception as exc:
                self.broken = True
                failure = UncertainOutcome('pipe failed; request may have committed; shutdown attempted; no automatic retry')
                try:
                    self.close()  # Stop endpoint admission; never restart or retry a mutation.
                except CleanupUncertain:
                    failure.add_note('Cleanup was attempted but endpoint shutdown could not be fully confirmed.')
                raise failure from exc
            if not response['ok']:
                raise Rejected(response['error'])
            return response['value']
        finally:
            lock.release()

    def owner(self, op, operation_id=None, **values):
        command = {'op': op, **values}
        if op not in ('describe', 'inspect', 'packet'):
            command['operation_id'] = operation_id or token()
        return self.call('owner', command)

    def peer(self, op, value):
        return self.call('peer', {'op': op, 'value': value})

    def close(self):
        errors = []
        for name in ('owner_w', 'owner_r', 'peer_w', 'peer_r'):
            fd = getattr(self, name, None)
            setattr(self, name, None)  # Idempotence: never close a reused descriptor later.
            if fd is not None and fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    errors.append('descriptor close')
        process = self.process
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                except OSError:
                    errors.append('terminate')
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    except OSError:
                        errors.append('kill')
                    try:
                        process.wait(timeout=1)
                    except (subprocess.TimeoutExpired, OSError):
                        errors.append('reap')
                except OSError:
                    errors.append('wait after terminate')
            except OSError:
                errors.append('initial wait')
                # Still attempt kill/reap when ordinary waiting failed unexpectedly.
                try:
                    process.kill()
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    errors.append('fallback reap')
            if process.stderr:
                try:
                    process.stderr.close()
                except OSError:
                    errors.append('diagnostic pipe close')
        if errors:
            raise CleanupUncertain('Cleanup could not be fully confirmed: ' + ', '.join(errors))


class Experiment:
    def __init__(self, bob_module='independent_peer.worker'):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-independent-peers-')
        self.peers = {}
        try:
            self.peers['alice'] = PeerProcess('alice', self.temp.name)
            self.peers['bob'] = PeerProcess('bob', self.temp.name, bob_module)
            public = {name: peer.owner('describe')['descriptor'] for name, peer in self.peers.items()}
            self.task = {'id': token(), 'context': digest({'fixture_scope': 'One fictional bounded question and answer.'}), 'capability': CAPABILITY}
            for actor, peer in self.peers.items():
                peer.owner('configure', task=self.task, peer=public['bob' if actor == 'alice' else 'alice'])
        except Exception as exc:
            try:
                self.close()
            except CleanupUncertain:
                exc.add_note('Fixture cleanup was attempted but could not be fully confirmed.')
            raise

    @property
    def alice(self):
        return self.peers['alice']

    @property
    def bob(self):
        return self.peers['bob']

    def close(self):
        errors = []
        for actor, peer in self.peers.items():
            try:
                peer.close()
            except Exception:
                errors.append(actor + ' cleanup')
        try:
            self.temp.cleanup()
        except Exception:
            errors.append('temporary state cleanup')
        if errors:
            raise CleanupUncertain('Cleanup could not be fully confirmed: ' + ', '.join(errors))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.close()
        except CleanupUncertain:
            if exc is None:
                raise
            exc.add_note('Fixture cleanup was attempted but could not be fully confirmed.')
