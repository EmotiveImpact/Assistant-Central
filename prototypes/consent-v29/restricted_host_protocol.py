"""Restricted local MCP-shaped 2025-06-18 profile, not a host or OS sandbox.

Trusted construction only: dispatch must be the exact task/actor-bound proposal
callback, never the executor command router. Only handle(bytes) is wire-facing.
No sockets, stdio launcher, host installation, owner operations or retry loop.
"""
import copy
import json
import math
import re
import threading
from generic_protocol import Task, identifier, validate_task_scope, task_context_digest
from network import Denied, canonical, digest

PROTOCOL_VERSION = '2025-06-18'
MAX_INPUT = 16384
MAX_OUTPUT = 32768
MAX_REQUESTS = 1024


def closed(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def bounded_text(n):
    return {'type': 'string', 'minLength': 1, 'maxLength': n}


IDENTIFIER = {'type': 'string', 'pattern': '^[a-z0-9_-]{1,64}$', 'maxLength': 64}
HASH = {'type': 'string', 'pattern': '^[a-f0-9]{64}$', 'maxLength': 64}
ITEM = closed({'title': bounded_text(128), 'url': {**bounded_text(256), 'pattern': '^https://'},
               'summary': bounded_text(512)})
COMMON = {'version': {'const': 2}, 'conversation': IDENTIFIER, 'task': IDENTIFIER,
          'operation': IDENTIFIER, 'capability': {'const': 'public-resource-shortlist-v1'},
          'context': HASH, 'sender': IDENTIFIER, 'recipient': IDENTIFIER}
ENVELOPE = {'oneOf': [
    closed({**COMMON, 'type': {'const': 'request'}, 'reply_to': {'type': 'null'},
            'payload': closed({'query': bounded_text(512), 'max_items': {'type': 'integer', 'minimum': 1, 'maximum': 5}})}),
    closed({**COMMON, 'type': {'const': 'result'}, 'reply_to': HASH,
            'payload': closed({'items': {'type': 'array', 'maxItems': 5, 'items': ITEM}})})]}
TOOL_SCHEMAS = {'propose': closed({'proposal_id': IDENTIFIER, 'envelope': ENVELOPE}),
                'proposal_status': closed({'proposal_id': IDENTIFIER}), 'inbox': closed({})}
STATES = {'awaiting_owner_review', 'unavailable', 'pending', 'deferred', 'declined',
          'authorized', 'submitted', 'expired', 'stale', 'superseded', 'withdrawn'}
DELIVERY_STATES = {None, 'queued', 'dispatched', 'received', 'processed', 'blocked', 'received_blocked', 'stopped_uncertain'}


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON member')
        obj[key] = value
    return obj


def bounded_tree(root):
    pending = [(root, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 32 or nodes > 2048:
            raise ValueError('JSON complexity limit')
        if type(value) is float and not math.isfinite(value):
            raise ValueError('Nonfinite JSON number')
        if type(value) is str:
            value.encode('utf-8')
        elif type(value) is dict:
            pending.extend((v, depth + 1) for pair in value.items() for v in pair)
        elif type(value) is list:
            pending.extend((v, depth + 1) for v in value)


def invalid_constant(value):
    raise ValueError('Nonfinite JSON')


class ProtocolError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class RestrictedHostSession:
    def __init__(self, task, actor, dispatch):
        if type(task) is not Task or type(actor) is not str or actor not in task.participants or not callable(dispatch):
            raise Denied('Expected trusted exact task, actor and restricted callback')
        self._task, self._actor, self._dispatch = task, actor, dispatch
        self._state, self._ids = 'new', set()
        self._lock = threading.Lock()
        # Fresh schemas disclose only this already-bound scope, not other tasks
        # or identity labels. Runtime validation remains authoritative.
        self._schemas = copy.deepcopy(TOOL_SCHEMAS)
        requester = actor == task.requester
        envelope_schema = copy.deepcopy(ENVELOPE['oneOf'][0 if requester else 1])
        if task.capability == 'bounded-text-exchange-v1':
            envelope_schema['properties']['payload'] = (
                closed({'prompt': bounded_text(512), 'max_reply_chars': {'type': 'integer', 'minimum': 1, 'maximum': 512}})
                if requester else closed({'text': bounded_text(512)}))
        scope = {'conversation': task.conversation.id, 'task': task.id,
                 'operation': task.operation, 'capability': task.capability,
                 'context': task_context_digest(task), 'sender': actor,
                 'recipient': task.responder if requester else task.requester}
        for field, value in scope.items():
            envelope_schema['properties'][field] = {'const': value}
        self._schemas['propose']['properties']['envelope'] = envelope_schema

    def application_tools(self):
        """Trusted adapter composition: fresh scoped discovery, no protocol state."""
        with self._lock:
            return [{'name': name,
                     'description': 'Offline task-bound proposal data only; no owner authorization or delivery.',
                     'inputSchema': copy.deepcopy(schema)} for name, schema in self._schemas.items()]

    def application_call(self, name, arguments):
        """Shared closed validation for an independently negotiated SDK adapter.

        This synchronous callback is serialized, never retried, and preserves
        thread-affine storage. The caller owns lifecycle and transport bounds.
        All exceptions are fixed tool errors; failure can follow a committed write.
        """
        with self._lock:
            try:
                if self._state == 'closed':
                    raise ProtocolError(-32000, 'Session closed')
                params = {'name': name, 'arguments': arguments}
                bounded_tree(params)
                if len(canonical(params).encode('utf-8')) > MAX_INPUT:
                    raise ProtocolError(-32602, 'Invalid params')
                result = self._call(params)
                self._encode(result)
                return result
            except ProtocolError:
                text = 'Invalid proposal operation'
            except Exception:
                text = 'Internal error; outcome unknown'
            return {'content': [{'type': 'text', 'text': text}], 'isError': True}

    def close(self):
        """Trusted transport lifecycle only. Closed sessions cannot be reopened."""
        with self._lock:
            self._state = 'closed'

    @staticmethod
    def _encode(value):
        result = canonical(value).encode('utf-8')
        if len(result) > MAX_OUTPUT:
            raise ValueError('Oversized output')
        return result

    @staticmethod
    def _error(request_id, code, message):
        return RestrictedHostSession._encode({'jsonrpc': '2.0', 'id': request_id,
                                             'error': {'code': code, 'message': message}})

    def handle(self, data):
        """One UTF-8 JSON message, no framing. Returns bytes or None (notification).

        Serialized calls prevent lifecycle and request-ID races. A valid request
        ID is consumed even if execution fails. Never retry a callback after an
        exception; its outcome might be uncertain. Durable proposal IDs, unlike
        JSON-RPC IDs, can safely query/replay exact proposals through the boundary.
        """
        with self._lock:
            return self._handle(data)

    def _handle(self, data):
        request_id, notification = None, False
        try:
            if type(data) is not bytes or len(data) > MAX_INPUT:
                raise ValueError('Invalid input size/type')
            request = json.loads(data.decode('utf-8'), object_pairs_hook=unique_object,
                                 parse_constant=invalid_constant)
            bounded_tree(request)
        except (ValueError, UnicodeError, RecursionError):
            return self._error(None, -32700, 'Invalid bounded JSON')
        try:
            if (type(request) is not dict or request.get('jsonrpc') != '2.0'
                    or type(request.get('method')) is not str
                    or not {'jsonrpc', 'method'} <= set(request) <= {'jsonrpc', 'method', 'id', 'params'}):
                raise ProtocolError(-32600, 'Invalid request')
            notification = 'id' not in request
            if not notification:
                candidate = request['id']
                if not ((type(candidate) is int and abs(candidate) <= 9007199254740991)
                        or (type(candidate) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', candidate))):
                    raise ProtocolError(-32600, 'Invalid request ID')
                request_id = candidate
                key = (type(candidate), candidate)
                if key in self._ids:
                    raise ProtocolError(-32600, 'Request ID already used')
                if len(self._ids) >= MAX_REQUESTS:
                    self._state = 'closed'
                    raise ProtocolError(-32000, 'Session capacity exhausted')
                self._ids.add(key)
            params = request.get('params', {})
            if type(params) is not dict:
                raise ProtocolError(-32602, 'Invalid params')
            method = request['method']
            if self._state == 'closed':
                raise ProtocolError(-32000, 'Session closed')
            if notification:
                # Never run tools (especially propose) as a notification.
                if method == 'notifications/initialized' and params == {} and self._state == 'initializing':
                    self._state = 'ready'
                return None
            if method == 'initialize':
                if self._state != 'new':
                    raise ProtocolError(-32600, 'Already initialized')
                if (set(params) != {'protocolVersion', 'capabilities', 'clientInfo'}
                        or type(params['protocolVersion']) is not str
                        or not params['protocolVersion'] or len(params['protocolVersion']) > 64
                        or params['capabilities'] != {} or type(params['capabilities']) is not dict
                        or type(params['clientInfo']) is not dict
                        or set(params['clientInfo']) != {'name', 'version'}
                        or any(type(v) is not str or not v or len(v) > 128 for v in params['clientInfo'].values())):
                    raise ProtocolError(-32602, 'Invalid params')
                self._state = 'initializing'
                result = {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'restricted-offline-proposals', 'version': '0.14.0'}}
            elif method == 'ping':
                if params:
                    raise ProtocolError(-32602, 'Invalid params')
                result = {}
            elif method in ('tools/list', 'tools/call'):
                if self._state != 'ready':
                    raise ProtocolError(-32000, 'Session not ready')
                if method == 'tools/list':
                    if params:
                        raise ProtocolError(-32602, 'Invalid params')
                    result = {'tools': [{'name': name,
                              'description': 'Offline task-bound proposal data only; no owner authorization or delivery.',
                              'inputSchema': schema} for name, schema in self._schemas.items()]}
                else:
                    result = self._call(params)
            else:
                raise ProtocolError(-32601, 'Method not found')
            return self._encode({'jsonrpc': '2.0', 'id': request_id, 'result': result})
        except ProtocolError as exc:
            return None if notification else self._error(request_id, exc.code, exc.message)
        except Exception:
            # No paths, SQL, owner cards, recipient details or exception strings.
            return None if notification else self._error(request_id, -32603, 'Internal error; outcome unknown')

    def _call(self, params):
        if set(params) != {'name', 'arguments'} or type(params['name']) is not str:
            raise ProtocolError(-32602, 'Invalid params')
        name, args = params['name'], params['arguments']
        if name not in TOOL_SCHEMAS or type(args) is not dict:
            raise ProtocolError(-32602, 'Invalid params')
        if set(args) != set(TOOL_SCHEMAS[name]['required']):
            raise ProtocolError(-32602, 'Invalid params')
        try:
            if name != 'inbox':
                identifier(args['proposal_id'])
            if name == 'propose':
                message = validate_task_scope(self._task, args['envelope'])
                if message['sender'] != self._actor:
                    raise Denied('Wrong actor')
        except (Denied, ValueError, TypeError):
            raise ProtocolError(-32602, 'Invalid params') from None
        try:
            value = self._dispatch({'method': name, **args})
        except Denied:
            return {'content': [{'type': 'text', 'text': 'Proposal operation rejected'}], 'isError': True}
        # Validate output too. The callback is trusted but accidental owner-card
        # routing or schema expansion must not silently leak additional fields.
        self._validate_output(name, args, value)
        return {'content': [{'type': 'text', 'text': canonical(value)}], 'isError': False}

    def _validate_output(self, name, args, value):
        if type(value) is not dict:
            raise ValueError('Invalid output')
        if name != 'inbox':
            if (set(value) != {'proposal_id', 'envelope_digest', 'state', 'delivery_state'}
                    or value['proposal_id'] != args['proposal_id']
                    or type(value['envelope_digest']) is not str
                    or not re.fullmatch(r'[a-f0-9]{64}', value['envelope_digest'])
                    or value['state'] not in STATES or value['delivery_state'] not in DELIVERY_STATES
                    or (name == 'propose' and value['envelope_digest'] != digest(args['envelope']))):
                raise ValueError('Invalid output')
        else:
            if (set(value) != {'messages', 'payload_trust'} or value['payload_trust'] != 'untrusted_inert'
                    or type(value['messages']) is not list or len(value['messages']) > 1):
                raise ValueError('Invalid output')
            for item in value['messages']:
                if type(item) is not dict or set(item) != {'envelope', 'envelope_digest'}:
                    raise ValueError('Invalid output')
                envelope = validate_task_scope(self._task, item['envelope'])
                if envelope['recipient'] != self._actor or item['envelope_digest'] != digest(envelope):
                    raise ValueError('Invalid output')
