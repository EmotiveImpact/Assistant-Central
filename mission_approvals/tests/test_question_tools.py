"""Owner question MCP tools, driven by the official MCP client. Fictional identities."""
import unittest

from mission_approvals.inbox import OfferInbox
from mission_approvals.server import build_server
from mission_approvals.tests.test_inbox_tools import InboxToolTests, payload
from owner_phone.questions import OwnerQuestions, QuestionAccess


class QuestionToolTests(InboxToolTests):
    def setUp(self):
        super().setUp()
        self.questions = OwnerQuestions(self.store.directory.parent / 'questions', self.store, self.keys['bob'])
        self.server = build_server(OfferInbox(lambda: int(self.now)), conversation_inbox=self.access,
                                   owner_questions=QuestionAccess(self.questions, self.access._lease,
                                                                  lambda: self.sessions['bob']))

    def tearDown(self):
        self.questions.close()
        super().tearDown()

    def test_tools_registered_only_when_host_supplies_inbox(self):
        self.assertEqual(self.tools(), ['acknowledge_inbox', 'ask_my_owner', 'check_inbox', 'inbox_status',
                                        'list_mission_offers', 'owner_answer', 'review_mission_offer'])

    def test_ask_and_read_answer(self):
        asked = payload(self.call('ask_my_owner', {'request_id': 'q1', 'question': 'Fictional: train or coach?',
                                                    'options': ['Train', 'Coach']}))
        self.assertEqual(asked['state'], 'waiting')
        self.questions.answer(self.sessions['bob'], asked['question_id'], 0)
        answer = payload(self.call('owner_answer', {'request_id': 'q1'}))
        self.assertEqual((answer['answer'], answer['authority']), ('Train', 'information-only'))

    def test_bad_input_is_refused(self):
        self.assertTrue(self.call('ask_my_owner', {'request_id': 'q1', 'question': 'Fictional?',
                                                   'options': ['Only']}).is_error)
        self.assertTrue(self.call('owner_answer', {'request_id': 'unknown'}).is_error)


del InboxToolTests

if __name__ == '__main__':
    unittest.main()
