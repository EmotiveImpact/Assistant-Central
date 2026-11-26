"""Pure bounded trusted-owner composition; no keys, I/O, allocation or agent tools."""
import json
import re
from generic_capabilities import PUBLIC_SHORTLIST, BOUNDED_TEXT
from generic_protocol import IdentityReference, Conversation, Task, task_envelope, task_context_digest
from network import Denied, digest
from generic_capabilities import validate_result_against_request

FIELDS = {'selector','task_id','conversation_id','requester','query','max_items'}
TEXT_FIELDS = (FIELDS - {'max_items'}) | {'capability', 'max_reply_chars'}
MAX_CUSTOM_TASKS = 8


def validate_spec(spec):
    if type(spec) is not dict or set(spec) not in (FIELDS, TEXT_FIELDS):
        raise Denied('Expected exact bounded task composition fields')
    for key, pattern in (('selector',r'custom-[a-z0-9][a-z0-9-]{0,47}'),
                         ('task_id',r'[a-z0-9][a-z0-9-]{0,63}'),
                         ('conversation_id',r'[a-z0-9][a-z0-9-]{0,63}')):
        if type(spec[key]) is not str or not re.fullmatch(pattern,spec[key]):
            raise Denied('Invalid custom task '+key)
    if type(spec['requester']) is not str or spec['requester'] not in ('alice','bob'):
        raise Denied('Only fictional Alice and Bob may participate')
    query = spec['query']
    if type(query) is not str or not 1 <= len(query) <= 512 or query != query.strip() or any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF for c in query):
        raise Denied('Expected bounded nonempty inert query without control characters')
    if set(spec) == TEXT_FIELDS:
        if spec['capability'] != BOUNDED_TEXT:
            raise Denied('Unknown composed capability')
        if type(spec['max_reply_chars']) is not int or not 1 <= spec['max_reply_chars'] <= 512:
            raise Denied('Expected integer max_reply_chars from 1 to 512')
    elif type(spec['max_items']) is not int or not 1 <= spec['max_items'] <= 5:
        raise Denied('Expected integer max_items from 1 to 5')
    return dict(spec)


def composed_fixture(spec):
    spec = validate_spec(spec)
    identities = (IdentityReference('alice','provider-one-fixture','Alice'),
                  IdentityReference('bob','provider-two-fixture','Bob'))
    commitment = digest({'domain':'agent-network-task-composition/v1','spec':spec})
    is_text = spec.get('capability') == BOUNDED_TEXT
    task = Task(spec['task_id'], Conversation(spec['conversation_id'],identities),
                spec['requester'], 'bob' if spec['requester']=='alice' else 'alice',
                BOUNDED_TEXT if is_text else PUBLIC_SHORTLIST,
                'exchange-text' if is_text else 'find-public-resources',composition_digest=commitment)
    payload = ({'prompt':spec['query'],'max_reply_chars':spec['max_reply_chars']} if is_text
               else {'query':spec['query'],'max_items':spec['max_items']})
    request = task_envelope(task,'request',payload)
    return task, identities, request, None


def preview(spec):
    spec = validate_spec(spec)
    task = composed_fixture(spec)[0]
    result = {'spec':spec,'selector':spec['selector'],'requester':task.requester,'responder':task.responder,'task':task.id,'context':task_context_digest(task),'fictional':True,'temporary':True}
    result['review_digest'] = digest({'domain':'agent-network-task-composition-review/v1',**result})
    return result


def parse_startup(value):
    if type(value) is not str or len(value.encode()) > 8192:
        raise Denied('Composition startup configuration exceeds bound')
    def exact_pairs(pairs):
        result = {}
        for key, val in pairs:
            if key in result: raise Denied('Duplicate composition startup field')
            result[key] = val
        return result
    try:
        return validate_spec(json.loads(value,object_pairs_hook=exact_pairs))
    except (ValueError, TypeError, RecursionError) as exc:
        raise Denied('Invalid composition startup configuration') from exc


def validate_composed_request(spec, message):
    if message is None:
        return
    task, _, request, _ = composed_fixture(spec)
    if message.get('type') == 'request' and message != request:
        raise Denied('Request differs from immutable owner composition')
    if message.get('type') == 'result':
        from generic_protocol import validate_task_scope
        message = validate_task_scope(task, message)
        if message['reply_to'] != digest(request):
            raise Denied('Result differs from immutable composition request linkage')
        validate_result_against_request(task.capability, request['payload'], message['payload'])

