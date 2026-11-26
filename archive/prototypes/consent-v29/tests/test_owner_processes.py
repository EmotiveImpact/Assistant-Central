import json
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from demo import fixture
from fixture_ipc import JsonProcess
from network import context_digest, digest
from owner_auth import DOMAIN, decision_bytes

ROOT = Path(__file__).resolve().parent.parent


class OwnerProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'state.sqlite3')
        self.meeting, self.agents, _ = fixture()
        self.keys = {owner: Ed25519PrivateKey.generate() for owner in self.meeting.participants if owner != 'bob'}
        self.signer = JsonProcess('owner_fixture_process.py', '--owner', 'bob')
        self.hello = self.signer.read()
        self.roots = {owner: key.public_key().public_bytes_raw().hex() for owner, key in self.keys.items()}
        self.roots['bob'] = self.hello['public_key']
        self.worker = JsonProcess('executor_fixture_process.py', '--state-file', self.path)
        self.assertTrue(self.worker.request({'owner_public_keys': self.roots})['ready'])

    def tearDown(self):
        self.worker.close()
        self.signer.close()
        self.tmp.cleanup()

    def decision(self, owner='bob', action='pair', target=None):
        now = int(time.time())
        return {'version': 1, 'domain': DOMAIN, 'owner': owner, 'action': action,
                'context': context_digest(self.meeting), 'nonce': secrets.token_hex(16),
                'issued_at': now, 'expires_at': now + 300,
                'target': target or {'peer': 'alice', 'contact_version': 0, 'ttl': 3600}}

    def sign(self, decision, envelope=None, phrase=None):
        phrase = phrase if phrase is not None else f"APPROVE bob {decision['action']} {decision['nonce']}"
        return self.signer.request({'decision': decision, 'envelope': envelope, 'confirmation': phrase})

    def test_private_key_never_crosses_signer_handshake(self):
        self.assertEqual(set(self.hello), {'owner', 'public_key', 'fixture_only'})
        self.assertNotEqual(self.signer.process.pid, self.worker.process.pid)
        self.assertEqual(len(self.hello['public_key']), 64)

    def test_worker_accepts_verified_signature_from_separate_signer(self):
        decision = self.decision()
        signed = self.sign(decision)['signed']
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.roots['bob'])).verify(
            bytes.fromhex(signed['signature']), decision_bytes(decision))
        result = self.worker.request({'signed': signed, 'envelope': None})
        self.assertTrue(result['ok']); self.assertFalse(result['replayed'])
        self.assertEqual(result['result']['contact_version'], 1)

    def test_worker_cannot_approve_sign_or_replace_its_roots(self):
        requests = ({'method': 'sign'}, {'owner_approve': True}, {'private_key': 'export'},
                    {'owner_public_keys': self.roots}, {'signed': {'approved': True}, 'envelope': None})
        for request in requests:
            with self.subTest(request=request):
                result = self.worker.request(request)
                self.assertFalse(result['ok'])
                self.assertEqual(set(result), {'ok', 'error'})

    def test_signer_requires_exact_confirmation_and_correct_owner(self):
        decision = self.decision()
        self.assertFalse(self.sign(decision, phrase='yes')['ok'])
        self.assertFalse(self.sign(decision, phrase='APPROVE bob')['ok'])
        self.assertFalse(self.sign(self.decision(owner='alice'))['ok'])
        self.assertTrue(self.sign(decision)['ok'])

    def test_signer_rejects_body_that_differs_from_reviewed_digest(self):
        message = self.agents[1].preview_availability(self.meeting)
        decision = self.decision(action='send', target={'recipient': 'alice', 'envelope_digest': digest(message), 'pair_versions': [1, 1]})
        message['payload']['candidate_indices'] = [0]
        self.assertFalse(self.sign(decision, envelope=message)['ok'])

    def test_worker_restart_preserves_signature_replay_state(self):
        signed = self.sign(self.decision())['signed']
        self.assertFalse(self.worker.request({'signed': signed, 'envelope': None})['replayed'])
        self.worker.close()
        self.worker = JsonProcess('executor_fixture_process.py', '--state-file', self.path)
        self.assertTrue(self.worker.request({'owner_public_keys': self.roots})['ready'])
        self.assertTrue(self.worker.request({'signed': signed, 'envelope': None})['replayed'])

    def test_worker_refuses_changed_root_after_restart(self):
        self.worker.close()
        self.worker = JsonProcess('executor_fixture_process.py', '--state-file', self.path)
        changed = dict(self.roots)
        changed['bob'] = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        result = self.worker.request({'owner_public_keys': changed})
        self.assertFalse(result['ok'])
        self.assertIn('roots changed', result['error'])

    def test_signature_alone_does_not_replace_bilateral_pairing(self):
        message = self.agents[1].preview_availability(self.meeting)
        decision = self.decision(action='send', target={'recipient': 'alice', 'envelope_digest': digest(message), 'pair_versions': [1, 1]})
        signed = self.sign(decision, envelope=message)['signed']
        self.assertFalse(self.worker.request({'signed': signed, 'envelope': message})['ok'])


class SignedDemoTests(unittest.TestCase):
    def run_demo(self, *args, input=None):
        return subprocess.run([sys.executable, 'signed_demo.py', *args], cwd=ROOT,
                              input=input, capture_output=True, text=True, timeout=15, check=True).stdout

    def test_full_demo_uses_four_separate_owner_signers(self):
        output = self.run_demo('--simulate')
        self.assertIn('All four fictional participants accepted: True', output)
        self.assertIn('Signed message decisions: 12', output)
        self.assertIn('All disposable signer processes stopped', output)

    def test_demo_cancellation_stops_execution(self):
        output = self.run_demo('--simulate', '--cancel-after', '5')
        self.assertIn('after 5 locally processed messages', output)
        self.assertNotIn('All four fictional participants accepted', output)

    def test_manual_denial_does_not_turn_into_a_signed_approval(self):
        output = self.run_demo(input='NO\n')
        self.assertIn('Exact owner confirmation phrase was not supplied', output)
        self.assertNotIn('Signed message decisions:', output)
        self.assertIn('All disposable signer processes stopped', output)

    def test_demo_rejects_invalid_stop_count(self):
        self.assertIn('Cancel-after must be between', self.run_demo('--simulate', '--cancel-after', '0'))
