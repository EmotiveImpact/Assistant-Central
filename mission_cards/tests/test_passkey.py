"""Offline tests for passkey-signed approvals, with a simulated authenticator."""
import hashlib
import json
import struct
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from mission_cards.card import MissionCard
from mission_cards.passkey import FLAG_UP, FLAG_UV, PasskeyRegistry, b64url, challenge_for
from mission_cards.receipts import statement_for
from mission_cards.text import CardError

RP, ORIGIN = 'assistantcentral.example', 'https://assistantcentral.example'
NOW = 1_800_000_000


class Authenticator:
    """Stands in for the passkey on an owner's phone."""

    def __init__(self, rp=RP):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = hashlib.sha256(str(id(self)).encode()).digest()[:16]
        self.rp_hash, self.count = hashlib.sha256(rp.encode()).digest(), 0

    def assert_(self, challenge, origin=ORIGIN, flags=FLAG_UP | FLAG_UV, kind='webauthn.get', bump=True):
        if bump:
            self.count += 1
        auth = self.rp_hash + bytes([flags]) + struct.pack('>I', self.count)
        client = json.dumps({'type': kind, 'challenge': b64url(challenge), 'origin': origin}).encode()
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return self.credential_id, auth, client, sig


def acceptance_statement():
    card = MissionCard('offsite-1', 'Pick a venue', {'edem': 'Edem', 'sam': 'Sam'}, lambda: NOW)
    card.add_constraint('sam', 'Step-free access')
    d = card.digest()
    card.acknowledge('edem', d)
    card.acknowledge('sam', d)
    card.deliver('edem', d, 'Corn Exchange', {'c1': {'status': 'met', 'note': 'Lift'}})
    card.accept('sam', d)
    return statement_for(d, 'offsite-1', card.log.events()[-1])


class PasskeyTests(unittest.TestCase):
    def setUp(self):
        self.registry = PasskeyRegistry(RP, ORIGIN)
        self.sam, self.edem = Authenticator(), Authenticator()
        self.registry.register('sam', self.sam.credential_id, self.sam.key.public_key())
        self.registry.register('edem', self.edem.credential_id, self.edem.key.public_key())
        self.statement = acceptance_statement()

    def test_phone_approval_produces_checkable_receipt(self):
        receipt = self.registry.approve(self.statement, *self.sam.assert_(challenge_for(self.statement)))
        self.assertEqual(self.registry.verify_receipt(receipt), self.statement)

    def test_other_owners_passkey_cannot_approve(self):
        with self.assertRaisesRegex(CardError, 'different owner'):
            self.registry.approve(self.statement, *self.edem.assert_(challenge_for(self.statement)))

    def test_assertion_for_another_step_is_refused(self):
        other = {**self.statement, 'predicate': {**self.statement['predicate'], 'step': 'returned'}}
        with self.assertRaisesRegex(CardError, 'different step'):
            self.registry.approve(self.statement, *self.sam.assert_(challenge_for(other)))

    def test_origin_rp_flags_and_type(self):
        c = challenge_for(self.statement)
        cases = [(self.sam.assert_(c, origin='https://evil.example'), 'origin'),
                 (self.sam.assert_(c, flags=FLAG_UP), 'not verified'),
                 (self.sam.assert_(c, kind='webauthn.create'), 'Not a WebAuthn assertion')]
        for args, message in cases:
            with self.assertRaisesRegex(CardError, message):
                self.registry.approve(self.statement, *args)
        wrong_rp = Authenticator(rp='evil.example')
        wrong_rp.key, wrong_rp.credential_id = self.sam.key, self.sam.credential_id
        with self.assertRaisesRegex(CardError, 'relying party'):
            self.registry.approve(self.statement, *wrong_rp.assert_(c))

    def test_replay_is_refused(self):
        args = self.sam.assert_(challenge_for(self.statement))
        self.registry.approve(self.statement, *args)
        with self.assertRaisesRegex(CardError, 'counter'):
            self.registry.approve(self.statement, *args)

    def test_forged_signature_and_tampered_receipt(self):
        cred, auth, client, _ = self.sam.assert_(challenge_for(self.statement))
        bad = ec.generate_private_key(ec.SECP256R1()).sign(auth + hashlib.sha256(client).digest(),
                                                           ec.ECDSA(hashes.SHA256()))
        with self.assertRaisesRegex(CardError, 'signature'):
            self.registry.approve(self.statement, cred, auth, client, bad)
        receipt = self.registry.approve(self.statement, *self.sam.assert_(challenge_for(self.statement)))
        changed = {**self.statement, 'predicate': {**self.statement['predicate'], 'details': {'waived': ['c1']}}}
        from pilot.crypto import canonical
        receipt['payload'] = b64url(canonical(changed))
        with self.assertRaisesRegex(CardError, 'different step'):
            self.registry.verify_receipt(receipt)

    def test_registration_rules(self):
        with self.assertRaises(CardError):
            self.registry.register('sam', self.sam.credential_id, self.sam.key.public_key())
        with self.assertRaises(CardError):
            self.registry.register('sam', b'x' * 16, ec.generate_private_key(ec.SECP384R1()).public_key())
        with self.assertRaisesRegex(CardError, 'Unknown passkey'):
            self.registry.approve(self.statement, *Authenticator().assert_(challenge_for(self.statement)))


if __name__ == '__main__':
    unittest.main()
