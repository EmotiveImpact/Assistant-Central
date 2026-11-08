"""Public, informational fictional possession evidence. Never task authority."""
import copy
import json
import re
from network import Denied, canonical, digest
from bound_identity import signed_bytes, verify_owner

OWNER_DOMAIN = 'fictional-continuity-task-possession/v1'
CONTINUITY_DOMAIN = 'fictional-continuity-identity-possession/v1'
PURPOSE = 'informational-fictional-association-only'
MAX_IDENTITIES = 4
MAX_ASSOCIATIONS = 20
FIELDS = {'purpose','incarnation','identity_id','identity_version','continuity_root',
          'fingerprint','association_id','selector','context','actor','owner_root',
          'nonce','generation','issued_at','review_expires_at','certificate_expires_at'}


def detached(value):
    try:
        raw = canonical(value)
        if len(raw.encode('utf8')) > 8192: raise Denied('Continuity JSON exceeds bound')
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied('Expected bounded continuity JSON') from exc


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',value):
        raise Denied('Expected bounded continuity identifier')
    return value


def selector(value):
    if type(value) is not str or (value not in ('garden','astronomy') and
            not re.fullmatch(r'custom-[a-z0-9][a-z0-9-]{0,47}',value)):
        raise Denied('Expected existing bounded catalog or custom selector')
    return value


def hex64(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):
        raise Denied('Expected exact public fingerprint')
    return value


def validate_body(value):
    b = detached(value)
    if type(b) is not dict or set(b) != FIELDS: raise Denied('Expected closed continuity body')
    if b['purpose'] != PURPOSE: raise Denied('Not informational continuity evidence')
    for k in ('incarnation','continuity_root','fingerprint','context','owner_root','nonce'): hex64(b[k])
    for k in ('identity_id','association_id','actor'): identifier(b[k])
    selector(b['selector'])
    for k in ('identity_version','generation','issued_at','review_expires_at','certificate_expires_at'):
        if type(b[k]) is not int or not 1 <= b[k] <= 2**53: raise Denied('Expected bounded integer')
    if b['identity_version'] != 1 or b['fingerprint'] != digest({'continuity_root':b['continuity_root']}):
        raise Denied('Invalid continuity anchor')
    if not b['issued_at'] < b['review_expires_at'] <= b['issued_at']+120:
        raise Denied('Invalid review lifetime')
    if not b['review_expires_at'] < b['certificate_expires_at'] <= b['issued_at']+86400:
        raise Denied('Invalid certificate lifetime')
    if b['owner_root'] == b['continuity_root']: raise Denied('Possession keys must be distinct')
    return b


def review(body):
    body = validate_body(body)
    return {'body':body,'review_digest':digest({'domain':'fictional-continuity-review/v1','body':body})}


def verify_certificate(certificate, incarnation):
    """Historical cryptographic validity only, not current activity or authority."""
    c = detached(certificate)
    if type(c) is not dict or set(c) != {'body','owner_signature','continuity_signature'}:
        raise Denied('Expected closed continuity certificate')
    b = validate_body(c['body'])
    if b['incarnation'] != hex64(incarnation): raise Denied('Foreign workspace incarnation')
    verify_owner(b['owner_root'], OWNER_DOMAIN, b, c['owner_signature'])
    verify_owner(b['continuity_root'], CONTINUITY_DOMAIN, b, c['continuity_signature'])
    return c
