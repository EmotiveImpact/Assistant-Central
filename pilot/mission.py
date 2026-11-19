"""Versioned local mission terms, explicit task envelopes and fixture-only quotes."""
import hashlib
import json
import re

from .crypto import canonical, digest, fingerprint

AGREEMENT = 'assistant-central/mission-agreement/1'
TASK_PREFIX = 'assistant-central/mission-task/1\n'
CONTEXT_PREFIX = 'ac01c0de5eed0001'
DIRECT = 'assistant-central/direct-owner-offer/1'
PROJECTION = 'mission-brief-only/1'
TARIFF = 'fictional-usd-v1'
BASE_MICROUSD = 20
OUTPUT_MICROUSD = 2


def check(condition):
    if not condition:
        raise ValueError('Invalid mission terms or binding')


def bounded(value, limit):
    check(type(value) is str and value.strip() and len(value.encode('utf-8')) <= limit)
    return value


def cap(value):
    check(type(value) is int and 0 <= value <= 1_000_000_000)
    return value


def terms(value):
    check(type(value) is dict and set(value) == {'goal', 'deliverable', 'executor', 'criteria', 'cap_microusd'})
    bounded(value['goal'], 512)
    bounded(value['deliverable'], 512)
    check(type(value['executor']) is str and re.fullmatch('[a-f0-9]{64}', value['executor']))
    cap(value['cap_microusd'])
    checks = value['criteria']
    check(type(checks) is list and 1 <= len(checks) <= 12)
    for criterion in checks:
        check(type(criterion) is dict and set(criterion) == {'kind', 'value'})
        kind, expected = criterion['kind'], criterion['value']
        if kind in ('contains', 'human_review'):
            bounded(expected, 256)
        elif kind == 'sha256':
            check(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected))
        elif kind == 'max_utf8_bytes':
            check(type(expected) is int and 1 <= expected <= 32768)
        else:
            raise ValueError('Unknown success criterion')
    check(len({canonical(c) for c in checks}) == len(checks))
    return value


def agreement_content(value):
    return canonical({'domain': AGREEMENT, 'terms': terms(value)}).decode()


def read_agreement(statement):
    value = json.loads(statement['content'])
    check(agreement_content(value['terms']) == statement['content'])
    return value['terms']


def mission_context(commitment, limit):
    check(type(commitment) is str and re.fullmatch('[0-9a-f]{64}', commitment))
    return CONTEXT_PREFIX + digest([AGREEMENT, commitment, cap(limit)])[len(CONTEXT_PREFIX):]


def task_text(brief, limit, commitment):
    mission_context(commitment, limit)
    return TASK_PREFIX + canonical({'brief': bounded(brief, 4096), 'cap_microusd': limit,
                                    'agreement_digest': commitment}).decode()


def direct_offer(requester, task_id, expires, agreed):
    return {'domain': DIRECT, 'requester': requester, 'task_id': task_id,
            'expires': expires, 'terms': terms(agreed)}


def direct_task_text(brief, offer):
    return TASK_PREFIX + canonical({'brief': bounded(brief, 4096), 'offer': offer}).decode()


def task_details(text, context):
    check(text.startswith(TASK_PREFIX))
    value = json.loads(text[len(TASK_PREFIX):])
    if 'offer' in value:
        offer = value['offer']
        check(offer == direct_offer(offer['requester'], offer['task_id'], offer['expires'], offer['terms']))
        limit, commitment = offer['terms']['cap_microusd'], digest(offer)
        check(direct_task_text(value['brief'], offer) == text)
    else:
        limit, commitment = value['cap_microusd'], value['agreement_digest']
        check(task_text(value['brief'], limit, commitment) == text)
    check(mission_context(commitment, limit) == context)
    return value, limit


def validate_task(body):
    value, _ = task_details(body['text'], body['context'])
    offer = value.get('offer')
    if offer is not None:
        check(offer['requester'] == fingerprint(body['sender']) and offer['task_id'] == body['task_id'])
        check(offer['expires'] == body['expires'] and offer['terms']['executor'] == fingerprint(body['recipient']))


def fixture_request(request, context):
    if not context.startswith(CONTEXT_PREFIX):
        return request, None
    value, limit = task_details(request['input'], context)
    check(request['model'] == 'synthetic-research-v1' and request['max_output_tokens'] == 128)
    wire_request = {**request, 'input': value['brief']}
    return wire_request, {'tariff': TARIFF, 'cap_microusd': limit,
            'reserve_microusd': BASE_MICROUSD + OUTPUT_MICROUSD * request['max_output_tokens'],
            'base_microusd': BASE_MICROUSD, 'per_output_token_microusd': OUTPUT_MICROUSD,
            'simulated': True}


def evaluate(statement, artifact_id, artifact):
    """Pure local checks. Caller supplies a currently authorised original return."""
    agreed = read_agreement(statement)
    check(digest(artifact) == artifact_id and artifact['context'] == mission_context(digest(statement), agreed['cap_microusd']))
    return evidence(agreed, statement['id'], statement['revision'], digest(statement), artifact_id, artifact)


def evidence(agreed, proposal_id, revision, commitment, artifact_id, artifact):
    check(digest(artifact) == artifact_id and artifact['context'] == mission_context(commitment, agreed['cap_microusd']))
    content = artifact['text']
    encoded = content.encode('utf-8')
    findings = []
    for rule in agreed['criteria']:
        kind, expected = rule['kind'], rule['value']
        if kind == 'human_review':
            finding = {'status': 'needs_owner_review'}
        else:
            if kind == 'contains':
                observed = expected in content
                passed = observed
            elif kind == 'sha256':
                observed = hashlib.sha256(encoded).hexdigest()
                passed = observed == expected
            else:
                observed = len(encoded)
                passed = observed <= expected
            finding = {'status': 'passed' if passed else 'failed', 'observed': observed}
        findings.append({**rule, **finding})
    return {'proposal_id': proposal_id, 'revision': revision,
            'proposal_digest': commitment, 'artifact_id': artifact_id,
            'parent_task_id': artifact['parent_id'], 'content_sha256': hashlib.sha256(encoded).hexdigest(),
            'findings': findings, 'all_checks_passed': all(f['status'] == 'passed' for f in findings),
            'recipient_decision_required': True}
