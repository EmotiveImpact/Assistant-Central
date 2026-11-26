#!/usr/bin/env python3
"""Fixed synthetic-only local MCP stdio pilot. No host setup or peer transport."""
import hashlib
import importlib.abc
import json
import logging
import os
from pathlib import Path
import stat
import sys
import warnings
from contextlib import ExitStack
from unittest.mock import patch

R4_MANIFEST_SHA256 = 'ded41439c7fe7a35370019b30fcbb6a773bcd82e67de1f406a98104c2fb7d71c'
FIXTURE_SHA256 = '2a6d3fef6cb8e9f88838a0cdd42cb4822d9e46311b113d85205f75e3eac37869'
ROOT = Path(__file__).resolve().parent
IDLE_SECONDS = 300
WRITE_SECONDS = 10
READ_CAP = 4096
WRITE_CAP = 32768
EMPTY_INBOX = {'knowledge': 'No trusted local snapshot published.', 'publication': 0, 'items': []}
DIAGNOSTICS = {
    64: b'SYNTHETIC_STDIO_STARTUP_REJECTED\n',
    65: b'SYNTHETIC_STDIO_INPUT_TERMINATED\n',
    70: b'SYNTHETIC_STDIO_LOCAL_FAILURE_OUTCOME_UNCERTAIN\n',
    74: b'SYNTHETIC_STDIO_OUTPUT_FAILURE_OUTCOME_UNCERTAIN\n',
    75: b'SYNTHETIC_STDIO_IDLE_TIMEOUT_OUTCOME_UNCERTAIN\n',
}


class PilotFailure(RuntimeError):
    """Never serialize the exception or user input to diagnostics."""


class DiscardText:
    encoding = 'utf-8'
    errors = 'strict'
    def write(self, text):
        return len(text)
    def flush(self):
        return None
    def isatty(self):
        return False


def quiet_python_streams():
    """Dependencies are trusted; this is not OS-level native-code isolation."""
    sys.stdout = sys.__stdout__ = DiscardText()
    sys.stderr = sys.__stderr__ = DiscardText()
    logging.disable(logging.CRITICAL)
    warnings.simplefilter('ignore')
    sys.unraisablehook = lambda unused: None


def diagnostic(code, write=os.write):
    """One short fixed diagnostic, no retry or dynamic exception detail."""
    if code in DIAGNOSTICS:
        try:
            write(2, DIAGNOSTICS[code])
        except BaseException:
            pass


def verify_inputs(root=ROOT):
    root = root.resolve(strict=True)
    if (root / 'baseline_r4').is_symlink():
        raise PilotFailure()
    baseline = (root / 'baseline_r4').resolve(strict=True)
    if not baseline.is_relative_to(root):
        raise PilotFailure()
    manifest_path = (baseline / 'RAW_SOURCE_MANIFEST.json').resolve(strict=True)
    if not manifest_path.is_relative_to(baseline):
        raise PilotFailure()
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != R4_MANIFEST_SHA256:
        raise PilotFailure()
    files = json.loads(raw)['files']
    for name, expected in files.items():
        path = (baseline / name).resolve(strict=True)
        if not path.is_relative_to(baseline) or not path.is_file():
            raise PilotFailure()
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise PilotFailure()
    # All three import roots are below baseline. Reject unmanifested executable
    # modules anywhere in that tree, and symlinks (including directory symlinks).
    # Integrity checks are not race-safe against a concurrent directory writer.
    for path in baseline.rglob('*'):
        if path.is_symlink():
            raise PilotFailure()
        if path.is_file() and path.suffix in {'.py', '.pyc', '.so', '.pyd'}:
            if str(path.relative_to(baseline)) not in files:
                raise PilotFailure()
    fixture_path = (root / 'public_fixture.json').resolve(strict=True)
    if not fixture_path.is_relative_to(root):
        raise PilotFailure()
    fixture_raw = fixture_path.read_bytes()
    if hashlib.sha256(fixture_raw).hexdigest() != FIXTURE_SHA256:
        raise PilotFailure()
    return baseline, json.loads(fixture_raw), len(files)


