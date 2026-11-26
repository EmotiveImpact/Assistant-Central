"""Owner questions and the Telegram adapter with a fake Bot API. Fictional identities."""
import sqlite3
import unittest
from unittest import mock
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

    def tap(self, phone, payload, chat_id=777, markup=None):
        # Telegram sends back the message the button was on, buttons included.
        message = {'chat': {'id': chat_id}, **({'reply_markup': markup} if markup else {})}
        phone.handle({'update_id': 2, 'callback_query': {'id': 'cb1', 'data': payload, 'message': message}})


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
        self.tap(phone, buttons[0]['callback_data'], markup=message['reply_markup'])
        answer = self.access.answer('q1')
        self.assertEqual((answer['answer'], answer['answered_via']), ('Friday', 'phone'))
        self.assertIn('Answered: Friday', self.bot.sent('answerCallbackQuery')[-1]['text'])

    def test_a_tap_counts_while_parlu_is_locked_and_unpair_stops_the_next_message(self):
        phone = self.phone('full')
        self.pair(phone)
        self.ask()
        phone.send_waiting()
        callback = self.bot.sent()[-1]['reply_markup']['inline_keyboard'][1][0]['callback_data']
        with mock.patch.object(self.questions.storage, 'open', side_effect=ConversationDenied('locked')):
            self.tap(phone, callback)  # The question text cannot be read, and is not needed.
        self.assertEqual(self.bot.sent('answerCallbackQuery')[-1]['text'], 'Answer saved.')
        self.assertEqual(self.access.answer('q1')['answer'], 'Saturday')
        # A batch reads the pairing before every message, so an Unpair mid-batch sends nothing more.
        self.ask('q2'); self.ask('q3')
        before = len(self.bot.sent())
        real = phone._call
        def unpair_after_first(method, payload, **options):
            result = real(method, payload, **options)
            if method == 'sendMessage':
                self.questions.unpair(self.sessions['bob'])
            return result
        with mock.patch.object(phone, '_call', side_effect=unpair_after_first):
            self.assertEqual(phone.send_waiting(), 1)
        self.assertEqual(len(self.bot.sent()), before + 1)

    def test_replacement_pairing_reports_when_the_new_code_is_used(self):
        phone = self.phone('full')
        self.pair(phone)
        first = self.questions.phone_status(self.sessions['bob'])
        made = self.questions.start_pairing(self.sessions['bob'])
        waiting = self.questions.phone_status(self.sessions['bob'])
        self.assertEqual((waiting['paired'], waiting['pairing_open'], waiting['paired_at']), (True, True, first['paired_at']))
        phone.handle({'update_id': 9, 'message': {'chat': {'id': 888, 'type': 'private'}, 'text': '/start ' + made['code']}})
        done = self.questions.phone_status(self.sessions['bob'])
        self.assertFalse(done['pairing_open'])
        self.assertGreaterEqual(done['paired_at'], made['started_at'])
        self.assertEqual(self.questions.paired_chat(), '888')

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


class RunnerTests(QuestionCase):
    def test_a_refused_message_never_stops_the_bot_hearing_a_new_phone(self):
        from owner_phone.runner import PhoneRunner
        old_chat_blocked = self.bot

        def post(url, payload, timeout):
            if url.endswith('/sendMessage') and payload.get('chat_id') == '777':
                return {'ok': False, 'description': 'Forbidden: bot was blocked by the user'}
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'parlu_fictional_bot'}}
            return old_chat_blocked(url, payload, timeout)

        runner = PhoneRunner(self.questions, 'full', token=TOKEN, post=post)
        self.pair(runner.phone)
        self.ask()
        code = self.questions.start_pairing(self.sessions['bob'])['code']
        self.bot.updates = [{'update_id': 5, 'message': {'chat': {'id': 888, 'type': 'private'}, 'text': f'/start {code}'}}]
        with self.assertRaises(TelegramError):
            runner.step()  # The old chat refused the question, but the new phone was still heard.
        self.assertEqual(self.questions.paired_chat(), '888')
        runner.step()
        self.assertEqual(self.bot.sent()[-1]['chat_id'], '888')
        self.assertIn('which day', self.bot.sent()[-1]['text'])
