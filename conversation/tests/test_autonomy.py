"""Autonomy dial, private guidance and exact draft review; fictional identities."""
import sqlite3
import unittest
from contextlib import closing

from pilot.auth import AuthError
from conversation import ConversationDenied
from conversation.autonomy import OwnerDesk, DeskAccess, MAX_POLICY_SECONDS
from conversation.tests.test_inbox import InboxCase

REFUSED = (AuthError, ConversationDenied)


class DeskCase(InboxCase):
    def setUp(self):
        super().setUp()
        self.desk = OwnerDesk(self.root / 'desk_bob', self.ledger, self.inbox, self.keys['bob'])
        self.bob_lease = self.lease()

    def tearDown(self):
        self.desk.close()
        super().tearDown()

    def propose(self, request, text='Fictional reply', lease=None):
        return self.desk.propose(self.sessions['bob'], lease or self.bob_lease, request_id=request, text=text)

    def set_policy(self, mode, **kwargs):
        return self.desk.set_policy(self.sessions['bob'], 'bob_assistant', 'thread_1', mode=mode, **kwargs)

    def raw(self, table):
        with closing(sqlite3.connect(self.root / 'desk_bob' / 'desk.sqlite')) as db:
            return db.execute(f'SELECT body FROM {table}').fetchall()

    def alice_history(self):
        binding = self.ledger.bind_context(*self.actor('alice'), 'thread_1')
        return self.ledger.history(*self.actor('alice'), binding)


class DefaultReviewTests(DeskCase):
    def test_default_is_review_each_and_nothing_is_sent(self):
        self.assertEqual(self.desk.policy(self.sessions['bob'], 'bob_assistant', 'thread_1'),
                         {'mode': 'review_each', 'standing': False})
        result = self.propose('p1')
        self.assertEqual(result['state'], 'awaiting_owner')
        self.assertIsNone(result['message_id'])
        self.assertEqual(self.alice_history(), [])

    def test_owner_approves_exact_text_which_is_sent_as_owner_message(self):
        self.propose('p1', 'Fictional proposal: Tuesday works')
        [draft] = self.desk.drafts(self.sessions['bob'])
        self.assertEqual(draft['text'], 'Fictional proposal: Tuesday works')
        self.assertEqual(draft['trust'], 'assistant-written')
        with self.assertRaises(ConversationDenied):
            self.desk.approve(self.sessions['bob'], draft['draft_id'], 'f' * 64)
        result = self.desk.approve(self.sessions['bob'], draft['draft_id'], draft['digest'])
        self.assertEqual(result['state'], 'sent')
        self.assertFalse(result['sent_without_review'])
        [event] = self.alice_history()
        self.assertEqual((event['kind'], event['text']), ('message', 'Fictional proposal: Tuesday works'))
        self.assertEqual(self.desk.drafts(self.sessions['bob']), [])
        # Approval is single use.
        with self.assertRaises(ConversationDenied):
            self.desk.approve(self.sessions['bob'], draft['draft_id'], draft['digest'])
        status = self.desk.status_for(self.sessions['bob'], self.bob_lease, 'p1')
        self.assertEqual((status['state'], status['message_id']), ('sent', event['id']))

    def test_decline_sends_nothing(self):
        self.propose('p1')
        [draft] = self.desk.drafts(self.sessions['bob'])
        self.desk.decline(self.sessions['bob'], draft['draft_id'])
        self.assertEqual(self.desk.status_for(self.sessions['bob'], self.bob_lease, 'p1')['state'], 'declined')
        with self.assertRaises(ConversationDenied):
            self.desk.approve(self.sessions['bob'], draft['draft_id'], draft['digest'])
        self.assertEqual(self.alice_history(), [])

    def test_propose_is_idempotent_and_refuses_changed_text(self):
        first = self.propose('p1', 'Fictional A')
        self.assertEqual(self.propose('p1', 'Fictional A'), first)
        with self.assertRaises(ConversationDenied):
            self.propose('p1', 'Fictional B')
        self.assertEqual(len(self.desk.drafts(self.sessions['bob'])), 1)


