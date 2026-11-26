import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from demo import fixture, slot
from durable import LocalDelivery
from network import Denied, Meeting, context_digest
from session import PersistentSession


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "state.sqlite3")
        self.delivery = LocalDelivery(self.path)
        self.meeting, self.agents, _ = fixture()
        self.session = PersistentSession(self.delivery, self.agents, self.meeting)
        self.context = context_digest(self.meeting)
        for agent in self.agents:
            self.delivery.owner_pair("alice", agent.identity, self.context)
            self.delivery.owner_pair(agent.identity, "alice", self.context)

    def tearDown(self):
        self.delivery.close()
        self.tmp.cleanup()

    def send(self, agent, message):
        approval = self.delivery.owner_approve(message)
        self.session.submit(agent, message, approval)
        return approval

    def restart(self):
        self.delivery.close()
        self.delivery = LocalDelivery(self.path)
        # New object identities model a fresh application process.
        _, self.agents, _ = fixture()
        self.session = PersistentSession(self.delivery, self.agents, self.meeting)

    def test_restart_after_every_transition(self):
        for i in range(4):
            agent = self.agents[i]
            self.send(agent, agent.preview_availability(self.meeting))
            self.restart()
        self.assertEqual(self.session.view().propose(self.agents[0]), slot("15:00", "15:30"))
        for i in range(4):
            self.send(self.agents[0], self.session.view().preview_proposal(self.agents[0], self.agents[i].identity))
            self.restart()
            self.send(self.agents[i], self.session.view().preview_acceptance(self.agents[i]))
            self.restart()
            self.assertEqual(self.session.view().agreed, i == 3)
        self.assertEqual(len(self.session.view().audit), 12)

    def test_failure_rolls_back_receipt_approval_and_transition(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.delivery.owner_approve(message)
        self.delivery.db.execute("CREATE TRIGGER force_failure BEFORE INSERT ON transitions BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.session.submit(self.agents[1], message, approval)
        self.assertEqual(self.delivery.db.execute("SELECT used FROM approvals WHERE id=?", (approval,)).fetchone()[0], 0)
        self.assertEqual(self.delivery.owner_inbox("alice"), [])
        self.assertEqual(self.session.view().audit, [])
        self.delivery.db.execute("DROP TRIGGER force_failure")
        self.session.submit(self.agents[1], message, approval)
        self.assertEqual(len(self.session.view().audit), 1)

    def test_concurrent_duplicate_submit_across_connections(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.delivery.owner_approve(message)
        def submit(_):
            store = LocalDelivery(self.path)
            try:
                meeting, agents, _ = fixture()
                session = PersistentSession(store, agents, meeting)
                return session.submit(agents[1], message, approval)
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(set(pool.map(submit, range(8))), {approval})
        self.assertEqual(len(self.session.view().audit), 1)
        self.assertEqual(len(self.delivery.owner_inbox("alice")), 1)

    def test_altered_context_does_not_resume_existing_session(self):
        altered = Meeting(self.meeting.id, "alice", self.meeting.participants, (slot("23:00", "23:30"),))
        with self.assertRaises(Denied):
            PersistentSession(self.delivery, self.agents, altered)

    def test_raw_payload_does_not_enter_inbox(self):
        message = self.agents[1].preview_availability(self.meeting)
        message["payload"]["private_projects"] = ["secret"]
        with self.assertRaises(Denied):
            self.delivery.owner_approve(message)
        self.assertEqual(self.delivery.owner_inbox("alice"), [])

    def test_impersonation_denied(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.delivery.owner_approve(message)
        with self.assertRaises(Denied):
            self.session.submit(self.agents[0], message, approval)

    def test_repairing_does_not_restore_revoked_approval(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.delivery.owner_approve(message)
        self.delivery.owner_revoke("alice", "bob", self.context)
        self.delivery.owner_pair("alice", "bob", self.context)
        with self.assertRaises(Denied):
            self.session.submit(self.agents[1], message, approval)

    def test_committed_retry_after_revocation_does_not_redisclose(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.send(self.agents[1], message)
        self.delivery.owner_revoke("alice", "bob", self.context)
        self.restart()
        self.assertEqual(self.session.submit(self.agents[1], message, approval), approval)
        self.assertEqual(len(self.session.view().audit), 1)

    def test_storage_limits_fail_closed(self):
        self.delivery.max_records = 1
        message = self.agents[1].preview_availability(self.meeting)
        self.delivery.owner_approve(message)
        with self.assertRaises(Denied):
            self.delivery.owner_approve(message)

    def test_malformed_inputs_fail_without_state_change(self):
        for value in (None, [], {}, {"payload": {1}}, {"version": float("nan")}):
            with self.subTest(value=value):
                with self.assertRaises(Denied):
                    self.delivery.owner_approve(value)
                with self.assertRaises(Denied):
                    self.session.submit(self.agents[1], value, [])
        self.assertEqual(self.delivery.owner_inbox("alice"), [])
        self.assertEqual(self.session.view().audit, [])

    def test_processing_failure_rolls_back_everything(self):
        message = self.agents[1].preview_availability(self.meeting)
        approval = self.delivery.owner_approve(message)
        self.delivery.db.execute("CREATE TRIGGER force_processing_failure BEFORE UPDATE ON deliveries BEGIN SELECT RAISE(ABORT, 'simulated processing failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.session.submit(self.agents[1], message, approval)
        self.assertEqual(self.delivery.db.execute("SELECT used FROM approvals WHERE id=?", (approval,)).fetchone()[0], 0)
        self.assertEqual(self.delivery.owner_inbox("alice"), [])
        self.assertEqual(self.session.view().audit, [])

    def test_competing_approvals_only_one_transition(self):
        message = self.agents[1].preview_availability(self.meeting)
        approvals = [self.delivery.owner_approve(message) for _ in range(2)]
        def submit(approval):
            store = LocalDelivery(self.path)
            try:
                meeting, agents, _ = fixture()
                session = PersistentSession(store, agents, meeting)
                try:
                    session.submit(agents[1], message, approval)
                    return True
                except Denied:
                    return False
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(submit, approvals)), 1)
        self.assertEqual(len(self.session.view().audit), 1)
        self.assertEqual(self.delivery.db.execute("SELECT SUM(used) FROM approvals").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
