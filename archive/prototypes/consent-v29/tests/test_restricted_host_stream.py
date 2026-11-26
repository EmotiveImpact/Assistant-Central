"""Real anonymous pipes plus bounded fault streams; no production host launcher."""
import contextlib
import io
import json
import os
import select
import threading
import unittest
from unittest.mock import patch

from generic_demo import fixture
from network import Denied
from restricted_host_protocol import RestrictedHostSession, MAX_INPUT
from restricted_host_stream import serve, READ_CHUNK
from test_restricted_host_protocol import wire
import test_owner_workspace as workspace_tests
from task_fixtures import fixture as catalog_fixture


INITIALIZE = wire('initialize', 'init', protocolVersion='2025-06-18', capabilities={},
                  clientInfo={'name': 'fictional-pipe-client', 'version': '1'})
INITIALIZED = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'


def frames(*records):
    return b'\n'.join(records) + b'\n'


def tool(name, ident=1, **arguments):
    return wire('tools/call', ident, name=name, arguments=arguments)


class PipeClient:
    """Trusted harness owns both pipe ends, but only writes protocol bytes.

    OwnerWorkspace and all owner controls stay outside serve and its input.
    Test timeouts are harness safeguards, not transport timeout claims.
    """
    def __init__(self, session):
        source, sink = os.pipe()
        output, destination = os.pipe()
        self.reader = os.fdopen(source, 'rb')
        self.writer = os.fdopen(destination, 'wb', buffering=0)
        self.input = os.fdopen(sink, 'wb', buffering=0)
        self.output = os.fdopen(output, 'rb', buffering=0)
        self.end = None
        def run():
            try:
                self.end = serve(self.reader, self.writer, session)
            finally:
                self.reader.close()
                self.writer.close()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.seq = 0

    def send(self, data, fragment=7):
        for offset in range(0, len(data), fragment):
            self.input.write(data[offset:offset + fragment])

    def receive(self):
        data = bytearray()
        while not data.endswith(b'\n'):
            if not select.select([self.output], [], [], 5)[0]:
                raise AssertionError('Pipe response timeout')
            item = self.output.read(1)
            if not item:
                raise AssertionError('Unexpected pipe EOF')
            data.extend(item)
        return json.loads(data)

    def initialize(self):
        self.send(frames(INITIALIZE, INITIALIZED))
        assert self.receive()['result']['protocolVersion'] == '2025-06-18'

    def call(self, name, **arguments):
        self.seq += 1
        self.send(frames(tool(name, self.seq, **arguments)))
        return self.receive()

    def close(self):
        if not self.input.closed:
            self.input.close()
        self.thread.join(5)
        if self.thread.is_alive():
            raise AssertionError('Pipe server did not terminate')
        self.output.close()


