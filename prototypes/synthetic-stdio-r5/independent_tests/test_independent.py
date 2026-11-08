"""Ordinary one-process stdio and synthetic adapter contracts only.

No peer process, cross-lane lifecycle, reused-descriptor, native host, network,
key-generation, installation, or credential operation is part of these tests.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
COLOCATED_ROOT = HERE.parent
if (COLOCATED_ROOT / 'launcher.py').is_file() and (COLOCATED_ROOT / 'public_fixture.json').is_file():
    ROOT = COLOCATED_ROOT
else:
    if not os.environ.get('STDIO_R5_ROOT'):
        raise RuntimeError('Standalone review requires explicit STDIO_R5_ROOT.')
    ROOT = Path(os.environ['STDIO_R5_ROOT']).resolve(strict=True)
if not (ROOT / 'baseline_r4' / 'RAW_SOURCE_MANIFEST.json').is_file():
    raise RuntimeError('The selected release lacks the frozen baseline manifest.')
SPEC = importlib.util.spec_from_file_location('independently_reviewed_r5_launcher', ROOT / 'launcher.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
FIXTURE = json.loads((ROOT / 'public_fixture.json').read_text())
TEXT = FIXTURE['proposal_text']


def request(rid, method, params=None):
    result = {'jsonrpc': '2.0', 'id': rid, 'method': method}
    if params is not None:
        result['params'] = params
    return result


def initialize(rid=1, version='2025-11-25', **extras):
    params = {'protocolVersion': version, 'capabilities': {},
              'clientInfo': {'name': 'independent-synthetic-review', 'version': '1'}}
    params.update(extras)
    return request(rid, 'initialize', params)


READY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}


def tool(rid, name, arguments=None):
    return request(rid, 'tools/call', {'name': name, 'arguments': {} if arguments is None else arguments})


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def invoke(data, root=ROOT, **kwargs):
    return subprocess.run([sys.executable, '-I', '-B', str(root / 'launcher.py')],
                          input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={'REVIEW_SYNTHETIC_ENV': 'SYNTHETIC_REVIEW_NO_ECHO'},
                          timeout=20, **kwargs)


def exchange(values):
    result = invoke(b''.join(encode(value) for value in values))
    return result, [json.loads(line) for line in result.stdout.splitlines()]


class ProtocolChecks(unittest.TestCase):
    def clean(self, result, code=0):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, launcher.DIAGNOSTICS.get(code, b''))

    def test_all_four_supported_versions_negotiate_exactly(self):
        for version in ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'):
            with self.subTest(version=version):
                result, replies = exchange([initialize(version=version), READY, request(2, 'tools/list')])
                self.clean(result)
                self.assertEqual(replies[0]['result']['protocolVersion'], version)
                self.assertEqual([t['name'] for t in replies[1]['result']['tools']],
                                 ['propose', 'proposal_status', 'processed_inbox'])

    def test_unsupported_version_has_no_fallback_and_recovery_needs_new_id(self):
        result, replies = exchange([initialize(version='2099-01-01'), initialize(rid=2), READY,
                                    tool(3, 'processed_inbox')])
        self.clean(result)
        self.assertEqual(replies[0]['error']['code'], -32602)
        self.assertEqual(replies[1]['result']['protocolVersion'], '2025-11-25')
        self.assertEqual(replies[2]['result']['structuredContent'], launcher.EMPTY_INBOX)

    def test_capabilities_and_metadata_do_not_expand_or_echo(self):
        sentinel = 'SYNTHETIC_PRIVATE_LOOKING_METADATA_NEVER_ECHO'
        init = initialize(capabilities={'roots': {'listChanged': True}, 'sampling': {}, 'elicitation': {}},
                          clientInfo={'name': sentinel, 'version': sentinel}, _meta={'sentinel': sentinel})
        result, replies = exchange([init, READY, request(2, 'tools/list', {'_meta': {'sentinel': sentinel}})])
        self.clean(result)
        self.assertEqual(set(replies[0]['result']['capabilities']), {'tools'})
        self.assertEqual(replies[0]['result']['capabilities']['tools'], {'listChanged': False})
        self.assertNotIn(sentinel.encode(), result.stdout + result.stderr)
        self.assertNotIn(b'SYNTHETIC_REVIEW_NO_ECHO', result.stdout + result.stderr)

    def test_other_mcp_surfaces_are_rejected_without_losing_ready_state(self):
        names = ('resources/list', 'prompts/list', 'sampling/createMessage', 'roots/list',
                 'elicitation/create', 'logging/setLevel', 'tasks/get', 'owner/approve')
        values = [initialize(), READY]
        values += [request(index + 2, name, {}) for index, name in enumerate(names)]
        values += [tool(20, 'processed_inbox')]
        result, replies = exchange(values)
        self.clean(result)
        self.assertEqual([v['error']['code'] for v in replies[1:-1]], [-32601] * len(names))
        self.assertEqual(replies[-1]['result']['structuredContent'], launcher.EMPTY_INBOX)

    def test_json_escaped_exact_text_and_crlf_use_same_proposal(self):
        prefix = encode(initialize()) + encode(READY)
        escaped_text = ''.join('\\u%04x' % ord(char) for char in TEXT)
        escaped = ('{"jsonrpc":"2.0","id":2,"method":"tools/call","params":'
                   '{"name":"propose","arguments":{"text":"' + escaped_text + '"}}}\r\n').encode()
        result = invoke(prefix + escaped + encode(tool(3, 'propose', {'text': TEXT})))
        self.clean(result)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[1]['result'], replies[2]['result'])
        self.assertEqual(replies[1]['result']['structuredContent']['state'], 'pending')

    def test_text_near_misses_are_rejected_and_later_exact_text_succeeds(self):
        variants = [TEXT + '\n', '\ufeff' + TEXT, TEXT.lower(), TEXT.replace(' ', '\u00a0', 1), TEXT + '\x00']
        values = [initialize(), READY]
        values += [tool(index + 2, 'propose', {'text': text}) for index, text in enumerate(variants)]
        values += [tool(20, 'propose', {'text': TEXT}), tool(21, 'processed_inbox')]
        result, replies = exchange(values)
        self.clean(result)
        self.assertTrue(all(reply['result']['isError'] for reply in replies[1:-2]))
        self.assertEqual(replies[-2]['result']['structuredContent']['state'], 'pending')
        self.assertEqual(replies[-1]['result']['structuredContent'], launcher.EMPTY_INBOX)

    def test_proposal_is_not_persistent_across_clean_new_sessions(self):
        result, replies = exchange([initialize(), READY, tool(2, 'propose', {'text': TEXT})])
        self.clean(result)
        proposal = replies[-1]['result']['structuredContent']
        result, replies = exchange([initialize(), READY,
            tool(2, 'proposal_status', {'proposal_id': proposal['proposal_id']}),
            tool(3, 'processed_inbox'), tool(4, 'propose', {'text': TEXT})])
        self.clean(result)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertEqual(replies[2]['result']['structuredContent'], launcher.EMPTY_INBOX)
        self.assertEqual(replies[3]['result']['structuredContent'], proposal)

    def test_partial_tail_is_not_dispatched_after_prior_valid_proposal(self):
        data = b''.join(map(encode, [initialize(), READY, tool(2, 'propose', {'text': TEXT})]))
        result = invoke(data + encode(tool(3, 'propose', {'text': TEXT}))[:-1])
        self.clean(result, 65)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([v['id'] for v in replies], [1, 2])
        self.assertEqual(replies[-1]['result']['structuredContent']['state'], 'pending')

    def test_invalid_non_scalar_unicode_is_rejected_without_echo(self):
        data = encode(initialize()) + encode(READY)
        data += b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"propose","arguments":{"text":"\\ud800"}}}\n'
        data += encode(tool(3, 'processed_inbox'))
        result = invoke(data)
        self.clean(result)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[1]['error']['code'], -32600)
        self.assertEqual(replies[-1]['result']['structuredContent'], launcher.EMPTY_INBOX)
        self.assertNotIn(b'ud800', result.stdout + result.stderr)

    def test_regular_file_stdin_or_stdout_is_rejected(self):
        command = [sys.executable, '-I', '-B', str(ROOT / 'launcher.py')]
        with tempfile.TemporaryFile() as regular:
            result = subprocess.run(command, stdin=regular, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=20)
            self.clean(result, 64)
            self.assertEqual(result.stdout, b'')
        with tempfile.TemporaryFile() as regular:
            result = subprocess.run(command, input=b'', stdout=regular,
                                    stderr=subprocess.PIPE, timeout=20)
            self.clean(result, 64)
            regular.seek(0)
            self.assertEqual(regular.read(), b'')


class SyntheticAdapterChecks(unittest.TestCase):
    def test_actual_anyio_receive_timeout_sets_flag(self):
        import anyio
        class Waits:
            EndOfStream = anyio.EndOfStream
            fail_after = staticmethod(anyio.fail_after)
            @staticmethod
            async def wait_readable(fd):
                await anyio.sleep_forever()
        def blocked(fd, size):
            raise BlockingIOError()
        reader = launcher.StdioReader(Waits(), read=blocked)
        with patch.object(launcher, 'IDLE_SECONDS', 0.03):
            with self.assertRaises(launcher.PilotFailure):
                anyio.run(reader.receive, 16)
        self.assertTrue(reader.idle_timeout)

    def test_actual_anyio_partial_write_timeout_never_replays_prefix(self):
        import anyio
        class Waits:
            fail_after = staticmethod(anyio.fail_after)
            @staticmethod
            async def wait_writable(fd):
                await anyio.sleep_forever()
        writes = []
        def blocked_after_prefix(fd, value):
            writes.append(bytes(value))
            if len(writes) == 1:
                return 2
            raise BlockingIOError()
        writer = launcher.StdioWriter(Waits(), write=blocked_after_prefix)
        with patch.object(launcher, 'WRITE_SECONDS', 0.03):
            with self.assertRaises(TimeoutError):
                anyio.run(writer.send, b'abcdef')
        self.assertEqual(writes, [b'abcdef', b'cdef'])

    def test_falsy_nonbytes_and_bool_sizes_are_contract_errors_not_eof(self):
        import anyio
        for value in (None, False, 0, '', bytearray()):
            with self.subTest(value=repr(value)), self.assertRaises(launcher.PilotFailure):
                anyio.run(launcher.StdioReader(anyio, read=lambda fd, size: value).receive, 1)
        for size in (True, False, 0, -1, 4097, 1.0):
            with self.subTest(size=size), self.assertRaises(launcher.PilotFailure):
                anyio.run(launcher.StdioReader(anyio, read=lambda fd, size: b'x').receive, size)
        with self.assertRaises(anyio.EndOfStream):
            anyio.run(launcher.StdioReader(anyio, read=lambda fd, size: b'').receive, 1)

    def test_maximum_sized_write_advances_to_complete_once(self):
        import anyio
        accepted = bytearray()
        def small_write(fd, value):
            count = min(997, len(value))
            accepted.extend(value[:count])
            return count
        payload = b'q' * launcher.WRITE_CAP
        anyio.run(launcher.StdioWriter(anyio, write=small_write).send, payload)
        self.assertEqual(accepted, payload)


class IntegrityChecks(unittest.TestCase):
    def copy_release(self, target):
        shutil.copytree(ROOT / 'baseline_r4', target / 'baseline_r4')
        shutil.copyfile(ROOT / 'public_fixture.json', target / 'public_fixture.json')
        shutil.copyfile(ROOT / 'launcher.py', target / 'launcher.py')

    def test_altered_referenced_codec_fails_before_protocol_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.copy_release(target)
            source = target / 'baseline_r4' / 'raw_bridge' / 'codec.py'
            source.write_bytes(source.read_bytes() + b'\n# synthetic integrity mutation\n')
            result = invoke(encode(initialize()), root=target)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (64, b'', launcher.DIAGNOSTICS[64]))

    def test_missing_referenced_codec_fails_before_protocol_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.copy_release(target)
            (target / 'baseline_r4' / 'raw_bridge' / 'codec.py').unlink()
            result = invoke(encode(initialize()), root=target)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (64, b'', launcher.DIAGNOSTICS[64]))

    def test_internal_same_bytes_symlink_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.copy_release(target)
            source = target / 'baseline_r4' / 'raw_bridge' / 'codec.py'
            opaque_copy = target / 'baseline_r4' / 'raw_bridge' / 'codec-data.txt'
            opaque_copy.write_bytes(source.read_bytes())
            source.unlink()
            source.symlink_to(opaque_copy.name)
            with self.assertRaises(launcher.PilotFailure):
                launcher.verify_inputs(target)

    def test_empty_module_shadow_and_generated_bytecode_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.copy_release(target)
            for name in ('anyio.py', 'baseline_r3/mcp.py', 'baseline_r3/baseline_r2/extra.pyd', '__pycache__/extra.pyc'):
                source = target / 'baseline_r4' / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b'')
                with self.subTest(name=name), self.assertRaises(launcher.PilotFailure):
                    launcher.verify_inputs(target)
                source.unlink()

    def test_selected_checkout_and_frozen_input_hashes_match(self):
        baseline, fixture, count = launcher.verify_inputs(ROOT)
        self.assertEqual(launcher.ROOT, ROOT)
        self.assertEqual(baseline, ROOT / 'baseline_r4')
        self.assertEqual(count, 67)
        self.assertEqual(fixture, FIXTURE)
        self.assertEqual(hashlib.sha256((baseline / 'RAW_SOURCE_MANIFEST.json').read_bytes()).hexdigest(),
                         launcher.R4_MANIFEST_SHA256)
        self.assertEqual(hashlib.sha256((ROOT / 'public_fixture.json').read_bytes()).hexdigest(),
                         launcher.FIXTURE_SHA256)


if __name__ == '__main__':
    unittest.main()
