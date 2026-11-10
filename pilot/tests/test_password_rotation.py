"""Disposable owner credentials only; no real account/password is changed."""
import contextlib
import io
import getpass
import warnings
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from pilot.auth import AuthError, AuthOutcomeUnknown, LocalOwnerAuth
from pilot import auth as auth_module
from pilot.security import main

OLD = 'fictional-original-passphrase'
NEW = 'fictional-replacement-passphrase'


class PasswordRotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owner'
        self.now = 1000
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)
        self.addCleanup(lambda: self.auth.close())
        self.public = self.auth.bootstrap('fictional-owner', 'fictional-assistant', OLD)
        self.first = self.auth.login(OLD)
        self.second = self.auth.login(OLD)

    def credentials(self):
        return tuple(self.auth._db.execute('SELECT salt,verifier,nonce,vault FROM account').fetchone())

    def reopen(self):
        self.auth.close()
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)

    def test_rotation_changes_all_wrapping_material_and_revokes_every_session(self):
        before = self.credentials()
        signature = self.auth.sign(self.first, b'unchanged identity')
        peer = X25519PrivateKey.generate().public_key().public_bytes_raw()
        shared = self.auth.exchange(self.first, peer)
        result = self.auth.change_password(self.first, OLD, NEW)
        self.assertEqual(result, {'password_changed': True, 'all_sessions_revoked': True, 'identity_unchanged': True})
        self.assertTrue(all(a != b for a, b in zip(before, self.credentials())))
        self.assertFalse(self.auth.status()['unlocked'])
        self.assertEqual(self.auth.status()['active_sessions'], 0)
        for token in (self.first, self.second):
            with self.assertRaises(AuthError): self.auth.authenticate(token)
        fresh = self.auth.login(NEW)
        self.assertEqual(self.auth.public_identity(), self.public)
        self.assertEqual(self.auth.sign(fresh, b'unchanged identity'), signature)
        self.assertEqual(self.auth.exchange(fresh, peer), shared)
        for token in (self.first, self.second):
            with self.assertRaises(AuthError): self.auth.authenticate(token)
        with self.assertRaises(AuthError): self.auth.login(OLD)

    def test_rotation_survives_restart_without_restoring_old_password_or_tokens(self):
        self.auth.change_password(self.first, OLD, NEW)
        self.reopen()
        with self.assertRaises(AuthError): self.auth.login(OLD)
        self.now += 1
        self.auth.login(NEW)
        self.assertEqual(self.auth.public_identity(), self.public)
        with self.assertRaises(AuthError): self.auth.authenticate(self.first)

    def test_current_password_is_required_even_with_a_valid_session(self):
        before = self.credentials()
        with self.assertRaises(AuthError): self.auth.change_password(self.first, 'incorrect-current-password', NEW)
        self.assertEqual(self.credentials(), before)
        self.auth.authenticate(self.first)
        with self.assertRaises(AuthError): self.auth.change_password(self.first, OLD, NEW)
        with self.assertRaises(AuthError): self.auth.login(OLD)
        self.now += 1
        self.auth.change_password(self.first, OLD, NEW)

    def test_login_and_rotation_share_persistent_throttling(self):
        with self.assertRaises(AuthError): self.auth.login('incorrect-current-password')
        with self.assertRaises(AuthError): self.auth.change_password(self.first, OLD, NEW)
        self.reopen()
        with self.assertRaises(AuthError): self.auth.login(OLD)
        self.now += 1
        self.auth.login(OLD)

    def test_invalid_or_cross_owner_session_cannot_change_credentials(self):
        other = LocalOwnerAuth(Path(self.temp.name) / 'other', clock=lambda: self.now)
        self.addCleanup(other.close)
        other.bootstrap('other-owner', 'other-assistant', OLD)
        foreign = other.login(OLD)
        before = self.credentials()
        for token in (None, '', 'x' * 43, foreign):
            with self.subTest(token=token), self.assertRaises(AuthError):
                self.auth.change_password(token, OLD, NEW)
        self.assertEqual(self.credentials(), before)

    def test_invalid_new_password_and_same_password_leave_credentials_unchanged(self):
        before = self.credentials()
        for password in (None, True, [], 'short', '\ud800' * 12, 'x' * 1025, OLD):
            with self.subTest(password=repr(password)[:30]), self.assertRaises(AuthError):
                self.auth.change_password(self.first, OLD, password)
        self.assertEqual(self.credentials(), before)
        self.auth.authenticate(self.first)
        self.auth.authenticate(self.second)

    def test_expiry_during_new_key_derivation_prevents_rotation(self):
        before = self.credentials()
        original = auth_module._derive
        def delayed(password, salt):
            result = original(password, salt)
            if password == NEW.encode(): self.now = 1900
            return result
        with patch.object(auth_module, '_derive', delayed), self.assertRaises(AuthError):
            self.auth.change_password(self.first, OLD, NEW)
        self.assertEqual(self.credentials(), before)
        self.auth.login(OLD)

    def test_rotation_cannot_cross_an_authorised_runtime_commit(self):
        started, finished = threading.Event(), threading.Event()
        errors = []
        def rotate():
            started.set()
            try: self.auth.change_password(self.first, OLD, NEW)
            except BaseException as error: errors.append(error)
            finally: finished.set()
        with self.auth.authorised(self.second):
            worker = threading.Thread(target=rotate)
            worker.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(.05))
            self.auth.authenticate(self.second)
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        with self.assertRaises(AuthError): self.auth.authenticate(self.second)

    def test_concurrent_rotations_cannot_reuse_a_revoked_session(self):
        outcomes = []
        def rotate(password):
            try:
                self.auth.change_password(self.first, OLD, password)
                outcomes.append(('changed', password))
            except AuthError:
                outcomes.append(('denied', password))
        workers = [threading.Thread(target=rotate, args=(value,)) for value in (NEW, 'second-fictional-replacement')]
        for worker in workers: worker.start()
        for worker in workers: worker.join(5); self.assertFalse(worker.is_alive())
        self.assertEqual(sorted(item[0] for item in outcomes), ['changed', 'denied'])
        self.auth.login(next(value for state, value in outcomes if state == 'changed'))

    def test_password_keys_and_tokens_never_enter_output_or_files(self):
        output = io.StringIO()
        private = [key.private_bytes_raw() for key in self.auth._vault]
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.auth.change_password(self.first, OLD, NEW)
        self.assertEqual(output.getvalue(), '')
        contents = b''.join(path.read_bytes() for path in self.path.iterdir() if path.is_file())
        for secret in [OLD.encode(), NEW.encode(), self.first.encode(), self.second.encode(), *private]:
            self.assertNotIn(secret, contents)

    def test_commit_failure_before_or_after_commit_requires_restart(self):
        # Both outcomes lock this instance. Restart invalidates retained tokens
        # whether the credential update was rolled back or really committed.
        for committed in (False, True):
            with self.subTest(committed=committed):
                real = self.auth._db
                class FaultConnection:
                    def __getattr__(self, name): return getattr(real, name)
                    def __enter__(self): real.__enter__(); return self
                    def __exit__(self, kind, value, trace):
                        if committed: real.__exit__(kind, value, trace)
                        else: real.rollback()
                        raise OSError('synthetic lost commit acknowledgement')
                self.auth._db = FaultConnection()
                with self.assertRaises(AuthOutcomeUnknown): self.auth.change_password(self.first, OLD, NEW)
                self.auth._db = real
                self.assertIsNone(self.auth._vault)
                for operation in (lambda: self.auth.authenticate(self.first), lambda: self.auth.login(NEW),
                                  lambda: self.auth.sign(self.second, b'no revival')):
                    with self.assertRaises(AuthOutcomeUnknown): operation()
                self.reopen()
                self.auth.login(NEW if committed else OLD)
                for token in (self.first, self.second):
                    with self.assertRaises(AuthError): self.auth.authenticate(token)
                if not committed:
                    self.first = self.auth.login(OLD)
                    self.second = self.auth.login(OLD)

    def test_cli_refuses_getpass_echo_fallback(self):
        self.auth.close()
        def unsafe_prompt(*_):
            warnings.warn('Password input may be echoed', getpass.GetPassWarning)
            self.fail('An unsafe prompt must not consume a password')
        with patch('pilot.security.getpass.getpass', side_effect=unsafe_prompt), self.assertRaises(SystemExit) as caught:
            main(['change-password', '--directory', str(self.path)])
        self.assertIn('private interactive terminal', str(caught.exception))
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)
        self.auth.login(OLD)

    def test_existing_running_service_blocks_cli_before_prompting(self):
        with patch('pilot.security.getpass.getpass') as prompt, self.assertRaises(SystemExit):
            main(['change-password', '--directory', str(self.path)])
        prompt.assert_not_called()

    def test_cli_changes_existing_account_with_private_prompts_only(self):
        self.auth.close()
        output = io.StringIO()
        with patch('pilot.security.getpass.getpass', side_effect=[OLD, NEW, NEW]) as prompts, contextlib.redirect_stdout(output):
            main(['change-password', '--directory', str(self.path)])
        self.assertEqual(prompts.call_count, 3)
        self.assertEqual(json.loads(output.getvalue())['password_changed'], True)
        self.assertNotIn(OLD, output.getvalue()); self.assertNotIn(NEW, output.getvalue())
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)
        self.auth.login(NEW)
        self.assertEqual(self.auth.public_identity(), self.public)

    def test_cli_mismatched_confirmation_leaves_password_unchanged(self):
        self.auth.close()
        with patch('pilot.security.getpass.getpass', side_effect=[OLD, NEW, 'different-confirmation']), self.assertRaises(SystemExit):
            main(['change-password', '--directory', str(self.path)])
        self.auth = LocalOwnerAuth(self.path, clock=lambda: self.now)
        self.auth.login(OLD)

    def test_cli_never_creates_a_missing_owner_directory(self):
        missing = Path(self.temp.name) / 'missing'
        with patch('pilot.security.getpass.getpass') as prompt, self.assertRaises(SystemExit):
            main(['change-password', '--directory', str(missing)])
        prompt.assert_not_called()
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
