"""Trusted construction helpers for disposable offline integration tests/demo only.

Creates no accounts or persistent private credentials. Do not expose owner signing
keys or these helpers to an agent. Real enrollment/key custody is not implemented.
"""
import secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from bound_identity import BINDING_DOMAIN, DELIVERY_DOMAIN, IdentityRegistry, possession_digest, signed_bytes
from network import context_digest, digest
from owner_auth import DOMAIN, decision_bytes
from vendor.a4a_sdk.keys import Keys
from vendor.a4a_sdk import crypto


class FixtureAuthorities:
    def __init__(self, meeting, now):
        self.meeting, self.context = meeting, context_digest(meeting)
        self.owner_keys = {owner: Ed25519PrivateKey.generate() for owner in meeting.participants}
        self.transport_keys = {owner: Keys() for owner in meeting.participants}
        self.owner_roots = {owner: key.public_key().public_bytes_raw().hex() for owner, key in self.owner_keys.items()}
        self.bindings = {}
        from generic_protocol import Task
        for owner in meeting.participants:
            allowed = ([peer for peer in meeting.participants if peer!=owner] if type(meeting) is Task
                       else sorted(meeting.participants) if owner == meeting.coordinator else [meeting.coordinator])
            body = {'version': 1, 'domain': BINDING_DOMAIN, 'owner': owner, 'context': self.context,
                    'transport_pubkey': self.transport_keys[owner].pubkey_hex, 'receive_from': allowed,
                    'issued_at': int(now), 'expires_at': int(now) + 86400}
            proof = crypto.sign(possession_digest(body), self.transport_keys[owner].privkey_hex)
            token = {'binding': body, 'transport_proof': proof}
            token['owner_signature'] = self.owner_keys[owner].sign(signed_bytes(BINDING_DOMAIN, token)).hex()
            self.bindings[owner] = token
        self.registry = IdentityRegistry(meeting, self.owner_roots, self.bindings)

    def control(self, owner, action, target, now, nonce=None):
        body = {'version': 1, 'domain': DOMAIN, 'action': action, 'owner': owner, 'context': self.context,
                'nonce': nonce or secrets.token_hex(16), 'issued_at': int(now), 'expires_at': int(now) + 300,
                'target': target}
        return {'decision': body, 'signature': self.owner_keys[owner].sign(decision_bytes(body)).hex()}

    def delivery(self, message, pair_versions, now, ttl=300, nonce=None):
        sender, recipient = message['sender'], message['recipient']
        body = {'version': 1, 'domain': DELIVERY_DOMAIN, 'action': 'send', 'owner': sender,
                'context': self.context, 'nonce': nonce or secrets.token_hex(16),
                'issued_at': int(now), 'expires_at': int(now) + ttl,
                'target': {'recipient': recipient, 'envelope_digest': digest(message), 'pair_versions': pair_versions,
                           'sender_binding': self.registry.binding_digest(sender),
                           'recipient_binding': self.registry.binding_digest(recipient)}}
        return {'decision': body, 'signature': self.owner_keys[sender].sign(signed_bytes(DELIVERY_DOMAIN, body)).hex()}

    def pair_all(self, gateway, now):
        from generic_protocol import Task
        if type(self.meeting) is Task:
            for owner in self.meeting.participants:
                peer=next(p for p in self.meeting.participants if p!=owner)
                version=gateway.delivery.contact_version(owner,peer,self.context)
                gateway.apply(self.control(owner,'pair',{'peer':peer,'contact_version':version,'ttl':3600},now))
            return
        for owner in self.meeting.participants:
            for a, b in dict.fromkeys(((owner, self.meeting.coordinator), (self.meeting.coordinator, owner))):
                version = gateway.delivery.contact_version(a, b, self.context)
                gateway.apply(self.control(a, 'pair', {'peer': b, 'contact_version': version, 'ttl': 3600}, now))
