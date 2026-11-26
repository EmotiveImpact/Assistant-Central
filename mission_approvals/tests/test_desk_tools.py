"""Owner desk MCP tools over the real ledger, driven by the official MCP client. Fictional identities."""
import unittest

from conversation.autonomy import DeskAccess, OwnerDesk
from mission_approvals.inbox import OfferInbox
from mission_approvals.server import build_server
from mission_approvals.tests.test_inbox_tools import InboxToolTests, payload


class DeskToolTests(InboxToolTests):
    def setUp(self):
        super().setUp()
        self.desk = OwnerDesk(self.store.directory.parent / 'desk', self.ledger, self.store, self.keys['bob'])
        lease = self.access._lease
        self.server = build_server(OfferInbox(lambda: int(self.now)), conversation_inbox=self.access,
                                   owner_desk=DeskAccess(self.desk, lease, lambda: self.sessions['bob']))

    def tearDown(self):
        self.desk.close()
        super().tearDown()

    def history(self):
        binding = self.ledger.bind_context(self.keys['alice'], self.sessions['alice'], 'trip')
        return self.ledger.history(self.keys['alice'], self.sessions['alice'], binding)

    def test_tools_registered_only_when_host_supplies_inbox(self):
        self.assertEqual(self.tools(), ['acknowledge_inbox', 'check_inbox', 'inbox_status',
                                        'list_mission_offers', 'message_status', 'propose_message',
                                        'read_owner_guidance', 'review_mission_offer'])

    def test_default_waits_for_owner_then_sends_exact_text(self):
        result = payload(self.call('propose_message', {'request_id': 'm1', 'text': 'Fictional: Friday suits'}))
        self.assertEqual(result['state'], 'awaiting_owner')
        self.assertEqual(self.history(), [])
        [draft] = self.desk.drafts(self.sessions['bob'])
        self.desk.approve(self.sessions['bob'], draft['draft_id'], draft['digest'])
        status = payload(self.call('message_status', {'request_id': 'm1'}))
        self.assertEqual(status['state'], 'sent')
        self.assertEqual([e['text'] for e in self.history()], ['Fictional: Friday suits'])

    def test_standing_policy_sends_marked_as_assistant(self):
        self.desk.set_policy(self.sessions['bob'], 'bob_assistant', 'trip', mode='within_limits', max_auto=1)
        result = payload(self.call('propose_message', {'request_id': 'm1', 'text': 'Fictional hello'}))
        self.assertTrue(result['sent_without_review'])
        self.assertEqual(self.history()[0]['kind'], 'assistant')
        second = payload(self.call('propose_message', {'request_id': 'm2', 'text': 'Fictional again'}))
        self.assertEqual(second['state'], 'awaiting_owner')

    def test_changed_text_for_same_request_is_refused(self):
        self.call('propose_message', {'request_id': 'm1', 'text': 'Fictional A'})
        self.assertTrue(self.call('propose_message', {'request_id': 'm1', 'text': 'Fictional B'}).is_error)
        self.assertTrue(self.call('propose_message', {'request_id': 'bad id!', 'text': 'Fictional'}).is_error)

    def test_guidance_reaches_only_this_assistant(self):
        self.desk.add_guidance(self.sessions['bob'], 'bob_assistant', 'trip', 'Fictional: budget is tight')
        notes = payload(self.call('read_owner_guidance'))
        self.assertEqual([n['text'] for n in notes['notes']], ['Fictional: budget is tight'])
        self.assertEqual(self.history(), [])

    def test_expired_session_reports_unavailable_without_detail(self):
        self.auths['bob'].logout(self.sessions['bob'])
        self.assertTrue(self.call('read_owner_guidance').is_error)
        self.assertTrue(self.call('propose_message', {'request_id': 'm1', 'text': 'Fictional'}).is_error)


del InboxToolTests  # Do not run the parent suite twice from this module.

if __name__ == '__main__':
    unittest.main()
