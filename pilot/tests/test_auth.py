"""Synthetic local account tests, not enrollment of real human identities."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from pilot.auth import LocalOwnerAuth, AuthError


PASSWORD = "SYNTHETIC-ONLY secret passphrase"


class OwnerAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'owner'
        self.now = 1000
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)
        self.addCleanup(lambda: self.auth.close())
        self.public = self.auth.bootstrap('alice', 'assistant-a', PASSWORD)

    def login(self, **kwargs):
        return self.auth.login(PASSWORD, **kwargs)

    def reopen(self):
        self.auth.close()
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)

    def test_bootstrap_is_locked_and_enrollment_cannot_be_replaced(self):
        self.assertFalse(self.auth.status()['unlocked'])
        self.assertFalse(self.auth.status()['human_identity_verified'])
        for owner, agent in (('alice', 'assistant-a'), ('bob', 'assistant-b')):
            with self.assertRaises(AuthError): self.auth.bootstrap(owner, agent, PASSWORD)
        self.assertEqual(self.auth.public_identity(), self.public)

    def test_session_binds_enrolled_identity_without_owner_argument(self):
        token = self.login()
        identity = self.auth.authenticate(token)
        self.assertEqual(identity['owner_id'], 'alice')
        self.assertEqual(identity['agent_id'], 'assistant-a')
        self.assertEqual(identity['expires_at'], 1900)
        self.assertEqual(set(identity), {'owner_id', 'agent_id', 'identity_fingerprint', 'expires_at'})
        with self.assertRaises(TypeError): self.auth.authenticate(token, owner_id='bob')
        with self.assertRaises(TypeError): self.auth.login(PASSWORD, owner_id='bob')

    def test_cross_owner_token_is_rejected_even_with_same_password(self):
        other = LocalOwnerAuth(Path(self.tmp.name) / 'other', clock=lambda: self.now)
        self.addCleanup(other.close)
        other.bootstrap('bob', 'assistant-b', PASSWORD)
        other_token, token = other.login(PASSWORD), self.login()
        with self.assertRaises(AuthError): self.auth.authenticate(other_token)
        with self.assertRaises(AuthError): other.authenticate(token)
        self.assertNotEqual(self.public['signing_key'], other.public_identity()['signing_key'])

    def test_wrong_and_malformed_credentials_never_leak(self):
        for value in (None, True, [], {}, '', 'short', '\ud800' * 12, 'x' * 1025):
            with self.subTest(value=repr(value)), self.assertRaises(AuthError) as caught:
                self.auth.login(value)
            self.assertEqual(str(caught.exception), 'Authentication failed')
        with self.assertRaises(AuthError) as caught: self.auth.login('SYNTHETIC bad password')
        self.assertNotIn('password', str(caught.exception).lower())
        for token in (None, True, [], {}, '', 'alice', 'a' * 43, 'a' * 10000):
            with self.subTest(token=repr(token)[:30]), self.assertRaises(AuthError): self.auth.authenticate(token)

    def test_login_backoff_is_persistent_and_clears_after_success(self):
        with self.assertRaises(AuthError): self.auth.login('wrong synthetic password')
        with self.assertRaises(AuthError): self.login()
        self.reopen()
        with self.assertRaises(AuthError): self.login()
        self.now += 1
        token = self.login()
        self.auth.logout(token)
        with self.assertRaises(AuthError): self.auth.login('wrong synthetic password')
        self.now += 1
        self.login()

    def test_expiry_is_enforced_for_auth_sign_and_exchange(self):
        token = self.login(ttl=2)
        self.now = 1002
        peer = X25519PrivateKey.generate().public_key().public_bytes_raw()
        for call in (lambda: self.auth.authenticate(token), lambda: self.auth.sign(token, b'data'),
                     lambda: self.auth.exchange(token, peer)):
            with self.assertRaises(AuthError): call()
        self.assertFalse(self.auth.status()['unlocked'])

    def test_session_ttl_is_finite_and_bounded(self):
        for ttl in (0, -1, 3601, True, None, '100', float('inf'), float('nan')):
            with self.subTest(ttl=ttl), self.assertRaises(AuthError): self.login(ttl=ttl)
        self.login(ttl=3600)

    def test_logout_revokes_only_that_session_and_last_logout_locks(self):
        first, second = self.login(), self.login()
        self.auth.logout(first)
        with self.assertRaises(AuthError): self.auth.authenticate(first)
        self.auth.authenticate(second)
        self.assertTrue(self.auth.status()['unlocked'])
        self.auth.logout(second)
        self.assertFalse(self.auth.status()['unlocked'])

    def test_revoke_all_requires_current_session_and_locks(self):
        first, second = self.login(), self.login()
        with self.assertRaises(AuthError): self.auth.revoke_all('x' * 43)
        self.auth.revoke_all(first)
        for token in (first, second):
            with self.assertRaises(AuthError): self.auth.authenticate(token)
        self.assertFalse(self.auth.status()['unlocked'])

    def test_restart_invalidates_old_sessions_and_requires_password(self):
        token = self.login()
        signature = self.auth.sign(token, b'original message')
        self.reopen()
        self.assertEqual(self.auth.public_identity(), self.public)
        self.assertFalse(self.auth.status()['unlocked'])
        with self.assertRaises(AuthError): self.auth.authenticate(token)
        fresh = self.login()
        self.assertNotEqual(token, fresh)
        self.assertEqual(self.auth.sign(fresh, b'original message'), signature)
        with self.assertRaises(AuthError): self.auth.authenticate(token)

    def test_signatures_and_key_exchange_match_public_identity(self):
        token = self.login()
        raw_signing = base64.urlsafe_b64decode(self.public['signing_key'] + '=')
        Ed25519PublicKey.from_public_bytes(raw_signing).verify(self.auth.sign(token, b'SYNTHETIC'), b'SYNTHETIC')
        peer = X25519PrivateKey.generate()
        shared = self.auth.exchange(token, peer.public_key().public_bytes_raw())
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        self.assertEqual(shared, peer.exchange(X25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(self.public['exchange_key'] + '='))))
        for data in ('text', b'', b'x' * (1024 * 1024 + 1)):
            with self.assertRaises(AuthError): self.auth.sign(token, data)
        for key in ('key', b'x', b'\0' * 32):
            with self.assertRaises(AuthError): self.auth.exchange(token, key)

    def test_plaintext_password_tokens_and_private_keys_are_not_stored_or_logged(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            token = self.login()
            self.auth.sign(token, b'SYNTHETIC')
            status = self.auth.status()
        self.assertEqual(output.getvalue(), '')
        contents = b''.join(p.read_bytes() for p in self.path.iterdir() if p.is_file())
        self.assertNotIn(PASSWORD.encode(), contents)
        self.assertNotIn(token.encode(), contents)
        self.assertNotIn(self.auth._vault[0].private_bytes_raw(), contents)
        self.assertNotIn(self.auth._vault[1].private_bytes_raw(), contents)
        self.assertNotIn(token, json.dumps(status))
        self.assertEqual(len(self.auth._db.execute('SELECT digest FROM sessions').fetchone()[0]), 64)

    def test_storage_modes_are_private_and_permissive_changes_fail_closed(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        for filename in ('auth.sqlite', 'auth.lock'):
            path = self.path / filename
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        token = self.login()
        os.chmod(self.path / 'auth.sqlite', 0o644)
        with self.assertRaises(AuthError): self.auth.authenticate(token)
        with self.assertRaises(AuthError): self.auth.sign(token, b'cannot sign')
        os.chmod(self.path / 'auth.sqlite', 0o600)

    def test_world_readable_directory_is_rejected_without_chmod(self):
        path = Path(self.tmp.name) / 'permissive'
        path.mkdir(mode=0o755)
        with self.assertRaises(AuthError): LocalOwnerAuth(path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_symlink_directory_and_database_are_rejected(self):
        path = Path(self.tmp.name) / 'link'
        path.symlink_to(self.path)
        with self.assertRaises(AuthError): LocalOwnerAuth(path)
        alternate = Path(self.tmp.name) / 'alternate'; alternate.mkdir(mode=0o700)
        (alternate / 'auth.sqlite').symlink_to(self.path / 'auth.sqlite')
        with self.assertRaises(AuthError): LocalOwnerAuth(alternate)

    def test_second_instance_cannot_invalidate_running_sessions(self):
        token = self.login()
        with self.assertRaises(AuthError): LocalOwnerAuth(self.path)
        self.auth.authenticate(token)

    def test_public_identity_is_detached_and_database_substitution_is_rejected(self):
        token = self.login()
        other = self.auth.public_identity(); other['owner_id'] = 'mallory'
        self.assertEqual(self.auth.authenticate(token)['owner_id'], 'alice')
        with self.auth._db:
            self.auth._db.execute('UPDATE account SET public=?',
                                 (json.dumps(other, sort_keys=True, separators=(',', ':')),))
        for call in (lambda: self.auth.authenticate(token), lambda: self.auth.sign(token, b'cannot spoof'),
                     lambda: self.auth.public_identity(), lambda: self.login()):
            with self.assertRaises(AuthError): call()

    def test_vault_tampering_fails_after_reopen(self):
        with self.auth._db:
            self.auth._db.execute('UPDATE account SET vault=?', (b'X' * 80,))
        self.reopen()
        with self.assertRaises(AuthError): self.login()
        self.assertFalse(self.auth.status()['unlocked'])

    def test_invalid_vault_format_and_schema_are_rejected(self):
        with self.auth._db: self.auth._db.execute('UPDATE account SET version=?', ('future-unknown',))
        self.auth.close()
        with self.assertRaises(AuthError): LocalOwnerAuth(self.path)

    def test_clock_rollback_and_invalid_clock_do_not_extend_session(self):
        token = self.login()
        self.now = 999
        with self.assertRaises(AuthError): self.auth.authenticate(token)
        self.now = float('nan')
        with self.assertRaises(AuthError): self.auth.authenticate(token)

    def test_authorised_guard_serialises_revocation_through_operation(self):
        token = self.login()
        start, finished = threading.Event(), threading.Event()
        errors = []
        def revoke():
            start.set()
            try: self.auth.logout(token)
            except BaseException as error: errors.append(error)
            finally: finished.set()
        with self.auth.authorised(token) as identity:
            thread = threading.Thread(target=revoke); thread.start()
            self.assertTrue(start.wait(2))
            self.assertFalse(finished.wait(0.05))
            self.assertEqual(identity['owner_id'], 'alice')
            self.auth.authenticate(token)
        thread.join(2)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        with self.assertRaises(AuthError): self.auth.authenticate(token)


if __name__ == '__main__':
    unittest.main()
