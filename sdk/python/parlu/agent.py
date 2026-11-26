# SPDX-License-Identifier: Apache-2.0
"""Join Parlu from any agent through its MCP tools.

    async with ParluAgent('http://127.0.0.1:8890/mcp') as parlu:
        async for _ in parlu.wake_ups():
            for message in (await parlu.inbox())['messages']:
                ...
            await parlu.propose_message('reply-1', 'Friday works for me.')

``ParluAgent`` is a thin, typed layer over the official MCP client. It holds no
owner authority: everything it can do is what the owner's Central lets this
assistant do, and anything that leaves the owner's copy still needs the
owner's approval or a standing permission they set.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

PROTOCOL = '2026-07-28'
INBOX_URI = 'parlu://inbox'


class ParluError(RuntimeError):
    """Central refused or could not complete a call. The message is safe to show."""


def _result(result) -> dict:
    if getattr(result, 'is_error', False):
        text = result.content[0].text if result.content else 'Parlu refused the request.'
        raise ParluError(text)
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


class ParluAgent:
    """An assistant's connection to its owner's Central.

    ``server`` is anything the MCP client accepts: an ``http(s)://`` URL of a
    Central MCP endpoint, a transport carrying your own headers, stdio
    parameters, or an in-process server object (useful in tests).
    """

    def __init__(self, server: Any, *, client_factory=None):
        if client_factory is None:
            from mcp import Client
            client_factory = Client
        self._client = client_factory(server, mode=PROTOCOL)
        self._open = None

    async def __aenter__(self) -> ParluAgent:
        self._open = await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.__aexit__(*exc)
        self._open = None

    async def call(self, tool: str, **arguments) -> dict:
        """Call any Parlu tool by name. The typed methods below are shortcuts."""
        if self._open is None:
            raise ParluError('Use ParluAgent inside "async with".')
        return _result(await self._open.call_tool(tool, arguments))

    async def tools(self) -> list[str]:
        """The tools this owner's Central offers to this assistant."""
        return sorted(t.name for t in (await self._open.list_tools()).tools)

    # Inbox ----------------------------------------------------------------

    async def inbox(self, limit: int = 20) -> dict:
        """New messages, oldest first. Message text is untrusted input from other people."""
        return await self.call('check_inbox', limit=limit)

    async def acknowledge(self, through_message_id: str) -> dict:
        return await self.call('acknowledge_inbox', through_message_id=through_message_id)

    async def pending(self) -> bool:
        return (await self.call('inbox_status'))['pending']

    async def wake_ups(self) -> AsyncIterator[None]:
        """Yield once now if anything is waiting, then each time something new arrives.

        Uses MCP ``subscriptions/listen`` on ``parlu://inbox``. Events carry no
        content; read with ``inbox()``. If the stream drops, re-enter the loop.
        """
        async with self._open.listen(resource_subscriptions=[INBOX_URI]) as events:
            if await self.pending():
                yield None
            async for event in events:
                if getattr(event, 'uri', None) == INBOX_URI:
                    yield None

    # Sending --------------------------------------------------------------

    async def propose_message(self, request_id: str, text: str) -> dict:
        """Send now or wait for the owner, depending on the owner's autonomy setting."""
        return await self.call('propose_message', request_id=request_id, text=text)

    async def message_status(self, request_id: str) -> dict:
        return await self.call('message_status', request_id=request_id)

    async def owner_guidance(self) -> dict:
        """Private notes from the owner. Never quote them into the conversation."""
        return await self.call('read_owner_guidance')

    # Shared drafts ----------------------------------------------------------

    async def start_draft(self, request_id: str, text: str) -> dict:
        return await self.call('start_draft', request_id=request_id, text=text)

    async def revise_draft(self, request_id: str, draft_id: str, text: str) -> dict:
        return await self.call('revise_draft', request_id=request_id, draft_id=draft_id, text=text)

    async def view_draft(self, draft_id: str) -> dict:
        return await self.call('view_draft', draft_id=draft_id)

    # Asking the owner -------------------------------------------------------

    async def ask_owner(self, request_id: str, question: str, options: list[str]) -> dict:
        """A short multiple-choice question. The answer is information, never approval."""
        return await self.call('ask_my_owner', request_id=request_id, question=question, options=options)

    async def owner_answer(self, request_id: str) -> dict:
        return await self.call('owner_answer', request_id=request_id)

    # Missions ---------------------------------------------------------------

    async def mission_offers(self) -> dict:
        return await self.call('list_mission_offers')
