"""Questions on the owner's phone: pairing from Parlu over real HTTP, with a fictional bot."""
import os
import threading
import time
import unittest
from unittest import mock

from owner_phone.questions import QuestionAccess
from owner_phone.runner import PhoneRunner
from owner_phone.telegram import NOTICE_TEXT
from workspace_ui import approval_service
from workspace_ui.conversation_service import ConversationConfig, VERSION
from workspace_ui.tests.test_conversation_service import ConversationHTTPTests as Base

TOKEN = '123456:fictional-test-token'


class FictionalBot:
    """Stands in for the Telegram Bot API. Nothing here reaches the internet."""
    def __init__(self):
        self.calls, self.updates, self.lock = [], [], threading.Lock()

    def __call__(self, url, payload, timeout):
        method = url.rsplit('/', 1)[1]
        assert url.startswith('https://api.telegram.org/bot' + TOKEN + '/')
        with self.lock:
            self.calls.append((method, payload))
            if method == 'getMe':
                return {'ok': True, 'result': {'username': 'parlu_fictional_bot'}}
            if method == 'getUpdates':
                batch, self.updates = self.updates, []
                if batch:
                    return {'ok': True, 'result': batch}
        if method == 'getUpdates':
            time.sleep(0.05)
            return {'ok': True, 'result': []}
        return {'ok': True, 'result': {}}

    def sent(self):
        with self.lock:
            return [payload for method, payload in self.calls if method == 'sendMessage']

    def answered(self):
        with self.lock:
            return [payload for method, payload in self.calls if method == 'answerCallbackQuery']


def until(check, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError('timed out')


class PhoneTests(Base):
    def setUp(self):
        self.bot = FictionalBot()
        runner = lambda questions, mode: PhoneRunner(questions, mode, token=TOKEN, post=self.bot)
        patch = mock.patch.object(approval_service, 'PhoneRunner', runner)
        patch.start()
        self.addCleanup(patch.stop)
        super().setUp()

    mode = 'notice'

    def start(self):
        self.config = ConversationConfig({'version': VERSION, 'directory': str(self.config.directory),
                                          'actors': [{'directory': str(a['directory']), 'fingerprint': a['fingerprint']}
                                                     for a in self.config.actors],
                                          'phone': {'telegram': self.mode}})
        super().start()

    def ask_alice(self):
        approvals = self.server.owner.approvals
        principal, token = self.keys['alice'], self.tokens['alice']
        def make():
            lease = approvals.inbox.provision(principal, token, 'alice_assistant', 'thread_1')
            _, questions, _ = approvals.owner(principal)
            return QuestionAccess(questions, lease, lambda: token).ask('q1', 'Fictional: train or coach?', ['Train', 'Coach'])
        return make

    def test_pair_from_parlu_then_questions_reach_the_phone(self):
        status = until(lambda: (lambda s: s if s['bot'] else None)(self.call('alice', '/api/approvals/phone')))
        self.assertEqual((status['available'], status['paired'], status['mode'], status['bot']),
                         (True, False, 'notice', 'parlu_fictional_bot'))
        self.call('alice', '/api/approvals/phone/pair', {'extra': 1}, expect=400)
        made = self.call('alice', '/api/approvals/phone/pair', {})
        self.assertEqual(made['start_link'], 'https://t.me/parlu_fictional_bot?start=' + made['code'])
        with self.bot.lock:
            self.bot.updates.append({'update_id': 1, 'message': {'chat': {'id': 777, 'type': 'private'},
                                                                 'text': '/start ' + made['code']}})
        until(lambda: self.call('alice', '/api/approvals/phone')['paired'])
        self.create()
        self.server.owner_worker.submit(self.ask_alice()).result()
        # Notice mode: the phone learns only that a question is waiting, never its words.
        until(lambda: any(m['text'] == NOTICE_TEXT and m['chat_id'] == '777' for m in self.bot.sent()))
        self.assertFalse(any('train' in m['text'].lower() for m in self.bot.sent()))
        self.assertEqual(self.call('alice', '/api/approvals/phone/unpair', {}), {'paired': False})
        self.assertFalse(self.call('alice', '/api/approvals/phone')['paired'])

    def test_full_mode_taps_answer_even_after_signing_out(self):
        self.stop()
        self.mode = 'full'
        self.start()
        self.tokens = {n: self.login(n) for n in self.keys}
        until(lambda: self.call('alice', '/api/approvals/phone')['bot'])
        made = self.call('alice', '/api/approvals/phone/pair', {})
        with self.bot.lock:
            self.bot.updates.append({'update_id': 1, 'message': {'chat': {'id': 777, 'type': 'private'},
                                                                 'text': '/start ' + made['code']}})
        until(lambda: self.call('alice', '/api/approvals/phone')['paired'])
        self.create()
        self.server.owner_worker.submit(self.ask_alice()).result()
        message = until(lambda: next((m for m in self.bot.sent() if 'train' in m['text'].lower()), None))
        coach = message['reply_markup']['inline_keyboard'][1][0]
        self.assertTrue(any(q['question'] == 'Fictional: train or coach?' for q in self.call('alice', '/api/approvals')['questions']))
        # Alice signs out; Parlu stays open and the bot keeps listening.
        self.call('alice', '/api/session', {}, method='DELETE')
        with self.bot.lock:
            self.bot.updates.append({'update_id': 2, 'callback_query': {'id': 'cb1', 'data': coach['callback_data'],
                                                                        'message': {'chat': {'id': 777}, 'reply_markup': message['reply_markup']}}})
        until(lambda: any(m.get('text') == 'Answered: Coach' for m in self.bot.answered()))
        self.tokens['alice'] = self.login('alice')
        self.assertFalse(any(q['question'] == 'Fictional: train or coach?' for q in self.call('alice', '/api/approvals')['questions']))

    def test_only_the_person_running_parlu_gets_the_bot(self):
        status = self.call('bob', '/api/approvals/phone')
        self.assertEqual((status['available'], status['reason']), (False, 'not_set_up'))
        self.call('bob', '/api/approvals/phone/pair', {}, expect=400)
        self.assertEqual(self.request('GET', '/api/approvals/phone')[0], 401)


class PhoneConfigTests(Base):
    def test_phone_needs_a_known_mode_and_a_token(self):
        base = {'version': VERSION, 'directory': str(self.config.directory),
                'actors': [{'directory': str(a['directory']), 'fingerprint': a['fingerprint']} for a in self.config.actors]}
        for bad in ({'telegram': 'loud'}, {'telegram': 'notice', 'extra': 1}, 'notice'):
            with self.assertRaises(Exception):
                ConversationConfig({**base, 'phone': bad})
        self.stop()
        self.config = ConversationConfig({**base, 'phone': {'telegram': 'full'}})
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TELEGRAM_BOT_TOKEN', None)
            self.start()
        self.tokens = {n: self.login(n) for n in self.keys}
        status = self.call('alice', '/api/approvals/phone')
        self.assertEqual((status['available'], status['reason']), (False, 'no_bot_token'))
        self.call('alice', '/api/approvals/phone/pair', {}, expect=400)


def load_tests(loader, tests, pattern):
    # Only the tests written here; the shared HTTP base class's own tests run in their own module.
    suite = unittest.TestSuite()
    for case in (PhoneTests, PhoneConfigTests):
        for name in loader.getTestCaseNames(case):
            if name in vars(case):
                suite.addTest(case(name))
    return suite


if __name__ == '__main__':
    unittest.main()
