"""Bounded signed/encrypted pilot packets, with explicitly pinned peer keys.

This uses standard primitives, not a reviewed messaging protocol. No network or
private key storage belongs here. Auth objects keep signing/exchange keys private.
"""
import base64
import hashlib
import json
import math
import os
import re
import time

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PROTOCOL = 'assistant-central-pilot-packet/1'
KINDS = frozenset(('proposal', 'decision', 'cancel', 'receipt'))
MAX_PACKET = 32768
MAX_PAYLOAD = 16384
MAX_LIFETIME = 3600
_TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


class TransportDenied(ValueError):
    """Fixed local validation error; never a proof that remote work did not happen."""


def _need(condition, message='Invalid pilot packet'):
    if not condition:
        raise TransportDenied(message)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportDenied('Invalid canonical data') from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def token(value):
    _need(type(value) is str and _TOKEN.fullmatch(value) is not None, 'Invalid bounded identifier')
    return value


def b64(value):
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def unb64(value, size=None, *, maximum=MAX_PACKET):
    _need(type(value) is str and 0 < len(value) <= maximum * 2
          and re.fullmatch(r'[A-Za-z0-9_-]+', value) is not None, 'Invalid encoded bytes')
    try:
        raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    except (ValueError, TypeError):
        raise TransportDenied('Invalid encoded bytes') from None
    _need(len(raw) <= maximum and b64(raw) == value and (size is None or len(raw) == size),
          'Invalid encoded byte length')
    return raw


def validate_public(public):
    _need(type(public) is dict and set(public) == {'owner_id', 'agent_id', 'signing_key', 'exchange_key'},
          'Expected exact public identity')
    token(public['owner_id']); token(public['agent_id'])
    signing, exchange = unb64(public['signing_key'], 32), unb64(public['exchange_key'], 32)
    _need(signing != exchange and exchange != bytes(32), 'Invalid public identity keys')
    return json.loads(canonical(public))


def fingerprint(public):
    return digest(validate_public(public))


def _timestamp(value):
    _need(type(value) in (int, float) and math.isfinite(value) and value > 0,
          'Invalid packet timestamp')
    return value


def _json_payload(value):
    _need(type(value) is dict, 'Expected payload object')
    count = 0
    def walk(item, depth):
        nonlocal count
        count += 1
        _need(depth <= 8 and count <= 2048, 'Payload nesting or item bound exceeded')
        if type(item) is dict:
            _need(len(item) <= 128, 'Payload member bound exceeded')
            for key, child in item.items():
                _need(type(key) is str and 0 < len(key) <= 128, 'Invalid payload member')
                walk(child, depth + 1)
        elif type(item) is list:
            _need(len(item) <= 128, 'Payload list bound exceeded')
            for child in item: walk(child, depth + 1)
        else:
            _need(item is None or type(item) in (str, int, float, bool), 'Invalid payload type')
    walk(value, 0)
    encoded = canonical(value)
    _need(len(encoded) <= MAX_PAYLOAD, 'Payload byte bound exceeded')
    return encoded


def packet_header(packet):
    _need(type(packet) is dict and set(packet) == {'header', 'ciphertext', 'signature'},
          'Expected exact encrypted packet')
    _need(len(canonical(packet)) <= MAX_PACKET, 'Packet byte bound exceeded')
    header = packet['header']
    _need(type(header) is dict and set(header) == {
        'protocol', 'message_id', 'kind', 'sender', 'recipient', 'context', 'artifact_id',
        'proposal_id', 'created', 'expires', 'ephemeral', 'nonce'}, 'Invalid packet header')
    _need(header['protocol'] == PROTOCOL and type(header['kind']) is str and header['kind'] in KINDS,
          'Unsupported packet protocol or kind')
    for field in ('message_id', 'context', 'artifact_id', 'proposal_id'): token(header[field])
    for field in ('sender', 'recipient'):
        _need(type(header[field]) is str and re.fullmatch(r'[0-9a-f]{64}', header[field]) is not None,
              'Invalid peer fingerprint')
    _need(header['sender'] != header['recipient'], 'Peer exchange requires distinct identities')
    created, expires = _timestamp(header['created']), _timestamp(header['expires'])
    _need(0 < expires - created <= MAX_LIFETIME, 'Packet lifetime exceeds bound')
    unb64(header['ephemeral'], 32); unb64(header['nonce'], 12)
    _need(len(unb64(packet['ciphertext'], maximum=MAX_PAYLOAD + 16)) >= 18, 'Invalid ciphertext length')
    unb64(packet['signature'], 64)
    return json.loads(canonical(header))


