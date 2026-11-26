"""Offline Python/Node evidence only; fixed real children and synthetic owners."""
import copy
from contextlib import closing
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests import test_offline_peer_demo as baseline
from tests import test_offline_peer_review as faults
from generic_demo import fixture
from network import digest
from offline_peer_demo import Demo, SPEC, simulate, tool_value
from offline_peer_pipes import Peer, PeerFailure, node_runtime, write_deadline
from restricted_host_protocol import RestrictedHostSession, MAX_INPUT
from verify_checkpoint import source_paths
from tests import test_verify_checkpoint as verifier_tests


class NodeAliceDemoTests(baseline.OfflinePeerDemoTests):
    def setUp(self):
        super().setUp()
        self.demo.mixed_node = 'alice'


class NodeBobDemoTests(baseline.OfflinePeerDemoTests):
    def setUp(self):
        super().setUp()
        self.demo.mixed_node = 'bob'


class NodeTransportTests(faults.OfflinePeerIndependentReview):
    # Reuse all existing supervisor fault cases against the independent Node client.
    # The two tests that explicitly construct Peer directly still test the default.
    def make_peer(self, callback=None, envelope=None):
        with patch('tests.test_offline_peer_review.Peer',
                   side_effect=lambda *args, **kwargs: Peer(*args, **kwargs, client='node')):
            return super().make_peer(callback, envelope)


