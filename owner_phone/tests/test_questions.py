"""Owner questions and the Telegram adapter with a fake Bot API. Fictional identities."""
import sqlite3
import unittest
from contextlib import closing

from conversation import ConversationDenied
from conversation.tests.test_inbox import InboxCase
from owner_phone.questions import OwnerQuestions, QuestionAccess
from owner_phone.telegram import TelegramPhone, TelegramError, NOTICE_TEXT

TOKEN = '123456:fictional-test-token'


class FakeBot:
    def __init__(self):
        self.calls, self.updates, self.fail = [], [], False

    def __call__(self, url, payload, timeout):
        if self.fail:
            raise OSError(f'network down for {url}')
        method = url.rsplit('/', 1)[1]
        self.calls.append((method, payload))
        if method == 'getUpdates':
            batch, self.updates = self.updates, []
            return {'ok': True, 'result': batch}
        return {'ok': True, 'result': {}}

    def sent(self, method='sendMessage'):
        return [payload for name, payload in self.calls if name == method]


class QuestionCase(InboxCase):
    def setUp(self):
        super().setUp()
        self.questions = OwnerQuestions(self.root / 'questions_bob', self.inbox, self.keys['bob'])
        self.bob_lease = self.lease()
        self.access = QuestionAccess(self.questions, self.bob_lease, lambda: self.sessions['bob'])
        self.bot = FakeBot()

    def tearDown(self):
        self.questions.close()
        super().tearDown()

    def ask(self, request='q1', options=('Friday', 'Saturday')):
        return self.access.ask(request, 'Fictional: which day suits for the trip?', list(options))

    def phone(self, mode='full'):
        return TelegramPhone(self.questions, token=TOKEN, mode=mode, post=self.bot)

    def pair(self, phone, chat_id=777):
        code = self.questions.start_pairing(self.sessions['bob'])['code']
        phone.handle({'update_id': 1, 'message': {'chat': {'id': chat_id, 'type': 'private'}, 'text': f'/start {code}'}})

    def tap(self, phone, payload, chat_id=777):
        phone.handle({'update_id': 2, 'callback_query': {'id': 'cb1', 'data': payload,
                                                          'message': {'chat': {'id': chat_id}}}})


class QuestionTests(QuestionCase):
    def test_ask_answer_in_central_and_read_back(self):
        asked = self.ask()
        self.assertEqual((asked['state'], asked['authority']), ('waiting', 'information-only'))
        [waiting] = self.questions.waiting(self.sessions['bob'])
        self.questions.answer(self.sessions['bob'], waiting['question_id'], 1)
        answer = self.access.answer('q1')
        self.assertEqual((answer['state'], answer['answer'], answer['answered_via']), ('answered', 'Saturday', 'central'))
        with self.assertRaises(ConversationDenied):
            self.questions.answer(self.sessions['bob'], waiting['question_id'], 0)

    def test_ask_is_idempotent_and_bounded(self):
        first = self.ask()
        self.assertEqual(self.ask()['question_id'], first['question_id'])
        for options in (['Only one'], ['A', 'A'], ['A', 'B', 'C', 'D', 'E'], ['x' * 65, 'B']):
            with self.subTest(options=options), self.assertRaises(ConversationDenied):
                self.ask(f'q{len(options)}x', options)
        with self.assertRaises(ConversationDenied):
            self.access.ask('q1', 'Fictional: a different question', ['Friday', 'Saturday'])

    def test_question_expires(self):
        self.questions.ask(self.sessions['bob'], self.bob_lease, request_id='q1', seconds=60,
                           question='Fictional: still there?', options=['Yes', 'No'])
        self.now += 61
        self.assertEqual(self.access.answer('q1')['state'], 'expired')
        self.assertEqual(self.questions.waiting(self.sessions['bob']), [])

    def test_other_owner_and_revoked_lease_are_refused(self):
        self.ask()
        with self.assertRaises(Exception):
            self.questions.waiting(self.sessions['carol'])
        self.inbox.revoke(self.sessions['bob'], self.bob_lease)
        with self.assertRaises(Exception):
            self.access.answer('q1')

    def test_questions_are_encrypted_at_rest(self):
        self.ask()
        with closing(sqlite3.connect(self.root / 'questions_bob' / 'questions.sqlite')) as db:
            raw = db.execute('SELECT body FROM owner_questions').fetchall()
        self.assertTrue(raw and all('which day' not in row[0] for row in raw))


