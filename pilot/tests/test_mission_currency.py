"""Mission budgets signed in an explicit currency, alongside legacy US dollar terms."""
import unittest

from pilot.crypto import digest
from pilot.mission import (budget, direct_offer, direct_task_text, fixture_request, mission_context,
                           task_details, task_text, terms, terms_context)
from pilot.mission_budget import in_currency

BASE = {'executor': 'a' * 64, 'goal': 'Shortlist venues', 'deliverable': 'Three options',
        'criteria': [{'kind': 'contains', 'value': 'vegetarian'}]}
REQUEST = {'model': 'synthetic-research-v1', 'max_output_tokens': 128}


class MissionCurrencyTests(unittest.TestCase):
    def test_pounds_are_signed_into_terms_context_and_task(self):
        agreed = terms({**BASE, 'cap_micro': 60_000_000, 'currency': 'GBP'})
        self.assertEqual(budget(agreed), (60_000_000, 'GBP'))
        commitment = 'b' * 64
        context = terms_context(commitment, agreed)
        self.assertNotEqual(context, mission_context(commitment, 60_000_000))
        self.assertNotEqual(context, mission_context(commitment, 60_000_000, 'EUR'))
        text = task_text('Brief', 60_000_000, commitment, 'GBP')
        self.assertEqual(task_details(text, context)[1], (60_000_000, 'GBP'))
        with self.assertRaises(ValueError):
            task_details(text, mission_context(commitment, 60_000_000))
        _, quote = fixture_request({**REQUEST, 'input': text}, context)
        self.assertEqual((quote['currency'], quote['tariff'], quote['cap_micro'], quote['reserve_micro']),
                         ('GBP', 'fictional-gbp-v1', 60_000_000, 276))
        self.assertNotIn('cap_microusd', quote)

    def test_direct_offer_binds_currency(self):
        agreed = {**BASE, 'cap_micro': 900, 'currency': 'EUR'}
        offer = direct_offer('c' * 64, 'one', 1500, agreed)
        context = terms_context(digest(offer), agreed)
        _, quote = fixture_request({**REQUEST, 'input': direct_task_text('Brief', offer)}, context)
        self.assertEqual(quote['currency'], 'EUR')
        changed = {**offer, 'terms': {**agreed, 'currency': 'GBP'}}
        with self.assertRaises(ValueError):
            fixture_request({**REQUEST, 'input': direct_task_text('Brief', changed)}, context)

    def test_legacy_dollar_terms_are_unchanged(self):
        agreed = terms({**BASE, 'cap_microusd': 276})
        self.assertEqual(budget(agreed), (276, None))
        commitment = 'd' * 64
        self.assertEqual(terms_context(commitment, agreed), mission_context(commitment, 276))
        text = task_text('Brief', 276, commitment)
        self.assertIn('"cap_microusd":276', text)
        _, quote = fixture_request({**REQUEST, 'input': text}, mission_context(commitment, 276))
        self.assertEqual(quote['tariff'], 'fictional-usd-v1')
        self.assertNotIn('currency', quote)

    def test_unknown_or_mixed_currency_shapes_are_refused(self):
        for bad in ({**BASE, 'cap_micro': 1, 'currency': 'JPY'},
                    {**BASE, 'cap_micro': 1, 'currency': 'GBP', 'cap_microusd': 1},
                    {**BASE, 'cap_micro': 1},
                    {**BASE, 'cap_micro': -1, 'currency': 'GBP'}):
            with self.assertRaises(ValueError):
                terms(bad)

    def test_usage_records_take_the_mission_currency(self):
        legacy = {'simulated': True, 'actual_microusd': 20, 'held_microusd': 0}
        self.assertIs(in_currency(legacy, None), legacy)
        self.assertEqual(in_currency(legacy, 'GBP'), {'simulated': True, 'actual_micro': 20, 'held_micro': 0, 'currency': 'GBP'})


if __name__ == '__main__':
    unittest.main()
