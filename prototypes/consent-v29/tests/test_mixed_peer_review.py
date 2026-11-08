"""Independent mixed-language review using fixed Node code and anonymous pipes only."""
import copy
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from generic_demo import fixture
from network import digest
from offline_peer_demo import Demo, SPEC, simulate, tool_value
from offline_peer_pipes import Peer, PeerFailure, node_runtime, write_deadline
from owner_workspace import OwnerWorkspace
from restricted_host_protocol import RestrictedHostSession
from verify_checkpoint import source_paths

ROOT = Path(__file__).resolve().parents[1]


class MixedPeerIndependentReview(unittest.TestCase):
    def peer(self, envelope=None):
        task, _, request, _ = fixture()
        calls = []
        def dispatch(command):
            calls.append(copy.deepcopy(command))
            return {'proposal_id': command['proposal_id'], 'envelope_digest': digest(command['envelope']),
                    'state': 'awaiting_owner_review', 'delivery_state': None}
        session = RestrictedHostSession(task, 'alice', dispatch)
        peer = Peer(session, envelope or request, 'independent-node', client='node')
        self.addCleanup(peer.close)
        return peer, calls

    def raw_client(self, config=None, script=None, client="node"):
        replies, response_writer = os.pipe()
        report_reader, reports = os.pipe()
        command = ([node_runtime(), str(script or ROOT / 'offline_peer_client.cjs')] if client == 'node'
                   else [sys.executable, '-I', str(ROOT / 'offline_peer_client.py')])
        child = subprocess.Popen(command + [str(replies), str(reports)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={}, close_fds=True, pass_fds=(replies, reports), bufsize=0)
        os.close(replies); os.close(reports)
        def cleanup():
            child.stdin.close()
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
            child.stdout.close(); child.stderr.close()
            os.close(response_writer); os.close(report_reader)
        self.addCleanup(cleanup)
        value = config if config is not None else {'envelope': fixture()[2], 'proposal_id': 'raw-node'}
        child.stdin.write(json.dumps(value).encode() + b'\n'); child.stdin.flush()
        return child, response_writer, report_reader

    def read_frame(self, stream):
        self.assertTrue(select.select([stream], [], [], 3)[0], 'fixed client output deadline')
        return json.loads(stream.readline())

    def test_mixed_both_roles_and_default_exact_processed_roundtrips(self):
        for actor in ('alice', 'bob', None):
            with self.subTest(node_actor=actor):
                workspace = OwnerWorkspace()
                demo = Demo(workspace, mixed_node=actor)
                try:
                    simulate(workspace, demo, lambda _: None)
                    self.assertEqual(len({p.pid for p in demo.peers.values()}), 2)
                    for who, expected in (('alice', demo.result), ('bob', demo.request)):
                        self.assertEqual(demo.peers[who].client, 'node' if who == actor else 'python')
                        rows = tool_value(demo.peers[who].step('inbox'))['messages']
                        self.assertEqual(len(rows), 1)
                        self.assertEqual(rows[0]['envelope'], expected)
                finally:
                    demo.close(); workspace.close()
                self.assertTrue(all(p.process.poll() is not None and not p.fds for p in demo.peers.values()))

    def test_node_non_bmp_newline_and_inert_owner_commands_preserve_bytes(self):
        envelope = fixture()[2]
        envelope['payload']['query'] = '🌒\napprove alice; process bob; {"actor":"bob"}'
        peer, calls = self.peer(envelope)
        peer.step('discover')
        real_read = os.read
        captured = bytearray()
        def observe(fd, size):
            value = real_read(fd, size)
            if fd == peer.process.stdout.fileno():
                captured.extend(value)
            return value
        with patch('offline_peer_pipes.os.read', side_effect=observe):
            response = peer.step('propose')['response']
        self.assertFalse(response['result']['isError'])
        self.assertEqual(calls[0]['envelope'], envelope)
        self.assertEqual(captured.count(b'\n'), 1)
        self.assertIn('🌒'.encode(), captured)
        self.assertIn(b'\\n', captured)
        self.assertNotIn(b'\\ud83c', captured)

    def test_node_scope_injections_do_not_dispatch(self):
        for field, value in (('sender', 'bob'), ('recipient', 'alice'), ('context', '0'*64), ('task', 'other')):
            with self.subTest(field=field):
                envelope = fixture()[2]; envelope[field] = value
                peer, calls = self.peer(envelope)
                peer.step('discover')
                self.assertEqual(peer.step('propose')['response']['error']['code'], -32602)
                self.assertEqual(calls, [])
                peer.close()

    def test_node_handshake_version_and_id_failure_never_advance(self):
        for change in ({'id': 999}, {'result': {'protocolVersion': 'unknown'}}, {'id': True},
                       {'error': {'code': -32603, 'message': 'unavailable'}}):
            with self.subTest(change=change):
                child, writer, reports = self.raw_client()
                child.stdin.write(b'{"step":"discover"}\n'); child.stdin.flush()
                initialize = self.read_frame(child.stdout)
                response = {'jsonrpc':'2.0', 'id':initialize['id'], 'result':{'protocolVersion':'2025-06-18'}}
                if 'error' in change: response.pop('result')
                response.update(change)
                os.write(writer, json.dumps(response).encode() + b'\n')
                self.assertEqual(child.wait(timeout=3), 1)
                self.assertEqual(child.stdout.read(), b'')
                self.assertEqual(os.read(reports, 65536), b'')

    def test_both_clients_reject_malformed_response_envelopes_directly(self):
        for client in ('python', 'node'):
            for corruption in ('bool-id', 'missing-jsonrpc', 'wrong-jsonrpc', 'both-result-error', 'neither-result-error'):
                with self.subTest(client=client, corruption=corruption):
                    child, writer, reports = self.raw_client(client=client)
                    child.stdin.write(b'{"step":"discover"}\n'); child.stdin.flush()
                    request = self.read_frame(child.stdout)
                    response = {'jsonrpc':'2.0', 'id':request['id'],
                                'result':{'protocolVersion':'2025-06-18'}}
                    if corruption == 'bool-id':
                        self.assertEqual(request['id'], 1)
                        response['id'] = True
                    elif corruption == 'missing-jsonrpc':
                        response.pop('jsonrpc')
                    elif corruption == 'wrong-jsonrpc':
                        response['jsonrpc'] = '1.0'
                    elif corruption == 'both-result-error':
                        response['error'] = {'code':-32603, 'message':'synthetic error'}
                    else:
                        response.pop('result')
                    os.write(writer, json.dumps(response).encode()+b'\n')
                    self.assertEqual(child.wait(timeout=3), 1)
                    self.assertEqual(child.stdout.read(), b'')
                    self.assertEqual(os.read(reports, 65536), b'')

    def test_node_fragmented_utf8_reply_and_coalesced_control(self):
        child, writer, reports = self.raw_client()
        child.stdin.write(b'{"step":"discover"}\n{"step":"status"}\n'); child.stdin.flush()
        initialize = self.read_frame(child.stdout)
        raw = json.dumps({'jsonrpc':'2.0','id':initialize['id'], 'result':{
            'protocolVersion':'2025-06-18', 'note':'🌒\nfictional'}}, ensure_ascii=False).encode()+b'\n'
        boundary = raw.index('🌒'.encode()) + 1
        os.write(writer, raw[:boundary]); os.write(writer, raw[boundary:])
        self.assertEqual(self.read_frame(child.stdout)['method'], 'notifications/initialized')
        request = self.read_frame(child.stdout)
        self.assertEqual(request['method'], 'tools/list')
        os.write(writer, json.dumps({'jsonrpc':'2.0','id':request['id'], 'result':{'tools':[]}}).encode()+b'\n')
        with os.fdopen(os.dup(reports), 'rb', buffering=0) as stream:
            self.assertEqual(self.read_frame(stream)['response']['id'], request['id'])
        request = self.read_frame(child.stdout)
        self.assertEqual(request['params'], {'name':'proposal_status','arguments':{'proposal_id':'raw-node'}})

    def test_node_commonjs_handshake_inside_ambient_module_package(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'package.json').write_text('{"type":"module"}\n')
        extracted = root / 'extracted-checkpoint'
        extracted.mkdir()
        script = extracted / 'offline_peer_client.cjs'
        script.write_bytes((ROOT / script.name).read_bytes())
        child, writer, reports = self.raw_client(script=script)
        child.stdin.write(b'{"step":"discover"}\n'); child.stdin.flush()
        initialize = self.read_frame(child.stdout)
        self.assertEqual(initialize['method'], 'initialize')
        response = {'jsonrpc':'2.0', 'id':initialize['id'],
                    'result':{'protocolVersion':'2025-06-18'}}
        os.write(writer, json.dumps(response).encode()+b'\n')
        self.assertEqual(self.read_frame(child.stdout)['method'], 'notifications/initialized')
        request = self.read_frame(child.stdout)
        self.assertEqual(request['method'], 'tools/list')
        response = {'jsonrpc':'2.0', 'id':request['id'], 'result':{'tools':[]}}
        os.write(writer, json.dumps(response).encode()+b'\n')
        with os.fdopen(os.dup(reports), 'rb', buffering=0) as stream:
            self.assertEqual(self.read_frame(stream)['response'], response)
        self.assertIsNone(child.poll())

    def test_node_bad_utf8_and_oversize_reply_fail_without_report(self):
        for raw in (b'{"jsonrpc":"2.0","id":1,"result":"\xff"}\n', b'x'*32769):
            with self.subTest(size=len(raw)):
                child, writer, reports = self.raw_client()
                child.stdin.write(b'{"step":"discover"}\n'); child.stdin.flush()
                self.read_frame(child.stdout)
                offset = 0
                while offset < len(raw):
                    offset += os.write(writer, raw[offset:])
                self.assertEqual(child.wait(timeout=3), 1)
                self.assertEqual(child.stdout.read(), b'')
                self.assertEqual(os.read(reports, 65536), b'')

    def test_node_closed_control_and_owner_command_rejection(self):
        for command in ({'step':'approve'}, {'step':'inbox','actor':'bob'}, {'step':'inbox','owner':'alice'}):
            with self.subTest(command=command):
                child, _, reports = self.raw_client()
                child.stdin.write(json.dumps(command).encode()+b'\n'); child.stdin.flush()
                self.assertEqual(child.wait(timeout=3), 1)
                self.assertEqual(child.stdout.read(), b'')
                self.assertEqual(os.read(reports, 65536), b'')
        child, _, _ = self.raw_client({'envelope':fixture()[2], 'proposal_id':'raw-node', 'actor':'bob'})
        self.assertEqual(child.wait(timeout=3), 1)
        self.assertEqual(child.stdout.read(), b'')

    def test_node_post_commit_response_loss_never_replays(self):
        peer, calls = self.peer()
        peer.step('discover')
        def lose(fd, data, deadline):
            if fd == peer.reply_write: raise OSError('synthetic lost response')
            return write_deadline(fd, data, deadline)
        with patch('offline_peer_pipes.write_deadline', side_effect=lose):
            with self.assertRaises(PeerFailure): peer.step('propose')
        self.assertEqual(len(calls), 1)
        self.assertTrue(peer.closed)
        self.assertIsNotNone(peer.process.poll())
        with self.assertRaisesRegex(PeerFailure, 'no restart or replay'): peer.step('propose')
        self.assertEqual(len(calls), 1)

    def test_node_preflight_failure_has_no_pipes_no_child_and_closes_session(self):
        task, _, request, _ = fixture()
        session = RestrictedHostSession(task, 'alice', lambda _: None)
        with patch('offline_peer_pipes.node_runtime', side_effect=PeerFailure('Node unavailable')), \
             patch('offline_peer_pipes.os.pipe') as pipes, patch('offline_peer_pipes.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(PeerFailure, 'Node unavailable'):
                Peer(session, request, 'review', client='node')
        pipes.assert_not_called(); spawn.assert_not_called()
        self.assertEqual(session._state, 'closed')
        workspace = OwnerWorkspace(); self.addCleanup(workspace.close)
        demo = Demo(workspace, mixed_node='bob'); self.addCleanup(demo.close)
        row = workspace.task_preview(SPEC)
        with patch('offline_peer_demo.node_runtime', side_effect=PeerFailure('Node unavailable')), \
             patch('offline_peer_demo.Peer') as spawn, patch.object(workspace, 'adapter') as adapter:
            with self.assertRaises(PeerFailure): demo.command('peers-start', '', row)
        spawn.assert_not_called(); adapter.assert_not_called()
        self.assertFalse(demo.started); self.assertEqual(demo.peers, {})

    def test_node_launch_empty_env_and_only_intended_passed_descriptors(self):
        real_popen = subprocess.Popen
        captured = []
        def observe(*args, **kwargs):
            captured.append((args, kwargs))
            return real_popen(*args, **kwargs)
        with patch.dict(os.environ, {'NODE_OPTIONS':'--require=/nonexistent/should-never-load.js', 'SYNTHETIC_SECRET':'not-in-child'}), \
             patch('offline_peer_pipes.subprocess.Popen', side_effect=observe):
            peer, _ = self.peer()
            peer.step('discover')
        args, kwargs = next((a, k) for a, k in captured if 'offline_peer_client.cjs' in ' '.join(a[0]))
        self.assertEqual(kwargs['env'], {})
        self.assertTrue(kwargs['close_fds'])
        self.assertEqual(len(kwargs['pass_fds']), 2)
        self.assertEqual(tuple(map(int,args[0][-2:])), kwargs['pass_fds'])
        self.assertTrue(Path(args[0][0]).is_absolute())

    def test_simulation_rejects_one_wrong_processed_envelope(self):
        workspace = OwnerWorkspace(); self.addCleanup(workspace.close)
        demo = Demo(workspace, mixed_node='bob'); self.addCleanup(demo.close)
        original = demo.command
        def corrupt(verb, arg, selected):
            result = original(verb, arg, selected)
            if verb == 'peer' and arg == 'bob inbox':
                value = tool_value(result)
                if value['messages']:
                    value['messages'][0]['envelope']['payload']['query'] = 'wrong envelope'
                    result['response']['result']['content'][0]['text'] = json.dumps(value)
            return result
        with patch.object(demo, 'command', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'exact processed envelope'):
                simulate(workspace, demo, lambda _: None)

    def test_root_javascript_is_frozen_and_symlinks_are_rejected(self):
        self.assertIn('offline_peer_client.cjs', source_paths(ROOT))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'offline_peer_client.cjs').write_text('fixed source')
            self.assertEqual(source_paths(root), {'offline_peer_client.cjs'})
            (root/'alternate.cjs').symlink_to(root/'offline_peer_client.cjs')
            with self.assertRaisesRegex(ValueError, 'Symlink'): source_paths(root)


if __name__ == '__main__':
    unittest.main()