class TelegramTests(QuestionCase):
    def test_pairing_then_full_mode_button_answers(self):
        phone = self.phone('full')
        self.pair(phone)
        self.assertTrue(self.questions.phone_status(self.sessions['bob'])['paired'])
        self.ask()
        self.assertEqual(phone.send_waiting(), 1)
        self.assertEqual(phone.send_waiting(), 0)  # Each question goes out once.
        message = self.bot.sent()[-1]
        self.assertIn('which day', message['text'])
        buttons = [row[0] for row in message['reply_markup']['inline_keyboard']]
        self.assertEqual([b['text'] for b in buttons], ['Friday', 'Saturday'])
        self.assertTrue(all(len(b['callback_data'].encode()) <= 64 for b in buttons))
        self.tap(phone, buttons[0]['callback_data'])
        answer = self.access.answer('q1')
        self.assertEqual((answer['answer'], answer['answered_via']), ('Friday', 'phone'))
        self.assertIn('Answered: Friday', self.bot.sent('answerCallbackQuery')[-1]['text'])

    def test_notice_mode_sends_no_question_text(self):
        phone = self.phone('notice')
        self.pair(phone)
        self.ask()
        phone.send_waiting()
        self.assertEqual(self.bot.sent()[-1], {'chat_id': '777', 'text': NOTICE_TEXT})

    def test_forged_tag_other_chat_and_bad_code_are_refused(self):
        phone = self.phone('full')
        self.pair(phone, chat_id=777)
        question = self.ask()
        good = f"a:{question['question_id']}:0:{self.questions.tag(question['question_id'], 0)}"
        self.tap(phone, f"a:{question['question_id']}:1:{self.questions.tag(question['question_id'], 0)}")
        self.tap(phone, good, chat_id=999)
        self.tap(phone, 'nonsense')
        self.assertEqual(self.access.answer('q1')['state'], 'waiting')
        # A stranger cannot pair with a guessed code, and a used code cannot be replayed.
        phone.handle({'update_id': 3, 'message': {'chat': {'id': 999, 'type': 'private'}, 'text': '/start 0000'}})
        self.assertEqual(self.questions.paired_chat(), '777')

    def test_pairing_code_expires_and_is_single_use(self):
        phone = self.phone()
        code = self.questions.start_pairing(self.sessions['bob'])['code']
        self.now += 601
        phone.handle({'update_id': 1, 'message': {'chat': {'id': 1, 'type': 'private'}, 'text': f'/start {code}'}})
        self.assertIsNone(self.questions.paired_chat())

    def test_unpaired_sends_nothing_and_unpair_works(self):
        phone = self.phone()
        self.ask()
        self.assertEqual(phone.send_waiting(), 0)
        self.pair(phone)
        self.questions.unpair(self.sessions['bob'])
        self.assertIsNone(self.questions.paired_chat())
        self.assertFalse(phone.nudge(2))

    def test_poll_advances_offset_and_errors_hide_token(self):
        phone = self.phone()
        code = self.questions.start_pairing(self.sessions['bob'])['code']
        self.bot.updates = [{'update_id': 41, 'message': {'chat': {'id': 5, 'type': 'private'}, 'text': f'/start {code}'}}]
        self.assertEqual(phone.poll_once(), 1)
        self.assertEqual(phone.offset, 42)
        self.assertEqual(self.questions.paired_chat(), '5')
        self.bot.fail = True
        with self.assertRaises(TelegramError) as caught:
            phone.poll_once()
        self.assertNotIn('fictional-test-token', str(caught.exception))
        self.assertNotIn('fictional-test-token', repr(phone))

    def test_nudge_is_body_free(self):
        phone = self.phone()
        self.pair(phone)
        self.assertTrue(phone.nudge(3))
        self.assertEqual(self.bot.sent()[-1]['text'], '3 items are waiting for your review in Parlu.')


if __name__ == '__main__':
    unittest.main()
