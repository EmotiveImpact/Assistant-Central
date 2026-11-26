import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from demo import fixture
from durable import LocalDelivery
from network import Denied, Meeting, context_digest
from session import PersistentSession


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'state.sqlite3')
        self.delivery = LocalDelivery(self.path)
        self.meeting, self.agents, _ = fixture()
        self.session = PersistentSession(self.delivery, self.agents, self.meeting)
        self.context = context_digest(self.meeting)
        for agent in self.agents:
            self.delivery.owner_pair('alice', agent.identity, self.context)
            self.delivery.owner_pair(agent.identity, 'alice', self.context)
        self.message = self.agents[1].preview_availability(self.meeting)
        self.approval = self.delivery.owner_approve(self.message)

    def tearDown(self):
        self.delivery.close()
        self.tmp.cleanup()

    def test_cancellation_invalidates_unused_approvals_and_survives_restart(self):
        self.session.owner_cancel(self.agents[2])
        self.assertEqual(self.delivery.db.execute('SELECT COUNT(*) FROM approvals').fetchone()[0], 0)
        self.delivery.close()
        self.delivery = LocalDelivery(self.path)
        meeting, agents, _ = fixture()
        session = PersistentSession(self.delivery, agents, meeting)
        self.assertEqual(session.view().cancellation['owner'], 'charlie')
        self.assertFalse(session.view().agreed)
        with self.assertRaises(Denied):
            session.submit(agents[1], self.message, self.approval)
        self.assertEqual(self.delivery.owner_inbox('alice'), [])

    def test_new_pairings_approvals_deliveries_and_previews_fail_closed(self):
        self.session.owner_cancel(self.agents[1])
        operations = (
            lambda: self.delivery.owner_pair('alice', 'bob', self.context),
            lambda: self.delivery.owner_approve(self.message),
            lambda: self.delivery.deliver(self.message, self.approval),
            lambda: self.session.view().propose(self.agents[0]),
            lambda: self.session.view().preview_proposal(self.agents[0], 'bob'),
            lambda: self.session.view().preview_acceptance(self.agents[1]),
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(Denied):
                operation()

    def test_committed_retry_is_read_only_after_cancellation(self):
        self.session.submit(self.agents[1], self.message, self.approval)
        self.session.owner_cancel(self.agents[1])
        self.assertEqual(self.session.submit(self.agents[1], self.message, self.approval), self.approval)
        self.assertEqual(len(self.session.view().audit), 1)
        self.assertEqual(len(self.delivery.owner_inbox('alice')), 1)

    def test_repeated_cancellation_preserves_original_owner_and_timestamp(self):
        result = self.session.owner_cancel(self.agents[2])
        self.assertEqual(self.session.owner_cancel(self.agents[3]), result)
        self.assertEqual(self.delivery.db.execute('SELECT COUNT(*) FROM cancellations').fetchone()[0], 1)

    def test_foreign_owner_object_is_not_local_authority(self):
        _, foreign_agents, _ = fixture()
        for owner in (foreign_agents[0], 'alice', None):
            with self.subTest(owner=owner), self.assertRaises(Denied):
                self.session.owner_cancel(owner)
        self.assertIsNone(self.session.view().cancellation)

    def test_cancellation_cannot_arrive_as_an_agent_message(self):
        self.message['type'] = 'cancel'
        self.message['payload'] = {}
        with self.assertRaises(Denied):
            self.delivery.owner_approve(self.message)
        with self.assertRaises(Denied):
            self.session.submit(self.agents[1], self.message, self.approval)
        self.assertIsNone(self.session.view().cancellation)

    def test_failure_rolls_back_cancellation_and_approval_invalidation(self):
        self.delivery.db.execute("CREATE TRIGGER fail_cancel BEFORE DELETE ON approvals BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.session.owner_cancel(self.agents[1])
        self.assertIsNone(self.session.view().cancellation)
        self.assertEqual(self.delivery.db.execute('SELECT COUNT(*) FROM approvals').fetchone()[0], 1)
        self.delivery.db.execute('DROP TRIGGER fail_cancel')
        self.session.submit(self.agents[1], self.message, self.approval)

    def test_cancellation_is_bound_to_exact_context(self):
        other = Meeting('other-meeting', 'alice', self.meeting.participants, self.meeting.candidates)
        other_session = PersistentSession(self.delivery, self.agents, other)
        other_context = context_digest(other)
        self.delivery.owner_pair('alice', 'bob', other_context)
        self.delivery.owner_pair('bob', 'alice', other_context)
        other_message = self.agents[1].preview_availability(other)
        other_approval = self.delivery.owner_approve(other_message)
        self.session.owner_cancel(self.agents[1])
        other_session.submit(self.agents[1], other_message, other_approval)
        self.assertIsNone(other_session.view().cancellation)
        self.assertEqual(len(other_session.view().audit), 1)

    def test_cancellation_overrides_prior_agreement_without_erasing_history(self):
        for agent in self.agents:
            message = agent.preview_availability(self.meeting)
            self.session.submit(agent, message, self.delivery.owner_approve(message))
        for agent in self.agents:
            proposal = self.session.view().preview_proposal(self.agents[0], agent.identity)
            self.session.submit(self.agents[0], proposal, self.delivery.owner_approve(proposal))
            acceptance = self.session.view().preview_acceptance(agent)
            self.session.submit(agent, acceptance, self.delivery.owner_approve(acceptance))
        self.assertTrue(self.session.view().agreed)
        self.session.owner_cancel(self.agents[3])
        self.assertFalse(self.session.view().agreed)
        self.assertEqual(len(self.session.view().audit), 12)
        self.assertEqual(len(self.session.view()._acceptances), 4)

    def test_concurrent_send_and_cancel_have_one_serialized_outcome(self):
        barrier = Barrier(2)
        def work(cancel):
            store = LocalDelivery(self.path)
            try:
                meeting, agents, _ = fixture()
                session = PersistentSession(store, agents, meeting)
                barrier.wait(timeout=5)
                if cancel:
                    session.owner_cancel(agents[2])
                    return 'cancelled'
                try:
                    session.submit(agents[1], self.message, self.approval)
                    return 'sent-before-cancel'
                except Denied:
                    return 'cancelled-before-send'
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(work, (False, True)))
        self.assertIn('cancelled', outcomes)
        sent = 'sent-before-cancel' in outcomes
        self.assertEqual(len(self.session.view().audit), int(sent))
        self.assertEqual(len(self.delivery.owner_inbox('alice')), int(sent))
        self.assertEqual(self.session.view().cancellation['owner'], 'charlie')
        self.assertEqual(self.delivery.db.execute('SELECT COUNT(*) FROM approvals WHERE used=0').fetchone()[0], 0)

    def test_cancel_record_limit_fails_closed(self):
        self.delivery.max_records = 1
        self.delivery.db.execute('INSERT INTO cancellations VALUES (?,?,?)', ('0' * 64, 'alice', 0))
        with self.assertRaises(Denied):
            self.session.owner_cancel(self.agents[1])
        self.assertIsNone(self.session.view().cancellation)


if __name__ == '__main__':
    unittest.main()
