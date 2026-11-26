"""Every assistant-facing tool states explicitly whether it reads, changes or reaches beyond Parlu."""
import unittest

import anyio
from mcp import Client

from mission_approvals.inbox import OfferInbox
from mission_approvals.server import build_server
from mission_cards.app import card_app
from mission_cards.tools import CardBook, register_card_tools

READ_ONLY = {'list_mission_offers', 'check_inbox', 'inbox_status', 'read_owner_guidance', 'message_status',
             'view_draft', 'list_drafts', 'owner_answer', 'list_mission_cards', 'view_mission_card',
             'list_mission_activity', 'show_mission_card'}


class AnnotationTests(unittest.TestCase):
    def test_every_tool_has_explicit_hints(self):
        unused = object()  # Tools only touch their access when called.
        server = build_server(OfferInbox(lambda: 0), conversation_inbox=unused, owner_desk=unused,
                              shared_drafts=unused, owner_questions=unused)
        book = CardBook()
        server_with_cards = build_server(OfferInbox(lambda: 0))
        register_card_tools(server_with_cards, book, 'owner')
        async def tools(srv):
            async with Client(srv, mode='2026-07-28') as client:
                return (await client.list_tools()).tools
        from mcp.server.mcpserver import MCPServer
        app_server = MCPServer('cards', extensions=[card_app(book, 'owner')])
        listed = anyio.run(tools, server) + anyio.run(tools, server_with_cards) + anyio.run(tools, app_server)
        self.assertGreaterEqual(len({t.name for t in listed}), 22)
        for tool in listed:
            with self.subTest(tool=tool.name):
                hints = tool.annotations
                self.assertIsNotNone(hints)
                for value in (hints.read_only_hint, hints.destructive_hint, hints.open_world_hint):
                    self.assertIsInstance(value, bool)
                self.assertEqual(hints.read_only_hint, tool.name in READ_ONLY)
                self.assertFalse(hints.destructive_hint)
                self.assertFalse(hints.open_world_hint)


if __name__ == '__main__':
    unittest.main()
