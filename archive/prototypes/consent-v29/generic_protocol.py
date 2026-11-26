"""Explicit v2 conversation/task protocol, independent of scheduling.

IDs and provider/display labels are references, never authentication. The entire
immutable task context and exact message must be covered by existing owner proof.
No v1 migration, dynamic capabilities, or executable payloads are supported.
"""
from dataclasses import dataclass
import json
import re
from network import Denied, canonical, digest
from generic_capabilities import CAPABILITIES, BOUNDED_TEXT, text, validate_payload


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[a-z0-9_-]{1,64}', value):
        raise Denied('Invalid protocol identifier')


@dataclass(frozen=True)
class IdentityReference:
    id: str
    provider: str
    display_name: str

    def __post_init__(self):
        identifier(self.id)
        text(self.provider, 64)
        text(self.display_name, 128)

    @property
    def identity(self):
        return self.id

    def to_dict(self):
        return {'id': self.id, 'provider': self.provider, 'display_name': self.display_name}


@dataclass(frozen=True)
class Conversation:
    id: str
    identities: tuple[IdentityReference, ...]

    def __post_init__(self):
        identifier(self.id)
        if type(self.identities) not in (tuple, list):
            raise Denied('Conversation identities must be a sequence')
        object.__setattr__(self, 'identities', tuple(self.identities))
        if not 2 <= len(self.identities) <= 10 or any(type(i) is not IdentityReference for i in self.identities):
            raise Denied('Need 2–10 immutable identity references')
        if len(set(self.participants)) != len(self.identities):
            raise Denied('Identity references must be distinct')

    @property
    def participants(self):
        return tuple(i.id for i in self.identities)

    def to_dict(self):
        return {'id': self.id, 'identities': [i.to_dict() for i in self.identities]}


@dataclass(frozen=True)
class Task:
    id: str
    conversation: Conversation
    requester: str
    responder: str
    capability: str
    operation: str
    composition_digest: str | None = None

    def __post_init__(self):
        identifier(self.id)
        if self.composition_digest is not None and (type(self.composition_digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", self.composition_digest)):
            raise Denied("Invalid immutable composition commitment")
        identifier(self.operation)
        if type(self.conversation) is not Conversation:
            raise Denied('Task needs an immutable conversation')
        if (type(self.requester) is not str or type(self.responder) is not str
                or self.requester == self.responder
                or self.requester not in self.conversation.participants
                or self.responder not in self.conversation.participants):
            raise Denied('Task needs two distinct conversation participants')
        if type(self.capability) is not str or self.capability not in CAPABILITIES:
            raise Denied('Task capability is not allowlisted')
        if self.capability == BOUNDED_TEXT and self.operation != 'exchange-text':
            raise Denied('Text exchange requires its fixed operation')

    @property
    def participants(self):
        # Only the two task peers receive authority in the existing identity scope.
        return (self.requester, self.responder)

    def to_dict(self):
        return {'id': self.id, 'conversation': self.conversation.to_dict(),
                'requester': self.requester, 'responder': self.responder,
                'capability': self.capability, 'operation': self.operation,
                **({'composition_digest': self.composition_digest} if self.composition_digest is not None else {})}


def task_context_digest(task):
    if type(task) is not Task:
        raise Denied('Expected an exact v2 task context')
    return digest({'domain': 'agent-network-task-context/v2', 'task': task.to_dict()})


def snapshot_task_envelope(value):
    try:
        body = canonical(value)
        if len(body.encode()) > 8192:
            raise Denied('Message too large')
        message = json.loads(body)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied('Message must be bounded JSON') from exc
    fields = {'version', 'type', 'conversation', 'task', 'operation', 'reply_to',
              'capability', 'context', 'sender', 'recipient', 'payload'}
    if type(message) is not dict or set(message) != fields:
        raise Denied('Unknown or missing v2 envelope fields')
    if type(message['version']) is not int or message['version'] != 2:
        raise Denied('Expected explicit protocol v2')
    for key in ('conversation', 'task', 'operation', 'sender', 'recipient', 'capability'):
        identifier(message[key])
    if message['sender'] == message['recipient']:
        raise Denied('Task messages need distinct peers')
    if type(message['context']) is not str or not re.fullmatch(r'[a-f0-9]{64}', message['context']):
        raise Denied('Invalid task context digest')
    kind, reply = message['type'], message['reply_to']
    if type(kind) is not str or kind not in ('request', 'result'):
        raise Denied('Unsupported task operation type')
    if kind == 'request' and reply is not None:
        raise Denied('Request cannot reply to another operation')
    if kind == 'result' and (type(reply) is not str or not re.fullmatch(r'[a-f0-9]{64}', reply)):
        raise Denied('Result needs exact request digest')
    if message['capability'] == BOUNDED_TEXT and message['operation'] != 'exchange-text':
        raise Denied('Text exchange requires its fixed operation')
    validate_payload(message['capability'], kind, message['payload'])
    return message


def validate_task_scope(task, envelope):
    message = snapshot_task_envelope(envelope)
    expected = {'conversation': task.conversation.id, 'task': task.id,
                'operation': task.operation, 'capability': task.capability,
                'context': task_context_digest(task)}
    if any(message[k] != v for k, v in expected.items()):
        raise Denied('Message does not match immutable task scope')
    peers = (task.requester, task.responder) if message['type'] == 'request' else (task.responder, task.requester)
    if (message['sender'], message['recipient']) != peers:
        raise Denied('Message route does not match task direction')
    return message


def task_envelope(task, kind, payload, reply_to=None):
    sender, recipient = ((task.requester, task.responder) if kind == 'request'
                         else (task.responder, task.requester))
    return validate_task_scope(task, {'version': 2, 'type': kind,
        'conversation': task.conversation.id, 'task': task.id, 'operation': task.operation,
        'reply_to': reply_to, 'capability': task.capability, 'context': task_context_digest(task),
        'sender': sender, 'recipient': recipient, 'payload': payload})
