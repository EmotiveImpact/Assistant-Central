"""Independent review regressions using disposable synthetic credentials."""
from pathlib import Path
import tempfile
import unittest

from pilot.auth import AuthError, AuthOutcomeUnknown, LocalOwnerAuth
from pilot.runtime import PilotRuntime


class PasswordRotationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.auth = LocalOwnerAuth(Path(self.temp.name) / 'owner', clock=lambda: self.now)
        self.addCleanup(self.auth.close)
        self.old = 'disposable-old-review-password'
        self.new = 'disposable-new-review-password'
        self.auth.bootstrap('review-owner', 'review-agent', self.old)
        self.token = self.auth.login(self.old)

    def test_interrupt_at_commit_requires_restart_and_cannot_revive_tokens(self):
        real = self.auth._db
        class InterruptConnection:
            def __getattr__(self, name): return getattr(real, name)
            def __enter__(self): real.__enter__(); return self
            def __exit__(self, kind, value, trace):
                real.rollback()
                raise KeyboardInterrupt('synthetic interrupted commit acknowledgement')
        self.auth._db = InterruptConnection()
        try:
            with self.assertRaises(KeyboardInterrupt):
                self.auth.change_password(self.token, self.old, self.new)
        finally:
            self.auth._db = real
        self.assertIsNone(self.auth._vault)
        # Neither a successful login nor revival of an old token is safe until
        # restart resolves the unknown transaction outcome and deletes tokens.
        with self.assertRaises(AuthOutcomeUnknown):
            self.auth.login(self.old)
        with self.assertRaises(AuthOutcomeUnknown):
            self.auth.authenticate(self.token)
        directory = self.auth.directory
        self.auth.close()
        self.auth = LocalOwnerAuth(directory, clock=lambda: self.now)
        self.addCleanup(self.auth.close)
        self.auth.login(self.old)
        with self.assertRaises(AuthError):
            self.auth.authenticate(self.token)

    def test_rotation_preserves_queued_packet_and_peer_pins(self):
        root = Path(self.temp.name)
        peer_auth = LocalOwnerAuth(root / 'peer-auth', clock=lambda: self.now)
        self.addCleanup(peer_auth.close)
        peer_auth.bootstrap('review-peer', 'review-peer-agent', self.old)
        peer_token = peer_auth.login(self.old)
        sender = PilotRuntime(root / 'sender-runtime', self.auth, clock=lambda: self.now)
        self.addCleanup(sender.close)
        receiver = PilotRuntime(root / 'receiver-runtime', peer_auth, clock=lambda: self.now)
        self.addCleanup(receiver.close)
        sender.enrol_peer(self.token, receiver.identity, receiver.fingerprint)
        receiver.enrol_peer(peer_token, sender.identity, sender.fingerprint)
        fingerprints = (sender.fingerprint, receiver.fingerprint)
        item = sender.propose(self.token, receiver.fingerprint, 'task',
                              'Synthetic rotation task', 'Disposable fictional text.',
                              'a' * 64, 'rotation-task', 1500)
        review = sender.review(self.token, item['id'])
        released = sender.release(self.token, item['id'], review['review_digest'])
        packet = sender.prepare_delivery(self.token, released['message_id'])
        self.auth.change_password(self.token, self.old, self.new)
        peer_auth.change_password(peer_token, self.old, self.new)
        with self.assertRaises(AuthError):
            sender.prepare_delivery(self.token, released['message_id'])
        with self.assertRaises(AuthError):
            receiver.receive(peer_token, packet)
        fresh = self.auth.login(self.new)
        peer_fresh = peer_auth.login(self.new)
        self.assertEqual(sender.prepare_delivery(fresh, released['message_id']), packet)
        received = receiver.receive(peer_fresh, packet)
        self.assertEqual(received['item']['id'], item['id'])
        self.assertIsNotNone(received['receipt'])
        sender.receive(fresh, received['receipt'])
        self.assertEqual((sender.fingerprint, receiver.fingerprint), fingerprints)
        for auth, token in ((self.auth, self.token), (peer_auth, peer_token)):
            with self.assertRaises(AuthError):
                auth.authenticate(token)

    def test_expiry_after_credential_write_rolls_back_and_locks_instance(self):
        real = self.auth._db
        before = tuple(real.execute('SELECT salt,verifier,nonce,vault FROM account').fetchone())
        outer = self
        class DelayedConnection:
            def __getattr__(self, name): return getattr(real, name)
            def __enter__(self): real.__enter__(); return self
            def __exit__(self, *args): return real.__exit__(*args)
            def execute(self, sql, *args):
                result = real.execute(sql, *args)
                if sql.startswith('UPDATE account SET salt='):
                    outer.now += 900
                return result
        self.auth._db = DelayedConnection()
        try:
            with self.assertRaises(AuthOutcomeUnknown):
                self.auth.change_password(self.token, self.old, self.new)
        finally:
            self.auth._db = real
        self.assertEqual(tuple(real.execute('SELECT salt,verifier,nonce,vault FROM account').fetchone()), before)
        with self.assertRaises(AuthOutcomeUnknown):
            self.auth.login(self.old)


if __name__ == '__main__':
    unittest.main()
