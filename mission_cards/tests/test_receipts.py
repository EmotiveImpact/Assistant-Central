"""Offline tests for signed mission step receipts."""
import base64
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mission_cards.card import MissionCard
from mission_cards.receipts import PAYLOAD_TYPE, matches_log, pae, sign, statement_for, verify
from mission_cards.text import CardError

NOW = 1_800_000_000


def mission(goal='Pick a venue'):
    card = MissionCard('offsite-1', goal, {'edem': 'Edem', 'sam': 'Sam'}, lambda: NOW)
    card.add_constraint('sam', 'Step-free access')
    d = card.digest()
    card.acknowledge('edem', d)
    card.acknowledge('sam', d)
    card.deliver('edem', d, 'Corn Exchange', {'c1': {'status': 'met', 'note': 'Lift'}})
    card.accept('sam', d)
    return card, d


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.keys = {'edem': Ed25519PrivateKey.generate(), 'sam': Ed25519PrivateKey.generate()}
        self.public = {o: k.public_key() for o, k in self.keys.items()}
        self.card, self.d = mission()
        self.events = self.card.log.events()
        self.accepted = next(e for e in self.events if e['kind'] == 'accepted')

    def receipt(self, event, signer=None):
        statement = statement_for(self.d, 'offsite-1', event)
        return sign(statement, self.keys[signer or event['actor']])

    def test_owner_signed_receipt_verifies_and_matches_log(self):
        statement = verify(self.receipt(self.accepted), self.public)
        self.assertEqual(statement['predicate']['step'], 'accepted')
        self.assertEqual(statement['subject'][0]['digest']['sha256'], self.d)
        self.assertTrue(matches_log(statement, self.events))

    def test_every_decision_step_gets_a_receipt(self):
        steps = [e for e in self.events if e['kind'] in ('acknowledged', 'delivered', 'accepted')]
        self.assertEqual(len(steps), 4)
        for event in steps:
            self.assertTrue(matches_log(verify(self.receipt(event), self.public), self.events))

    def test_host_cannot_fake_an_owners_yes(self):
        host_key = Ed25519PrivateKey.generate()
        forged = sign(statement_for(self.d, 'offsite-1', self.accepted), host_key)
        with self.assertRaisesRegex(CardError, 'not signed by the owner'):
            verify(forged, self.public)
        with self.assertRaisesRegex(CardError, 'not signed by the owner'):
            verify(self.receipt(self.accepted, signer='edem'), self.public)

    def test_tampered_payload_fails(self):
        envelope = self.receipt(self.accepted)
        statement = json.loads(base64.b64decode(envelope['payload']))
        statement['predicate']['details']['waived'] = ['c1']
        from pilot.crypto import canonical
        envelope['payload'] = base64.b64encode(canonical(statement)).decode()
        with self.assertRaises(CardError):
            verify(envelope, self.public)

    def test_receipt_for_a_step_not_in_this_log(self):
        other, other_d = mission('Pick a different venue')
        foreign = verify(sign(statement_for(other_d, 'offsite-1', other.log.events()[-1]), self.keys['sam']),
                         self.public)
        self.assertFalse(matches_log(foreign, self.events))

    def test_only_decisions_get_receipts(self):
        with self.assertRaises(CardError):
            statement_for(self.d, 'offsite-1', self.events[0])
        with self.assertRaises(CardError):
            statement_for(self.d, 'other', self.accepted)

    def test_malformed_envelopes(self):
        good = self.receipt(self.accepted)
        for bad in (None, {}, {**good, 'payloadType': 'text/plain'}, {**good, 'payload': '%%%'},
                    {**good, 'signatures': []}, {**good, 'payload': base64.b64encode(b'not json').decode()}):
            with self.assertRaises(CardError):
                verify(bad, self.public)

    def test_pae_matches_dsse_spec_example(self):
        self.assertEqual(pae('http://example.com/HelloWorld', b'hello world'),
                         b'DSSEv1 29 http://example.com/HelloWorld 11 hello world')
        self.assertEqual(PAYLOAD_TYPE, 'application/vnd.in-toto+json')


if __name__ == '__main__':
    unittest.main()
