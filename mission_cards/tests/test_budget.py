"""Offline tests for owner-signed mission spending mandates."""
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mission_cards.budget import BudgetLedger, mandate, sign_mandate
from mission_cards.receipts import sign, statement_for
from mission_cards.text import CardError

NOW = 1_800_000_000
CARD = 'c' * 64


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.keys = {'edem': Ed25519PrivateKey.generate(), 'sam': Ed25519PrivateKey.generate()}
        self.public = {o: k.public_key() for o, k in self.keys.items()}
        self.statement = mandate('edem', 'offsite-1', CARD, 'sam', 'GBP', 5000, 2000, NOW + 3600,
                                 'Venue deposit for the team offsite')
        self.ledger = BudgetLedger(sign_mandate(self.statement, self.keys['edem']), self.public, 'offsite-1', CARD)

    def test_charges_within_the_mandate(self):
        self.assertEqual(self.ledger.charge('sam', 'GBP', 2000, 'Deposit', NOW)['remaining_minor'], 3000)
        self.assertEqual(self.ledger.charge('sam', 'GBP', 1500, 'Catering', NOW)['remaining_minor'], 1500)
        self.assertEqual(self.ledger.spent(), 3500)

    def test_limits_hold(self):
        cases = [(('sam', 'GBP', 2001, 'Too big', NOW), 'per-charge'),
                 (('mallory', 'GBP', 100, 'Wrong payee', NOW), 'payee'),
                 (('sam', 'USD', 100, 'Wrong currency', NOW), 'currency'),
                 (('sam', 'GBP', 100, 'Late', NOW + 3600), 'expired'),
                 (('sam', 'GBP', 0, 'Zero', NOW), 'whole number'),
                 (('sam', 'GBP', 10.5, 'Fraction', NOW), 'whole number')]
        for args, message in cases:
            with self.assertRaisesRegex(CardError, message):
                self.ledger.charge(*args)
        for _ in range(2):
            self.ledger.charge('sam', 'GBP', 2000, 'Instalment', NOW)
        with self.assertRaisesRegex(CardError, 'exceed the mission budget'):
            self.ledger.charge('sam', 'GBP', 1001, 'One more', NOW)
        self.assertEqual(self.ledger.remaining(), 1000)

    def test_mandate_must_be_signed_by_its_owner(self):
        forged = sign_mandate(self.statement, self.keys['sam'])
        with self.assertRaisesRegex(CardError, 'not signed by the owner'):
            BudgetLedger(forged, self.public, 'offsite-1', CARD)

    def test_mandate_bound_to_mission_and_card_version(self):
        envelope = sign_mandate(self.statement, self.keys['edem'])
        with self.assertRaisesRegex(CardError, 'different mission'):
            BudgetLedger(envelope, self.public, 'other', CARD)
        with self.assertRaisesRegex(CardError, 'different version'):
            BudgetLedger(envelope, self.public, 'offsite-1', 'd' * 64)

    def test_step_receipt_is_not_a_mandate(self):
        event = {'kind': 'accepted', 'anchor': 'offsite-1', 'seq': 3, 'hash': 'e' * 64, 'actor': 'edem',
                 'at': NOW, 'prev': 'f' * 64, 'body': {}}
        receipt = sign(statement_for(CARD, 'offsite-1', event), self.keys['edem'])
        with self.assertRaisesRegex(CardError, 'expected kind'):
            BudgetLedger(receipt, self.public, 'offsite-1', CARD)

    def test_invalid_mandates(self):
        base = dict(owner='edem', mission_id='offsite-1', card_digest=CARD, payee='sam', currency='GBP',
                    total_minor=5000, per_charge_minor=2000, expires=NOW, purpose='Deposit')
        for change in ({'payee': 'edem'}, {'currency': 'BTC'}, {'per_charge_minor': 6000},
                       {'total_minor': 10_000_001}, {'purpose': ''}, {'card_digest': 'short'}):
            with self.assertRaises(CardError):
                mandate(**{**base, **change})


if __name__ == '__main__':
    unittest.main()
