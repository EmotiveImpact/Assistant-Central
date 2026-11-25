"""Signed receipts for mission steps, as in-toto Statements inside DSSE envelopes.

Each owner signs their own steps (acknowledging a card, delivering, accepting or returning)
with a key they hold. The envelope can be carried by any host or relay, but only the
owner's key can produce a valid signature, so a host cannot fake anyone's yes. The format
follows the in-toto attestation Statement v1 and DSSE v1 specifications (both Apache-2.0),
so standard tooling can read the receipts. Nothing is copied from those projects; the
small encoders below are written from the published specifications.
"""
import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from pilot.crypto import canonical, digest

from .text import CardError, need

STATEMENT_TYPE = 'https://in-toto.io/Statement/v1'
PAYLOAD_TYPE = 'application/vnd.in-toto+json'
PREDICATE_TYPE = 'https://github.com/EmotiveImpact/Assistant-Central/receipts/mission-step/v1'
SIGNED_STEPS = frozenset({'acknowledged', 'delivered', 'accepted', 'returned'})


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _unb64(text: object) -> bytes:
    need(type(text) is str, 'Invalid envelope encoding')
    try:
        return base64.b64decode(text, validate=True)
    except ValueError:
        raise CardError('Invalid envelope encoding') from None


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding."""
    kind = payload_type.encode('utf-8')
    return b'DSSEv1 %d %s %d %s' % (len(kind), kind, len(payload), payload)


def key_id(public_key: Ed25519PublicKey) -> str:
    return digest(_b64(public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)))


def statement_for(card_snapshot_digest: str, mission_id: str, event: dict) -> dict:
    """The receipt statement for one logged step of a mission."""
    need(event.get('kind') in SIGNED_STEPS, 'Only owner decisions and deliveries get receipts')
    need(event.get('anchor') == mission_id, 'Event belongs to a different mission')
    return {
        '_type': STATEMENT_TYPE,
        'subject': [
            {'name': f'mission/{mission_id}/card', 'digest': {'sha256': card_snapshot_digest}},
            {'name': f'mission/{mission_id}/event/{event["seq"]}', 'digest': {'sha256': event['hash']}},
        ],
        'predicateType': PREDICATE_TYPE,
        'predicate': {'mission_id': mission_id, 'step': event['kind'], 'actor': event['actor'],
                      'at': event['at'], 'previous_event': event['prev'], 'details': event['body']},
    }


def sign(statement: dict, private_key: Ed25519PrivateKey) -> dict:
    """Run on the owner's own device: wrap and sign one statement."""
    payload = canonical(statement)
    signature = private_key.sign(pae(PAYLOAD_TYPE, payload))
    return {'payloadType': PAYLOAD_TYPE, 'payload': _b64(payload),
            'signatures': [{'keyid': key_id(private_key.public_key()), 'sig': _b64(signature)}]}


def verify(envelope: object, owner_keys: dict) -> dict:
    """Check an envelope against the owners' registered public keys.

    ``owner_keys`` maps owner id to Ed25519PublicKey. The signer must be the owner named
    as the step's actor. Returns the statement, or raises CardError.
    """
    need(type(envelope) is dict and envelope.get('payloadType') == PAYLOAD_TYPE, 'Not a receipt envelope')
    payload = _unb64(envelope.get('payload'))
    try:
        statement = json.loads(payload)
    except ValueError:
        raise CardError('Receipt payload is not JSON') from None
    need(type(statement) is dict and statement.get('_type') == STATEMENT_TYPE
         and statement.get('predicateType') == PREDICATE_TYPE, 'Not a mission step receipt')
    need(canonical(statement) == payload, 'Receipt payload is not canonical')
    actor = statement['predicate'].get('actor')
    public_key = owner_keys.get(actor)
    need(public_key is not None, 'No registered key for the owner who took this step')
    signatures = envelope.get('signatures')
    need(type(signatures) is list and signatures, 'Receipt is unsigned')
    expected = key_id(public_key)
    for entry in signatures:
        if type(entry) is dict and entry.get('keyid') == expected:
            try:
                public_key.verify(_unb64(entry.get('sig')), pae(PAYLOAD_TYPE, payload))
                return statement
            except InvalidSignature:
                break
    raise CardError("Receipt is not signed by the owner who took this step")


def matches_log(statement: dict, events: list[dict]) -> bool:
    """True if the receipt names a step that is really in this copy of the mission log."""
    subject = {s['name']: s['digest']['sha256'] for s in statement.get('subject', [])}
    mission_id = statement['predicate']['mission_id']
    for event in events:
        if subject.get(f'mission/{mission_id}/event/{event["seq"]}') == event['hash']:
            return event['kind'] == statement['predicate']['step'] and event['actor'] == statement['predicate']['actor']
    return False
