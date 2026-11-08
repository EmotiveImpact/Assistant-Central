"""Bounded already-decoded offline MCP composition. Not a byte transport."""
import json
import math
import re
from importlib.metadata import version
import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions
from mcp.shared.message import SessionMessage
from facade_candidate import AssistantFacade

VERSIONS = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
MAX_MESSAGE_BYTES = 16384
MAX_OUTPUT_BYTES = 32768
MAX_DEPTH = 8
MAX_COLLECTION = 64
MAX_NODES = 512
MAX_REQUESTS = 128
MAX_MESSAGES = 160
PROTOCOL_ERROR = 'Request rejected.'
UNCERTAIN_ERROR = 'Operation outcome unavailable; local proposal persistence may be uncertain.'
TOOL_ERROR = 'Tool operation unavailable; local proposal persistence may be uncertain.'


def bounded(value, limit):
    """Bound traversal before JSON encoding; callers already decoded input."""
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError()
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if not -(2**53) < item < 2**53: raise ValueError()
        elif type(item) is float:
            if not math.isfinite(item): raise ValueError()
        elif type(item) is str:
            if len(item) > limit or len(item.encode('utf-8')) > limit: raise ValueError()
        elif type(item) is list:
            if len(item) > MAX_COLLECTION: raise ValueError()
            for child in item: visit(child, depth + 1)
        elif type(item) is dict:
            if len(item) > MAX_COLLECTION: raise ValueError()
            for key, child in item.items():
                if type(key) is not str: raise ValueError()
                visit(key, depth + 1); visit(child, depth + 1)
        else:
            raise ValueError()
    visit(value, 0)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > limit: raise ValueError()
    return encoded


def schema(key=None, spec=None):
    return {'type': 'object', 'properties': {key: spec} if key else {},
            'required': [key] if key else [], 'additionalProperties': False}


TOOLS = [
    types.Tool(name='propose', description='Persist unsigned exact text locally, at most 1024 UTF-8 bytes; never approve or send.',
        inputSchema=schema('text', {'type': 'string', 'minLength': 1, 'maxLength': 1024}),
        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)),
    types.Tool(name='proposal_status', description='Read one proposal of the fixed local actor.',
        inputSchema=schema('proposal_id', {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}),
        annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False)),
    types.Tool(name='processed_inbox', description='Read last explicitly published processed-only local inbox.',
        inputSchema=schema(), annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False)),
]


