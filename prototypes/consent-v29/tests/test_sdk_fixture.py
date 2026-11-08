import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from demo import fixture
from network import Denied, canonical
from sdk_transport_fixture import PinnedSdkFixture
from vendor.a4a_sdk.event import Event
from vendor.a4a_sdk.keys import Keys
from vendor.a4a_sdk import giftwrap, nip44

ROOT = Path(__file__).resolve().parent.parent


class PinnedSdkTests(unittest.TestCase):
    def setUp(self):
        self.meeting, self.agents, _ = fixture()
        self.transport = PinnedSdkFixture(self.meeting)
        self.message = self.agents[1].preview_availability(self.meeting)
        self.delivery_id = 'offline-fixture-delivery'
        self.now = 1794000000

    def wire(self):
        return self.transport.seal(self.message, self.delivery_id, self.now).model_dump()

    def custom_wire(self, *, sender='bob', message=None, tags=None, kind=14, inner_signer=None):
        message = self.message if message is None else message
        recipient = 'alice'
        signer = self.transport.keys[sender]
        inner = Event(kind=kind, tags=tags if tags is not None else [
            ['p', self.transport.public_keys[recipient]], ['d', self.delivery_id],
            ['a4a_conversation', message['context']]], content=canonical(message), created_at=self.now)
        inner.sign(inner_signer or signer)
        return giftwrap.wrap(inner, self.transport.public_keys[recipient], signer, now=self.now).model_dump()

    def test_real_sdk_encrypted_round_trip_preserves_exact_message(self):
        wire = self.wire()
        self.assertEqual(wire['kind'], 1059)
        self.assertNotEqual(wire['pubkey'], self.transport.public_keys['bob'])
        self.assertNotIn(canonical(self.message), wire['content'])
        self.assertEqual(self.transport.open(wire, 'alice', self.delivery_id), self.message)

    def test_each_wrap_uses_distinct_ephemeral_key_and_ciphertext(self):
        a, b = self.wire(), self.wire()
        self.assertNotEqual(a['pubkey'], b['pubkey'])
        self.assertNotEqual(a['content'], b['content'])
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(self.transport.open(a, 'alice', self.delivery_id), self.transport.open(b, 'alice', self.delivery_id))

    def test_wrong_recipient_and_delivery_are_rejected(self):
        for recipient, delivery in (('dana', self.delivery_id), ('alice', 'wrong-delivery'), ('outsider', self.delivery_id)):
            with self.subTest(recipient=recipient), self.assertRaises((Denied, giftwrap.GiftWrapError)):
                self.transport.open(self.wire(), recipient, delivery)

    def test_outer_ciphertext_signature_and_identity_tampering_are_rejected(self):
        for field, value in (('content', 'A' * 200), ('sig', '0' * 128), ('pubkey', self.transport.public_keys['dana'])):
            wire = self.wire(); wire[field] = value
            with self.subTest(field=field), self.assertRaises((Denied, giftwrap.GiftWrapError)):
                self.transport.open(wire, 'alice', self.delivery_id)

    def test_valid_signature_does_not_authorize_impersonation(self):
        wire = self.custom_wire(sender='dana')  # Body still falsely claims Bob.
        with self.assertRaises(Denied): self.transport.open(wire, 'alice', self.delivery_id)

    def test_seal_inner_signer_substitution_is_rejected_by_upstream(self):
        wire = self.custom_wire(inner_signer=self.transport.keys['dana'])
        with self.assertRaises(giftwrap.GiftWrapError): self.transport.open(wire, 'alice', self.delivery_id)

    def test_unknown_kind_and_duplicate_or_wrong_context_tags_are_rejected(self):
        tags = [['p', self.transport.public_keys['alice']], ['d', self.delivery_id],
                ['a4a_conversation', self.message['context']]]
        wires = [self.custom_wire(kind=1), self.custom_wire(tags=tags + [tags[0]]),
                 self.custom_wire(tags=tags[:2] + [['a4a_conversation', '0' * 64]])]
        for wire in wires:
            with self.subTest(tags=wire['id']), self.assertRaises(Denied):
                self.transport.open(wire, 'alice', self.delivery_id)

    def test_private_fields_and_unsupported_actions_do_not_pass_encryption_boundary(self):
        private = copy.deepcopy(self.message); private['payload']['private_calendar'] = 'secret'
        cancel = copy.deepcopy(self.message); cancel.update(type='cancel', payload={})
        for message in (private, cancel):
            with self.subTest(message=message['type']), self.assertRaises(Denied):
                self.transport.open(self.custom_wire(message=message), 'alice', self.delivery_id)

    def test_unknown_outer_fields_and_oversize_are_rejected(self):
        wire = self.wire()
        for patch in ({'extra': 'authority'}, {'content': 'x' * 70000}):
            with self.subTest(patch=list(patch)), self.assertRaises(Denied):
                self.transport.open({**wire, **patch}, 'alice', self.delivery_id)

    def test_unsigned_inner_event_is_rejected(self):
        signer = self.transport.keys['bob']
        inner = Event(kind=14, content=canonical(self.message), created_at=self.now)
        wire = giftwrap.wrap(inner, self.transport.public_keys['alice'], signer, now=self.now).model_dump()
        with self.assertRaises(giftwrap.GiftWrapError): self.transport.open(wire, 'alice', self.delivery_id)

    def test_nip44_mac_rejects_changed_payload(self):
        sender, recipient = self.transport.keys['bob'], self.transport.keys['alice']
        ciphertext = nip44.encrypt('fictional availability', sender.privkey_hex, recipient.pubkey_hex)
        altered = ('A' if ciphertext[5] != 'A' else 'B')
        ciphertext = ciphertext[:5] + altered + ciphertext[6:]
        with self.assertRaises(nip44.Nip44Error): nip44.decrypt(ciphertext, recipient.privkey_hex, sender.pubkey_hex)

    def test_offline_fixture_runs_with_socket_guard_installed(self):
        result = subprocess.run([sys.executable, 'sdk_fixture_check.py'], cwd=ROOT, capture_output=True,
                                text=True, timeout=10, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['socket_operations'], 'denied')
        self.assertEqual(report['pinned_sdk_encrypted_round_trip'], 'passed')
        self.assertFalse(report['private_keys_saved_or_exported'])

    def test_network_guard_actually_blocks_socket_creation(self):
        command = "from offline_guard import install; install(); import socket; socket.socket()"
        result = subprocess.run([sys.executable, '-c', command], cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Offline fixture forbids', result.stderr)

    def test_network_guard_blocks_child_processes(self):
        command = "from offline_guard import install; install(); import subprocess; subprocess.run(['true'])"
        result = subprocess.run([sys.executable, '-c', command], cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Offline fixture forbids', result.stderr)
