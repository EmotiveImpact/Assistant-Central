import json
import unittest
import anyio

from integration.demo import exercise
from integration.team_proposals import BoundArtifactProposal
from test_team_proposals import fixture, TEXT


def call(identifier, name, arguments):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}


async def raw_exchange(bound, records):
    """Finite raw input supports notifications and intentionally absent replies."""
    from raw_bridge.transport import RawBridge
    incoming = iter([(json.dumps(record) + '\n').encode() for record in records])
    replies = []

    class Reader:
        async def receive(self, limit):
            try:
                return next(incoming)
            except StopIteration:
                raise anyio.EndOfStream from None

    class Writer:
        async def send(self, value):
            replies.append(json.loads(value))

    with anyio.fail_after(10):
        await RawBridge(bound.facade).run(Reader(), Writer())
    return replies


def initialize(identifier='init'):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-11-25', 'capabilities': {},
        'clientInfo': {'name': 'synthetic-negative-test', 'version': '1'}}}


class WireTests(unittest.TestCase):
    def setUp(self):
        self.w = fixture()
        self.addCleanup(self.w.close)
        self.bound = BoundArtifactProposal(self.w, 'research-v1', 'copy', expected_context=self.w.context)
        self.addCleanup(self.bound.close)

    def test_actual_recovered_three_tool_path_stages_without_execution(self):
        calls = [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, call(2, 'propose', {'text': TEXT}),
                 call(3, 'proposal_status', {'proposal_id': self.bound.proposal_id}), call(4, 'processed_inbox', {})]
        replies = anyio.run(exercise, self.bound, calls)
        names = [tool['name'] for tool in replies[1]['result']['tools']]
        self.assertEqual(names, ['propose', 'proposal_status', 'processed_inbox'])
        self.assertEqual(replies[2]['result']['structuredContent']['state'], 'pending')
        self.assertEqual(replies[3]['result']['structuredContent']['state'], 'pending')
        self.assertEqual(replies[4]['result']['structuredContent']['items'], [])
        self.assertEqual(self.w._row('copy')['state'], 'planned')

    def test_owner_tool_is_unavailable_and_not_executed(self):
        replies = anyio.run(exercise, self.bound, [call(1, 'approve_send', {'owner': 'bob'})])
        self.assertIn('error', replies[1])
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_changed_text_returns_fixed_error_without_echo(self):
        secret = 'private-synthetic-marker-must-not-echo'
        replies = anyio.run(exercise, self.bound, [call(1, 'propose', {'text': secret})])
        self.assertTrue(replies[1]['result']['isError'])
        self.assertNotIn(secret, json.dumps(replies[1]))
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_revocation_during_session_blocks_staging(self):
        def revoke(index):
            self.w.revoke_task('carol', 'copy', expected_context=self.w.context)
        async def run():
            return await exercise(self.bound, [call(1, 'propose', {'text': TEXT})], before_each=revoke)
        replies = anyio.run(run)
        self.assertTrue(replies[1]['result']['isError'])

    def test_history_after_revocation_remains_readonly_on_wire(self):
        def revoke(index):
            if index == 1:
                self.w.revoke_task('carol', 'copy', expected_context=self.w.context)
        calls = [call(1, 'propose', {'text': TEXT}), call(2, 'proposal_status', {'proposal_id': self.bound.proposal_id}),
                 call(3, 'propose', {'text': TEXT})]
        async def run(): return await exercise(self.bound, calls, before_each=revoke)
        replies = anyio.run(run)
        self.assertEqual(replies[2]['result']['structuredContent']['state'], 'pending')
        self.assertTrue(replies[3]['result']['isError'])

    def test_fragmented_utf8_crosses_existing_raw_codec(self):
        w = fixture(team_id='utf8-wire-team', text='Synthetic 🙂 note')
        self.addCleanup(w.close)
        b = BoundArtifactProposal(w, 'research-v1', 'copy', expected_context=w.context)
        self.addCleanup(b.close)
        async def run(): return await exercise(b, [call(1, 'propose', {'text': 'Synthetic 🙂 note'})], fragment_size=1)
        replies = anyio.run(run)
        self.assertEqual(replies[1]['result']['structuredContent']['content_digest'], b.content_digest)

    def test_tool_before_initialization_is_rejected_without_staging(self):
        replies = anyio.run(raw_exchange, self.bound, [call(1, 'propose', {'text': TEXT})])
        self.assertIn('error', replies[0])
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_missing_initialized_notification_blocks_staging(self):
        replies = anyio.run(raw_exchange, self.bound,
                            [initialize(), call(1, 'propose', {'text': TEXT})])
        self.assertIn('error', replies[1])
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_duplicate_initialization_cannot_reset_binding(self):
        records = [initialize(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                   call(1, 'propose', {'text': TEXT}), initialize('second-init'),
                   call(2, 'proposal_status', {'proposal_id': self.bound.proposal_id})]
        replies = anyio.run(raw_exchange, self.bound, records)
        self.assertIn('error', replies[2])
        self.assertEqual(replies[3]['result']['structuredContent']['proposal_id'], self.bound.proposal_id)
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 1)

    def test_crossed_proposal_and_extra_route_selectors_are_rejected(self):
        calls = [call(1, 'proposal_status', {'proposal_id': '0' * 64})]
        calls += [call(index + 2, 'propose', {'text': TEXT, key: 'synthetic-other'})
                  for index, key in enumerate(('recipient', 'task', 'owner'))]
        replies = anyio.run(exercise, self.bound, calls)
        for reply in replies[1:]:
            self.assertTrue('error' in reply or reply.get('result', {}).get('isError'))
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_duplicate_json_members_rejected_before_staging(self):
        raw = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"propose","arguments":{"text":"bad","text":"bad"}}}\n'
        replies = anyio.run(exercise, self.bound, [raw])
        self.assertIn('error', replies[1])
        self.assertEqual(self.bound._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)


if __name__ == '__main__': unittest.main()