class OfflineBridge:
    def __init__(self, facade):
        if type(facade) is not AssistantFacade:
            raise TypeError('A fixed AssistantFacade is required.')
        if version('mcp') != '1.29.0':
            raise RuntimeError('Requires mcp==1.29.0.')
        self._facade = facade
        self._used = False
        self._server = Server('offline-fixed-proposal-bridge', version='r3')
        @self._server.list_tools()
        async def list_tools():
            return TOOLS
        @self._server.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            try:
                self._arguments(name, arguments)
                if name == 'propose': result = self._facade.propose(arguments)
                elif name == 'proposal_status': result = self._facade.status(arguments)
                else: result = self._facade.processed_inbox(arguments)
                encoded = bounded(result, MAX_OUTPUT_BYTES // 2)
                return types.CallToolResult(content=[types.TextContent(type='text', text=encoded)], structuredContent=result)
            except Exception:
                return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=TOOL_ERROR)])

    @staticmethod
    def _arguments(name, args):
        bounded(args, 8192)
        if type(args) is not dict: raise ValueError()
        if name == 'propose':
            if set(args) != {'text'} or type(args['text']) is not str: raise ValueError()
            if not 0 < len(args['text']) <= 1024 or len(args['text'].encode('utf-8')) > 1024: raise ValueError()
        elif name == 'proposal_status':
            if set(args) != {'proposal_id'} or type(args['proposal_id']) is not str or not re.fullmatch('[0-9a-f]{64}', args['proposal_id']): raise ValueError()
        elif name == 'processed_inbox':
            if args: raise ValueError()
        else: raise ValueError()

    async def run(self, incoming, outgoing):
        """Caller owns connected SessionMessage streams. Single-use, serial forwarding."""
        if self._used: raise RuntimeError('Bridge is single-use.')
        self._used = True
        sdk_send, sdk_read = anyio.create_memory_object_stream(0)
        sdk_write, sdk_receive = anyio.create_memory_object_stream(0)
        options = InitializationOptions(server_name='offline-fixed-proposal-bridge', server_version='r3',
            capabilities=types.ServerCapabilities(tools=types.ToolsCapability(listChanged=False)))
        seen = set()
        state = 'new'
        async with sdk_send, sdk_read, sdk_write, sdk_receive, anyio.create_task_group() as group:
            group.start_soon(self._server.run, sdk_read, sdk_write, options)
            try:
                for _ in range(MAX_MESSAGES):
                    try: item = await incoming.receive()
                    except anyio.EndOfStream: break
                    request_id = None
                    error_code = -32600
                    forwarded_possible = False
                    reply = None
                    try:
                        if type(item) is not SessionMessage: raise ValueError()
                        message = item.message.root
                        # Validate ID independently so bounded errors may safely correlate.
                        candidate = getattr(message, 'id', None)
                        if type(candidate) is int and 0 <= candidate < 2**31:
                            request_id = candidate
                        elif type(candidate) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', candidate):
                            request_id = candidate
                        elif hasattr(message, 'id'): raise ValueError()
                        if request_id is not None:
                            if request_id in seen or len(seen) >= MAX_REQUESTS: raise ValueError()
                            seen.add(request_id)
                        # Reject original envelope extras before exclude_none can hide nulls.
                        if message.model_extra: raise ValueError()
                        data = message.model_dump(by_alias=True, exclude_none=True)
                        bounded(data, MAX_MESSAGE_BYTES)
                        method = data.get('method')
                        if set(data) - {'jsonrpc', 'id', 'method', 'params'}: raise ValueError()
                        models = {'initialize': types.InitializeRequest,
                                  'notifications/initialized': types.InitializedNotification,
                                  'ping': types.PingRequest, 'tools/list': types.ListToolsRequest,
                                  'tools/call': types.CallToolRequest}
                        if method not in models:
                            error_code = -32601
                            raise ValueError()
                        # Phase/envelope failures are invalid requests, independent of params.
                        if method == 'notifications/initialized':
                            if state != 'await_initialized' or request_id is not None: raise ValueError()
                        elif request_id is None:
                            raise ValueError()
                        elif method == 'initialize':
                            if state != 'new': raise ValueError()
                        elif method != 'ping' and state != 'ready':
                            raise ValueError()
                        error_code = -32602
                        models[method].model_validate(data)
                        params = data.get('params', {})
                        if type(params) is not dict: raise ValueError()
                        # Validate original SDK shape before discarding inert metadata.
                        params = {k: v for k, v in params.items() if k != '_meta'}
                        next_state = state
                        if method == 'initialize':
                            if set(params) != {'protocolVersion', 'capabilities', 'clientInfo'}: raise ValueError()
                            if params['protocolVersion'] not in VERSIONS: raise ValueError()
                            params = {'protocolVersion': params['protocolVersion'], 'capabilities': {},
                                      'clientInfo': {'name': 'inert-local-client', 'version': '0'}}
                            next_state = 'await_initialized'
                        elif method == 'notifications/initialized':
                            if params: raise ValueError()
                            next_state = 'ready'
                        elif method in ('tools/list', 'ping'):
                            if params: raise ValueError()
                        elif method == 'tools/call':
                            if set(params) not in ({'name'}, {'name', 'arguments'}): raise ValueError()
                            params.setdefault('arguments', {})
                            self._arguments(params['name'], params['arguments'])
                        data['params'] = params
                        forwarded = SessionMessage(types.JSONRPCMessage.model_validate(data))
                        forwarded_possible = True
                        await sdk_send.send(forwarded)
                        if request_id is not None:
                            response = await sdk_receive.receive()
                            output = response.message.root.model_dump(by_alias=True, exclude_none=True)
                            bounded(output, MAX_OUTPUT_BYTES)
                            if 'error' in output: raise ValueError()
                            reply = SessionMessage(types.JSONRPCMessage.model_validate(output))
                        state = next_state
                    except Exception:
                        if request_id is not None:
                            reply = SessionMessage(types.JSONRPCMessage(types.JSONRPCError(
                                jsonrpc='2.0', id=request_id, error=types.ErrorData(
                                    code=-32603 if forwarded_possible else error_code,
                                    message=UNCERTAIN_ERROR if forwarded_possible else PROTOCOL_ERROR))))
                        # Invalid notifications/IDs have no safe reply correlation.
                    if reply is not None:
                        # Delivery failures escape: never retry an uncertain send.
                        await outgoing.send(reply)
            finally:
                group.cancel_scope.cancel()
