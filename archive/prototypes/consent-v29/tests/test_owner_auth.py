import copy
import os
import secrets
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from demo import fixture
from durable import LocalDelivery
from network import Denied, digest
from owner_auth import DOMAIN, SignedOwnerGateway, decision_bytes, validate_decision
from session import PersistentSession


class OwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'state.sqlite3')
        self.now = [1000]
        self.delivery = LocalDelivery(self.path, clock=lambda: self.now[0])
        self.meeting, self.agents, _ = fixture()
        self.session = PersistentSession(self.delivery, self.agents, self.meeting)
        self.keys = {owner: Ed25519PrivateKey.generate() for owner in self.meeting.participants}
        self.roots = {owner: key.public_key().public_bytes_raw().hex() for owner, key in self.keys.items()}
        self.gateway = SignedOwnerGateway(self.session, self.roots)
        for agent in self.agents:
            for owner, peer in dict.fromkeys(((agent.identity, 'alice'), ('alice', agent.identity))):
                self.pair(owner, peer)
        self.message = self.agents[1].preview_availability(self.meeting)

    def tearDown(self):
        self.delivery.close()
        self.tmp.cleanup()

    def sign(self, owner, action, target, **changes):
        decision = {'version': 1, 'domain': DOMAIN, 'owner': owner, 'action': action,
                    'context': self.session.context, 'nonce': secrets.token_hex(16),
                    'issued_at': self.now[0], 'expires_at': self.now[0] + 300, 'target': target}
        decision.update(changes)
        return {'decision': decision, 'signature': self.keys[owner].sign(decision_bytes(decision)).hex()}

    def pair(self, owner, peer):
        version = self.delivery.contact_version(owner, peer, self.session.context)
        return self.gateway.apply(self.sign(owner, 'pair', {'peer': peer, 'ttl': 3600, 'contact_version': version}))

    def pending_send(self, message=None):
        message = self.message if message is None else message
        return self.sign(message['sender'], 'send', {'recipient': message['recipient'],
            'envelope_digest': digest(message), 'pair_versions': self.gateway.contact_versions(message['sender'], message['recipient'])})

    def cancel(self):
        return self.gateway.apply(self.sign('charlie', 'cancel', {'meeting': self.meeting.id}))

    def test_signed_send_commits_one_processed_receipt(self):
        signed = self.pending_send()
        result = self.gateway.apply(signed, self.message)
        self.assertFalse(result['replayed'])
        self.assertEqual(result['result']['state'], 'processed_locally')
        self.assertEqual(self.delivery.owner_inbox('alice')[0]['state'], 'processed')
        self.assertEqual(len(self.session.view().audit), 1)

    def test_no_private_key_or_signing_function_on_gateway(self):
        self.assertFalse(hasattr(self.gateway, 'sign'))
        self.assertFalse(hasattr(self.gateway, 'keys'))
        self.assertEqual(self.gateway.public_keys, self.roots)

    def test_wrong_owner_signature_is_rejected(self):
        signed = self.pending_send()
        signed['signature'] = self.keys['alice'].sign(decision_bytes(signed['decision'])).hex()
        with self.assertRaises(Denied): self.gateway.apply(signed, self.message)
        self.assertEqual(self.delivery.owner_inbox('alice'), [])

    def test_unsigned_changed_or_extra_signature_fields_are_rejected(self):
        signed = self.pending_send()
        for mutation in ({'signature': '0' * 128}, {'signature': ''}, {'approved': True}, {'private_key': 'not-a-key'}):
            with self.subTest(mutation=mutation), self.assertRaises(Denied):
                self.gateway.apply({**signed, **mutation}, self.message)

    def test_body_and_recipient_substitution_are_rejected(self):
        signed = self.pending_send()
        for patch in ({'recipient': 'dana'}, {'payload': {'candidate_indices': [0]}}, {'sender': 'alice'}):
            with self.subTest(patch=patch), self.assertRaises(Denied):
                self.gateway.apply(signed, {**self.message, **patch})

    def test_expired_and_future_decisions_are_rejected(self):
        for issued, expires in ((600, 900), (1001, 1200)):
            with self.subTest(issued=issued), self.assertRaises(Denied):
                signed = self.pending_send()
                d = signed['decision']; d.update(issued_at=issued, expires_at=expires)
                signed['signature'] = self.keys['bob'].sign(decision_bytes(d)).hex()
                self.gateway.apply(signed, self.message)

    def test_committed_retry_after_expiry_and_cancel_is_read_only(self):
        signed = self.pending_send()
        original = self.gateway.apply(signed, self.message)['result']
        self.cancel()
        self.now[0] = 5000
        retry = self.gateway.apply(signed, self.message)
        self.assertTrue(retry['replayed'])
        self.assertEqual(retry['result'], original)
        self.assertEqual(len(self.session.view().audit), 1)

    def test_pending_send_fails_after_cancel(self):
        signed = self.pending_send()
        self.cancel()
        with self.assertRaises(Denied): self.gateway.apply(signed, self.message)
        self.assertEqual(self.delivery.owner_inbox('alice'), [])

    def test_revoke_then_repair_cannot_revive_unseen_signed_send(self):
        signed = self.pending_send()
        version = self.delivery.contact_version('alice', 'bob', self.session.context)
        self.gateway.apply(self.sign('alice', 'revoke', {'peer': 'bob', 'contact_version': version}))
        self.pair('alice', 'bob')
        with self.assertRaises(Denied): self.gateway.apply(signed, self.message)
        self.gateway.apply(self.pending_send(), self.message)
        self.assertEqual(len(self.session.view().audit), 1)

    def test_pending_pair_cannot_reverse_later_revocation(self):
        version = self.delivery.contact_version('alice', 'bob', self.session.context)
        pending = self.sign('alice', 'pair', {'peer': 'bob', 'ttl': 3600, 'contact_version': version})
        self.gateway.apply(self.sign('alice', 'revoke', {'peer': 'bob', 'contact_version': version}))
        with self.assertRaises(Denied): self.gateway.apply(pending)
        with self.assertRaises(Denied): self.delivery._paired('alice', 'bob', self.session.context)

    def test_pairing_replay_does_not_renew_expiry(self):
        version = self.delivery.contact_version('alice', 'bob', self.session.context)
        signed = self.sign('alice', 'pair', {'peer': 'bob', 'ttl': 3600, 'contact_version': version})
        self.gateway.apply(signed)
        expiry = self.delivery.db.execute("SELECT expires FROM contacts WHERE owner='alice' AND peer='bob'").fetchone()[0]
        self.now[0] += 100
        self.assertTrue(self.gateway.apply(signed)['replayed'])
        self.assertEqual(self.delivery.db.execute("SELECT expires FROM contacts WHERE owner='alice' AND peer='bob'").fetchone()[0], expiry)

    def test_nonce_cannot_be_reused_for_other_action(self):
        signed = self.pending_send(); self.gateway.apply(signed, self.message)
        cancel = self.sign('bob', 'cancel', {'meeting': self.meeting.id}, nonce=signed['decision']['nonce'])
        with self.assertRaises(Denied): self.gateway.apply(cancel)
        self.assertIsNone(self.session.view().cancellation)

    def test_signer_root_replacement_is_forbidden(self):
        other = dict(self.roots)
        other['bob'] = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        with self.assertRaises(Denied): SignedOwnerGateway(self.session, other)
        self.assertEqual(SignedOwnerGateway(self.session, self.roots).public_keys, self.roots)

    def test_duplicate_or_partial_roots_are_rejected(self):
        for roots in ({'alice': self.roots['alice']}, {owner: self.roots['alice'] for owner in self.roots}):
            with self.subTest(roots=roots), self.assertRaises(Denied): SignedOwnerGateway(self.session, roots)

    def test_roots_are_detached_from_bootstrap_object(self):
        self.roots['bob'] = '0' * 64
        self.assertNotEqual(self.gateway.public_keys['bob'], self.roots['bob'])
        self.gateway.apply(self.pending_send(), self.message)

    def test_decision_log_failure_rolls_back_send_and_consent(self):
        signed = self.pending_send()
        self.delivery.db.execute("CREATE TRIGGER fail_decision BEFORE INSERT ON owner_decisions BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.gateway.apply(signed, self.message)
        self.assertEqual(self.delivery.owner_inbox('alice'), [])
        self.assertEqual(self.delivery.db.execute('SELECT COUNT(*) FROM approvals').fetchone()[0], 0)
        self.assertEqual(len(self.session.view().audit), 0)
        self.delivery.db.execute('DROP TRIGGER fail_decision')
        self.gateway.apply(signed, self.message)

    def test_cancellation_log_failure_rolls_back_cancel(self):
        self.delivery.db.execute("CREATE TRIGGER fail_decision BEFORE INSERT ON owner_decisions BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.cancel()
        self.assertIsNone(self.session.view().cancellation)

    def test_wrong_context_action_and_time_fields_fail_closed(self):
        original = self.pending_send()['decision']
        mutations = ({'context': '0' * 64}, {'domain': 'another-domain'}, {'version': True},
                     {'issued_at': True}, {'expires_at': 2000}, {'nonce': 'a'},
                     {'action': 'sign'}, {'target': {'recipient': 'alice'}}, {'extra': 'unsafe'})
        for patch in mutations:
            d = {**copy.deepcopy(original), **patch}
            signed = {'decision': d, 'signature': self.keys['bob'].sign(decision_bytes(d)).hex()}
            with self.subTest(patch=patch), self.assertRaises(Denied): self.gateway.apply(signed, self.message)

    def test_non_send_decision_cannot_smuggle_message(self):
        signed = self.sign('bob', 'cancel', {'meeting': self.meeting.id})
        with self.assertRaises(Denied): self.gateway.apply(signed, self.message)

    def test_record_limit_rejects_new_decision_but_allows_read_only_retry(self):
        signed = self.pending_send(); self.gateway.apply(signed, self.message)
        self.delivery.max_records = 1
        self.assertTrue(self.gateway.apply(signed, self.message)['replayed'])
        with self.assertRaises(Denied): self.cancel()

    def test_restart_preserves_replay_and_roots(self):
        signed = self.pending_send(); self.gateway.apply(signed, self.message)
        self.delivery.close()
        self.delivery = LocalDelivery(self.path, clock=lambda: self.now[0])
        self.session = PersistentSession(self.delivery, self.agents, self.meeting)
        self.gateway = SignedOwnerGateway(self.session, self.roots)
        self.assertTrue(self.gateway.apply(signed, self.message)['replayed'])
        self.assertEqual(len(self.session.view().audit), 1)

    def test_concurrent_signed_retry_has_one_effect(self):
        signed = self.pending_send()
        def submit(_):
            store = LocalDelivery(self.path, clock=lambda: self.now[0])
            try:
                meeting, agents, _ = fixture()
                gateway = SignedOwnerGateway(PersistentSession(store, agents, meeting), self.roots)
                return gateway.apply(signed, self.message)
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(8)))
        self.assertEqual(sum(not result['replayed'] for result in results), 1)
        self.assertEqual(len(self.session.view().audit), 1)

    def test_full_signed_meeting_flow(self):
        for agent in self.agents:
            message = agent.preview_availability(self.meeting)
            self.gateway.apply(self.pending_send(message), message)
        for agent in self.agents:
            proposal = self.session.view().preview_proposal(self.agents[0], agent.identity)
            self.gateway.apply(self.pending_send(proposal), proposal)
            acceptance = self.session.view().preview_acceptance(agent)
            self.gateway.apply(self.pending_send(acceptance), acceptance)
        self.assertTrue(self.session.view().agreed)
        self.assertEqual(len(self.session.view().audit), 12)

    def test_malformed_decisions_are_bounded(self):
        for decision in (None, [], {'oversize': 'x' * 5000}, {'number': float('nan')}):
            with self.subTest(decision=type(decision)), self.assertRaises(Denied): validate_decision(decision)
