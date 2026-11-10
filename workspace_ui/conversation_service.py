"""Optional trusted coordinating-host facade. No model or provider history API.

All authenticators, owner services and the ledger live on the existing single
owner worker. Browser requests select no filesystem path or authority. Every
actor logs into an existing private owner account; the coordinating owner must
independently keep a current session. No keys/passwords are retained by this
facade and no synthetic owner approval is manufactured.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time

from conversation import ConversationLedger, ContextBinding
from conversation.ledger import need, identifier
from pilot.auth import AuthError, _private_path
from pilot.crypto import fingerprint
from pilot.https_mailbox import read_private
from pilot.server import OwnerService, RequestDenied, exact, strict_json, encode

VERSION = 'assistant-central-conversation-host/1'
MAX_RESPONSE = 1024 * 1024


class ConversationConfig:
    def __init__(self, value):
        exact(value, ('version', 'directory', 'actors'))
        need(value['version'] == VERSION and type(value['actors']) is list and 1 <= len(value['actors']) <= 31)
        self.directory = self.path(value['directory'])
        self.actors = []
        for item in value['actors']:
            exact(item, ('directory', 'fingerprint'))
            path = self.path(item['directory'])
            need(type(item['fingerprint']) is str and re.fullmatch(r'[a-f0-9]{64}', item['fingerprint']))
            need(path not in [a['directory'] for a in self.actors] and path != self.directory)
            _private_path(path / 'auth.sqlite')
            self.actors.append({'directory': path, 'fingerprint': item['fingerprint']})

    @staticmethod
    def path(value):
        need(type(value) is str and len(value) <= 4096 and Path(value).is_absolute())
        path = Path(value)
        # Reject symlinks in all trusted-config path components too.
        need(not any(p.is_symlink() for p in (path, *path.parents)))
        _private_path(path, directory=True)
        return path


def load_conversation_config(path):
    return ConversationConfig(strict_json(read_private(path, 16384)))


class ConversationService:
    """Wrap, do not replace, separately authenticated real owner runtimes."""
    def __init__(self, primary, config):
        need(type(config) is ConversationConfig)
        self.primary = primary
        self.mailbox = primary.mailbox  # Existing peer ingress remains primary-only.
        self.services = {}
        self.ledger = None
        self.reviews = {}
        self.extra_services = []
        try:
            primary_id = fingerprint(primary.auth.public_identity())
            self.services[primary_id] = primary
            for actor in config.actors:
                need(actor['directory'] != primary.auth.directory)
                service = OwnerService(actor['directory'])
                self.extra_services.append(service)
                key = fingerprint(service.auth.public_identity())
                need(key == actor['fingerprint'] and key not in self.services)
                self.services[key] = service
            self.aliases = {}
            for key, service in self.services.items():
                alias = service.auth.public_identity()['owner_id']
                need(alias not in self.aliases)
                self.aliases[alias] = key
            need(config.directory not in [s.auth.directory for s in self.services.values()])
            self.ledger = ConversationLedger(config.directory, primary.auth,
                                            {key: s.auth for key, s in self.services.items()})
        except BaseException:
            for service in reversed(self.extra_services):
                service.close()
            if self.ledger is not None:
                self.ledger.close()
            raise

    def close(self):
        self.reviews.clear()
        if self.ledger is not None:
            self.ledger.close()
        for service in reversed(self.extra_services):
            service.close()
        self.primary.close()

    def actor(self, token):
        # Authenticate, release the individual auth lock, THEN enter the ledger.
        # Never hold an auth lock while the ledger acquires globally sorted locks.
        for principal, service in self.services.items():
            try:
                service.auth.authenticate(token)
                return principal, service
            except AuthError:
                continue
        raise AuthError('Authentication required')

    @staticmethod
    def session_key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def binding(self, principal, conversation_id, value):
        exact(value, ('member_epoch', 'policy_generation'))
        identifier(value['member_epoch'])
        need(type(value['policy_generation']) is int and value['policy_generation'] > 0)
        return ContextBinding(conversation_id, principal, value['member_epoch'], value['policy_generation'])

    def public_actor(self, principal):
        identity = self.services[principal].auth.public_identity()
        return {'principal': principal, 'owner_id': identity['owner_id'], 'agent_id': identity['agent_id']}

    def call(self, method, path, token, body):
        if path == '/api/session' and method == 'POST':
            exact(body, ('password',), ('account',))
            account = body.get('account')
            if account is None or account == '':
                service = self.primary
            else:
                if type(account) is not str or account not in self.aliases:
                    raise AuthError('Authentication required')
                service = self.services[self.aliases[account]]
            return service.call(method, path, None, {'password': body['password']})
        principal, service = self.actor(token)
        if path == '/api/session' and method == 'DELETE':
            self.reviews = {k: v for k, v in self.reviews.items() if v['session'] != self.session_key(token)}
        if path.startswith('/api/conversations'):
            result = self.conversation_call(principal, token, method, path, body)
            need(len(encode(result)) <= MAX_RESPONSE)
            return result
        result = service.call(method, path, token, body)
        if path == '/api/state' and method == 'GET':
            result['conversations'] = {'enabled': True, 'local_host_only': True,
                                       'coordinator': self.public_actor(self.ledger.storage_owner),
                                       'provider_history_authorised': False}
        return result

    def conversation_call(self, principal, token, method, path, body):
        ledger = self.ledger
        # A bounded in-memory exact review cache is a UI capability, never an
        # owner approval. It is lost on restart and bound to this exact session.
        now = time.monotonic()
        self.reviews = {k: v for k, v in self.reviews.items() if v['deadline'] > now}
        if path == '/api/conversations' and method == 'GET':
            return {'rooms': ledger.list_conversations(principal, token),
                    'invitations': ledger.list_invitations(principal, token),
                    'actors': [self.public_actor(p) for p in self.services],
                    'principal': principal, 'local_host_only': True,
                    'audience': 'local-owner-only', 'execution_authority': False}
        if path == '/api/conversations/grants/list' and method == 'POST':
            exact(body, (), ('conversation_id', 'after'))
            return {'grants': ledger.list_history_grants(principal, token, body.get('conversation_id'), after=body.get('after'))}
        if path == '/api/conversations/grants' and method == 'GET':
            return {'grants': ledger.list_history_grants(principal, token)}
        if path == '/api/conversations' and method == 'POST':
            exact(body, ('id',))
            return {'binding': asdict(ledger.create(principal, token, body['id']))}
        invitation = re.fullmatch(r'/api/conversations/invitations/([A-Za-z0-9_-]{1,64})/(accept|cancel)', path)
        if invitation and method == 'POST':
            exact(body, ())
            value = getattr(ledger, 'accept_invitation' if invitation[2] == 'accept' else 'cancel_invitation')(principal, token, invitation[1])
            return {'binding': asdict(value)} if value else {'saved': True}
        grant = re.fullmatch(r'/api/conversations/grants/([A-Za-z0-9_-]{1,64})/(approve|revoke)', path)
        if grant and method == 'POST':
            if grant[2] == 'revoke':
                exact(body, ())
                ledger.revoke_history_grant(principal, token, grant[1])
                return {'saved': True}
            exact(body, ('review_digest',))
            cached = self.reviews.get(grant[1])
            need(cached is not None and cached['principal'] == principal and cached['session'] == self.session_key(token))
            review = cached['review']
            value = ledger.approve_history_grant(principal, token, review, body['review_digest'])
            return {'id': value}
        room = re.fullmatch(r'/api/conversations/([A-Za-z0-9_-]{1,64})(?:/(history|read|context|message|message-outcome|invite|remove|grants|grant-review))?', path)
        if room is None:
            raise RequestDenied('Unknown conversation operation')
        room_id, action = room.groups()
        if action is None and method == 'GET':
            binding = ledger.bind_context(principal, token, room_id)
            rooms = ledger.list_conversations(principal, token)
            info = next(r for r in rooms if r['id'] == room_id)
            return {**info, 'binding': asdict(binding), 'participants': ledger.participants(principal, token, binding)}
        if action == 'grants' and method == 'GET':
            return {'grants': ledger.list_history_grants(principal, token, room_id)}
        if method != 'POST':
            raise RequestDenied('Unknown conversation operation')
        if action == 'invite':
            exact(body, ('recipient', 'binding'))
            binding = self.binding(principal, room_id, body['binding'])
            ledger.participants(principal, token, binding)
            return ledger.invite(principal, token, room_id, body['recipient'])
        if action == 'remove':
            exact(body, ('recipient', 'binding'))
            binding = self.binding(principal, room_id, body['binding'])
            ledger.participants(principal, token, binding)
            ledger.remove_member(principal, token, room_id, body['recipient'])
            return {'saved': True}
        if action == 'message-outcome':
            exact(body, ('binding', 'request_id', 'expected_request_digest'))
            return ledger.inspect_message_outcome(
                principal, token, self.binding(principal, room_id, body['binding']),
                request_id=body['request_id'], expected_request_digest=body['expected_request_digest'])
        if action == 'message':
            exact(body, ('binding', 'request_id', 'text'))
            return ledger.append(principal, token, self.binding(principal, room_id, body['binding']),
                                 request_id=body['request_id'], text=body['text'])
        if action == 'history':
            exact(body, ('binding',), ('after', 'query'))
            return {'messages': ledger.history(principal, token, self.binding(principal, room_id, body['binding']),
                                               after=body.get('after'), query=body.get('query'), limit=25)}
        if action == 'read':
            exact(body, ('binding', 'event_id'))
            return ledger.read(principal, token, self.binding(principal, room_id, body['binding']), body['event_id'])
        if action == 'context':
            exact(body, ('binding', 'event_ids'))
            need(type(body['event_ids']) is list and len(body['event_ids']) <= 25)
            return ledger.context(principal, token, self.binding(principal, room_id, body['binding']), body['event_ids'])
        if action == 'grant-review':
            exact(body, ('binding', 'recipient', 'event_ids', 'purpose', 'expires_at'))
            need(type(body['event_ids']) is list and len(body['event_ids']) <= 25)
            binding = self.binding(principal, room_id, body['binding'])
            context = ledger.context(principal, token, binding, body['event_ids'])
            review = ledger.prepare_history_grant(principal, token, room_id, body['recipient'], body['event_ids'],
                                                  purpose=body['purpose'], expires_at=body['expires_at'])
            need(len(self.reviews) < 128 and sum(v['principal'] == principal for v in self.reviews.values()) < 16)
            key = review['statement']['id']
            self.reviews[key] = {'review': review, 'principal': principal, 'session': self.session_key(token), 'deadline': now + 600}
            return {**review, 'messages': context['messages'], 'recipient': self.public_actor(body['recipient']),
                    'review_valid_seconds': 600, 'execution_authority': False}
        raise RequestDenied('Unknown conversation operation')
