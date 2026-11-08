"""Owner-approved, proof-of-possession fixture transport identities.

Bootstrap owner keys are trusted fictional roots, not real-human authentication.
This module verifies public data only and never generates or stores private keys.
"""
import copy
import hashlib
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from network import Denied, canonical, digest, snapshot_envelope
from owner_auth import DOMAIN as OWNER_DOMAIN, validate_decision
from vendor.a4a_sdk import crypto

BINDING_DOMAIN = 'agent-network-fixture-binding/v1'
POSSESSION_DOMAIN = 'agent-network-fixture-possession/v1'
DELIVERY_DOMAIN = 'agent-network-encrypted-delivery/v1'
RECEIPT_DOMAIN = 'agent-network-offline-receipt/v1'
_HEX64 = re.compile(r'[a-f0-9]{64}')
_HEX128 = re.compile(r'[a-f0-9]{128}')


def signed_bytes(domain, body):
    return (domain + '\n' + canonical(body)).encode('ascii')


def possession_digest(binding):
    return hashlib.sha256(signed_bytes(POSSESSION_DOMAIN, binding)).hexdigest()


def verify_owner(public_key, domain, body, signature):
    if type(signature) is not str or not _HEX128.fullmatch(signature):
        raise Denied('Invalid owner signature encoding')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), signed_bytes(domain, body))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise Denied('Owner signature verification failed') from exc


def verify_binding_token(meeting, owner_root, owner, token):
    from network import context_digest
    context, participants = context_digest(meeting), set(meeting.participants)
    if owner not in participants:
        raise Denied("Unknown binding owner")
    try:
        raw = canonical(token)
        if len(raw.encode()) > 4096: raise Denied('Binding exceeds size limit')
        token = json.loads(raw)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied('Binding must be bounded JSON') from exc
    if type(token) is not dict or set(token) != {'binding', 'transport_proof', 'owner_signature'}:
        raise Denied('Unknown or missing identity-binding fields')
    body = token['binding']
    fields = {'version', 'domain', 'owner', 'context', 'transport_pubkey', 'receive_from', 'issued_at', 'expires_at'}
    if type(body) is not dict or set(body) != fields:
        raise Denied('Invalid identity-binding schema')
    if (type(body['version']) is not int or body['version'] != 1 or body['domain'] != BINDING_DOMAIN
            or body['owner'] != owner or body['context'] != context):
        raise Denied('Identity binding names another owner, context or domain')
    pubkey, peers = body['transport_pubkey'], body['receive_from']
    if type(pubkey) is not str or not _HEX64.fullmatch(pubkey):
        raise Denied('Invalid transport public key')
    if (type(peers) is not list or any(type(p) is not str or p not in participants for p in peers)
            or peers != sorted(set(peers))):
        raise Denied('Receive permission must list exact distinct meeting peers')
    if any(type(body[field]) is not int or not 0 <= body[field] < 2**63 for field in ('issued_at', 'expires_at')):
        raise Denied('Invalid identity-binding times')
    if not 1 <= body['expires_at'] - body['issued_at'] <= 86400:
        raise Denied('Fixture binding must expire within one day')
    proof = token['transport_proof']
    if type(proof) is not str or not _HEX128.fullmatch(proof) or not crypto.verify(possession_digest(body), proof, pubkey):
        raise Denied('Transport key possession was not proved')
    verify_owner(owner_root, BINDING_DOMAIN,
                 {'binding': body, 'transport_proof': proof}, token['owner_signature'])
    return token


