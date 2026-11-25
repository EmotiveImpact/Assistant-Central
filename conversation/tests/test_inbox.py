"""Assistant inbox over real local sessions and the encrypted ledger; fictional identities."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from pilot.auth import LocalOwnerAuth, AuthError
from pilot.crypto import fingerprint
from conversation import ConversationLedger, ConversationDenied
from conversation.inbox import InboxStore, AssistantLease, MAX_LEASE_SECONDS


class InboxCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 2000000000.0
        self.auths, self.keys, self.sessions = {}, {}, {}
        for name in ('alice', 'bob', 'carol'):
            auth = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            auth.bootstrap(name, name + '_assistant', 'Fictional test password')
            self.auths[name] = auth
            self.keys[name] = fingerprint(auth.public_identity())
            self.sessions[name] = auth.login('Fictional test password')
        self.ledger = ConversationLedger(self.root / 'ledger', self.auths['alice'],
                                         {self.keys[n]: a for n, a in self.auths.items()}, clock=lambda: self.now)
        self.ledger.create(*self.actor('alice'), 'thread_1')
        self.join('bob')
        self.inbox = InboxStore(self.root / 'inbox', self.ledger)

    def tearDown(self):
        self.inbox.close()
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.tmp.cleanup()

    def actor(self, name):
        return self.keys[name], self.sessions[name]

    def join(self, name):
        invite = self.ledger.invite(*self.actor('alice'), 'thread_1', self.keys[name])
        return self.ledger.accept_invitation(*self.actor(name), invite['id'])

    def post(self, name, text, request):
        binding = self.ledger.bind_context(*self.actor(name), 'thread_1')
        return self.ledger.append(*self.actor(name), binding, request_id=request, text=text)

    def lease(self, name='bob', assistant='bob_assistant', **kwargs):
        return self.inbox.provision(*self.actor(name), assistant, 'thread_1', **kwargs)

    def ids(self, result):
        return [m['id'] for m in result['messages']]


class InboxDeliveryTests(InboxCase):
    def test_pending_returns_untrusted_messages_in_order_and_ack_advances(self):
        first = self.post('alice', 'Fictional plan, part one', 'r1')
        second = self.post('alice', 'Fictional plan, part two', 'r2')
        lease = self.lease()
        batch = self.inbox.pending(self.sessions['bob'], lease)
        self.assertEqual(self.ids(batch), [first['id'], second['id']])
        self.assertFalse(batch['execution_authority'])
        self.assertEqual(batch['trust'], 'untrusted-messages')
        self.inbox.acknowledge(self.sessions['bob'], lease, first['id'])
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], lease)), [second['id']])
        self.inbox.acknowledge(self.sessions['bob'], lease, second['id'])
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], lease)), [])

    def test_cursor_survives_restart_and_never_moves_backwards(self):
        first = self.post('alice', 'Fictional one', 'r1')
        second = self.post('alice', 'Fictional two', 'r2')
        lease = self.lease()
        self.inbox.pending(self.sessions['bob'], lease)
        self.inbox.acknowledge(self.sessions['bob'], lease, second['id'])
        # Repeating or acknowledging an earlier message is a harmless no-op.
        self.assertEqual(self.inbox.acknowledge(self.sessions['bob'], lease, second['id'])['acknowledged_through'], second['id'])
        self.assertEqual(self.inbox.acknowledge(self.sessions['bob'], lease, first['id'])['acknowledged_through'], second['id'])
        self.inbox.close()
        self.inbox = InboxStore(self.root / 'inbox', self.ledger)
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], lease)), [])
        third = self.post('alice', 'Fictional three', 'r3')
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], lease)), [third['id']])

    def test_cannot_acknowledge_an_undelivered_or_unknown_message(self):
        lease = self.lease()
        message = self.post('alice', 'Fictional unseen', 'r1')
        with self.assertRaises(ConversationDenied):
            self.inbox.acknowledge(self.sessions['bob'], lease, message['id'])
        with self.assertRaises(ConversationDenied):
            self.inbox.acknowledge(self.sessions['bob'], lease, 'not_a_real_event')

    def test_batches_are_bounded_and_page_by_cursor(self):
        posted = [self.post('alice', f'Fictional item {i}', f'r{i}')['id'] for i in range(5)]
        lease = self.lease()
        batch = self.inbox.pending(self.sessions['bob'], lease, limit=2)
        self.assertEqual(self.ids(batch), posted[:2])
        self.assertTrue(batch['more'])
        self.inbox.acknowledge(self.sessions['bob'], lease, posted[1])
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], lease, limit=2)), posted[2:4])
        for bad in (0, 51, '3'):
            with self.assertRaises(ConversationDenied):
                self.inbox.pending(self.sessions['bob'], lease, limit=bad)


class InboxAuthorityTests(InboxCase):
    def test_new_generation_fences_old_lease_but_keeps_position(self):
        first = self.post('alice', 'Fictional one', 'r1')
        old = self.lease()
        self.inbox.pending(self.sessions['bob'], old)
        self.inbox.acknowledge(self.sessions['bob'], old, first['id'])
        second = self.post('alice', 'Fictional two', 'r2')
        new = self.lease()
        self.assertEqual(new.generation, old.generation + 1)
        for call in (lambda: self.inbox.pending(self.sessions['bob'], old),
                     lambda: self.inbox.wake_hint(self.sessions['bob'], old)):
            with self.assertRaises(ConversationDenied):
                call()
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], new)), [second['id']])

    def test_old_generation_cannot_acknowledge_what_new_generation_has_not_seen(self):
        message = self.post('alice', 'Fictional one', 'r1')
        old = self.lease()
        self.inbox.pending(self.sessions['bob'], old)
        new = self.lease()
        with self.assertRaises(ConversationDenied):
            self.inbox.acknowledge(self.sessions['bob'], old, message['id'])
        # The new generation must see it before it can acknowledge it.
        with self.assertRaises(ConversationDenied):
            self.inbox.acknowledge(self.sessions['bob'], new, message['id'])
        self.inbox.pending(self.sessions['bob'], new)
        self.inbox.acknowledge(self.sessions['bob'], new, message['id'])

    def test_lease_expiry_revocation_and_forged_fields_fail_closed(self):
        lease = self.lease(ttl=60)
        for forged in (replace(lease, principal=self.keys['alice']), replace(lease, assistant_id='other'),
                       replace(lease, generation=lease.generation + 1), replace(lease, expires_at=lease.expires_at + 600)):
            with self.assertRaises((ConversationDenied, AuthError)):
                self.inbox.pending(self.sessions['bob'], forged)
        self.now += 61
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], lease)
        fresh = self.lease()
        self.inbox.revoke(self.sessions['bob'], fresh)
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], fresh)

    def test_lease_length_is_bounded(self):
        for ttl in (0, -1, MAX_LEASE_SECONDS + 1, float('inf')):
            with self.assertRaises(ConversationDenied):
                self.lease(ttl=ttl)

    def test_requires_the_owners_own_current_session(self):
        lease = self.lease()
        with self.assertRaises((ConversationDenied, AuthError)):
            self.inbox.pending(self.sessions['alice'], lease)
        self.auths['bob'].logout(self.sessions['bob'])
        with self.assertRaises((ConversationDenied, AuthError)):
            self.inbox.pending(self.sessions['bob'], lease)

    def test_non_member_cannot_provision(self):
        with self.assertRaises(ConversationDenied):
            self.inbox.provision(*self.actor('carol'), 'carol_assistant', 'thread_1')

    def test_removal_blocks_reads_and_rejoin_needs_new_lease_with_future_only_cursor(self):
        before = self.post('alice', 'Fictional before removal', 'r1')
        lease = self.lease()
        self.inbox.pending(self.sessions['bob'], lease)
        self.ledger.remove_member(*self.actor('alice'), 'thread_1', self.keys['bob'])
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], lease)
        self.post('alice', 'Fictional while away', 'r2')
        self.join('bob')
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], lease)  # Old epoch lease.
        after = self.post('alice', 'Fictional after rejoin', 'r3')
        rejoined = self.lease()
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['bob'], rejoined)), [after['id']])
        with self.assertRaises(ConversationDenied):
            self.inbox.acknowledge(self.sessions['bob'], rejoined, before['id'])

    def test_clock_rewind_after_restart_does_not_revive_expired_lease(self):
        lease = self.lease(ttl=30)
        self.now += 31
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], lease)
        self.inbox.close()
        self.inbox = InboxStore(self.root / 'inbox', self.ledger)
        self.now -= 20
        # Either the owner's auth store or the inbox's own persisted fence refuses.
        with self.assertRaises((ConversationDenied, AuthError)):
            self.inbox.pending(self.sessions['bob'], lease)
        persisted = self.inbox.db.execute('SELECT observed FROM inbox_meta').fetchone()[0]
        self.assertGreaterEqual(persisted, self.now + 20)


class WakeHintTests(InboxCase):
    def test_hint_is_body_free_and_changes_only_when_something_arrives(self):
        lease = self.lease()
        empty = self.inbox.wake_hint(self.sessions['bob'], lease)
        self.assertEqual(set(empty), {'pending', 'hint'})
        self.assertFalse(empty['pending'])
        self.assertEqual(self.inbox.wake_hint(self.sessions['bob'], lease), empty)
        message = self.post('alice', 'Fictional secret travel plan', 'r1')
        waiting = self.inbox.wake_hint(self.sessions['bob'], lease)
        self.assertTrue(waiting['pending'])
        self.assertNotEqual(waiting['hint'], empty['hint'])
        text = repr(waiting)
        for leaked in ('secret', 'travel', message['id'], self.keys['alice']):
            self.assertNotIn(leaked, text)
        self.inbox.pending(self.sessions['bob'], lease)
        self.inbox.acknowledge(self.sessions['bob'], lease, message['id'])
        self.assertFalse(self.inbox.wake_hint(self.sessions['bob'], lease)['pending'])

    def test_hint_changes_for_arrivals_beyond_one_page(self):
        for i in range(51):
            self.post('alice', f'Fictional bulk {i}', f'r{i}')
        lease = self.lease()
        before = self.inbox.wake_hint(self.sessions['bob'], lease)
        self.post('alice', 'Fictional late arrival', 'late')
        self.assertNotEqual(self.inbox.wake_hint(self.sessions['bob'], lease)['hint'], before['hint'])

    def test_hint_does_not_reveal_history_hidden_from_a_new_member(self):
        self.post('alice', 'Fictional earlier history', 'r1')
        self.join('carol')
        lease = self.lease('carol', 'carol_assistant')
        self.assertFalse(self.inbox.wake_hint(self.sessions['carol'], lease)['pending'])
        self.assertEqual(self.ids(self.inbox.pending(self.sessions['carol'], lease)), [])


class StoreIntegrityTests(InboxCase):
    def test_store_file_is_private_and_unknown_version_refused(self):
        path = self.root / 'inbox' / 'inbox.sqlite'
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.inbox.db.execute("UPDATE inbox_meta SET version='other'")
        self.inbox.close()
        with self.assertRaises(ConversationDenied):
            InboxStore(self.root / 'inbox', self.ledger)
        self.inbox = InboxStore(self.root / 'inbox_two', self.ledger)

    def test_lease_is_a_plain_host_value_type(self):
        self.assertIsInstance(self.lease(), AssistantLease)
        with self.assertRaises(ConversationDenied):
            self.inbox.pending(self.sessions['bob'], {'principal': self.keys['bob']})


if __name__ == '__main__':
    unittest.main()