class Guard:
    """Defense in depth for this trusted process, not a sandbox guarantee."""
    def __init__(self):
        self.counts = {'blocked': 0, 'local_unix_socket_creations': 0,
                       'memory_databases': 0}

    def deny(self, *unused, **ignored):
        self.counts['blocked'] += 1
        raise PilotFailure()

    def audit(self, event, arguments):
        if event == 'socket.__new__':
            # CPython's asyncio loop creates an AF_UNIX/SOCK_STREAM wakeup pair.
            # No connect/bind/listen/resolve operation is allowed below.
            if tuple(arguments[1:]) != (1, 1, 0):
                self.deny()
            self.counts['local_unix_socket_creations'] += 1
        elif event.startswith('socket.'):
            self.deny()
        elif event in {'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty',
                       'os.posix_spawn', 'os.exec', 'pty.spawn'}:
            self.deny()
        elif event == 'sqlite3.connect':
            if arguments[0] != ':memory:':
                self.deny()
            self.counts['memory_databases'] += 1

    def import_guard(self):
        guard = self
        class NoPeerTransport(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {'independent_peer.endpoint', 'independent_peer.pipes',
                                'independent_peer.worker', 'independent_peer.fixture'}:
                    guard.deny()
                return None
        return NoPeerTransport()


class StdioReader:
    def __init__(self, anyio_module, fd=0, read=os.read):
        self.anyio, self.fd, self.read = anyio_module, fd, read
        self.idle_timeout = False

    async def receive(self, size):
        if type(size) is not int or not 0 < size <= READ_CAP:
            raise PilotFailure()
        try:
            with self.anyio.fail_after(IDLE_SECONDS):
                while True:
                    try:
                        chunk = self.read(self.fd, size)
                        break
                    except (BlockingIOError, InterruptedError):
                        await self.anyio.wait_readable(self.fd)
        except TimeoutError:
            self.idle_timeout = True
            raise PilotFailure() from None
        if type(chunk) is not bytes or len(chunk) > size:
            raise PilotFailure()
        if not chunk:
            raise self.anyio.EndOfStream
        return chunk


class StdioWriter:
    def __init__(self, anyio_module, fd=1, write=os.write):
        self.anyio, self.fd, self.write = anyio_module, fd, write

    async def send(self, data):
        # Partial success advances only through this same encoded reply. No
        # request is replayed; a subsequent failure aborts the entire session.
        if type(data) is not bytes or not 0 < len(data) <= WRITE_CAP:
            raise PilotFailure()
        view = memoryview(data)
        offset = 0
        with self.anyio.fail_after(WRITE_SECONDS):
            while offset < len(view):
                try:
                    count = self.write(self.fd, view[offset:])
                except (BlockingIOError, InterruptedError):
                    await self.anyio.wait_writable(self.fd)
                    continue
                if type(count) is not int or not 0 < count <= len(view) - offset:
                    raise PilotFailure()
                offset += count
        return None


def synthetic_facade(store, fixture, facade_type):
    """Exact frozen type retained; only this instance's propose is narrowed."""
    facade = facade_type(store)
    original_propose = facade.propose
    allowed = frozenset((fixture['proposal_text'],))
    def propose(arguments):
        if (type(arguments) is not dict or set(arguments) != {'text'} or
                type(arguments['text']) is not str or arguments['text'] not in allowed):
            raise PilotFailure()
        return original_propose(arguments)
    facade.propose = propose
    if facade.processed_inbox({}) != EMPTY_INBOX:
        raise PilotFailure()
    return facade


def run_pilot(baseline, fixture):
    # Cleared before importing dependencies. -I also ignores Python env/user site;
    # the interpreter, installed site packages and startup hooks remain trusted.
    os.environ.clear()
    guard = Guard()
    sys.addaudithook(guard.audit)
    sys.meta_path.insert(0, guard.import_guard())
    sys.path[0:0] = [str(baseline / 'baseline_r3' / 'baseline_r2'),
                     str(baseline / 'baseline_r3'), str(baseline)]
    from importlib.metadata import version
    if version('mcp') != '1.29.0':
        raise PilotFailure()
    import anyio
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    with ExitStack() as stack:
        for cls in (Ed25519PrivateKey, X25519PrivateKey):
            for method in ('generate', 'from_private_bytes'):
                stack.enter_context(patch.object(cls, method, side_effect=guard.deny))
        import independent_peer.protocol as protocol
        stack.enter_context(patch.object(protocol.Identity, '__init__', side_effect=guard.deny))
        from facade_candidate import store as store_module
        for cls in (store_module.OwnerReview, store_module.SnapshotPublisher):
            stack.enter_context(patch.object(cls, '__init__', side_effect=guard.deny))
        from raw_bridge.transport import RawBridge
        store = store_module.ProposalStore(':memory:', actor=fixture['actor'],
            task_value=fixture['task'], public=fixture['public'])
        try:
            facade = synthetic_facade(store, fixture, store_module.AssistantFacade)
            bridge = RawBridge(facade)
            reader, writer = StdioReader(anyio), StdioWriter(anyio)
            code = 0
            try:
                anyio.run(bridge.run, reader, writer, backend='asyncio')
            except BaseException:
                if bridge.facts.output_uncertain:
                    code = 74
                elif reader.idle_timeout:
                    code = 75
                else:
                    code = 70
            else:
                if bridge.facts.termination != 'eof':
                    code = 65
            # Postcondition read only. No publisher, owner object or recovery.
            rows = [json.loads(row[0]) for row in store._db.execute('SELECT value FROM proposals')]
            if (len(rows) > 1 or any(row['text'] != fixture['proposal_text'] or row['state'] != 'pending' for row in rows)
                    or facade.processed_inbox({}) != EMPTY_INBOX or guard.counts['blocked']):
                code = 70 if code == 0 else code
            return code
        finally:
            store.close()


def main():
    quiet_python_streams()
    code = 64
    try:
        # Also cover startup rejection: diagnostics must not block on a full pipe.
        if stat.S_ISFIFO(os.fstat(2).st_mode):
            os.set_blocking(2, False)
        # No configurable fixture, plugin, actor, storage path or provider.
        if len(sys.argv) != 1 or not sys.flags.isolated or not sys.flags.dont_write_bytecode:
            raise PilotFailure()
        if sys.version_info[:2] != (3, 12) or os.name != 'posix':
            raise PilotFailure()
        if not all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (0, 1)):
            raise PilotFailure()
        baseline, fixture, _ = verify_inputs()
        os.set_blocking(0, False)
        os.set_blocking(1, False)
        code = 70
        code = run_pilot(baseline, fixture)
    except BaseException:
        pass
    diagnostic(code)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