class IdentityRegistry:
    def __init__(self, meeting, owner_roots, bindings):
        from network import context_digest
        self.meeting, self.context = meeting, context_digest(meeting)
        participants = set(meeting.participants)
        if (type(owner_roots) is not dict or set(owner_roots) != participants
                or any(type(v) is not str or not _HEX64.fullmatch(v) for v in owner_roots.values())
                or len(set(owner_roots.values())) != len(participants)):
            raise Denied('Fixture owner roots must exactly match distinct meeting owners')
        if type(bindings) is not dict or set(bindings) != participants:
            raise Denied('Identity bindings must match every meeting participant')
        self.owner_roots = dict(owner_roots)
        self.bindings, self.public_keys = {}, {}
        for owner, token in bindings.items():
            token = verify_binding_token(meeting, self.owner_roots[owner], owner, token)
            self.bindings[owner] = token
            self.public_keys[owner] = token['binding']['transport_pubkey']
        if len(set(self.public_keys.values())) != len(participants):
            raise Denied('Different owners cannot silently share one transport identity')
        self.fingerprint = digest({'owner_roots': self.owner_roots, 'bindings': self.bindings})

    def binding_digest(self, owner):
        if owner not in self.bindings: raise Denied('Unknown bound owner')
        return digest(self.bindings[owner])

    def active_at(self, owner, when):
        body = self.bindings[owner]['binding']
        if not body['issued_at'] <= when < body['expires_at']:
            raise Denied('Transport identity binding is expired or not yet valid')

    def permits(self, sender, recipient, when):
        if sender not in self.bindings or recipient not in self.bindings:
            raise Denied('Unknown fixture transport owner')
        self.active_at(sender, when); self.active_at(recipient, when)
        if sender not in self.bindings[recipient]['binding']['receive_from']:
            raise Denied('Recipient has not approved receiving from this fixture sender')

    def pin(self, store):
        store.db.execute('CREATE TABLE IF NOT EXISTS encrypted_identity_registry (context TEXT PRIMARY KEY, fingerprint TEXT NOT NULL)')
        with store.transaction():
            row = store.db.execute('SELECT fingerprint FROM encrypted_identity_registry WHERE context=?', (self.context,)).fetchone()
            if row and row[0] != self.fingerprint:
                raise Denied('Pinned fixture transport identities changed; automatic replacement is forbidden')
            if row is None:
                if store.db.execute('SELECT COUNT(*) FROM encrypted_identity_registry').fetchone()[0] >= store.max_records:
                    raise Denied('Identity-registry record limit reached')
                store.db.execute('INSERT INTO encrypted_identity_registry VALUES (?,?)', (self.context, self.fingerprint))

    def validate_delivery(self, value, envelope=None):
        """Validate an unsigned draft. This does NOT grant authority to execute it."""
        try:
            encoded = canonical(value)
            if len(encoded.encode()) > 4096: raise Denied('Delivery decision too large')
            decision = json.loads(encoded)
        except (TypeError, ValueError, RecursionError) as exc:
            raise Denied('Invalid delivery decision JSON') from exc
        if type(decision) is not dict or decision.get('domain') != DELIVERY_DOMAIN or decision.get('action') != 'send':
            raise Denied('Wrong encrypted-delivery decision domain')
        target = decision.get('target')
        fields = {'recipient', 'envelope_digest', 'pair_versions', 'sender_binding', 'recipient_binding'}
        if type(target) is not dict or set(target) != fields:
            raise Denied('Delivery approval must bind exact sender and recipient identities')
        base = copy.deepcopy(decision); base['domain'] = OWNER_DOMAIN
        base['target'] = {k: v for k, v in target.items() if k not in ('sender_binding', 'recipient_binding')}
        validate_decision(base)  # Reuse the closed v4 time/nonce/message-scope grammar.
        owner, recipient = decision['owner'], target['recipient']
        if owner not in self.owner_roots or recipient not in self.owner_roots or decision['context'] != self.context:
            raise Denied('Delivery owner, recipient or context is not enrolled')
        if (target['sender_binding'] != self.binding_digest(owner)
                or target['recipient_binding'] != self.binding_digest(recipient)):
            raise Denied('Approved transport identity does not match the pinned recipient or sender')
        message = None
        if envelope is not None:
            message = snapshot_envelope(envelope)
            if (message['sender'] != owner or message['recipient'] != recipient or message['context'] != self.context
                    or digest(message) != target['envelope_digest']):
                raise Denied('Delivery approval does not cover this exact message')
        return decision, message

    def verify_delivery(self, signed, envelope=None):
        if type(signed) is not dict or set(signed) != {'decision', 'signature'}:
            raise Denied('A signed encrypted-delivery decision is required')
        decision, message = self.validate_delivery(signed['decision'], envelope)
        verify_owner(self.owner_roots[decision['owner']], DELIVERY_DOMAIN, decision, signed['signature'])
        return decision, message
