"""Owner approvals signed with a passkey on their phone (WebAuthn).

The owner approves a mission step by completing a WebAuthn assertion whose challenge is
the hash of that step's receipt statement (the same DSSE pre-authentication encoding used
by ``receipts.py``). The resulting passkey receipt binds the yes to a key held in the
owner's authenticator: a host can carry it but cannot produce it. Verification follows
the WebAuthn Level 3 assertion steps for ES256 credentials, using only ``cryptography``.

Checked: credential belongs to the owner named as actor, ``type`` is ``webauthn.get``,
challenge equals the statement hash, origin and RP ID match, user presence and user
verification flags are set, the signature is valid, and the signature counter moves
forward (when the authenticator keeps one).
"""
import base64
import hashlib
import json
import struct
import threading

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from pilot.crypto import canonical

from .receipts import PAYLOAD_TYPE, pae
from .text import CardError, ident, need

PASSKEY_ENVELOPE = 'assistant-central/passkey-receipt/1'
FLAG_UP, FLAG_UV = 0x01, 0x04


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def unb64url(text: object) -> bytes:
    need(type(text) is str, 'Invalid encoding')
    try:
        return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    except ValueError:
        raise CardError('Invalid encoding') from None


def challenge_for(statement: dict) -> bytes:
    return hashlib.sha256(pae(PAYLOAD_TYPE, canonical(statement))).digest()


class PasskeyRegistry:
    """Owners' registered passkey credentials for one relying party."""

    def __init__(self, rp_id: str, origin: str):
        self.rp_id, self.origin = rp_id, origin
        self._rp_hash = hashlib.sha256(rp_id.encode('utf-8')).digest()
        self._lock = threading.Lock()
        self._creds: dict[str, dict] = {}

    def register(self, owner: str, credential_id: bytes, public_key: ec.EllipticCurvePublicKey) -> None:
        ident(owner, 'owner')
        need(isinstance(public_key, ec.EllipticCurvePublicKey) and isinstance(public_key.curve, ec.SECP256R1),
             'Only ES256 (P-256) passkeys are supported')
        with self._lock:
            need(b64url(credential_id) not in self._creds, 'Credential already registered')
            self._creds[b64url(credential_id)] = {'owner': owner, 'key': public_key, 'count': 0}

    def _check(self, statement, credential_id, authenticator_data, client_data_json, signature):
        cred = self._creds.get(b64url(credential_id))
        need(cred is not None, 'Unknown passkey')
        need(cred['owner'] == statement.get('predicate', {}).get('actor'),
             'This passkey belongs to a different owner')
        try:
            client = json.loads(client_data_json)
        except ValueError:
            raise CardError('Invalid client data') from None
        need(type(client) is dict and client.get('type') == 'webauthn.get', 'Not a WebAuthn assertion')
        need(client.get('challenge') == b64url(challenge_for(statement)), 'Assertion is for a different step')
        need(client.get('origin') == self.origin, 'Assertion came from a different origin')
        need(len(authenticator_data) >= 37 and authenticator_data[:32] == self._rp_hash, 'Wrong relying party')
        flags = authenticator_data[32]
        need(flags & FLAG_UP and flags & FLAG_UV, 'The owner was not verified on their device')
        try:
            cred['key'].verify(signature, authenticator_data + hashlib.sha256(client_data_json).digest(),
                               ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            raise CardError('Passkey signature is not valid') from None
        return cred, struct.unpack('>I', authenticator_data[33:37])[0]

    def approve(self, statement: dict, credential_id: bytes, authenticator_data: bytes,
                client_data_json: bytes, signature: bytes) -> dict:
        """Verify a fresh assertion, advance the counter and return a passkey receipt."""
        with self._lock:
            cred, count = self._check(statement, credential_id, authenticator_data, client_data_json, signature)
            if count or cred['count']:
                need(count > cred['count'], 'Passkey counter did not advance; possible replay or cloned key')
            cred['count'] = count
        return {'domain': PASSKEY_ENVELOPE, 'payloadType': PAYLOAD_TYPE, 'payload': b64url(canonical(statement)),
                'webauthn': {'credential_id': b64url(credential_id), 'authenticator_data': b64url(authenticator_data),
                             'client_data_json': b64url(client_data_json), 'signature': b64url(signature)}}

    def verify_receipt(self, envelope: object) -> dict:
        """Re-check a stored passkey receipt offline (the counter is not re-applied)."""
        need(type(envelope) is dict and envelope.get('domain') == PASSKEY_ENVELOPE
             and envelope.get('payloadType') == PAYLOAD_TYPE and type(envelope.get('webauthn')) is dict,
             'Not a passkey receipt')
        payload = unb64url(envelope.get('payload'))
        try:
            statement = json.loads(payload)
        except ValueError:
            raise CardError('Receipt payload is not JSON') from None
        need(type(statement) is dict and canonical(statement) == payload, 'Receipt payload is not canonical')
        w = envelope['webauthn']
        with self._lock:
            self._check(statement, unb64url(w.get('credential_id')), unb64url(w.get('authenticator_data')),
                        unb64url(w.get('client_data_json')), unb64url(w.get('signature')))
        return statement
