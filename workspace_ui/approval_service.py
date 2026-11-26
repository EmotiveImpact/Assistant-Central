"""One approval inbox for each owner in Central.

Everything that waits for a person is gathered in one place: messages their
assistant proposed, questions their assistant asked, shared drafts waiting for
their approval, and their own timeline. Each decision still goes through the
store that owns it, with that store's checks, the owner's own session and the
exact digest the owner was shown.
"""
from pathlib import Path
import re
import time

from conversation.autonomy import OwnerDesk
from conversation.inbox import InboxStore
from conversation.ledger import ConversationDenied, identifier, need
from conversation.proposals import LocalProposals
from conversation.shared_draft import draft_view
from conversation.timeline import OwnerTimeline
from owner_phone.questions import OwnerQuestions
from owner_phone.runner import PhoneRunner
from pilot.server import RequestDenied, exact

MISSION_PREFIX = '{"domain":"assistant-central/mission-agreement/'
ROUTE = re.compile(r'/api/approvals(?:/(messages|questions|drafts)/([A-Za-z0-9_-]{1,64})/(approve|decline|answer|review))?')
SETTINGS = re.compile(r'/api/approvals/(policy|guidance|timeline)')
PHONE = re.compile(r'/api/approvals/phone(?:/(pair|unpair))?')


