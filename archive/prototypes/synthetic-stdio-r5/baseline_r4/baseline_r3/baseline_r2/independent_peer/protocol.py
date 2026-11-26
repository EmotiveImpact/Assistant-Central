"""Strict experimental protocol. No A4A/wire interoperability claim."""
import base64
import hashlib
import json
import os
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

MAX_FRAME = 65536
MAX_TEXT = 1024
PROTOCOL = 'independent-peer-experiment/1'
CAPABILITY = 'fictional-answer/1'
ACTORS = ('alice', 'bob')

class Rejected(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Rejected(reason)


def exact(obj, keys):
    need(type(obj) is dict and set(obj) == set(keys.split()), 'invalid fields')


def canonical(obj):
    try:
        return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                          allow_nan=False).encode('ascii')
    except (ValueError, TypeError) as exc:
        raise Rejected('not canonical JSON') from exc


def parse(raw):
    need(type(raw) is bytes and len(raw) <= MAX_FRAME, 'frame size')
    def pairs(items):
        obj = {}
        for k, v in items:
            need(k not in obj, 'duplicate JSON key')
            obj[k] = v
        return obj
    try:
        text = raw.decode('utf-8', errors='strict')
        # Bound lexical container nesting before recursive JSON construction.
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == '\\':
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in '[{':
                depth += 1
                need(depth <= 24, 'JSON depth')
            elif character in ']}':
                depth -= 1
        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Rejected('nonfinite number')))
        def bound(v, depth=0):
            need(depth <= 24, 'JSON depth')
            if type(v) is dict:
                need(len(v) <= 32, 'object width')
                for k, child in v.items():
                    need(len(k) <= 64 and not any(0xD800 <= ord(c) <= 0xDFFF for c in k), 'key length or Unicode')
                    bound(child, depth + 1)
            elif type(v) is list:
                need(len(v) <= 32, 'array width')
                for child in v:
                    bound(child, depth + 1)
            elif type(v) is str:
                need(len(v) <= 24000 and not any(0xD800 <= ord(c) <= 0xDFFF for c in v), 'string length or Unicode')
            else:
                need(v is None or type(v) in (bool, int), 'JSON scalar type')
                if type(v) is int:
                    need(abs(v) <= 2**53, 'integer bound')
        bound(obj)
        return obj
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Rejected('invalid JSON') from exc


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def token():
    return os.urandom(16).hex()


def hexid(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{32}', value) is not None, 'invalid id')


def hashid(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'invalid digest')


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def unb64(value, size=None):
    need(type(value) is str and len(value) <= 24000, 'invalid encoding')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise Rejected('invalid encoding') from exc
    need(b64(raw) == value and (size is None or len(raw) == size), 'invalid encoded size')
    return raw


def public(key):
    return b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


class Identity:
    """One endpoint's keys, memory only. Never exported by the service."""
    def __init__(self, actor):
        need(actor in ACTORS, 'fixed actor required')
        self.actor = actor
        self.signer = Ed25519PrivateKey.generate()
        self.box = X25519PrivateKey.generate()
        self.descriptor = {'actor': actor, 'signing': public(self.signer), 'encryption': public(self.box), 'incarnation': token()}

    def sign(self, domain, body):
        return {'body': body, 'signature': b64(self.signer.sign(canonical({'domain': PROTOCOL + '/' + domain, 'body': body})))}


def descriptor(value):
    exact(value, 'actor signing encryption incarnation')
    need(value['actor'] in ACTORS, 'unknown actor')
    unb64(value['signing'], 32)
    unb64(value['encryption'], 32)
    hexid(value['incarnation'])
    return value


def verify(signed, domain, peer):
    exact(signed, 'body signature')
    try:
        Ed25519PublicKey.from_public_bytes(unb64(peer['signing'], 32)).verify(
            unb64(signed['signature'], 64), canonical({'domain': PROTOCOL + '/' + domain, 'body': signed['body']}))
    except Exception as exc:
        raise Rejected('signature rejected') from exc
    return signed['body']


def task(value):
    exact(value, 'id context capability')
    hexid(value['id'])
    hashid(value['context'])
    need(value['capability'] == CAPABILITY, 'unsupported capability')
    return value


def scope(task_value, sender, recipient, kind):
    return {'task': task_value['id'], 'context': task_value['context'], 'capability': CAPABILITY,
            'sender': sender, 'recipient': recipient, 'kind': kind}


def grant_body(body, expected_scope, descriptors):
    exact(body, 'scope nonce epoch sender_binding recipient_binding')
    need(body['scope'] == expected_scope, 'grant scope mismatch')
    hexid(body['nonce'])
    need(type(body['epoch']) is int and 0 < body['epoch'] <= 2**31, 'grant epoch')
    need(body['sender_binding'] == digest(descriptors[expected_scope['sender']]) and
         body['recipient_binding'] == digest(descriptors[expected_scope['recipient']]), 'grant binding mismatch')


def seal(identity, recipient, signed_message):
    """Ephemeral-static X25519, HKDF-SHA256, AES-256-GCM; signed inner body."""
    ephemeral = X25519PrivateKey.generate()
    header = {'protocol': PROTOCOL, 'sender': identity.actor, 'recipient': recipient['actor'],
              'sender_binding': digest(identity.descriptor), 'recipient_binding': digest(recipient),
              'ephemeral': public(ephemeral), 'nonce': b64(os.urandom(12))}
    secret = ephemeral.exchange(X25519PublicKey.from_public_bytes(unb64(recipient['encryption'], 32)))
    key = HKDF(algorithm=SHA256(), length=32, salt=None, info=canonical(header)).derive(secret)
    ciphertext = AESGCM(key).encrypt(unb64(header['nonce'], 12), canonical(signed_message), canonical(header))
    return {'header': header, 'ciphertext': b64(ciphertext)}


def open_packet(identity, peer, packet):
    exact(packet, 'header ciphertext')
    header = packet['header']
    exact(header, 'protocol sender recipient sender_binding recipient_binding ephemeral nonce')
    need(header['protocol'] == PROTOCOL and header['sender'] == peer['actor'] and header['recipient'] == identity.actor,
         'outer direction mismatch')
    need(header['sender_binding'] == digest(peer) and header['recipient_binding'] == digest(identity.descriptor), 'outer binding mismatch')
    try:
        secret = identity.box.exchange(X25519PublicKey.from_public_bytes(unb64(header['ephemeral'], 32)))
        key = HKDF(algorithm=SHA256(), length=32, salt=None, info=canonical(header)).derive(secret)
        raw = AESGCM(key).decrypt(unb64(header['nonce'], 12), unb64(packet['ciphertext']), canonical(header))
        signed = parse(raw)
    except Exception as exc:
        raise Rejected('decryption rejected') from exc
    return verify(signed, 'message', peer)
