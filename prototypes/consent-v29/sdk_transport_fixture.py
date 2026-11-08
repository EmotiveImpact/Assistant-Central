"""Pinned A4A crypto round-trip fixture. No relay/client, sockets or disk key store.

This does not accept owner consent, publish anything, or make security/compatibility
claims about a deployed product. Keys are disposable fictional fixtures only.
"""
import json
import re
from private_message_adapter import private_message_draft
from network import Denied, canonical, context_digest, snapshot_envelope
from vendor.a4a_sdk.event import Event
from vendor.a4a_sdk.keys import Keys
from vendor.a4a_sdk import giftwrap


class PinnedSdkFixture:
    def __init__(self, meeting):
        self.meeting = meeting
        self.keys = {owner: Keys() for owner in meeting.participants}
        self.public_keys = {owner: key.pubkey_hex for owner, key in self.keys.items()}

    @classmethod
    def for_bound_peer(cls, meeting, owner, private_key, public_keys):
        """Single-key fixture endpoint; its peer references are verified externally."""
        if (owner not in meeting.participants or type(public_keys) is not dict
                or set(public_keys) != set(meeting.participants)
                or any(type(key) is not str or not re.fullmatch(r'[a-f0-9]{64}', key) for key in public_keys.values())
                or len(set(public_keys.values())) != len(public_keys)
                or not isinstance(private_key, Keys) or private_key.pubkey_hex != public_keys[owner]):
            raise Denied('Private fixture key does not match the bound owner identity')
        peer = cls.__new__(cls)
        peer.meeting, peer.keys, peer.public_keys = meeting, {owner: private_key}, dict(public_keys)
        return peer

    def seal(self, envelope, delivery_id, created_at):
        message = snapshot_envelope(envelope)
        if message['sender'] not in self.keys:
            raise Denied('This fixture endpoint cannot sign for another sender')
        draft = private_message_draft(message, scope=self.meeting, peer_pubkeys=self.public_keys,
                                 delivery_id=delivery_id, created_at=created_at)
        sender_key = self.keys[message['sender']]
        inner = Event(**draft['inner_event']).sign(sender_key)
        return giftwrap.wrap(inner, self.public_keys[message['recipient']], sender_key, now=created_at)

    def open(self, wire_event, recipient, delivery_id):
        if recipient not in self.keys or type(delivery_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', delivery_id):
            raise Denied('Unknown fixture recipient or delivery ID')
        if type(wire_event) is not dict:
            raise Denied('Expected a detached A4A wire event')
        if set(wire_event) != {'id', 'pubkey', 'created_at', 'kind', 'tags', 'content', 'sig'}:
            raise Denied('Unexpected outer wire-event fields')
        if len(canonical(wire_event).encode()) > 65536:
            raise Denied('Outer event exceeds fixture size bound')
        outer = Event(**wire_event)
        # Upstream accepts some generic Nostr tag layouts. This fixture's subset
        # is intentionally stricter: exactly one recipient and no ambient authority.
        if outer.tags != [['p', self.public_keys[recipient]]]:
            raise Denied('Outer recipient tags are not the exact expected fixture layout')
        inner = giftwrap.unwrap(outer, self.keys[recipient])
        if inner.kind != 14:
            raise Denied('Expected a private application message')
        expected_tags = [['p', self.public_keys[recipient]], ['d', delivery_id],
                         ['a4a_conversation', context_digest(self.meeting)]]
        if inner.tags != expected_tags:
            raise Denied('Inner recipient, delivery or conversation tags do not match')
        try:
            message = snapshot_envelope(json.loads(inner.content))
        except (ValueError, TypeError) as exc:
            raise Denied('Invalid application content') from exc
        if inner.content != canonical(message):
            raise Denied('Application body is not canonical')
        if (message['recipient'] != recipient or message['context'] != context_digest(self.meeting)
                or self.public_keys.get(message['sender']) != inner.pubkey):
            raise Denied('Cryptographic sender does not match the enrolled fixture identity')
        # Validate routing and payload bounds through the explicit workflow adapter.
        private_message_draft(message, scope=self.meeting, peer_pubkeys=self.public_keys,
                         delivery_id=delivery_id, created_at=inner.created_at)
        return message
