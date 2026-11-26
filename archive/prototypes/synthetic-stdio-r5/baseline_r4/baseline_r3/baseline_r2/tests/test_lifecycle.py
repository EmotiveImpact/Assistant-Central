import os
import tempfile
import unittest
from unittest import mock

from independent_peer.fixture import CleanupUncertain, Experiment, PeerProcess, UncertainOutcome
from independent_peer.protocol import Rejected, token


class LifecycleTests(unittest.TestCase):
    def test_malformed_response_poisons_session(self):
        malformed = [[], None, True, {}, {'ok': 1, 'value': {}}, {'ok': True},
                     {'ok': True, 'value': {}, 'extra': 1}, {'ok': False},
                     {'ok': False, 'error': {}}, {'ok': False, 'error': 'x' * 201}]
        for response in malformed:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                peer = PeerProcess('alice', directory)
                try:
                    with mock.patch.object(peer, '_io', return_value=response):
                        with self.assertRaises(UncertainOutcome):
                            peer.owner('describe')
                    self.assertTrue(peer.broken)
                    self.assertIsNotNone(peer.process.poll())
                    with self.assertRaisesRegex(UncertainOutcome, 'poisoned'):
                        peer.owner('inspect')
                finally:
                    peer.close()

    def test_same_lane_concurrency_is_rejected_without_submission(self):
        with Experiment() as experiment:
            peer = experiment.alice
            with peer._lane_locks['owner']:
                with self.assertRaisesRegex(Rejected, 'concurrent'):
                    peer.owner('cancel')
            self.assertIsNone(peer.owner('inspect')['policy']['terminal'])
            self.assertFalse(peer.broken)

    def test_no_ambient_environment_inheritance(self):
        import independent_peer.fixture as fixture
        original = fixture.subprocess.Popen
        captured = []
        def spawn(*args, **kwargs):
            captured.append(kwargs['env'])
            return original(*args, **kwargs)
        with mock.patch.dict(os.environ, {'FICTIONAL_CREDENTIAL_TEST': 'must-not-inherit'}), \
             mock.patch.object(fixture.subprocess, 'Popen', side_effect=spawn):
            with Experiment() as experiment:
                self.assertTrue(experiment.alice.owner('inspect')['configured'])
        self.assertEqual(len(captured), 2)
        for environment in captured:
            self.assertEqual(environment, {'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'})

    def test_init_failure_after_spawn_reaps_started_child(self):
        import independent_peer.fixture as fixture
        original = fixture.subprocess.Popen
        children = []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); children.append(child); return child
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(fixture.subprocess, 'Popen', side_effect=spawn), \
             mock.patch.object(fixture.os, 'set_blocking', side_effect=OSError('synthetic fault')):
            with self.assertRaisesRegex(OSError, 'synthetic'):
                PeerProcess('alice', directory)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_experiment_cleanup_attempts_every_peer_and_temp_on_failure(self):
        fixture = Experiment.__new__(Experiment)
        first, second, temp = mock.Mock(), mock.Mock(), mock.Mock()
        first.close.side_effect = OSError('synthetic close failure')
        fixture.peers = {'alice': first, 'bob': second}
        fixture.temp = temp
        with self.assertRaisesRegex(CleanupUncertain, 'alice cleanup'):
            fixture.close()
        first.close.assert_called_once()
        second.close.assert_called_once()
        temp.cleanup.assert_called_once()

    def test_idempotent_close_does_not_close_reused_file_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            peer = PeerProcess('alice', directory)
            peer.owner('describe')
            peer.close()
            read_fd, write_fd = os.pipe()
            try:
                peer.close()
                os.write(write_fd, b'x')
                self.assertEqual(os.read(read_fd, 1), b'x')
            finally:
                os.close(read_fd); os.close(write_fd)

    def test_packet_bearing_owner_replay_is_fenced_after_cancel(self):
        with Experiment() as experiment:
            grant = experiment.bob.owner('allow_receive')['grant']
            operation = token()
            sent = experiment.alice.owner('approve_send', operation_id=operation, payload='Fiction.', grant=grant)
            experiment.alice.owner('cancel')
            with self.assertRaisesRegex(Rejected, 'terminal'):
                experiment.alice.owner('approve_send', operation_id=operation, payload='Fiction.', grant=grant)
            with self.assertRaisesRegex(Rejected, 'terminal'):
                experiment.alice.owner('packet', id=sent['id'])

    def test_historical_allow_replay_does_not_restore_revoked_grant(self):
        with Experiment() as experiment:
            operation = token()
            old = experiment.bob.owner('allow_receive', operation_id=operation)
            experiment.bob.owner('revoke_receive')
            self.assertEqual(experiment.bob.owner('allow_receive', operation_id=operation), old)
            self.assertFalse(experiment.bob.owner('inspect')['policy']['active'])


if __name__ == '__main__':
    unittest.main()
