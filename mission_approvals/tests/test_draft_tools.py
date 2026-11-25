"""Shared draft MCP tools over real proposals, driven by the official MCP client. Fictional identities."""
import unittest

from conversation.inbox import InboxAccess
from conversation.proposals import LocalProposals
from conversation.shared_draft import DraftAccess
from mission_approvals.inbox import OfferInbox
from mission_approvals.server import build_server
from mission_approvals.tests.test_inbox_tools import InboxToolTests, payload


class DraftToolTests(InboxToolTests):
    def setUp(self):
        super().setUp()
        self.proposals = LocalProposals(self.ledger, self.keys['alice'], self.sessions['alice'])
        self.drafts = DraftAccess(self.proposals, self.store, self.access._lease, lambda: self.sessions['bob'])
        self.server = build_server(OfferInbox(lambda: int(self.now)), conversation_inbox=self.access,
                                   shared_drafts=self.drafts)

    def approve(self, name, draft_id):
        binding = self.ledger.bind_context(self.keys[name], self.sessions[name], 'trip')
        review = self.proposals.prepare_approval(self.keys[name], self.sessions[name], binding, draft_id)
        self.proposals.approve(self.keys[name], self.sessions[name], binding, review, review['review_digest'])

    def test_tools_registered_only_when_host_supplies_inbox(self):
        self.assertEqual(self.tools(), ['acknowledge_inbox', 'check_inbox', 'inbox_status', 'list_drafts',
                                        'list_mission_offers', 'review_mission_offer', 'revise_draft',
                                        'start_draft', 'view_draft'])

    def test_draft_round_trip_and_owner_only_approval(self):
        draft = payload(self.call('start_draft', {'request_id': 'd1', 'text': 'Fictional: train at 9'}))
        self.assertEqual(draft['revision'], 1)
        self.assertIn('cannot approve', draft['next_step'])
        revised = payload(self.call('revise_draft', {'request_id': 'd2', 'draft_id': draft['draft_id'],
                                                     'text': 'Fictional: train at 10'}))
        self.assertEqual((revised['kind'], revised['revision']), ('revision', 2))
        self.approve('alice', revised['draft_id'])
        self.approve('bob', revised['draft_id'])
        view = payload(self.call('view_draft', {'draft_id': revised['draft_id']}))
        self.assertTrue(view['final'])
        listed = payload(self.call('list_drafts'))
        self.assertEqual([d['revision'] for d in listed['drafts']], [2])

    def test_peer_draft_text_is_cleaned_and_suggestions_stay_separate(self):
        own = DraftAccess(self.proposals, self.store,
                          self.store.provision(self.keys['alice'], self.sessions['alice'], 'alice_assistant', 'trip'),
                          lambda: self.sessions['alice'])
        theirs = own.start('a1', 'Fictional‮ plan\x07')
        view = payload(self.call('view_draft', {'draft_id': theirs['draft_id']}))
        self.assertNotIn('‮', view['text'])
        suggestion = payload(self.call('revise_draft', {'request_id': 's1', 'draft_id': theirs['draft_id'],
                                                        'text': 'Fictional counter plan'}))
        self.assertEqual(suggestion['kind'], 'suggestion')

    def test_unknown_draft_reports_unavailable(self):
        self.assertTrue(self.call('view_draft', {'draft_id': 'missing'}).is_error)


del InboxToolTests

if __name__ == '__main__':
    unittest.main()