class FragmentReader:
    def __init__(self, data, size=1):
        self.data, self.size = io.BytesIO(data), size
        self.limits = []
    def read(self, limit):
        self.limits.append(limit)
        return self.data.read(min(limit, self.size))


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def dispatch(command):
            self.calls.append(command)
            return {'messages': [], 'payload_trust': 'untrusted_inert'}
        self.session = RestrictedHostSession(fixture()[0], 'alice', dispatch)
    def run_stream(self, data, size=1, writer=None):
        reader = FragmentReader(data, size)
        writer = writer if writer is not None else io.BytesIO()
        end = serve(reader, writer, self.session)
        self.assertTrue(all(0 < n <= READ_CHUNK for n in reader.limits))
        return end, writer.getvalue()

    def test_actual_fragmented_pipe_multiple_records_notifications_and_errors(self):
        client = PipeClient(self.session)
        self.addCleanup(client.close)
        client.initialize()
        client.send(frames(INITIALIZED, b'not json', tool('inbox', 1),
                           wire('dispatch', 2), wire('ping', 3)), fragment=1)
        replies = [client.receive() for _ in range(4)]
        self.assertEqual(replies[0]['error']['code'], -32700)
        self.assertFalse(replies[1]['result']['isError'])
        self.assertEqual(replies[2]['error']['code'], -32601)
        self.assertEqual(replies[3]['result'], {})
        self.assertEqual(self.calls, [{'method': 'inbox'}])
        client.close()
        self.assertEqual(client.end.reason, 'eof')

    def test_actual_pipes_partial_eof_and_oversize_never_dispatch(self):
        for suffix, expected in ((tool('inbox'), 'partial_eof'),
                                 (b'x'*(MAX_INPUT+1), 'oversize_frame')):
            session = RestrictedHostSession(fixture()[0], 'alice', lambda c: self.calls.append(c))
            client = PipeClient(session)
            self.addCleanup(client.close)
            client.initialize()
            client.send(suffix, fragment=257)
            client.close()
            self.assertEqual(client.end.reason, expected)
        self.assertEqual(self.calls, [])

    def test_raw_newlines_are_record_boundaries_not_multiline_json(self):
        broken = tool('inbox').replace(b'"inbox"', b'"in\nbox"')
        end, output = self.run_stream(frames(INITIALIZE, INITIALIZED, broken, wire('ping', 8)), size=4096)
        records = list(map(json.loads, output.splitlines()))
        self.assertEqual([r['error']['code'] for r in records[1:3]], [-32700, -32700])
        self.assertEqual(records[3]['result'], {})
        self.assertEqual(self.calls, [])
        self.assertEqual(end.reason, 'eof')

    def test_utf8_fragmentation_and_escaped_newline_are_one_record(self):
        note = json.dumps({'jsonrpc':'2.0','method':'unknown','params':{'text':'🌱\nline'}}, ensure_ascii=False).encode()
        end, output = self.run_stream(frames(INITIALIZE, INITIALIZED, note, tool('inbox')))
        self.assertEqual(end.reason, 'eof')
        self.assertEqual(len(output.splitlines()), 2)
        self.assertEqual(len(self.calls), 1)

    def test_complete_malformed_frames_recover_without_diagnostic_pollution(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            end, output = self.run_stream(frames(b'\xff', b'{"id":1,"id":2}', b'',
                                           b'{"x":NaN}', wire('ping', 1)), size=4096)
        records = list(map(json.loads, output.splitlines()))
        self.assertEqual([r['error']['code'] for r in records[:-1]], [-32700]*4)
        self.assertEqual(records[-1]['result'], {})
        self.assertEqual(end.reason, 'eof')
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')
        self.assertEqual(self.calls, [])

    def test_oversize_stops_without_drain_or_following_callback(self):
        data = b'x'*(MAX_INPUT + 1) + frames(b'', INITIALIZE, INITIALIZED, tool('inbox'))
        reader, writer = FragmentReader(data, 4096), io.BytesIO()
        end = serve(reader, writer, self.session)
        self.assertEqual(end.reason, 'oversize_frame')
        self.assertLessEqual(reader.data.tell(), MAX_INPUT + 1)
        self.assertEqual(writer.getvalue(), b'')
        self.assertEqual(self.calls, [])

    def test_exact_limit_crlf_and_coalesced_records(self):
        ping = wire('ping', 1)
        end, output = self.run_stream(ping + b' '*(MAX_INPUT-len(ping)) + b'\n' + wire('ping', 2) + b'\r\n', size=4096)
        self.assertEqual(end.reason, 'eof')
        self.assertEqual([json.loads(r)['id'] for r in output.splitlines()], [1, 2])

    def test_partial_eof_never_dispatches_complete_json_without_delimiter(self):
        end, output = self.run_stream(frames(INITIALIZE, INITIALIZED) + tool('inbox'))
        self.assertEqual(end.reason, 'partial_eof')
        self.assertEqual(len(output.splitlines()), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(json.loads(self.session.handle(wire('ping', 9)))['error']['message'], 'Session closed')

    def test_short_writes_complete_bytes_not_callbacks(self):
        class ShortWriter(io.BytesIO):
            def write(self, data): return super().write(data[:3])
        end, output = self.run_stream(frames(INITIALIZE, INITIALIZED, tool('inbox')), writer=ShortWriter())
        self.assertEqual(end.reason, 'eof')
        self.assertEqual(len(output.splitlines()), 2)
        self.assertEqual(len(self.calls), 1)

    def test_write_and_flush_failures_are_terminal_and_sanitized(self):
        for mode in ('raise', 'zero', 'none', 'negative', 'huge', 'bool', 'flush'):
            with self.subTest(mode=mode):
                session = RestrictedHostSession(fixture()[0], 'alice', lambda c: None)
                class FailedWriter(io.BytesIO):
                    def write(self, data):
                        if mode == 'raise': raise OSError('SECRET path')
                        if mode == 'flush': return super().write(data)
                        return {'zero':0,'none':None,'negative':-1,'huge':999999,'bool':True}[mode]
                    def flush(self): raise OSError('SECRET flush')
                writer = FailedWriter()
                end = serve(io.BytesIO(frames(wire('ping', 1), wire('ping', 2))), writer, session)
                self.assertEqual(end.reason, 'output_failed')
                self.assertTrue(end.outcome_unknown)
                self.assertNotIn('SECRET', repr(end))
                self.assertNotIn(b'SECRET', writer.getvalue())
                self.assertEqual(json.loads(session.handle(wire('ping', 2)))['error']['message'], 'Session closed')

    def test_reader_lookup_and_noncallable_methods_fail_closed(self):
        class RaisingReader:
            @property
            def read1(self): raise RuntimeError('SECRET lookup')
        class NoncallableReader:
            read = 17
        class NoncallableRead1:
            read1 = False
            def read(self, n): raise AssertionError('Do not fallback')
        for reader in (object(), RaisingReader(), NoncallableReader(), NoncallableRead1()):
            session = RestrictedHostSession(fixture()[0], 'alice', lambda c: None)
            writer = io.BytesIO()
            end = serve(reader, writer, session)
            self.assertEqual(end.reason, 'input_failed')
            self.assertNotIn('SECRET', repr(end))
            self.assertEqual(writer.getvalue(), b'')
            self.assertEqual(json.loads(session.handle(wire('ping', 1)))['error']['message'], 'Session closed')

    def test_bad_reader_contract_and_read_exception_close_session(self):
        for value in (None, 'text', b'x'*(READ_CHUNK+1), OSError('SECRET')):
            class BadReader:
                def read(self, n):
                    if isinstance(value, Exception): raise value
                    return value
            session = RestrictedHostSession(fixture()[0], 'alice', lambda c: None)
            writer = io.BytesIO()
            self.assertEqual(serve(BadReader(), writer, session).reason, 'input_failed')
            self.assertEqual(writer.getvalue(), b'')
            self.assertEqual(json.loads(session.handle(wire('ping', 1)))['error']['message'], 'Session closed')


class WorkspaceStreamTests(unittest.TestCase):
    # Reuse only explicit owner-harness actions, not inherited tests or implicit
    # protocol setup. None of these functions is reachable from stream input.
    setUp = workspace_tests.WorkspaceTests.setUp
    service = workspace_tests.WorkspaceTests.service
    action = workspace_tests.WorkspaceTests.action
    bind = workspace_tests.WorkspaceTests.bind
    resolve = workspace_tests.WorkspaceTests.resolve
    submit = workspace_tests.WorkspaceTests.submit
    pair = workspace_tests.WorkspaceTests.pair
    summary = workspace_tests.WorkspaceTests.summary
    finish = workspace_tests.WorkspaceTests.finish

    def stream(self, key, actor):
        client = PipeClient(self.w.adapter(key, self.ctx[key], actor))
        self.addCleanup(client.close)
        client.initialize()
        return client

    def test_two_scoped_pipes_owner_controls_stay_separate_and_closed_fence(self):
        for key in self.ctx: self.bind(key)
        clients = {key:self.stream(key, catalog_fixture(key)[0].requester) for key in self.ctx}
        for key, client in clients.items():
            envelope = catalog_fixture(key)[2]
            answer = client.call('propose', proposal_id='same', envelope=envelope)
            self.assertEqual(json.loads(answer['result']['content'][0]['text'])['state'], 'awaiting_owner_review')
            self.assertEqual(self.service(key)._command('request_list', owner=envelope['sender']), [])
            with self.assertRaises(Denied): self.w.import_proposal(key, self.ctx[key], envelope['sender'], 'same')
            self.assertEqual(self.summary(key)['receiver_receipts'], 0)
            # Caller cannot create/bind/pair/import/approve or change scope.
            for name in ('create','bind','pair','approve','agent_proposal_review','select','dispatch'):
                self.assertIn('error', client.call(name))
            self.assertIn('error', client.call('inbox', actor='bob', task='astronomy'))
        for key in self.ctx: self.pair(key)  # Explicit synthetic owner actions.
        for key, client in clients.items():
            actor = catalog_fixture(key)[0].requester
            card = self.w.import_proposal(key, self.ctx[key], actor, 'same')
            with self.assertRaises(Denied): self.submit(key, card)
            self.finish(key, card)  # Separate approve/submit/send/process.
            other = 'astronomy' if key == 'garden' else 'garden'
            self.assertIn('error', client.call('propose', proposal_id='cross', envelope=catalog_fixture(other)[2]))
        self.w.close_task('garden', self.ctx['garden'])
        self.assertTrue(clients['garden'].call('inbox')['result']['isError'])
        self.assertFalse(clients['astronomy'].call('inbox')['result']['isError'])
        for key, client in clients.items():
            client.close()
            self.assertEqual(client.end.reason, 'eof')

    def test_actual_broken_response_pipe_stages_once_without_retry(self):
        self.bind('garden')
        client = self.stream('garden', 'alice')
        client.output.close()  # Peer disconnects after initialization.
        client.send(frames(tool('propose', 1, proposal_id='lost', envelope=catalog_fixture('garden')[2])))
        client.close()
        self.assertEqual(client.end.reason, 'output_failed')
        self.assertTrue(client.end.outcome_unknown)
        rows = self.w.proposals('garden', self.ctx['garden'], 'alice')
        self.assertEqual([r['proposal_id'] for r in rows], ['lost'])
        self.assertEqual(self.service('garden')._command('request_list', owner='alice'), [])
        self.assertEqual(self.summary('garden')['receiver_receipts'], 0)

    def test_lost_output_after_staging_reconnect_and_idempotency(self):
        self.bind('garden')
        session = self.w.adapter('garden', self.ctx['garden'], 'alice')
        proposal = tool('propose', 1, proposal_id='durable', envelope=catalog_fixture('garden')[2])
        class LoseProposalResponse(io.BytesIO):
            def __init__(self): super().__init__(); self.flushes = 0
            def flush(self):
                self.flushes += 1
                if self.flushes == 2: raise BrokenPipeError('SECRET lost')
        writer = LoseProposalResponse()
        with patch.object(session, '_dispatch', wraps=session._dispatch) as dispatch:
            end = serve(io.BytesIO(frames(INITIALIZE, INITIALIZED, proposal, tool('propose', 2,
                        proposal_id='must-not-run', envelope=catalog_fixture('garden')[2]))), writer, session)
            self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(end.reason, 'output_failed')
        self.assertTrue(end.outcome_unknown)
        self.assertEqual(len(self.w.proposals('garden', self.ctx['garden'], 'alice')), 1)
        self.assertEqual(self.service('garden')._command('request_list', owner='alice'), [])
        client = self.stream('garden', 'alice')
        answer = client.call('proposal_status', proposal_id='durable')
        self.assertEqual(json.loads(answer['result']['content'][0]['text'])['state'], 'awaiting_owner_review')
        for _ in range(3):
            self.assertFalse(client.call('propose', proposal_id='durable', envelope=catalog_fixture('garden')[2])['result']['isError'])
        client.send(frames(tool('propose', client.seq, proposal_id='durable', envelope=catalog_fixture('garden')[2])))
        self.assertEqual(client.receive()['error']['code'], -32600)
        self.pair('garden')
        card = self.w.import_proposal('garden', self.ctx['garden'], 'alice', 'durable')
        self.resolve('garden', card, 'decline')
        answer = client.call('propose', proposal_id='alias', envelope=catalog_fixture('garden')[2])
        self.assertEqual(json.loads(answer['result']['content'][0]['text'])['state'], 'declined')
        self.assertEqual(self.w.import_proposal('garden', self.ctx['garden'], 'alice', 'alias')['request_id'], card['request_id'])
        self.assertEqual(self.summary('garden')['receiver_receipts'], 0)
        # The unprocessed trailing call really was not dispatched.
        self.assertTrue(client.call('proposal_status', proposal_id='must-not-run')['result']['isError'])


if __name__ == '__main__': unittest.main()
