"""Independent v13 review: concurrent connections and atomic failure boundaries."""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from agent_proposals import AgentProposalBoundary
from durable import LocalDelivery
from encrypted_delivery import DurableEncryptedOutbox
from generic_demo import fixture
from generic_owner_workflow import GenericOwnerWorkflow
from generic_session import GenericPersistentSession
from integrated_fixture import FixtureAuthorities
from network import Denied
from owner_auth import SignedOwnerGateway


class AgentBoundaryIndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'sender.sqlite3'
        self.task, self.actors, self.message, _ = fixture()
        self.auth = FixtureAuthorities(self.task, 1000)
        self.store, self.boundary = self.connect()
        self.addCleanup(self.store.close)
        self.auth.pair_all(self.boundary.workflow.gateway, 1000)

    def connect(self):
        store = LocalDelivery(self.path, clock=lambda: 1000)
        session = GenericPersistentSession(store, self.actors, self.task)
        gateway = SignedOwnerGateway(session, self.auth.owner_roots)
        box = DurableEncryptedOutbox(gateway, self.auth.registry, self.auth.transport_keys)
        return store, AgentProposalBoundary(GenericOwnerWorkflow(gateway, box), 'alice')

    def propose(self, boundary=None, proposal_id='one', message=None):
        return (boundary or self.boundary).dispatch({
            'method': 'propose', 'proposal_id': proposal_id,
            'envelope': self.message if message is None else message})

    def count(self, table):
        return self.store.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def race(self, action):
        ready = threading.Barrier(2)
        def worker(index):
            store, boundary = self.connect()
            try:
                ready.wait(timeout=10)
                try:
                    return action(index, store, boundary)
                except Denied as exc:
                    return exc
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_two_connections_same_id_and_payload_deduplicate(self):
        results = self.race(lambda i, s, b: self.propose(b))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.count('agent_proposals'), 1)
        self.assertEqual(self.count('agent_proposal_ids'), 1)
        self.assertEqual(self.count('owner_requests'), 0)

    def test_two_connections_conflicting_id_has_one_winner(self):
        changed = copy.deepcopy(self.message)
        changed['payload']['query'] = 'Different request'
        results = self.race(lambda i, s, b: self.propose(b, message=changed if i else self.message))
        self.assertEqual(sum(isinstance(r, Denied) for r in results), 1)
        self.assertEqual(self.count('agent_proposals'), 1)
        self.assertEqual(self.count('agent_proposal_ids'), 1)

    def test_two_connections_alias_import_creates_one_unsigned_review(self):
        self.propose(proposal_id='first')
        self.propose(proposal_id='second')
        results = self.race(lambda i, s, b: b.prepare_owner_review(('first', 'second')[i]))
        self.assertEqual(results[0]['request_id'], results[1]['request_id'])
        self.assertEqual(self.count('owner_requests'), 1)
        row = self.store.db.execute('SELECT state,signed FROM owner_requests').fetchone()
        self.assertEqual(tuple(row), ('pending', None))
        self.assertEqual(self.count('encrypted_outbox'), 0)

    def test_two_connections_capacity_check_is_serialized(self):
        def action(i, store, boundary):
            store.max_records = 1
            return self.propose(boundary, proposal_id=('first', 'second')[i])
        results = self.race(action)
        self.assertEqual(sum(isinstance(r, Denied) for r in results), 1)
        self.assertEqual(self.count('agent_proposals'), 1)
        self.assertEqual(self.count('agent_proposal_ids'), 1)

    def test_alias_insert_fault_rolls_back_new_fingerprint(self):
        self.store.db.execute("""CREATE TRIGGER fail_alias BEFORE INSERT ON agent_proposal_ids
            BEGIN SELECT RAISE(ABORT, 'injected alias fault'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.propose()
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(self.count('agent_proposals'), 0)
        self.assertEqual(self.count('agent_proposal_ids'), 0)
        self.store.db.execute('DROP TRIGGER fail_alias')
        self.assertEqual(self.propose()['state'], 'awaiting_owner_review')

    def test_import_link_fault_rolls_back_unsigned_review(self):
        self.propose()
        self.store.db.execute("""CREATE TRIGGER fail_link BEFORE UPDATE ON agent_proposals
            BEGIN SELECT RAISE(ABORT, 'injected link fault'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.boundary.prepare_owner_review('one')
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual(self.count('owner_requests'), 0)
        self.assertIsNone(self.store.db.execute('SELECT request_id FROM agent_proposals').fetchone()[0])
        self.store.db.execute('DROP TRIGGER fail_link')
        card = self.boundary.prepare_owner_review('one')
        self.assertEqual(card['state'], 'pending')
        self.assertEqual(self.count('owner_requests'), 1)

    def test_owner_capacity_failure_does_not_link_or_drop_proposal(self):
        self.propose()
        self.boundary.workflow.prepare('alice', 'cancel')
        self.store.max_records = 1
        with self.assertRaises(Denied):
            self.boundary.prepare_owner_review('one')
        self.assertEqual(self.count('owner_requests'), 1)
        self.assertEqual(self.count('agent_proposals'), 1)
        self.assertIsNone(self.store.db.execute('SELECT request_id FROM agent_proposals').fetchone()[0])
        self.assertEqual(self.propose()['state'], 'awaiting_owner_review')


if __name__ == '__main__':
    unittest.main()
