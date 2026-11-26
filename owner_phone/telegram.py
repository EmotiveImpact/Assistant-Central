"""Telegram adapter for owner questions: pairing, sending and answering by button.

Uses the Bot API over HTTPS with long polling (``getUpdates``), so it needs no
public web address. The bot token comes from the host, typically the
``TELEGRAM_BOT_TOKEN`` environment variable, and is never logged or returned.

Telegram bot chats are not end-to-end encrypted. In the default ``notice`` mode
the phone only learns that a question is waiting, and the owner answers in
Central. In ``full`` mode, which the owner must choose, the question and its
options are sent to Telegram and the owner can answer with a button.
Only the one chat the owner paired with a one-time code is accepted.
"""
import json
import os
import re
import urllib.request

from conversation.ledger import ConversationDenied, need

from .questions import OwnerQuestions

API_BASE = 'https://api.telegram.org'
MODES = ('notice', 'full')
NOTICE_TEXT = 'Your assistant has a question for you. Open Parlu to answer it.'
ANSWER_NOTE = 'Your answer is information for your assistant. It does not approve sending, sharing, running or paying for anything.'


class TelegramError(RuntimeError):
    """A Telegram call failed. The message never contains the token."""


def _urllib_post(url, payload, timeout):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


class TelegramPhone:
    def __init__(self, questions, *, token=None, mode='notice', post=_urllib_post, api_base=API_BASE):
        need(type(questions) is OwnerQuestions and mode in MODES and callable(post))
        token = token if token is not None else os.environ.get('TELEGRAM_BOT_TOKEN', '')
        need(type(token) is str and 0 < len(token) <= 256 and ':' in token)
        self.questions, self.mode, self._post, self._base = questions, mode, post, api_base
        self.__token = token
        self.offset = None

    def _call(self, method, payload, timeout=35):
        try:
            result = self._post(f'{self._base}/bot{self.__token}/{method}', payload, timeout)
        except Exception as error:
            raise TelegramError(f'Telegram {method} failed ({type(error).__name__})') from None
        if type(result) is not dict or result.get('ok') is not True:
            raise TelegramError(f'Telegram {method} was refused')
        return result.get('result')

    def bot_name(self):
        """The bot's public username, for a t.me pairing link. ``None`` if Telegram gives none."""
        me = self._call('getMe', {}, timeout=10)
        name = me.get('username') if type(me) is dict else None
        return name if type(name) is str and re.fullmatch(r'[A-Za-z0-9_]{5,32}', name) else None

    # Outbound --------------------------------------------------------------

    def send_waiting(self):
        """Send each new question once to the paired chat. Returns how many were sent."""
        chat = self.questions.paired_chat()
        if chat is None:
            return 0
        sent = 0
        for question in self.questions.unsent_for_phone():
            self._call('sendMessage', self._question_message(chat, question))
            self.questions.mark_sent_to_phone(question['question_id'])
            sent += 1
        return sent

    def _question_message(self, chat, question):
        if self.mode == 'notice':
            return {'chat_id': chat, 'text': NOTICE_TEXT}
        buttons = [[{'text': option[:64],
                     'callback_data': f"a:{question['question_id']}:{index}:{self.questions.tag(question['question_id'], index)}"}]
                   for index, option in enumerate(question['options'])]
        return {'chat_id': chat, 'text': f"Your assistant asks:\n\n{question['question']}\n\n{ANSWER_NOTE}",
                'reply_markup': {'inline_keyboard': buttons}}

    def nudge(self, waiting):
        """A body-free reminder that owner reviews are waiting in Central."""
        need(type(waiting) is int and waiting > 0)
        chat = self.questions.paired_chat()
        if chat is None:
            return False
        noun = 'item is' if waiting == 1 else 'items are'
        self._call('sendMessage', {'chat_id': chat, 'text': f'{waiting} {noun} waiting for your review in Parlu.'})
        return True

    # Inbound ---------------------------------------------------------------

    def poll_once(self, timeout=30):
        """Fetch and handle one batch of updates. Returns the number handled."""
        payload = {'timeout': timeout, 'allowed_updates': ['message', 'callback_query']}
        if self.offset is not None:
            payload['offset'] = self.offset
        updates = self._call('getUpdates', payload, timeout=timeout + 5)
        need(type(updates) is list)
        for update in updates:
            if type(update) is dict and type(update.get('update_id')) is int:
                self.offset = update['update_id'] + 1
                self.handle(update)
        return len(updates)

    def handle(self, update):
        """Handle one update. Anything unexpected is ignored, never trusted."""
        try:
            if 'callback_query' in update:
                self._handle_button(update['callback_query'])
            elif 'message' in update:
                self._handle_message(update['message'])
        except (ConversationDenied, KeyError, TypeError, ValueError):
            pass

    def _handle_message(self, message):
        chat = message['chat']
        text = message.get('text', '')
        if chat.get('type') != 'private' or type(text) is not str or not text.startswith('/start '):
            return
        try:
            self.questions.complete_pairing(str(chat['id']), text.split(' ', 1)[1].strip())
            reply = 'Paired. Your assistant can now ask you questions here.'
        except ConversationDenied:
            reply = 'That pairing code is not valid. Create a new one in Parlu.'
        self._call('sendMessage', {'chat_id': chat['id'], 'text': reply})

    def _handle_button(self, query):
        chat = str(query['message']['chat']['id'])
        prefix, question_id, option, tag = query['data'].split(':')
        need(prefix == 'a' and option.isdigit())
        try:
            result = self.questions.answer_from_phone(chat, question_id, int(option), tag)
            note = f"Answered: {result['answer']}"
        except ConversationDenied:
            note = 'That question can no longer be answered here.'
        self._call('answerCallbackQuery', {'callback_query_id': query['id'], 'text': note[:200]})
