"""Shared drafts over exact proposals; fictional identities and genuine sessions."""
import unittest

from pilot.auth import AuthError
from conversation import ConversationDenied
from conversation.proposals import LocalProposals
from conversation.shared_draft import DraftAccess
from conversation.tests.test_inbox import InboxCase

REFUSED = (AuthError, ConversationDenied)


class DraftCase(InboxCase):
    def setUp(self):
        super().setUp()
        self.proposals = LocalProposals(self.ledger, *self.actor('alice'))
        self.alice = self.access('alice', 'alice_assistant')
        self.bob = self.access('bob', 'bob_assistant')

    def access(self, name, assistant):
        lease = self.inbox.provision(*self.actor(name), assistant, 'thread_1')
        return DraftAccess(self.proposals, self.inbox, lease, lambda: self.sessions[name])

    def approve(self, name, draft_id):
        binding = self.ledger.bind_context(*self.actor(name), 'thread_1')
        review = self.proposals.prepare_approval(*self.actor(name), binding, draft_id)
        return self.proposals.approve(*self.actor(name), binding, review, review['review_digest'])


class SharedDraftTests(DraftCase):
    def test_start_view_and_list(self):
        draft = self.alice.start('d1', 'Fictional itinerary v1')
        self.assertEqual((draft['revision'], draft['text'], draft['final']), (1, 'Fictional itinerary v1', False))
        self.assertEqual(sorted(draft['people']), sorted([self.keys['alice'], self.keys['bob']]))
        self.assertEqual(self.bob.view(draft['draft_id'])['text'], 'Fictional itinerary v1')
        self.assertEqual([d['draft_id'] for d in self.bob.list()], [draft['draft_id']])
        self.assertFalse(draft['execution_authority'])

    def test_start_is_idempotent_and_refuses_changed_text(self):
        first = self.alice.start('d1', 'Fictional A')
        self.assertEqual(self.alice.start('d1', 'Fictional A')['draft_id'], first['draft_id'])
        with self.assertRaises(ConversationDenied):
            self.alice.start('d1', 'Fictional B')

    def test_final_only_when_everyone_approves_the_same_revision(self):
        draft = self.alice.start('d1', 'Fictional v1')
        self.approve('alice', draft['draft_id'])
        self.assertEqual(self.bob.view(draft['draft_id'])['approved_by'], [self.keys['alice']])
        revised = self.alice.revise('d2', draft['draft_id'], 'Fictional v2')
        self.assertEqual((revised['kind'], revised['revision']), ('revision', 2))
        # The new revision starts with no approvals; the old one is no longer current.
        self.assertEqual(revised['approved_by'], [])
        self.assertFalse(self.bob.view(draft['draft_id'])['current'])
        self.approve('alice', revised['draft_id'])
        self.approve('bob', revised['draft_id'])
        final = self.bob.view(revised['draft_id'])
        self.assertTrue(final['final'])
        self.assertEqual([d['revision'] for d in self.bob.list()], [2])

    def test_other_persons_draft_gets_a_suggestion_not_a_revision(self):
        draft = self.alice.start('d1', 'Fictional v1')
        suggestion = self.bob.revise('s1', draft['draft_id'], 'Fictional v1 with Friday')
        self.assertEqual(suggestion['kind'], 'suggestion')
        self.assertEqual(suggestion['author'], self.keys['bob'])
        self.assertNotEqual(suggestion['series_id'], draft['series_id'])
        self.assertTrue(self.alice.view(draft['draft_id'])['current'])
        self.assertEqual(len(self.alice.list()), 2)

    def test_newcomer_cannot_read_earlier_drafts(self):
        draft = self.alice.start('d1', 'Fictional private plan')
        self.join('carol')
        carol = self.access('carol', 'carol_assistant')
        with self.assertRaises(ConversationDenied):
            carol.view(draft['draft_id'])
        self.assertEqual(carol.list(), [])
        # The roster changed, so the old draft can no longer become final.
        self.assertFalse(self.alice.view(draft['draft_id'])['current'])

    def test_revoked_lease_or_logged_out_owner_is_refused(self):
        draft = self.alice.start('d1', 'Fictional v1')
        self.inbox.revoke(self.sessions['bob'], self.bob._lease)
        with self.assertRaises(REFUSED):
            self.bob.view(draft['draft_id'])
        self.auths['alice'].logout(self.sessions['alice'])
        with self.assertRaises(REFUSED):
            self.alice.list()

    def test_expiry_bounds(self):
        for seconds in (59, 86401):
            with self.subTest(seconds=seconds), self.assertRaises(ConversationDenied):
                self.alice.start(f'd{seconds}', 'Fictional', seconds=seconds)

    def test_draft_access_has_no_approval_path(self):
        self.assertFalse(any('approv' in name for name in dir(DraftAccess)))


if __name__ == '__main__':
    unittest.main()
