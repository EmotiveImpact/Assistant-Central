"""Offline tests: the mission card MCP App is advertised, served and falls back to text."""
import unittest

import anyio
from mcp import Client
from mcp.server.mcpserver import MCPServer

from mission_cards.app import APP_URI, card_app
from mission_cards.card import MissionCard
from mission_cards.tools import CardBook, register_card_tools

NOW = 1_800_000_000


def server():
    book = CardBook()
    card = MissionCard('offsite-1', 'Pick a venue', {'edem': 'Edem', 'sam': 'Sam'}, lambda: NOW)
    card.add_constraint('sam', '<img src=x onerror=alert(1)> Step-free access')
    book.add(card)
    srv = MCPServer('cards', extensions=[card_app(book, 'edem')])
    register_card_tools(srv, book, 'edem')
    return srv


def run(fn):
    async def go():
        async with Client(server(), mode='2026-07-28') as client:
            return await fn(client)
    return anyio.run(go)


class AppTests(unittest.TestCase):
    def test_tool_points_at_ui_resource(self):
        tools = run(lambda c: c.list_tools())
        tool = next(t for t in tools.tools if t.name == 'show_mission_card')
        self.assertEqual(tool.meta['ui']['resourceUri'], APP_URI)

    def test_resource_is_served_as_mcp_app_html(self):
        result = run(lambda c: c.read_resource(APP_URI))
        content = result.contents[0]
        self.assertEqual(content.mime_type, 'text/html;profile=mcp-app')
        self.assertIn('textContent', content.text)
        self.assertNotIn('innerHTML', content.text)

    def test_tool_returns_structured_card_and_text_fallback(self):
        result = run(lambda c: c.call_tool('show_mission_card', {'mission_id': 'offsite-1'}))
        body = result.structured_content
        self.assertEqual(body['snapshot']['constraints'][0]['owner'], 'sam')
        self.assertEqual(body['waiting_on_you'], ['Review and acknowledge the mission card'])
        self.assertIn('c1. Must:', body['text'])

    def test_unknown_mission(self):
        result = run(lambda c: c.call_tool('show_mission_card', {'mission_id': 'nope'}))
        self.assertTrue(result.is_error)


if __name__ == '__main__':
    unittest.main()
