"""Offline tests: mission card tools driven by the MCP Python client at protocol 2026-07-28."""
import json
import unittest

import anyio
import mcp_types as types
from mcp import Client
from mcp.server.mcpserver import MCPServer

from mission_cards.card import MissionCard
from mission_cards.tools import CardBook, code, register_card_tools

NOW = 1_800_000_000


class Owner:
    """One owner's host: a server with card tools and a scripted owner answering prompts."""

    def __init__(self, book, owner_id):
        self.server = MCPServer(f'cards-{owner_id}')
        register_card_tools(self.server, book, owner_id)
        self.prompts, self.answer = [], None

    async def _elicit(self, ctx, params):
        self.prompts.append(params.message)
        return self.answer(params.message)

    def call(self, name, args=None):
        async def go():
            async with Client(self.server, mode='2026-07-28', elicitation_callback=self._elicit) as client:
                return await client.call_tool(name, args or {})
        return anyio.run(go)


def body(result):
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


def answer(**content):
    return lambda _m: types.ElicitResult(action='accept', content=content)


def setup():
    book = CardBook()
    card = MissionCard('offsite-1', 'Pick a venue', {'edem': 'Edem', 'sam': 'Sam'}, lambda: NOW)
    card.add_constraint('sam', 'Step-free access')
    book.add(card)
    return book, card, Owner(book, 'edem'), Owner(book, 'sam')


class ToolTests(unittest.TestCase):
    def test_full_mission_through_tools(self):
        book, card, edem, sam = setup()
        edem.answer = answer(confirm='add')
        self.assertEqual(body(edem.call('add_mission_constraint', {
            'mission_id': 'offsite-1', 'text': 'Near Leeds station', 'kind': 'must'}))['constraint_id'], 'c2')
        for owner in (edem, sam):
            owner.answer = lambda m: types.ElicitResult(
                action='accept', content={'confirm_code': m.split('Confirmation code: ')[1][:8]})
            self.assertTrue(body(owner.call('acknowledge_mission_card', {'mission_id': 'offsite-1'}))['recorded'])
        self.assertIn("Sam:\n    c1. Must: Step-free access", edem.prompts[-1])
        self.assertEqual(card.state(), 'agreed')
        d = body(edem.call('view_mission_card', {'mission_id': 'offsite-1'}))['card_digest']
        accounts = {'c1': {'status': 'not_met', 'note': 'Stairs only'}, 'c2': {'status': 'met', 'note': '5 min walk'}}
        self.assertEqual(body(edem.call('report_mission_delivery', {
            'mission_id': 'offsite-1', 'card_digest': d, 'summary': 'The Old Mill', 'accounts': accounts}))['state'],
            'delivered')
        waiting = body(sam.call('list_mission_cards'))['missions'][0]['waiting_on_you']
        self.assertIn('c1', waiting[0])
        sam.answer = answer(decision='accept', waive='', reason='')
        refused = sam.call('review_mission_delivery', {'mission_id': 'offsite-1'})
        self.assertTrue(refused.is_error)
        self.assertIn('Not met and not waived: c1', refused.content[0].text)
        sam.answer = answer(decision='return', waive='', reason='Needs step-free access')
        self.assertEqual(body(sam.call('review_mission_delivery', {'mission_id': 'offsite-1'}))['state'], 'agreed')
        accounts['c1'] = {'status': 'met', 'note': 'Lift to all floors'}
        edem.call('report_mission_delivery', {'mission_id': 'offsite-1', 'card_digest': d,
                                              'summary': 'The Corn Exchange', 'accounts': accounts})
        sam.answer = answer(decision='accept')
        self.assertEqual(body(sam.call('review_mission_delivery', {'mission_id': 'offsite-1'}))['state'], 'accepted')
        records = body(sam.call('list_mission_activity', {'mission_id': 'offsite-1', 'after': 0}))['records']
        self.assertEqual(records[0]['seq'], 1)
        self.assertEqual(records[-1]['kind'], 'accepted')

    def test_wrong_code_and_dismissal_record_nothing(self):
        book, card, edem, _ = setup()
        edem.answer = answer(confirm_code='00000000')
        self.assertTrue(edem.call('acknowledge_mission_card', {'mission_id': 'offsite-1'}).is_error)
        edem.answer = lambda _m: types.ElicitResult(action='cancel')
        self.assertFalse(body(edem.call('acknowledge_mission_card', {'mission_id': 'offsite-1'}))['recorded'])
        edem.answer = answer(confirm='cancel')
        self.assertFalse(body(edem.call('add_mission_constraint', {
            'mission_id': 'offsite-1', 'text': 'x', 'kind': 'must'}))['recorded'])
        self.assertEqual(card.outstanding('edem'), ['Review and acknowledge the mission card'])
        self.assertEqual(len(card.snapshot()['constraints']), 1)

    def test_incomplete_delivery_refused_through_tool(self):
        book, card, edem, sam = setup()
        d = card.digest()
        card.acknowledge('edem', d)
        card.acknowledge('sam', d)
        result = edem.call('report_mission_delivery', {'mission_id': 'offsite-1', 'card_digest': d,
                                                       'summary': 'Venue', 'accounts': {}})
        self.assertTrue(result.is_error)
        self.assertIn('skips constraints: c1', result.content[0].text)

    def test_unknown_missions(self):
        _, _, edem, _ = setup()
        for mid in ('nope', '../offsite-1', ''):
            self.assertTrue(edem.call('view_mission_card', {'mission_id': mid}).is_error)

    def test_code_helper(self):
        self.assertEqual(code('abcdef0123456789'), 'abcdef01')


if __name__ == '__main__':
    unittest.main()