class StandingPolicyTests(DeskCase):
    def test_within_limits_sends_as_assistant_kind_until_cap(self):
        view = self.set_policy('within_limits', max_auto=2)
        self.assertTrue(view['standing'])
        sent = [self.propose(f'p{i}', f'Fictional {i}') for i in range(3)]
        self.assertEqual([s['state'] for s in sent], ['sent', 'sent', 'awaiting_owner'])
        self.assertTrue(sent[0]['sent_without_review'])
        events = self.alice_history()
        self.assertEqual([e['kind'] for e in events], ['assistant', 'assistant'])
        self.assertEqual(events[0]['author'], self.keys['bob'])
        self.assertEqual(self.desk.policy(self.sessions['bob'], 'bob_assistant', 'thread_1')['auto_used'], 2)
        # Retrying a sent request does not spend more allowance or send twice.
        self.assertEqual(self.propose('p0', 'Fictional 0')['message_id'], sent[0]['message_id'])
        self.assertEqual(len(self.alice_history()), 2)

    def test_check_in_pauses_after_every_and_owner_approval_resets_the_run(self):
        self.set_policy('check_in', every=2, max_auto=10)
        states = [self.propose(f'p{i}')['state'] for i in range(3)]
        self.assertEqual(states, ['sent', 'sent', 'awaiting_owner'])
        [draft] = self.desk.drafts(self.sessions['bob'])
        self.desk.approve(self.sessions['bob'], draft['draft_id'], draft['digest'])
        self.assertEqual(self.propose('p3')['state'], 'sent')
        self.assertEqual([e['kind'] for e in self.alice_history()], ['assistant', 'assistant', 'message', 'assistant'])

    def test_oversized_message_waits_for_review(self):
        self.set_policy('within_limits', max_bytes=10)
        self.assertEqual(self.propose('p1', 'x' * 11)['state'], 'awaiting_owner')
        self.assertEqual(self.propose('p2', 'x' * 10)['state'], 'sent')

    def test_policy_expires_back_to_review(self):
        self.set_policy('within_limits', ttl=60)
        self.now += 61
        self.assertEqual(self.desk.policy(self.sessions['bob'], 'bob_assistant', 'thread_1')['mode'], 'review_each')
        self.assertEqual(self.propose('p1')['state'], 'awaiting_owner')

    def test_clear_policy_restores_default(self):
        self.set_policy('within_limits')
        self.desk.clear_policy(self.sessions['bob'], 'bob_assistant', 'thread_1')
        self.assertEqual(self.propose('p1')['state'], 'awaiting_owner')

    def test_policy_bounds(self):
        for kwargs in ({'mode': 'anything'}, {'mode': 'check_in', 'every': 0}, {'mode': 'within_limits', 'max_auto': 201},
                       {'mode': 'within_limits', 'max_bytes': 16385}, {'mode': 'within_limits', 'ttl': MAX_POLICY_SECONDS + 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConversationDenied):
                self.desk.set_policy(self.sessions['bob'], 'bob_assistant', 'thread_1', **kwargs)

    def test_policy_is_per_assistant(self):
        self.set_policy('within_limits')
        other = self.lease(assistant='bob_other_assistant')
        self.assertEqual(self.propose('p1', lease=other)['state'], 'awaiting_owner')

    def test_refused_send_returns_allowance(self):
        self.set_policy('within_limits', max_auto=1)
        # Simulate a definite ledger refusal (for example, Bob was removed).
        original = self.ledger.append
        def refuse(*args, **kwargs):
            raise ConversationDenied('fictional refusal')
        self.ledger.append = refuse
        try:
            self.assertEqual(self.propose('p1')['state'], 'failed')
        finally:
            self.ledger.append = original
        self.assertEqual(self.desk.policy(self.sessions['bob'], 'bob_assistant', 'thread_1')['auto_used'], 0)
        self.assertEqual(self.propose('p2')['state'], 'sent')


class GuardTests(DeskCase):
    def test_other_owner_cannot_use_desk(self):
        with self.assertRaises(REFUSED):
            self.desk.drafts(self.sessions['carol'])
        with self.assertRaises(REFUSED):
            self.desk.set_policy(self.sessions['alice'], 'bob_assistant', 'thread_1', mode='within_limits')

    def test_lease_from_another_owner_is_refused(self):
        alice_lease = self.lease('alice', 'alice_assistant')
        with self.assertRaises(REFUSED):
            self.desk.propose(self.sessions['alice'], alice_lease, request_id='p1', text='Fictional')

    def test_revoked_or_expired_lease_is_refused(self):
        short = self.lease(assistant='bob_short', ttl=30)
        self.now += 31
        with self.assertRaises(REFUSED):
            self.propose('p1', lease=short)
        self.inbox.revoke(self.sessions['bob'], self.bob_lease)
        with self.assertRaises(REFUSED):
            self.propose('p2')

    def test_owner_must_be_a_member_to_set_policy(self):
        self.ledger.create(*self.actor('alice'), 'thread_2')
        with self.assertRaises(ConversationDenied):
            self.desk.set_policy(self.sessions['bob'], 'bob_assistant', 'thread_2', mode='within_limits')


class GuidanceTests(DeskCase):
    def test_guidance_is_private_scoped_and_encrypted(self):
        note = self.desk.add_guidance(self.sessions['bob'], 'bob_assistant', 'thread_1', 'Fictional: keep it brief')
        self.desk.add_guidance(self.sessions['bob'], 'bob_other_assistant', 'thread_1', 'Fictional: other')
        view = self.desk.guidance_for(self.sessions['bob'], self.bob_lease)
        self.assertEqual([n['text'] for n in view['notes']], ['Fictional: keep it brief'])
        self.assertEqual(view['audience'], 'this-assistant-only')
        # Not in the conversation.
        self.assertEqual(self.alice_history(), [])
        # Not readable at rest.
        raw = self.raw('desk_guidance')
        self.assertTrue(raw and all('keep it brief' not in row[0] for row in raw))
        self.desk.remove_guidance(self.sessions['bob'], note['id'])
        self.assertEqual(self.desk.guidance_for(self.sessions['bob'], self.bob_lease)['notes'], [])

    def test_drafts_are_encrypted_at_rest(self):
        self.propose('p1', 'Fictional secret draft')
        raw = self.raw('desk_drafts')
        self.assertTrue(raw and all('secret draft' not in row[0] for row in raw))

    def test_guidance_limits(self):
        with self.assertRaises(ConversationDenied):
            self.desk.add_guidance(self.sessions['bob'], 'bob_assistant', 'thread_1', 'x' * 4097)

    def test_desk_access_handle(self):
        self.desk.add_guidance(self.sessions['bob'], 'bob_assistant', 'thread_1', 'Fictional note')
        access = DeskAccess(self.desk, self.bob_lease, lambda: self.sessions['bob'])
        self.assertEqual(access.guidance()['notes'][0]['text'], 'Fictional note')
        self.assertEqual(access.propose('p1', 'Fictional')['state'], 'awaiting_owner')
        self.assertEqual(access.status('p1')['state'], 'awaiting_owner')

    def test_desk_survives_restart(self):
        self.set_policy('within_limits', max_auto=1)
        self.propose('p1')
        self.desk.close()
        self.desk = OwnerDesk(self.root / 'desk_bob', self.ledger, self.inbox, self.keys['bob'])
        self.assertEqual(self.propose('p2')['state'], 'awaiting_owner')
        self.assertEqual(self.desk.status_for(self.sessions['bob'], self.bob_lease, 'p1')['state'], 'sent')


if __name__ == '__main__':
    unittest.main()
