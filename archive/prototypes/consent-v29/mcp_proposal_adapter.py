"""Offline, transport-neutral MCP SDK adapter. No listener or host launcher.

Trusted composition binds one task/actor and the exact proposal-only dispatch.
Only run()'s SessionMessage streams are peer-facing. Client metadata is not auth.
"""
import importlib.metadata
import json

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.message import SessionMessage
from restricted_host_protocol import (RestrictedHostSession, bounded_tree,
                                      MAX_INPUT, MAX_OUTPUT, MAX_REQUESTS)

SDK_VERSION = '1.29.0'
SUPPORTED_VERSIONS = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
MAX_MESSAGES = 2048
MAX_ID_BYTES = 256


def _valid_id(value):
    if type(value) is int:
        return abs(value) <= 9007199254740991
    if type(value) is str:
        try:
            return len(value.encode('utf-8')) <= MAX_ID_BYTES
        except UnicodeError:
            return False
    return False


def _error(ident, code=-32600):
    return SessionMessage(types.JSONRPCMessage(types.JSONRPCError(
        jsonrpc='2.0', id=ident, error=types.ErrorData(
            code=code, message='Restricted protocol error; outcome may be unknown'))))


def _bounded(value, limit):
    bounded_tree(value)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > limit:
        raise ValueError('Bound exceeded')


class ProposalMCPAdapter:
    """Single-use SDK server; trusted Python object, not an untrusted-code sandbox."""
    def __init__(self, task, actor, dispatch):
        if importlib.metadata.version('mcp') != SDK_VERSION:
            raise RuntimeError('The reviewed MCP SDK version is required')
        self._binding = RestrictedHostSession(task, actor, dispatch)
        self._used = False
        self._server = Server('offline-scoped-proposals', version='0.1.0')

        @self._server.list_tools()
        async def list_tools():
            return [types.Tool(**tool) for tool in self._binding.application_tools()]

        # SDK schema errors include user values. Reuse the authoritative closed
        # application validator instead, including lexical integer restrictions.
        @self._server.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            return types.CallToolResult(**self._binding.application_call(name, arguments))

    async def run(self, read_stream, write_stream):
        """Serve already-decoded SDK streams once. Own neither external endpoint.

        No decoding/framing or authentication is supplied. A future raw transport
        must bound bytes BEFORE parsing, reject duplicate keys, and own timeouts.
        No reconnect or retry, including when a response is cancelled or lost.
        """
        if self._used:
            raise RuntimeError('Adapter instances are single-use')
        self._used = True
        to_sdk, sdk_read = anyio.create_memory_object_stream(0)
        sdk_write, from_sdk = anyio.create_memory_object_stream(0)
        ids = set()
        phase = 'new'

        async def ingress():
            nonlocal phase
            async with to_sdk:
                count = 0
                async for item in read_stream:
                    count += 1
                    if count > MAX_MESSAGES:
                        return
                    ident = None
                    request = False
                    try:
                        if not isinstance(item, SessionMessage):
                            raise ValueError('Invalid decoded message')
                        root = item.message.root
                        request = isinstance(root, types.JSONRPCRequest)
                        if request and _valid_id(root.id):
                            ident = root.id
                        raw = item.message.model_dump(mode='json', exclude_none=True)
                        _bounded(raw, MAX_INPUT)
                        if not request:
                            if not isinstance(root, types.JSONRPCNotification):
                                raise ValueError('No server-initiated requests')
                            # Only lifecycle/cancellation are forwarded. Tool-shaped
                            # notifications and unknown notifications never dispatch.
                            if root.method not in {'notifications/initialized', 'notifications/cancelled'}:
                                continue
                            types.ClientNotification.model_validate(raw)
                            if root.method == 'notifications/initialized' and phase == 'initializing':
                                phase = 'ready'
                            elif root.method != 'notifications/cancelled' or phase != 'ready':
                                continue
                            await to_sdk.send(SessionMessage(item.message))
                            continue
                        candidate = root.id
                        if not _valid_id(candidate):
                            raise ValueError('Invalid identifier')
                        ident = candidate
                        key = (type(ident), ident)
                        if key in ids:
                            raise ValueError('Duplicate request')
                        if len(ids) >= MAX_REQUESTS:
                            return
                        ids.add(key)
                        params = root.params or {}
                        if root.method == 'initialize':
                            if phase != 'new':
                                raise ValueError('Already initialized')
                            # Validate using the SDK model; extras are metadata,
                            # never application arguments or routing selectors.
                            types.InitializeRequest.model_validate(raw)
                            phase = 'initializing'
                        elif root.method == 'ping':
                            pass
                        elif phase != 'ready':
                            raise ValueError('Not initialized')
                        elif root.method == 'tools/call':
                            if (not {'name'} <= set(params) <= {'name', 'arguments', '_meta'}
                                    or type(params.get('name')) is not str
                                    or type(params.get('arguments', {})) is not dict):
                                raise ValueError('Invalid tool request')
                            if params['name'] not in {'propose', 'proposal_status', 'inbox'}:
                                await write_stream.send(SessionMessage(types.JSONRPCMessage(types.JSONRPCResponse(
                                    jsonrpc='2.0', id=ident, result={'content':[{'type':'text',
                                    'text':'Invalid proposal operation'}], 'isError':True}))))
                                continue
                        elif root.method == 'tools/list':
                            if not set(params) <= {'cursor', '_meta'} or params.get('cursor') is not None:
                                raise ValueError('No pagination')
                        else:
                            await write_stream.send(_error(ident, -32601))
                            continue
                        types.ClientRequest.model_validate(raw)
                        # Strip transport metadata supplied by the caller. Only
                        # protocol model fields reach the SDK, never auth context.
                        await to_sdk.send(SessionMessage(item.message))
                    except (ValueError, TypeError, UnicodeError, RecursionError):
                        # Invalid notifications receive no response.
                        if request:
                            if ident is None:
                                return  # SDK model cannot represent JSON-RPC null error IDs.
                            await write_stream.send(_error(ident))

        async def egress():
            async with from_sdk:
                async for item in from_sdk:
                    root = item.message.root
                    # SDK validation/internal failures may contain raw exceptions.
                    if isinstance(root, types.JSONRPCError):
                        item = _error(root.id, root.error.code)
                    try:
                        _bounded(item.message.model_dump(mode='json', exclude_none=True), MAX_OUTPUT)
                    except (ValueError, TypeError, UnicodeError, RecursionError):
                        item = _error(getattr(root, 'id', None), -32603)
                    await write_stream.send(item)

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(ingress)
                group.start_soon(egress)
                options = self._server.create_initialization_options()
                options.capabilities.experimental = None
                await self._server.run(sdk_read, sdk_write, options, raise_exceptions=False)
                group.cancel_scope.cancel()
        finally:
            self._binding.close()
            # Internal endpoints belong to this adapter; external streams do not.
            with anyio.CancelScope(shield=True):
                await to_sdk.aclose()
                await sdk_read.aclose()
                await sdk_write.aclose()
                await from_sdk.aclose()


def create_proposal_server(task, actor, dispatch):
    """Trusted factory only. dispatch MUST be the exact scoped proposal callback."""
    return ProposalMCPAdapter(task, actor, dispatch)
