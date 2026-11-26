"""Caller-owned async byte streams to the offline SDK adapter. LF records only."""
from dataclasses import dataclass
import anyio
from mcp import types
from mcp_raw_codec import decode_record, encode_record
from restricted_host_protocol import MAX_INPUT
from mcp_proposal_adapter import MAX_MESSAGES

READ_CHUNK = 4096


@dataclass(frozen=True)
class BridgeEnd:
    reason: str
    outcome_unknown: bool


class _Output:
    def __init__(self, stream):
        self.stream = stream
        self.lock = anyio.Lock()

    async def raw(self, data):
        async with self.lock:
            await self.stream.send(data + b'\n')

    async def send(self, item):
        await self.raw(encode_record(item.message.model_dump(mode='json', exclude_none=True)))


class _Input:
    def __init__(self, stream, output):
        self.stream, self.output = stream, output
        self.reason = 'session_ended'
        self.admitted = False

    def __aiter__(self):
        return self.records()

    async def records(self):
        pending = bytearray()
        count = 0
        while True:
            limit = min(READ_CHUNK, MAX_INPUT + 1 - len(pending))
            try:
                chunk = await self.stream.receive(limit)
            except anyio.EndOfStream:
                chunk = b''
            if type(chunk) is not bytes or len(chunk) > limit:
                self.reason = 'input_failed'
                return
            if not chunk:
                self.reason = 'partial_eof' if pending else 'eof'
                return
            start = 0
            while True:
                end = chunk.find(b'\n', start)
                fragment = chunk[start:] if end < 0 else chunk[start:end]
                if len(pending) + len(fragment) > MAX_INPUT:
                    self.reason = 'oversize_frame'
                    return
                pending.extend(fragment)
                if end < 0:
                    break
                count += 1
                if count > MAX_MESSAGES:
                    self.reason = 'message_limit'
                    return
                decoded = decode_record(bytes(pending))
                pending.clear()
                if decoded.error is not None:
                    await self.output.raw(decoded.error)
                elif decoded.message is not None:
                    if isinstance(decoded.message.message.root, types.JSONRPCRequest):
                        self.admitted = True
                    yield decoded.message
                start = end + 1


async def serve_lf(reader, writer, adapter):
    """Run a single pre-bound adapter without closing caller-owned endpoints.

    reader.receive(n) returns <= n bytes or raises EndOfStream. writer.send(bytes)
    must send the whole value or raise; this is NOT a partial OS write API.
    Cancellation propagates, never retries, and means prior outcomes are unknown.
    Errors are fixed local reports, not exception diagnostics. Peer errors are
    fixed bounded JSON. Deadlines/admission/lifetime/log policy belong to caller.
    """
    output = _Output(writer)
    incoming = _Input(reader, output)
    try:
        await adapter.run(incoming, output)
    except Exception:
        return BridgeEnd('stream_or_session_failed', incoming.admitted)
    return BridgeEnd(incoming.reason, incoming.admitted)
