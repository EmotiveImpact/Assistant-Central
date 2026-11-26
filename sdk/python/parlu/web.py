# SPDX-License-Identifier: Apache-2.0
"""Call Parlu with plain JSON over HTTP. Standard library only.

    from parlu.web import ParluWeb
    parlu = ParluWeb('http://127.0.0.1:8890/mcp', token='<lease token from Central>')
    if parlu.pending():
        batch = parlu.inbox()

Each call is one self-contained HTTPS POST of a JSON-RPC request, as defined
by the MCP 2026-07-28 HTTP transport, so the same requests work from any
language. See ``sdk/README.md`` for the raw request shape.
"""
from __future__ import annotations

import itertools
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .agent import PROTOCOL, ParluError

MAX_RESPONSE = 4 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_for(method: str, params: dict, request_id: int, name: str | None = None):
    """The exact body and headers for one call. Useful for porting to another language."""
    body = {'jsonrpc': '2.0', 'id': request_id, 'method': method,
            'params': {**params, '_meta': {'io.modelcontextprotocol/protocolVersion': PROTOCOL,
                                           'io.modelcontextprotocol/clientCapabilities': {}}}}
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
               'MCP-Protocol-Version': PROTOCOL, 'Mcp-Method': method}
    if name is not None:
        headers['Mcp-Name'] = name
    return body, headers


class ParluWeb:
    """A synchronous Parlu client for scripts and apps without an MCP library."""

    def __init__(self, url: str, *, token: str | None = None, timeout: float = 20):
        parts = urlsplit(url)
        local = parts.hostname in ('127.0.0.1', 'localhost', '::1')
        if parts.scheme != 'https' and not (parts.scheme == 'http' and local):
            raise ParluError('Use https, or http only to this computer.')
        self.url, self.token, self.timeout = url, token, timeout
        self._ids = itertools.count(1)
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _post(self, method: str, params: dict, name: str | None = None) -> dict:
        body, headers = request_for(method, params, next(self._ids), name)
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), method='POST', headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as error:
            raw = error.read(MAX_RESPONSE + 1)
            if error.code in (401, 403):
                raise ParluError('Central refused this assistant. Check the token.') from None
        except OSError:
            raise ParluError('Central could not be reached.') from None
        if len(raw) > MAX_RESPONSE:
            raise ParluError('The response was too large.')
        try:
            reply = json.loads(raw)
        except ValueError:
            raise ParluError('Central sent a response that was not JSON.') from None
        if 'error' in reply:
            raise ParluError(str(reply['error'].get('message', 'Parlu refused the request.')))
        return reply['result']

    def call(self, tool: str, **arguments) -> dict:
        result = self._post('tools/call', {'name': tool, 'arguments': arguments}, name=tool)
        text = result['content'][0]['text'] if result.get('content') else ''
        if result.get('isError'):
            raise ParluError(text or 'Parlu refused the request.')
        if result.get('structuredContent') is not None:
            return result['structuredContent']
        return json.loads(text)

    def tools(self) -> list[str]:
        return sorted(tool['name'] for tool in self._post('tools/list', {})['tools'])

    def inbox(self, limit: int = 20) -> dict:
        return self.call('check_inbox', limit=limit)

    def acknowledge(self, through_message_id: str) -> dict:
        return self.call('acknowledge_inbox', through_message_id=through_message_id)

    def pending(self) -> bool:
        return self.call('inbox_status')['pending']

    def propose_message(self, request_id: str, text: str) -> dict:
        return self.call('propose_message', request_id=request_id, text=text)

    def message_status(self, request_id: str) -> dict:
        return self.call('message_status', request_id=request_id)

    def ask_owner(self, request_id: str, question: str, options: list[str]) -> dict:
        return self.call('ask_my_owner', request_id=request_id, question=question, options=options)

    def owner_answer(self, request_id: str) -> dict:
        return self.call('owner_answer', request_id=request_id)
