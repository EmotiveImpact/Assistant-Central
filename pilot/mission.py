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
# Budgets are whole millionths of one currency unit. Legacy terms carry
# cap_microusd and mean US dollars; newer terms carry cap_micro plus an explicit
# currency, which is signed into the agreement, task envelope and context.
CURRENCIES = ('GBP', 'USD', 'EUR')
LEGACY_KEYS = frozenset({'goal', 'deliverable', 'executor', 'criteria', 'cap_microusd'})
CURRENCY_KEYS = frozenset({'goal', 'deliverable', 'executor', 'criteria', 'cap_micro', 'currency'})


def check(condition):
    if not condition:
        raise ValueError('Invalid mission terms or binding')


def bounded(value, limit):
    check(type(value) is str and value.strip() and len(value.encode('utf-8')) <= limit)
    return value


def cap(value):
    check(type(value) is int and 0 <= value <= 1_000_000_000)
    return value


def currency(value):
    check(value in CURRENCIES)
    return value


def budget(value):
    """(limit, currency) for valid terms; currency is None for legacy US dollar terms."""
    if 'cap_microusd' in value:
        return value['cap_microusd'], None
    return value['cap_micro'], value['currency']


def terms(value):
    check(type(value) is dict and set(value) in (LEGACY_KEYS, CURRENCY_KEYS))
    bounded(value['goal'], 512)
    bounded(value['deliverable'], 512)
    check(type(value['executor']) is str and re.fullmatch('[a-f0-9]{64}', value['executor']))
    if 'currency' in value:
        currency(value['currency'])
        cap(value['cap_micro'])
    else:
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
    check(type(value) is dict and set(value) == {'domain', 'terms'})
    check(agreement_content(value['terms']) == statement['content'])
    return value['terms']


def mission_context(commitment, limit, unit=None):
    check(type(commitment) is str and re.fullmatch('[0-9a-f]{64}', commitment))
    bound = [AGREEMENT, commitment, cap(limit)] if unit is None else [AGREEMENT, commitment, cap(limit), currency(unit)]
    return CONTEXT_PREFIX + digest(bound)[len(CONTEXT_PREFIX):]


def terms_context(commitment, agreed):
    return mission_context(commitment, *budget(agreed))


def task_text(brief, limit, commitment, unit=None):
    mission_context(commitment, limit, unit)
    value = ({'brief': bounded(brief, 4096), 'cap_microusd': limit, 'agreement_digest': commitment} if unit is None else
             {'brief': bounded(brief, 4096), 'cap_micro': limit, 'currency': unit, 'agreement_digest': commitment})
    return TASK_PREFIX + canonical(value).decode()


def money_keys(unit):
    """Key suffix for amounts: legacy US dollar missions keep their original field names."""
    return '_microusd' if unit is None else '_micro'


def amount(record, name):
    return record[name + '_micro'] if name + '_micro' in record else record[name + '_microusd']


def direct_offer(requester, task_id, expires, agreed):
    return {'domain': DIRECT, 'requester': requester, 'task_id': task_id,
            'expires': expires, 'terms': terms(agreed)}


def direct_task_text(brief, offer):
    return TASK_PREFIX + canonical({'brief': bounded(brief, 4096), 'offer': offer}).decode()


def task_details(text, context):
    check(text.startswith(TASK_PREFIX))
    value = json.loads(text[len(TASK_PREFIX):])
    check(type(value) is dict)
    if 'offer' in value:
        offer = value['offer']
        check(type(offer) is dict and set(offer) == {'domain','requester','task_id','expires','terms'})
        check(offer == direct_offer(offer['requester'], offer['task_id'], offer['expires'], offer['terms']))
        (limit, unit), commitment = budget(offer['terms']), digest(offer)
        check(direct_task_text(value['brief'], offer) == text)
    else:
        limit, unit, commitment = value.get('cap_micro', value.get('cap_microusd')), value.get('currency'), value['agreement_digest']
        check(task_text(value['brief'], limit, commitment, unit) == text)
    check(mission_context(commitment, limit, unit) == context)
    return value, (limit, unit)


def validate_task(body):
    value, _ = task_details(body['text'], body['context'])
    offer = value.get('offer')
    if offer is not None:
        check(offer['requester'] == fingerprint(body['sender']) and offer['task_id'] == body['task_id'])
        check(offer['expires'] == body['expires'] and offer['terms']['executor'] == fingerprint(body['recipient']))


def fixture_request(request, context):
    check(context.startswith(CONTEXT_PREFIX))
    value, (limit, unit) = task_details(request['input'], context)
    check(request['model'] == 'synthetic-research-v1' and request['max_output_tokens'] == 128)
    wire_request = {**request, 'input': value['brief']}
    if unit is None:
        return wire_request, {'tariff': TARIFF, 'cap_microusd': limit,
                'reserve_microusd': BASE_MICROUSD + OUTPUT_MICROUSD * request['max_output_tokens'],
                'base_microusd': BASE_MICROUSD, 'per_output_token_microusd': OUTPUT_MICROUSD,
                'simulated': True}
    # A fictional flat tariff per currency. It is not a converted provider price.
    return wire_request, {'tariff': 'fictional-' + unit.lower() + '-v1', 'currency': unit, 'cap_micro': limit,
            'reserve_micro': BASE_MICROUSD + OUTPUT_MICROUSD * request['max_output_tokens'],
            'base_micro': BASE_MICROUSD, 'per_output_token_micro': OUTPUT_MICROUSD,
            'simulated': True}


def evaluate(statement, artifact_id, artifact):
    """Pure local checks. Caller supplies a currently authorised original return."""
    agreed = read_agreement(statement)
    check(digest(artifact) == artifact_id and artifact['context'] == terms_context(digest(statement), agreed))
    return evidence(agreed, statement['id'], statement['revision'], digest(statement), artifact_id, artifact)


def evidence(agreed, proposal_id, revision, commitment, artifact_id, artifact):
    check(digest(artifact) == artifact_id and artifact['context'] == terms_context(commitment, agreed))
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
