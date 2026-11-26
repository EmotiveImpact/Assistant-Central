"""Independent adversarial stream review; no imported TestCase aliases."""
import io
import json
import threading
import unittest
from generic_demo import fixture
from restricted_host_protocol import RestrictedHostSession, MAX_INPUT
from restricted_host_stream import serve, READ_CHUNK


def req(method, ident, **params):
    return json.dumps(dict(jsonrpc='2.0', method=method, id=ident, params=params)).encode()


INIT = req('initialize', 'init', protocolVersion='2025-06-18', capabilities={},
           clientInfo={'name': 'review', 'version': '1'})
READY = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'
CALL = req('tools/call', 1, name='inbox', arguments={})


def frames(*items):
    return b'\n'.join(items) + b'\n'


class PartitionReader:
    def __init__(self, data, cuts):
        self.parts = [data[a:b] for a, b in zip([0] + cuts, cuts + [len(data)]) if a != b]
        self.limits = []
    def read(self, n):
        self.limits.append(n)
        if not self.parts:
            return b''
        result, self.parts[0] = self.parts[0][:n], self.parts[0][n:]
        if not self.parts[0]: self.parts.pop(0)
        return result


class HostStreamIndependentReview(unittest.TestCase):
    def session(self):
        calls = []
        def dispatch(command):
            calls.append(command)
            return {'messages': [], 'payload_trust': 'untrusted_inert'}
        return RestrictedHostSession(fixture()[0], 'alice', dispatch), calls

    def test_every_single_split_is_framing_equivalent(self):
        data = frames(INIT, READY,
            '{"jsonrpc":"2.0","method":"note","params":{"s":"☀\\n"}}'.encode(),
            b'\xff', b'{"x":{"y":1,"y":2}}', b'{"a":"raw\nLF"}', CALL)
        baseline = None
        for split in range(1, len(data)):
            session, calls = self.session()
            writer = io.BytesIO()
            end = serve(PartitionReader(data, [split]), writer, session)
            self.assertEqual(end.reason, 'eof')
            self.assertEqual(calls, [{'method': 'inbox'}])
            if baseline is None: baseline = writer.getvalue()
            self.assertEqual(writer.getvalue(), baseline, split)
        self.assertEqual(len(baseline.splitlines()), 6)

    def test_size_boundary_matrix_counts_cr_and_partial_eof(self):
        for length in (MAX_INPUT - 1, MAX_INPUT, MAX_INPUT + 1):
            for suffix in (b'\n', b'\r\n', b''):
                for chunk in (1, READ_CHUNK - 1, READ_CHUNK):
                    with self.subTest(length=length, suffix=suffix, chunk=chunk):
                        ping = req('ping', 42)
                        data = ping + b' ' * (length - len(ping)) + suffix
                        session, calls = self.session()
                        reader = PartitionReader(data, list(range(chunk, len(data), chunk)))
                        writer = io.BytesIO()
                        end = serve(reader, writer, session)
                        size = length + (suffix == b'\r\n')
                        reason = 'oversize_frame' if size > MAX_INPUT else ('eof' if suffix else 'partial_eof')
                        self.assertEqual(end.reason, reason)
                        self.assertEqual(bool(writer.getvalue()), reason == 'eof')
                        self.assertTrue(all(0 < n <= READ_CHUNK for n in reader.limits))
                        self.assertEqual(calls, [])

    def test_partial_write_failure_stops_coalesced_callbacks(self):
        session, calls = self.session()
        class Writer(io.BytesIO):
            flushes = 0
            partial = False
            def flush(self): self.flushes += 1
            def write(self, data):
                if self.flushes == 1:
                    if self.partial: raise OSError('PRIVATE details')
                    self.partial = True
                    return super().write(data[:5])
                return super().write(data)
        writer = Writer()
        end = serve(io.BytesIO(frames(INIT, READY, CALL,
            req('tools/call', 2, name='inbox', arguments={}))), writer, session)
        self.assertEqual((end.reason, end.outcome_unknown), ('output_failed', True))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(writer.getvalue().split(b'\n')), 2)
        self.assertNotIn(b'PRIVATE', writer.getvalue())
        self.assertFalse(writer.closed)

    def test_flush_backpressure_prevents_next_callback(self):
        session, calls = self.session()
        blocked, release = threading.Event(), threading.Event()
        class Writer(io.BytesIO):
            flushes = 0
            def flush(self):
                self.flushes += 1
                if self.flushes == 2:
                    blocked.set()
                    if not release.wait(5): raise TimeoutError('Harness safeguard')
        writer, ends = Writer(), []
        reader = io.BytesIO(frames(INIT, READY, CALL,
            req('tools/call', 2, name='inbox', arguments={})))
        thread = threading.Thread(target=lambda: ends.append(serve(reader, writer, session)), daemon=True)
        thread.start()
        try:
            self.assertTrue(blocked.wait(5))
            self.assertEqual(len(calls), 1)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(calls), 2)
        self.assertEqual(ends[0].reason, 'eof')
        self.assertFalse(reader.closed)
        self.assertFalse(writer.closed)

    def test_input_failure_after_effect_does_not_imply_rollback(self):
        session, calls = self.session()
        class Reader:
            first = True
            def read(self, n):
                if self.first:
                    self.first = False
                    return frames(INIT, READY, CALL)
                raise OSError('PRIVATE input failure')
        writer = io.BytesIO()
        end = serve(Reader(), writer, session)
        self.assertEqual((end.reason, end.outcome_unknown), ('input_failed', False))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(writer.getvalue().splitlines()), 2)
        self.assertNotIn('PRIVATE', repr(end))

    def test_read1_preference_writer_lookup_failure_and_cleanup(self):
        session, calls = self.session()
        class Reader(io.BytesIO):
            def read(self, n): raise AssertionError('Prefer read1')
        class Writer:
            @property
            def write(self): raise RuntimeError('PRIVATE writer lookup')
        end = serve(Reader(frames(req('ping', 1))), Writer(), session)
        self.assertEqual((end.reason, end.outcome_unknown), ('output_failed', True))
        self.assertEqual(calls, [])
        self.assertNotIn('PRIVATE', repr(end))
        self.assertEqual(json.loads(session.handle(req('ping', 99)))['error']['message'], 'Session closed')


if __name__ == '__main__': unittest.main()