def verify_packet(packet, sender_public, recipient_public):
    """Verify exact pinned direction and signature, without granting freshness."""
    sender, recipient = validate_public(sender_public), validate_public(recipient_public)
    header = packet_header(packet)
    _need(header['sender'] == fingerprint(sender) and header['recipient'] == fingerprint(recipient),
          'Packet does not match the pinned peer direction')
    signed = {'header': header, 'ciphertext': packet['ciphertext']}
    try:
        Ed25519PublicKey.from_public_bytes(unb64(sender['signing_key'], 32)).verify(
            unb64(packet['signature'], 64), canonical(signed))
    except (InvalidSignature, ValueError):
        raise TransportDenied('Packet signature verification failed') from None
    return header


def _key(shared, header):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(canonical(header)).digest(),
                info=PROTOCOL.encode('ascii')).derive(shared)


def seal(auth, session, recipient_public, *, message_id, context, artifact_id,
         proposal_id, kind, payload, expires, now=None):
    """Return one new packet. Queue it once; retries MUST use the stored bytes."""
    sender = validate_public(auth.public_identity())
    recipient = validate_public(recipient_public)
    now = _timestamp(time.time() if now is None else now)
    expires = _timestamp(expires)
    _need(0 < expires - now <= MAX_LIFETIME, 'Packet expiry must be within one hour')
    _need(type(kind) is str and kind in KINDS, 'Unsupported packet kind')
    for value in (message_id, context, artifact_id, proposal_id): token(value)
    plaintext = _json_payload(payload)
    ephemeral = X25519PrivateKey.generate()
    header = {'protocol': PROTOCOL, 'message_id': message_id, 'kind': kind,
              'sender': fingerprint(sender), 'recipient': fingerprint(recipient),
              'context': context, 'artifact_id': artifact_id, 'proposal_id': proposal_id,
              'created': now, 'expires': expires,
              'ephemeral': b64(ephemeral.public_key().public_bytes_raw()), 'nonce': b64(os.urandom(12))}
    try:
        shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(unb64(recipient['exchange_key'], 32)))
        ciphertext = AESGCM(_key(shared, header)).encrypt(unb64(header['nonce'], 12), plaintext, canonical(header))
    except ValueError:
        raise TransportDenied('Peer encryption key is invalid') from None
    signed = {'header': header, 'ciphertext': b64(ciphertext)}
    packet = {**signed, 'signature': b64(auth.sign(session, canonical(signed)))}
    verify_packet(packet, sender, recipient)
    return packet


def open_packet(auth, session, sender_public, packet, now=None):
    """Decrypt a fresh original packet only after checking the enrolled sender."""
    header = verify_packet(packet, sender_public, auth.public_identity())
    now = _timestamp(time.time() if now is None else now)
    _need(header['created'] <= now + 30 and header['expires'] > now, 'Packet is future-dated or expired')
    try:
        shared = auth.exchange(session, unb64(header['ephemeral'], 32))
        plaintext = AESGCM(_key(shared, header)).decrypt(
            unb64(header['nonce'], 12), unb64(packet['ciphertext'], maximum=MAX_PAYLOAD + 16), canonical(header))
        value = json.loads(plaintext)
        _need(_json_payload(value) == plaintext, 'Noncanonical decrypted payload')
    except (ValueError, TypeError, InvalidTag, UnicodeError, RecursionError):
        raise TransportDenied('Packet decryption or payload validation failed') from None
    return {'header': header, 'payload': value}
