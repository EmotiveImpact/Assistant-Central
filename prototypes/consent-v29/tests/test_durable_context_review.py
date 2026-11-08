"""Independent regression checks for immutable-context replay and history retries.

Faults below require direct trusted-local SQLite/in-memory mutation. They do not
model an adapter obtaining filesystem access or demonstrate OS isolation.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from generic_session import GenericPersistentSession
from network import Denied, canonical
from tests.test_state_sequence_campaign import Harness


class DurableContextReviewTests(unittest.TestCase):
    def fixture(self, text=False, requester='alice'):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        h = Harness(Path(tmp.name), 'independent-review', text, requester)
        self.addCleanup(h.close)
        return h

    def assert_denied_without_write(self, h, operations):
        before = h.snapshot()
        for operation in operations:
            with self.assertRaises(Denied):
                operation()
            self.assertEqual(before, h.snapshot())

    def test_late_third_transition_prevents_partial_inbox_and_owner_output(self):
        for text in (False, True):
            with self.subTest(text=text):
                h = self.fixture(text)
                h.ready()
                preview = h.response()
                h.deliver(h.prepare_response(preview))
                # First two messages remain perfectly valid. A stale LIMIT 2
                # reader would disclose both and never see the bad later row.
                h.store.db.execute(
                    'INSERT INTO transitions(session_id,delivery_id,body) VALUES (?,?,?)',
                    (h.task.id, 'late-corruption', canonical(h.request)))
                self.assert_denied_without_write(h, [
                    lambda owner=owner: h.boundaries[owner].dispatch({'method':'inbox'})
                    for owner in h.task.participants
                ] + [
                    lambda owner=owner: h.flow.received_messages(owner)
                    for owner in h.task.participants
                ] + [lambda: h.prepare_response(preview), h.session.view])

    def test_open_scope_mismatch_blocks_all_response_entry_points_and_new_alias(self):
        h = self.fixture(True, 'bob')
        h.ready()
        preview = h.response()
        b = h.boundaries[h.task.responder]
        command = {'method':'propose', 'proposal_id':'original', 'envelope':preview['envelope']}
        b.dispatch(command)
        original = h.session.context
        for change in ('memory', 'stored', 'deleted'):
            with self.subTest(change=change):
                if change == 'memory':
                    h.session.context = 'f' * 64
                elif change == 'stored':
                    h.store.db.execute('UPDATE sessions SET context=?', ('f' * 64,))
                else:
                    h.store.db.execute('DELETE FROM sessions')
                self.assert_denied_without_write(h, [
                    lambda: h.flow.response_context(h.task.responder), h.response,
                    lambda: h.prepare_response(preview),
                    lambda: b.dispatch({'method':'inbox'}),
                    lambda: b.dispatch({**command, 'proposal_id':'new-alias'}),
                ])
                h.session.context = original
                h.store.db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (h.task.id, original))
        self.assertEqual(h.response()['preview_digest'], preview['preview_digest'])

    def test_reopen_changed_context_fails_and_clean_reopen_preserves_history(self):
        h = self.fixture()
        h.ready()
        h.store.db.execute('UPDATE sessions SET context=?', ('f' * 64,))
        self.assert_denied_without_write(h, [
            lambda: GenericPersistentSession(h.store, h.actors, h.task)])
        h.store.db.execute('UPDATE sessions SET context=?', (h.session.context,))
        h.reopen()
        self.assertEqual(h.session.view().request, h.request)
        self.assertEqual(h.boundaries[h.task.responder].dispatch({'method':'inbox'})['messages'][0]['envelope'], h.request)

    def test_request_relative_result_bound_blocks_history_disclosure(self):
        for text in (False, True):
            with self.subTest(text=text):
                h = self.fixture(text)
                h.ready()
                preview = h.response()
                h.deliver(h.prepare_response(preview))
                bad = copy.deepcopy(preview['envelope'])
                bad['payload'] = ({'text':'123456789'} if text else
                    {'items':[{'title':'inert', 'url':'https://example.invalid', 'summary':'inert'}] * 3})
                h.store.db.execute("UPDATE transitions SET body=? WHERE delivery_id=(SELECT delivery_id FROM transitions ORDER BY seq DESC LIMIT 1)", (canonical(bad),))
                self.assert_denied_without_write(h, [
                    lambda: h.flow.received_messages(h.task.responder),
                    lambda: h.boundaries[h.task.responder].dispatch({'method':'inbox'}),
                    lambda: h.prepare_response(preview),
                ])

    def test_cancelled_alias_and_exact_retry_add_no_authority_or_delivery(self):
        h = self.fixture(True)
        h.ready()
        preview = h.response()
        b = h.boundaries[h.task.responder]
        command = {'method':'propose', 'proposal_id':'original', 'envelope':preview['envelope']}
        b.dispatch(command)
        card = b.prepare_owner_review('original')
        # A proposal and unsigned owner card never permit send.
        self.assert_denied_without_write(h, [lambda: h.flow.submit(card['owner'], card['request_id'])])
        h.gateway.apply(h.auth.control(h.task.requester, 'cancel', {'meeting':h.task.id}, h.now[0]))
        before = h.snapshot()
        b.dispatch({**command, 'proposal_id':'alias'})
        after = h.snapshot()
        for name in before:
            if name != 'agent_proposal_ids':
                self.assertEqual(before[name], after[name], name)
        self.assertEqual(b.prepare_owner_review('alias')['request_id'], card['request_id'])
        self.assertEqual(h.prepare_response(preview)['request_id'], card['request_id'])
        self.assertEqual(h.boundaries[h.task.responder].dispatch({'method':'inbox'})['messages'][0]['envelope'], h.request)
        self.assert_denied_without_write(h, [h.response, lambda: h.flow.submit(card['owner'], card['request_id'])])
        # The pre-existing processed request retry returns only its original ID.
        # That path intentionally does not require new projection or approval.
        receipt = h.store.db.execute('SELECT delivery_id FROM transitions').fetchone()[0]
        h.store.db.execute('UPDATE sessions SET context=?', ('f' * 64,))
        before = h.snapshot()
        self.assertEqual(h.session.submit(h.session.registry[h.task.requester], h.request, receipt), receipt)
        self.assertEqual(before, h.snapshot())


if __name__ == '__main__':
    unittest.main()
