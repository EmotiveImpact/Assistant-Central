"""Domain-separated owner withdrawal of an exact, provably unused authorization.

No signing keys, authority issuance, network I/O, or expiring replay fences.
"""
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from network import Denied, canonical

DOMAIN = 'agent-network-owner-withdrawal/v1'


def withdrawal_bytes(value):
    return (DOMAIN + '\n' + canonical(value)).encode('ascii')


def validate_withdrawal(value):
    try:
        encoded = canonical(value)
        if len(encoded.encode()) > 4096: raise Denied('Withdrawal exceeds size limit')
        body = json.loads(encoded)
    except (ValueError, TypeError, RecursionError) as exc:
        raise Denied('Withdrawal must be bounded JSON') from exc
    if type(body) is not dict or set(body) != {'version','domain','owner','context','nonce','issued_at','expires_at','target'}:
        raise Denied('Unknown or missing withdrawal fields')
    if type(body['version']) is not int or body['version'] != 1 or body['domain'] != DOMAIN:
        raise Denied('Wrong withdrawal domain or version')
    for field, pattern in (('owner','[a-z0-9_-]{1,64}'),('context','[a-f0-9]{64}'),('nonce','[a-f0-9]{32}')):
        if type(body[field]) is not str or not re.fullmatch(pattern,body[field]): raise Denied('Invalid withdrawal '+field)
    for field in ('issued_at','expires_at'):
        if type(body[field]) is not int or not 0 <= body[field] < 2**63: raise Denied('Invalid withdrawal time')
    if not 1 <= body['expires_at']-body['issued_at'] <= 600: raise Denied('Withdrawal must expire within ten minutes')
    target=body['target']
    if type(target) is not dict or set(target)!={'request_id','fingerprint','review_digest'}:
        raise Denied('Unknown or missing withdrawal target fields')
    for field in target:
        if type(target[field]) is not str or not re.fullmatch('[a-f0-9]{32}' if field=='request_id' else '[a-f0-9]{64}',target[field]):
            raise Denied('Invalid withdrawal target '+field)
    if body['nonce']==target['request_id']: raise Denied('Withdrawal needs a distinct nonce')
    return body


def verify_withdrawal(public_key_hex, signed):
    if type(signed) is not dict or set(signed)!={'withdrawal','signature'}: raise Denied('Exact signed withdrawal required')
    body=validate_withdrawal(signed['withdrawal']); signature=signed['signature']
    if type(signature) is not str or not re.fullmatch('[a-f0-9]{128}',signature): raise Denied('Invalid withdrawal signature encoding')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(bytes.fromhex(signature),withdrawal_bytes(body))
    except (InvalidSignature,ValueError,TypeError) as exc: raise Denied('Withdrawal signature verification failed') from exc
    return body


def assert_not_withdrawn(db, nonce):
    if db.execute('SELECT 1 FROM owner_authorization_withdrawals WHERE source_nonce=?',(nonce,)).fetchone():
        raise Denied('Owner authorization was permanently withdrawn')