class MixedPeerAdditionalTests(unittest.TestCase):
    def peer(self, client='node', envelope=None, callback=None):
        task, _, request, _ = fixture()
        calls = []
        def dispatch(command):
            calls.append(copy.deepcopy(command))
            if callback:
                return callback(command)
            return {'proposal_id': command['proposal_id'],
                    'envelope_digest': digest(command.get('envelope', envelope or request)),
                    'state': 'awaiting_owner_review', 'delivery_state': None}
        session = RestrictedHostSession(task, 'alice', dispatch)
        peer = Peer(session, envelope or request, 'mixed-proposal', client=client, timeout=.5)
        self.addCleanup(peer.close)
        return peer, calls

    def test_unicode_newline_exact_roundtrip_both_roles(self):
        for node_actor in ('alice', 'bob'):
            with self.subTest(node_actor=node_actor), patch.dict(SPEC, query='Moon 🌙 雪 café; inert $(not-executed)'):
                with closing(baseline.OwnerWorkspace()) as workspace:
                    demo = Demo(workspace, mixed_node=node_actor)
                    try:
                        demo.result['payload']['text'] = '🌕' * 99 + '\n'  # Exact 100 code-point request bound.
                        lines = []
                        simulate(workspace, demo, lines.append)
                        self.assertEqual(demo.peers[node_actor].client, 'node')
                        for actor, expected in (('alice', demo.result), ('bob', demo.request)):
                            actual = tool_value(demo.peers[actor].step('inbox'))['messages'][0]['envelope']
                            self.assertEqual(actual, expected)
                            self.assertEqual(json.dumps(actual, sort_keys=True, ensure_ascii=False).encode(),
                                             json.dumps(expected, sort_keys=True, ensure_ascii=False).encode())
                        self.assertEqual(sum('processed inbox still empty' in line for line in lines), 2)
                    finally:
                        demo.close()

    def test_incompatible_negotiation_and_response_ids_close_both_clients(self):
        real_handle = RestrictedHostSession.handle
        for client in ('node', 'python'):
            for corruption in ('version', 'id', 'bool-id'):
                with self.subTest(client=client, corruption=corruption):
                    peer, calls = self.peer(client)
                    def corrupt(session, raw):
                        result = json.loads(real_handle(session, raw))
                        if corruption == 'version':
                            result['result']['protocolVersion'] = 'unsupported'
                        else:
                            result['id'] = True if corruption == 'bool-id' else 999
                        return json.dumps(result).encode()
                    with patch.object(RestrictedHostSession, 'handle', corrupt):
                        with self.assertRaises(PeerFailure): peer.step('discover')
                    self.assertEqual(calls, [])
                    self.assertTrue(peer.closed)
                    self.assertIsNotNone(peer.process.poll())

    def test_unicode_schema_bound_uses_code_points_not_utf16_units(self):
        for client in ('node', 'python'):
            for extra in (0, 1):
                with self.subTest(client=client, extra=extra):
                    request = copy.deepcopy(fixture()[2])
                    request['payload']['query'] = '🌙' * (511 + extra) + '\n'
                    peer, calls = self.peer(client, envelope=request)
                    peer.step('discover')
                    response = peer.step('propose')['response']
                    if extra:
                        self.assertIn('error', response)
                        self.assertEqual(calls, [])
                    else:
                        self.assertFalse(response['result']['isError'])
                        self.assertEqual(calls[0]['envelope'], request)
                    peer.close()

    def test_node_byte_limit_exact_and_one_over_with_non_bmp(self):
        real_handle = RestrictedHostSession.handle
        for extra in (0, 1):
            request = copy.deepcopy(fixture()[2])
            request['payload']['query'] = '🌙' * 1000
            message = {'jsonrpc':'2.0', 'method':'tools/call', 'id':4,
                       'params':{'name':'propose', 'arguments':{'envelope':request, 'proposal_id':'mixed-proposal'}}}
            size = len(json.dumps(message, separators=(',', ':'), ensure_ascii=False).encode())
            request['payload']['query'] += 'a' * (MAX_INPUT - size + extra)
            peer, calls = self.peer(envelope=request)
            peer.step('discover')
            frames = []
            def capture(session, raw):
                frames.append(raw)
                return real_handle(session, raw)
            with patch.object(RestrictedHostSession, 'handle', capture):
                if extra:
                    with self.assertRaises(PeerFailure): peer.step('propose')
                    self.assertEqual(frames, [])
                else:
                    # Wire accepts exact byte limit; closed envelope schema still refuses this huge query.
                    self.assertIn('error', peer.step('propose')['response'])
                    self.assertEqual(len(frames[0]), MAX_INPUT)
                    self.assertLess(len(frames[0].decode()), MAX_INPUT)
            self.assertEqual(calls, [])
            peer.close()

    def test_missing_node_preflight_launches_nothing_and_no_replacement(self):
        with closing(baseline.OwnerWorkspace()) as workspace:
            demo = Demo(workspace, mixed_node='bob')
            self.addCleanup(demo.close)
            review = workspace.task_preview(SPEC)
            row = workspace.compose(SPEC, review['review_digest'], 'CREATE TASK')
            with patch('offline_peer_pipes.shutil.which', return_value=None), \
                 patch('offline_peer_demo.Peer') as launch:
                with self.assertRaisesRegex(PeerFailure, 'unavailable'):
                    demo.command('peers-start', '', row)
                launch.assert_not_called()
            self.assertFalse(demo.started)
            self.assertEqual(demo.peers, {})

    def test_late_node_failure_reaps_first_peer_without_substitution(self):
        with closing(baseline.OwnerWorkspace()) as workspace:
            demo = Demo(workspace, mixed_node='bob')
            self.addCleanup(demo.close)
            review = workspace.task_preview(SPEC)
            row = workspace.compose(SPEC, review['review_digest'], 'CREATE TASK')
            for binding in workspace.state(row['selector'], row['context'], 'alice')['bindings']:
                workspace.action(row['selector'], row['context'], {'action':'bind', 'owner':binding['owner'],
                    'binding_digest':binding['digest'], 'confirmation':'BIND '+binding['owner']})
            runtime = node_runtime()
            with patch('offline_peer_pipes.node_runtime', side_effect=PeerFailure('runtime disappeared')), \
                 patch('offline_peer_demo.node_runtime', return_value=runtime):
                with self.assertRaisesRegex(PeerFailure, 'disappeared'):
                    demo.command('peers-start', '', row)
            self.assertTrue(demo.started)
            self.assertEqual(list(demo.peers), ['alice'])
            self.assertTrue(demo.peers['alice'].closed)
            self.assertIsNotNone(demo.peers['alice'].process.poll())
            with self.assertRaises(baseline.Denied): demo.command('peers-start', '', row)

    def test_closed_choice_runtime_version_and_clean_environment(self):
        real_run, real_popen = subprocess.run, subprocess.Popen
        launches = []
        def spawn(*args, **kwargs):
            launches.append((args, kwargs.copy()))
            return real_popen(*args, **kwargs)
        with patch.dict(os.environ, {'NODE_OPTIONS':'--require=/never-load.js', 'NODE_PATH':'/never-load'}), \
             patch('offline_peer_pipes.subprocess.Popen', side_effect=spawn):
            peer, _ = self.peer()
            peer.step('discover')
        for _, kwargs in launches:
            self.assertEqual(kwargs['env'], {})
            self.assertTrue(kwargs['close_fds'])
        child = launches[-1][1]
        self.assertEqual(len(child['pass_fds']), 2)
        self.assertEqual(child['stderr'], subprocess.DEVNULL)
        with patch('offline_peer_pipes.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'v17.0.0\n')):
            with self.assertRaisesRegex(PeerFailure, 'Expected Node 18'): node_runtime()
        task, _, request, _ = fixture()
        with self.assertRaises(ValueError):
            Peer(RestrictedHostSession(task, 'alice', lambda _: None), request, 'p', client='shell')

    def test_full_verifier_requires_node_for_python_mixed_suite(self):
        harness = verifier_tests.ReportTests()
        for options in ({'node':False}, {'node_version':'v17.0.0\n'}):
            result = harness.invoke(full=True, **options)
            self.assertEqual(result['suites']['python']['status'], 'not-run')
            self.assertEqual(result['status'], 'incomplete-or-failed')

    def test_javascript_source_freeze_and_symlinks(self):
        for suffix in ('.js', '.cjs'):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = root / ('offline_peer_client' + suffix)
                script.write_text('fixed source')
                self.assertIn(script.name, source_paths(root))
                script.unlink()
                (root / 'data.txt').write_text('outside scope')
                script.symlink_to(root / 'data.txt')
                with self.assertRaisesRegex(ValueError, 'Symlink'): source_paths(root)


if __name__ == '__main__': unittest.main()
