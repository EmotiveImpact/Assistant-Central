import copy
import unittest
from demo import fixture
from network import Denied, digest
from review import render_review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.meeting, self.agents, _ = fixture()
        self.message = self.agents[1].preview_availability(self.meeting)

    def test_availability_shows_exact_names_recipient_and_all_candidate_meanings(self):
        output = render_review(self.meeting, self.message)
        self.assertIn('From: Bob [bob]', output)
        self.assertIn('Only recipient of this message: Alice [alice]', output)
        self.assertIn('2026-11-06T13:00:00Z to 2026-11-06T13:30:00Z (UTC): NOT AVAILABLE', output)
        self.assertIn('2026-11-06T14:00:00Z to 2026-11-06T14:30:00Z (UTC): AVAILABLE', output)
        self.assertIn(digest(self.message), output)
        self.assertIn('does not create a calendar booking', output)

    def test_proposal_and_acceptance_show_time_instead_of_raw_index(self):
        for kind, sender, recipient, verb in (('proposal', 'alice', 'bob', 'send a proposed time'),
                                               ('accept', 'bob', 'alice', 'accept the proposed time')):
            with self.subTest(kind=kind):
                self.message.update(type=kind, sender=sender, recipient=recipient, payload={'candidate_index': 2})
                output = render_review(self.meeting, self.message)
                self.assertIn(verb, output)
                self.assertIn('Exact time: 2026-11-06T15:00:00Z to 2026-11-06T15:30:00Z (UTC)', output)

    def test_empty_availability_is_explicit(self):
        self.message['payload']['candidate_indices'] = []
        output = render_review(self.meeting, self.message)
        self.assertIn('No candidate slots are available', output)
        self.assertEqual(output.count(': NOT AVAILABLE'), 4)

    def test_review_never_mutates_or_approves_the_message(self):
        original = copy.deepcopy(self.message)
        render_review(self.meeting, self.message)
        self.assertEqual(original, self.message)
        self.assertEqual(self.agents[1].human._grants, {})

    def test_malformed_private_or_wrong_context_messages_are_rejected(self):
        mutations = (
            {'context': '0' * 64}, {'meeting': 'wrong'}, {'recipient': 'stranger'},
            {'recipient': 'charlie'}, {'payload': {'candidate_indices': [15]}},
            {'payload': {'candidate_indices': [1], 'private_calendar': 'secret'}},
            {'sender': 'bob', 'type': 'proposal', 'payload': {'candidate_index': 1}},
            {'sender': 'bob\nAPPROVED'},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(Denied):
                render_review(self.meeting, {**self.message, **mutation})


if __name__ == '__main__':
    unittest.main()
