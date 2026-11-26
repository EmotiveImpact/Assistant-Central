"""Only this launcher, its synthetic stdio client and synthetic I/O unit seams."""
import asyncio
from contextlib import nullcontext
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import stat
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('synthetic_launcher', ROOT / 'launcher.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
FIXTURE = json.loads((ROOT / 'public_fixture.json').read_text())
TEXT = FIXTURE['proposal_text']


def request(rid, method, params=None):
    value = {'jsonrpc': '2.0', 'id': rid, 'method': method}
    if params is not None:
        value['params'] = params
    return value


def init(rid=1, version='2025-11-25'):
    return request(rid, 'initialize', {'protocolVersion': version, 'capabilities': {},
                    'clientInfo': {'name': 'synthetic-client', 'version': '1'}})


INITIALIZED = {'jsonrpc':'2.0', 'method':'notifications/initialized'}


def call(rid, name, args=None):
    return request(rid, 'tools/call', {'name': name, 'arguments': {} if args is None else args})


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def invoke(data, *, args=(), flags=('-I', '-B')):
    result = subprocess.run([sys.executable, *flags, str(ROOT / 'launcher.py'), *args],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={'SYNTHETIC_ENV_CANARY': 'DO_NOT_LOG_THIS_SENTINEL'}, timeout=20)
    return result


def exchange(values):
    result = invoke(b''.join(encode(v) for v in values))
    return result, [json.loads(line) for line in result.stdout.splitlines()]


class StdioIntegration(unittest.TestCase):
    def assert_clean(self, result, code=0):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, b'' if code == 0 else launcher.DIAGNOSTICS[code])

    def test_initialize_three_tools_empty_inbox_propose_replay_status(self):
        canonical = lambda x: json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        binding = {'schema': 'offline-exact-text-proposal/1', 'actor': FIXTURE['actor'],
                   'task': FIXTURE['task'], 'public': FIXTURE['public']}
        proposal_id = hashlib.sha256(canonical({'binding': binding, 'text': TEXT})).hexdigest()
        result, replies = exchange([init(), INITIALIZED, request(2, 'tools/list'),
            call(3, 'processed_inbox'), call(4, 'propose', {'text': TEXT}),
            call(5, 'propose', {'text': TEXT}), call(6, 'proposal_status', {'proposal_id': proposal_id}),
            call(7, 'processed_inbox')])
        self.assert_clean(result)
        self.assertEqual(replies[0]['result']['protocolVersion'], '2025-11-25')
        self.assertEqual([t['name'] for t in replies[1]['result']['tools']],
                         ['propose', 'proposal_status', 'processed_inbox'])
        self.assertEqual(replies[2]['result']['structuredContent'], launcher.EMPTY_INBOX)
        expected = {'proposal_id': proposal_id, 'content_digest': hashlib.sha256(canonical({'text': TEXT})).hexdigest(),
                    'state': 'pending', 'operation_id': None, 'command_digest': None, 'message_id': None,
                    'message_digest': None, 'packet_digest': None, 'evidence_basis': 'local unsigned proposal'}
        for reply in replies[3:6]:
            self.assertEqual(reply['result']['structuredContent'], expected)
        self.assertEqual(replies[6]['result']['structuredContent'], launcher.EMPTY_INBOX)

    def test_arbitrary_text_selectors_owner_tools_rejected(self):
        sentinel = 'PRIVATE_LOOKING_SYNTHETIC_SENTINEL_DO_NOT_LOG'
        values = [init(), INITIALIZED, call(2, 'propose', {'text': sentinel}),
            call(3, 'propose', {'text': TEXT, 'actor': 'bob'}),
            call(4, 'processed_inbox', {'actor': 'bob'}),
            call(5, 'proposal_status', {'proposal_id': '0'*64, 'store': '/tmp/private'}),
            call(6, 'approve_send', {}), call(7, 'publish', {}),
            call(8, 'propose', {'text': TEXT + ' '}), call(9, 'processed_inbox')]
        result, replies = exchange(values)
        self.assert_clean(result)
        self.assertTrue(replies[1]['result']['isError'])
        for reply in replies[2:7]:
            self.assertEqual(reply['error']['code'], -32602)
        self.assertTrue(replies[7]['result']['isError'])
        self.assertEqual(replies[8]['result']['structuredContent'], launcher.EMPTY_INBOX)
        self.assertNotIn(sentinel.encode(), result.stdout + result.stderr)
        self.assertNotIn(b'DO_NOT_LOG_THIS_SENTINEL', result.stdout + result.stderr)

    def test_protocol_invalid_duplicate_ids_and_unknown_method(self):
        result, replies = exchange([request(1, 'tools/list'), init(2), INITIALIZED,
             request(3, 'ping'), request(3, 'ping'), request(4, 'owner/release'),
             {'jsonrpc':'2.0','id':5,'method':'ping','extra':None},
             request(5, 'ping'), request(6, 'ping', None)])
        self.assert_clean(result)
        self.assertEqual([v.get('error', {}).get('code') for v in replies],
            [-32600, None, None, -32600, -32601, -32600, -32600, None])

    def test_malformed_utf8_duplicate_keys_and_notification_silence(self):
        bad = [b'\xff\n', b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
               b'{"jsonrpc":"2.0","method":"ping","params":null}\n', b'[]\n', b'\n']
        result = invoke(b''.join(bad))
        self.assert_clean(result)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r['error']['code'] for r in replies], [-32700, -32700, -32600, -32700])
        self.assertTrue(all(r['id'] is None for r in replies))

    def test_record_bound_and_no_dispatch_after_oversized(self):
        result = invoke(b'x'*16385+b'\n'+encode(init()))
        self.assert_clean(result, 65)
        self.assertEqual([json.loads(line)['error']['code'] for line in result.stdout.splitlines()], [-32700])
        result = invoke(b' '*16384+b'\n')
        self.assert_clean(result)
        self.assertEqual(json.loads(result.stdout)['error']['code'], -32700)

    def test_normal_eof_partial_eof_and_record_budget(self):
        self.assert_clean(invoke(b''))
        result = invoke(encode(init())[:-1])
        self.assert_clean(result, 65)
        self.assertEqual(result.stdout, b'')
        result = invoke(b'\n'*160)
        self.assert_clean(result, 65)
        self.assertEqual(len(result.stdout.splitlines()), 160)

    def test_duplicate_propose_id_does_not_hide_replay_contract(self):
        result, replies = exchange([init(), INITIALIZED, call(2,'propose',{'text':TEXT}),
                                  call(2,'propose',{'text':TEXT}), call(3,'propose',{'text':TEXT})])
        self.assert_clean(result)
        self.assertEqual(replies[2]['error']['code'], -32600)
        self.assertEqual(replies[1]['result'], replies[3]['result'])

    def test_fixed_startup_failures(self):
        for flags, args in [(('-B',), ()), (('-I',), ()), (('-I','-B'), ('--fixture', 'SECRET_SENTINEL'))]:
            result = invoke(b'', flags=flags, args=args)
            self.assert_clean(result, 64)
            self.assertEqual(result.stdout, b'')

    def test_sdk_stdio_client_session(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def run():
            params = StdioServerParameters(command=sys.executable,
                args=['-I', '-B', str(ROOT / 'launcher.py')], env={})
            with tempfile.TemporaryFile(mode='w+') as errors:
                async with stdio_client(params, errlog=errors) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                        result = await session.initialize()
                        self.assertEqual(result.protocolVersion, '2025-11-25')
                        listed = await session.list_tools()
                        self.assertEqual([tool.name for tool in listed.tools], ['propose','proposal_status','processed_inbox'])
                        self.assertEqual((await session.call_tool('processed_inbox', {})).structuredContent, launcher.EMPTY_INBOX)
                        proposal = await session.call_tool('propose', {'text': TEXT})
                        status = await session.call_tool('proposal_status', {'proposal_id':proposal.structuredContent['proposal_id']})
                        self.assertEqual(status.structuredContent, proposal.structuredContent)
                        self.assertEqual((await session.call_tool('propose', {'text':TEXT})).structuredContent, proposal.structuredContent)
                        self.assertTrue((await session.call_tool('propose', {'text':'not allowlisted'})).isError)
                errors.seek(0)
                self.assertEqual(errors.read(), '')
        anyio.run(run)


class FakeAnyio:
    class EndOfStream(Exception): pass
    def __init__(self): self.read_waits = self.write_waits = 0
    def fail_after(self, seconds): return nullcontext()
    async def wait_readable(self, fd): self.read_waits += 1
    async def wait_writable(self, fd): self.write_waits += 1


class AdapterUnitTests(unittest.TestCase):
    def test_partial_writes_complete_exactly_once(self):
        api = FakeAnyio()
        accepted = bytearray()
        actions = iter([2, BlockingIOError(), InterruptedError(), 1, 3])
        calls = []
        def write(fd, value):
            calls.append(bytes(value))
            action = next(actions)
            if isinstance(action, Exception): raise action
            accepted.extend(value[:action])
            return action
        self.assertIsNone(asyncio.run(launcher.StdioWriter(api, write=write).send(b'abcdef')))
        self.assertEqual(bytes(accepted), b'abcdef')
        self.assertEqual(calls, [b'abcdef',b'cdef',b'cdef',b'cdef',b'def'])
        self.assertEqual(api.write_waits, 2)

    def test_partial_failure_no_replay(self):
        calls = []
        def write(fd, value):
            calls.append(bytes(value))
            if len(calls) == 1: return 2
            raise BrokenPipeError('DO_NOT_LOG')
        with self.assertRaises(BrokenPipeError):
            asyncio.run(launcher.StdioWriter(FakeAnyio(), write=write).send(b'abcdef'))
        self.assertEqual(calls, [b'abcdef', b'cdef'])

    def test_writer_rejects_bad_counts_and_bad_payloads(self):
        for count in (0,-1,7,None,True):
            with self.subTest(count=count), self.assertRaises(launcher.PilotFailure):
                asyncio.run(launcher.StdioWriter(FakeAnyio(),write=lambda f,d:count).send(b'abcdef'))
        for payload in (b'', 'text', b'x'*32769):
            with self.subTest(payload_type=type(payload)), self.assertRaises(launcher.PilotFailure):
                asyncio.run(launcher.StdioWriter(FakeAnyio(),write=lambda f,d:len(d)).send(payload))

    def test_reader_wait_eof_and_contract(self):
        api = FakeAnyio()
        actions = iter([BlockingIOError(), b'abc', b''])
        def read(fd, size):
            result = next(actions)
            if isinstance(result, Exception): raise result
            return result
        reader = launcher.StdioReader(api, read=read)
        self.assertEqual(asyncio.run(reader.receive(4)), b'abc')
        with self.assertRaises(api.EndOfStream): asyncio.run(reader.receive(4))
        self.assertEqual(api.read_waits, 1)
        with self.assertRaises(launcher.PilotFailure): asyncio.run(reader.receive(4097))
        for value in ('bad', b'long', None, False, 0):
            with self.assertRaises(launcher.PilotFailure):
                asyncio.run(launcher.StdioReader(api,read=lambda f,s:value).receive(2))

    def test_fixed_diagnostics_no_dynamic_content_no_retry(self):
        for code, expected in launcher.DIAGNOSTICS.items():
            writes = []
            launcher.diagnostic(code, write=lambda fd,data:writes.append((fd,data)))
            self.assertEqual(writes, [(2,expected)])
            self.assertLessEqual(len(expected), 80)
        writes = []
        def bad(fd,data):
            writes.append(data)
            raise BrokenPipeError('NO_LOG_SENTINEL')
        launcher.diagnostic(74, write=bad)
        self.assertEqual(writes, [launcher.DIAGNOSTICS[74]])

    def test_guard_denies_external_actions_allows_local_wakeup_shape(self):
        guard = launcher.Guard()
        guard.audit('socket.__new__', (None,1,1,0))
        guard.audit('sqlite3.connect', (':memory:',))
        for event,args in [('socket.connect',()),('socket.bind',()),('socket.getaddrinfo',()),
                           ('socket.__new__',(None,2,1,0)),('subprocess.Popen',()),
                           ('os.fork',()),('sqlite3.connect',('/tmp/disallowed',))]:
            with self.assertRaises(launcher.PilotFailure): guard.audit(event,args)
        for name in ('independent_peer.fixture','independent_peer.worker','independent_peer.pipes','independent_peer.endpoint'):
            with self.assertRaises(launcher.PilotFailure): guard.import_guard().find_spec(name)
        self.assertEqual(guard.counts, {'blocked':11,'local_unix_socket_creations':1,'memory_databases':1})

    def test_exact_allowlist_precedes_facade_write(self):
        class StandinFacade:
            def __init__(self, store): self.saved=[]
            def propose(self,args): self.saved.append(args['text']); return {'synthetic':True}
            def processed_inbox(self,args): return dict(launcher.EMPTY_INBOX)
        facade = launcher.synthetic_facade(None,FIXTURE,StandinFacade)
        for args in ({'text':TEXT+' '},{'text':'SYNTHETIC: arbitrary'},{'text':TEXT,'actor':'bob'}, {'text':['bad']}):
            with self.assertRaises(launcher.PilotFailure): facade.propose(args)
        self.assertEqual(facade.saved, [])
        self.assertEqual(facade.propose({'text':TEXT}), {'synthetic':True})
        self.assertEqual(facade.saved, [TEXT])

    def test_manifest_and_public_fixture_are_verified(self):
        baseline, fixture, count = launcher.verify_inputs()
        self.assertEqual(count,67)
        self.assertEqual(fixture,FIXTURE)
        self.assertEqual(baseline, ROOT/'baseline_r4')

    def test_bad_manifest_and_fixture_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            shutil.copytree(ROOT/'baseline_r4',root/'baseline_r4')
            shutil.copyfile(ROOT/'public_fixture.json',root/'public_fixture.json')
            fixture=root/'public_fixture.json'
            fixture.write_bytes(fixture.read_bytes()+b' ')
            with self.assertRaises(launcher.PilotFailure): launcher.verify_inputs(root)
            shutil.copyfile(ROOT/'public_fixture.json',fixture)
            manifest=root/'baseline_r4'/'RAW_SOURCE_MANIFEST.json'
            manifest.write_text('{}')
            with self.assertRaises(launcher.PilotFailure): launcher.verify_inputs(root)

    def test_unmanifested_imports_and_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            shutil.copytree(ROOT/'baseline_r4',root/'baseline_r4')
            shutil.copyfile(ROOT/'public_fixture.json',root/'public_fixture.json')
            for relative in ('sqlite3.py','baseline_r3/shadow.pyc','baseline_r3/baseline_r2/shadow.so'):
                path=root/'baseline_r4'/relative
                path.write_bytes(b'NOT EXECUTABLE TEST SENTINEL')
                with self.assertRaises(launcher.PilotFailure): launcher.verify_inputs(root)
                path.unlink()
            linked=root/'baseline_r4'/'extra_package'
            linked.symlink_to(ROOT/'baseline_r4'/'raw_bridge', target_is_directory=True)
            with self.assertRaises(launcher.PilotFailure): launcher.verify_inputs(root)

    def test_runtime_escape_is_uncertain_not_startup_rejection(self):
        with patch.object(launcher,'quiet_python_streams'), \
             patch.object(launcher.sys,'argv',[str(ROOT/'launcher.py')]), \
             patch.object(launcher.sys,'flags',SimpleNamespace(isolated=1,dont_write_bytecode=1)), \
             patch.object(launcher.os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFIFO)), \
             patch.object(launcher.os,'set_blocking'), \
             patch.object(launcher,'verify_inputs',return_value=(ROOT/'baseline_r4',FIXTURE,67)), \
             patch.object(launcher,'run_pilot',side_effect=RuntimeError('NO_LOG')), \
             patch.object(launcher,'diagnostic') as diagnostic:
            self.assertEqual(launcher.main(),70)
            diagnostic.assert_called_once_with(70)


if __name__ == '__main__':
    unittest.main()