class ApprovalService:
    def __init__(self, host, directory, *, phone=None):
        self.host = host
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.inbox = InboxStore(self.directory / 'inbox', host.ledger)
        self._owners = {}
        self._reviews = {}
        self.phone, self.phone_problem = None, None
        if phone is not None:
            # One bot serves the person who runs this copy of Parlu, never the other local accounts.
            _, questions, _ = self.owner(host.ledger.storage_owner)
            try:
                self.phone = PhoneRunner(questions, phone['telegram']).start()
            except ConversationDenied:
                self.phone_problem = 'no_bot_token'

    def close(self):
        if self.phone is not None:
            self.phone.close()
        for desk, questions, timeline in self._owners.values():
            desk.close(); questions.close(); timeline.close()
        self._owners.clear()
        self.inbox.close()

    def owner(self, principal):
        if principal not in self._owners:
            base = self.directory / ('owner-' + principal[:32])
            base.mkdir(mode=0o700, exist_ok=True)
            auth = self.host.ledger.actors[principal]
            timeline = OwnerTimeline(base / 'timeline', auth, principal, self.host.ledger.clock)
            desk = OwnerDesk(base / 'desk', self.host.ledger, self.inbox, principal, timeline=timeline)
            questions = OwnerQuestions(base / 'questions', self.inbox, principal, timeline=timeline)
            self._owners[principal] = (desk, questions, timeline)
        return self._owners[principal]

    def _proposals(self, principal, token):
        missions = self.host.missions
        if missions.proposals is None and principal == self.host.ledger.storage_owner:
            missions.proposals = LocalProposals(self.host.ledger, principal, token)
        return missions.proposals

    # Listing ------------------------------------------------------------------

    def _drafts_waiting(self, principal, token):
        proposals = self._proposals(principal, token)
        if proposals is None:
            return None
        waiting = []
        for room in self.host.ledger.list_conversations(principal, token):
            binding = self.host.ledger.bind_context(principal, token, room['id'])
            for result in proposals.latest(principal, token, binding, limit=20):
                body = result['proposal']['statement']
                if body['content'].startswith(MISSION_PREFIX):
                    continue  # Mission agreements have their own screen.
                view = draft_view(result)
                if view['current'] and principal not in view['approved_by']:
                    waiting.append({**view, 'conversation_id': room['id'],
                                    'author_name': self._name(view['author'])})
        return waiting

    def _name(self, principal):
        service = self.host.services.get(principal)
        return service.auth.public_identity()['owner_id'] if service else 'Someone'

    def listing(self, principal, token):
        desk, questions, _ = self.owner(principal)
        messages = desk.drafts(token)
        asked = questions.waiting(token)
        drafts = self._drafts_waiting(principal, token)
        return {'messages': messages, 'questions': asked, 'drafts': drafts or [],
                'drafts_available': drafts is not None,
                'count': len(messages) + len(asked) + len(drafts or []),
                'note': 'Nothing here is sent, shared or agreed until you choose.'}

    # Decisions ----------------------------------------------------------------

    def _phone(self, principal, token, method, action, body):
        _, questions, _ = self.owner(principal)
        mine = principal == self.host.ledger.storage_owner
        if action is None and method == 'GET':
            status = questions.phone_status(token)  # Also checks the owner's session.
            if not mine or self.phone is None:
                return {**status, 'available': False, 'reason': self.phone_problem if mine and self.phone_problem else 'not_set_up'}
            return {**status, **self.phone.status()}
        need(method == 'POST' and mine and self.phone is not None)
        exact(body, ())
        if action == 'unpair':
            questions.unpair(token)
            return {'paired': False}
        made = questions.start_pairing(token)
        bot = self.phone.bot
        # Telegram turns this link into "/start <code>" in a private chat with the bot.
        return {**made, 'bot': bot, 'start_link': f'https://t.me/{bot}?start={made["code"]}' if bot else None}

    def call(self, principal, token, method, path, body):
        phone = PHONE.fullmatch(path)
        if phone:
            return self._phone(principal, token, method, phone[1], body)
        settings = SETTINGS.fullmatch(path)
        if settings:
            return self._settings(principal, token, method, settings[1], body)
        match = ROUTE.fullmatch(path)
        if match is None:
            raise RequestDenied('Unknown approval operation')
        kind, item, action = match.groups()
        if kind is None:
            if method != 'GET':
                raise RequestDenied('Unknown approval operation')
            return self.listing(principal, token)
        if method != 'POST':
            raise RequestDenied('Unknown approval operation')
        desk, questions, _ = self.owner(principal)
        if kind == 'messages' and action == 'approve':
            exact(body, ('digest',))
            return desk.approve(token, item, body['digest'])
        if kind == 'messages' and action == 'decline':
            exact(body, ())
            desk.decline(token, item)
            return {'declined': True}
        if kind == 'questions' and action == 'answer':
            exact(body, ('option',))
            return questions.answer(token, item, body['option'])
        if kind == 'drafts' and action == 'review':
            exact(body, ('conversation_id',))
            identifier(body['conversation_id'])
            proposals = self._proposals(principal, token)
            need(proposals is not None)
            binding = self.host.ledger.bind_context(principal, token, body['conversation_id'])
            review = proposals.prepare_approval(principal, token, binding, item)
            now = time.monotonic()
            self._reviews = {k: v for k, v in self._reviews.items() if v['deadline'] > now}
            need(len(self._reviews) < 128)
            self._reviews[(principal, item)] = {'review': review, 'binding': binding, 'deadline': now + 600,
                                                'session': self.host.session_key(token)}
            statement = review['proposal']['statement']
            return {'draft_id': item, 'text': statement['content'], 'revision': statement['revision'],
                    'people': [self._name(m['principal']) for m in statement['audience']],
                    'expires_at': statement['expires_at'], 'review_digest': review['review_digest'],
                    'scope': 'Agreeing to this exact text only. It sends, runs and pays for nothing.'}
        if kind == 'drafts' and action == 'approve':
            exact(body, ('review_digest',))
            cached = self._reviews.pop((principal, item), None)
            need(cached is not None and cached['session'] == self.host.session_key(token))
            result = self._proposals(principal, token).approve(principal, token, cached['binding'],
                                                               cached['review'], body['review_digest'])
            return draft_view(result)
        raise RequestDenied('Unknown approval operation')

    def _settings(self, principal, token, method, name, body):
        desk, _, timeline = self.owner(principal)
        if name == 'timeline' and method == 'POST':
            exact(body, (), ('after', 'conversation_id'))
            return timeline.read(token, after=body.get('after', 0), conversation_id=body.get('conversation_id'))
        if name == 'policy' and method == 'POST':
            exact(body, ('assistant_id', 'conversation_id', 'mode'), ('every', 'max_auto', 'max_bytes', 'ttl'))
            if body['mode'] == 'review_each':
                desk.clear_policy(token, body['assistant_id'], body['conversation_id'])
                return desk.policy(token, body['assistant_id'], body['conversation_id'])
            extra = {k: body[k] for k in ('every', 'max_auto', 'max_bytes', 'ttl') if k in body}
            return desk.set_policy(token, body['assistant_id'], body['conversation_id'], mode=body['mode'], **extra)
        if name == 'guidance' and method == 'POST':
            exact(body, ('assistant_id', 'conversation_id'), ('add', 'remove'))
            if 'add' in body:
                desk.add_guidance(token, body['assistant_id'], body['conversation_id'], body['add'])
            if 'remove' in body:
                desk.remove_guidance(token, body['remove'])
            return {'notes': desk.guidance(token, body['assistant_id'], body['conversation_id'])}
        raise RequestDenied('Unknown approval operation')
