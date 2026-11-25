"""Inbox MCP tools over the real ledger, driven by the official MCP client. Fictional identities."""
import json
from pathlib import Path
import tempfile
import unittest

import anyio
from mcp import Client

from conversation import ConversationLedger
from conversation.inbox import InboxAccess, InboxStore
from mission_approvals.inbox import OfferInbox
from mission_approvals.server import build_server
from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint


def payload(result):
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


class InboxToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.now = 2000000000.0
        self.auths, self.keys, self.sessions = {}, {}, {}
        for name in ('alice', 'bob'):
            auth = LocalOwnerAuth(root / name, clock=lambda: self.now)
            auth.bootstrap(name, name + '_assistant', 'Fictional test password')
            self.auths[name], self.keys[name] = auth, fingerprint(auth.public_identity())
            self.sessions[name] = auth.login('Fictional test password')
        self.ledger = ConversationLedger(root / 'ledger', self.auths['alice'],
                                         {self.keys[n]: a for n, a in self.auths.items()}, clock=lambda: self.now)
        self.ledger.create(self.keys['alice'], self.sessions['alice'], 'trip')
        invite = self.ledger.invite(self.keys['alice'], self.sessions['alice'], 'trip', self.keys['bob'])
        self.ledger.accept_invitation(self.keys['bob'], self.sessions['bob'], invite['id'])
        self.store = InboxStore(root / 'inbox', self.ledger)
        lease = self.store.provision(self.keys['bob'], self.sessions['bob'], 'bob_assistant', 'trip')
        self.access = InboxAccess(self.store, lease, lambda: self.sessions['bob'])
        self.server = build_server(OfferInbox(lambda: int(self.now)), conversation_inbox=self.access)

    def tearDown(self):
        self.store.close()
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.tmp.cleanup()

    def post(self, text, request):
        binding = self.ledger.bind_context(self.keys['alice'], self.sessions['alice'], 'trip')
        return self.ledger.append(self.keys['alice'], self.sessions['alice'], binding, request_id=request, text=text)

    def call(self, name, arguments=None):
        async def run():
            async with Client(self.server, mode='2026-07-28') as client:
                return await client.call_tool(name, arguments or {})
        return anyio.run(run)

    def tools(self):
        async def run():
            async with Client(self.server, mode='2026-07-28') as client:
                return sorted(t.name for t in (await client.list_tools()).tools)
        return anyio.run(run)

    def test_tools_registered_only_when_host_supplies_inbox(self):
        self.assertEqual(self.tools(), ['acknowledge_inbox', 'check_inbox', 'inbox_status',
                                        'list_mission_offers', 'review_mission_offer'])
        bare = build_server(OfferInbox(lambda: int(self.now)))
        async def run():
            async with Client(bare, mode='2026-07-28') as client:
                return sorted(t.name for t in (await client.list_tools()).tools)
        self.assertEqual(anyio.run(run), ['list_mission_offers', 'review_mission_offer'])

    def test_check_acknowledge_and_status_round_trip(self):
        self.assertFalse(payload(self.call('inbox_status'))['pending'])
        first = self.post('Fictional: shall we book the train?', 'r1')
        second = self.post('Fictional: Friday works for me', 'r2')
        self.assertEqual(payload(self.call('inbox_status')), {'pending': True})
        batch = payload(self.call('check_inbox'))
        self.assertEqual([m['id'] for m in batch['messages']], [first['id'], second['id']])
        self.assertEqual(batch['peer_authored_fields'], ['text'])
        done = payload(self.call('acknowledge_inbox', {'through_message_id': second['id']}))
        self.assertEqual(done['acknowledged_through'], second['id'])
        self.assertEqual(payload(self.call('check_inbox'))['messages'], [])
        self.assertFalse(payload(self.call('inbox_status'))['pending'])

    def test_model_cannot_choose_scope_or_acknowledge_unseen(self):
        unseen = self.post('Fictional unseen note', 'r1')
        result = self.call('acknowledge_inbox', {'through_message_id': unseen['id']})
        self.assertTrue(result.is_error)
        # Extra arguments naming another owner or conversation are not part of the tool.
        listed = payload(self.call('check_inbox', {'limit': 5}))
        self.assertEqual(listed['conversation_id'], 'trip')

    def test_control_characters_are_stripped_from_peer_text(self):
        self.post('Fictional‮ reversed\x07 text', 'r1')
        text = payload(self.call('check_inbox'))['messages'][0]['text']
        self.assertNotIn('‮', text)
        self.assertNotIn('\x07', text)

    def test_expired_session_reports_unavailable_without_detail(self):
        self.auths['bob'].logout(self.sessions['bob'])
        result = self.call('check_inbox')
        self.assertTrue(result.is_error)


if __name__ == '__main__':
    unittest.main()
