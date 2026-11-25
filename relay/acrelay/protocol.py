# SPDX-License-Identifier: AGPL-3.0-only
"""Wire protocol shared by the relay service and its clients.

The relay only ever sees opaque ciphertext packets, random mailbox identifiers
and hashed send tokens. It never sees an owner's identity key, a message, or
who a sender is: only which send grant a packet arrived under.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import quote, unquote, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

VERSION = 'assistant-central-relay/1'
CLOCK_SKEW = 300
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
NONCE = re.compile(r'[0-9a-f]{32}\Z')


class RelayError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


def b64e(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def b64d(text):
    if type(text) is not str or len(text) > 200000 or not re.fullmatch(r'[A-Za-z0-9_-]*', text):
        raise RelayError(400, 'bad_base64')
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def mailbox_id(public_key_bytes):
    return sha256_hex(b'acrelay-mailbox\x00' + public_key_bytes)


def token_hash(token):
    return sha256_hex(b'acrelay-send-token\x00' + token.encode())


def signing_bytes(method, path, timestamp, nonce, body):
    return '\n'.join([VERSION, method, path, str(timestamp), nonce, sha256_hex(body)]).encode()


class MailboxKey:
    """The owner's dedicated relay key. Separate from their identity key on purpose."""

    def __init__(self, private_key=None):
        self._key = private_key or Ed25519PrivateKey.generate()
        self.public_bytes = self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.mailbox = mailbox_id(self.public_bytes)

    @classmethod
    def from_seed(cls, seed):
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    def headers(self, method, path, body, *, now=None):
        timestamp = int(time.time() if now is None else now)
        nonce = secrets.token_hex(16)
        signature = self._key.sign(signing_bytes(method, path, timestamp, nonce, body))
        return {'AC-Mailbox': self.mailbox, 'AC-Time': str(timestamp), 'AC-Nonce': nonce,
                'AC-Signature': b64e(signature)}


def verify_signed(public_bytes, method, path, headers, body, now):
    try:
        timestamp = int(headers.get('ac-time', ''))
        nonce = headers.get('ac-nonce', '')
        signature = b64d(headers.get('ac-signature', ''))
    except (ValueError, RelayError):
        raise RelayError(401, 'bad_signature') from None
    if not NONCE.fullmatch(nonce) or abs(now - timestamp) > CLOCK_SKEW:
        raise RelayError(401, 'stale_or_bad_request')
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature, signing_bytes(method, path, timestamp, nonce, body))
    except (InvalidSignature, ValueError):
        raise RelayError(401, 'bad_signature') from None
    return nonce, timestamp


# Invite links ------------------------------------------------------------------

def new_send_token():
    return secrets.token_urlsafe(32)


def invite_link(relay_url, mailbox, token, identity_fingerprint, label=''):
    """Everything after ``#`` stays in the browser: servers never receive it.

    The link carries where to send (relay and mailbox), how (a send token) and
    who to expect (the inviter's identity fingerprint, to compare out of band).
    """
    if not HEX64.fullmatch(mailbox) or not HEX64.fullmatch(identity_fingerprint):
        raise RelayError(400, 'bad_invite')
    if len(label.encode()) > 64:
        raise RelayError(400, 'bad_invite')
    payload = json.dumps({'v': 1, 'r': relay_url.rstrip('/'), 'm': mailbox, 't': token,
                          'f': identity_fingerprint, 'l': label}, separators=(',', ':'), sort_keys=True)
    return relay_url.rstrip('/') + '/invite#' + b64e(payload.encode())


def parse_invite(link):
    try:
        parts = urlsplit(link)
        if parts.scheme not in ('https', 'http') or not parts.fragment:
            raise ValueError()
        value = json.loads(b64d(parts.fragment))
        if type(value) is not dict or value.get('v') != 1 or set(value) != {'v', 'r', 'm', 't', 'f', 'l'}:
            raise ValueError()
        if not HEX64.fullmatch(value['m']) or not HEX64.fullmatch(value['f']):
            raise ValueError()
        if type(value['t']) is not str or not 32 <= len(value['t']) <= 64:
            raise ValueError()
        relay = urlsplit(value['r'])
        if relay.scheme not in ('https', 'http') or relay.netloc != parts.netloc:
            raise ValueError()  # The link must point at the relay it names.
        if relay.scheme == 'http' and relay.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError()
        return {'relay_url': value['r'], 'mailbox': value['m'], 'send_token': value['t'],
                'identity_fingerprint': value['f'], 'label': value['l']}
    except (ValueError, TypeError, KeyError, RelayError, UnicodeError):
        raise RelayError(400, 'bad_invite') from None


def constant_equal(a, b):
    return hmac.compare_digest(a, b)
