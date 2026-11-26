"""Sequential synthetic-byte adapter. Caller retains stream ownership."""
from dataclasses import dataclass
import anyio
from mcp import types
from mcp.shared.message import SessionMessage
from mcp_bridge.bridge import OfflineBridge, MAX_REQUESTS
from .codec import RECORD_CAP, Rejected, decode_record, encode_record, error_record

READ_CHUNK = 4096
MAX_RECORDS = 160

class LocalFailure(RuntimeError):
    """Fixed local failure; no raw exception is exposed."""

@dataclass
class Facts:
    termination: str = 'not_started'
    records: int = 0
    admitted_to_r3: int = 0
    output_attempts: int = 0
    output_accepted: int = 0
    output_uncertain: bool = False
    proposal_persistence_possible: bool = False
    partial_eof_bytes: int = 0

class RawBridge:
    def __init__(self, facade):
        self._bridge = OfflineBridge(facade)
        self.facts = Facts()
        self._used = False

    async def run(self, reader, writer):
        if self._used: raise LocalFailure('Raw bridge is single-use.')
        self._used = True
        self.facts.termination = 'running'
        pending = bytearray()
        chunk = b''
        offset = 0
        facts = self.facts
        seen_ids = set()

        def consume_id(request_id):
            if request_id is None: return
            key = (type(request_id), request_id)
            if key in seen_ids or len(seen_ids) >= MAX_REQUESTS:
                raise Rejected(-32600, request_id)
            seen_ids.add(key)

        async def write(data):
            facts.output_attempts += 1
            try:
                result = await writer.send(data)
                if result is not None: raise LocalFailure('Byte writer contract failed.')
            except BaseException:
                facts.output_uncertain = True
                facts.termination = 'output_failure'
                raise
            facts.output_accepted += 1

        class Incoming:
            async def receive(inner):
                nonlocal chunk, offset
                while facts.records < MAX_RECORDS:
                    if offset == len(chunk):
                        try: chunk = await reader.receive(READ_CHUNK)
                        except anyio.EndOfStream:
                            facts.partial_eof_bytes = len(pending)
                            facts.termination = 'partial_eof' if pending else 'eof'
                            raise
                        if type(chunk) is not bytes or not 0 < len(chunk) <= READ_CHUNK:
                            facts.termination = 'reader_contract_failure'
                            raise LocalFailure('Byte reader contract failed.')
                        offset = 0
                    end = chunk.find(b'\n', offset)
                    stop = len(chunk) if end < 0 else end
                    size = stop - offset
                    if len(pending) + size > RECORD_CAP:
                        # Fail closed immediately. Do not accumulate or drain oversized input.
                        facts.records += 1
                        facts.termination = 'record_too_large'
                        await write(error_record(Rejected(-32700)))
                        raise anyio.EndOfStream
                    pending.extend(chunk[offset:stop])
                    offset = stop if end < 0 else end + 1
                    if end < 0: continue
                    record = bytes(pending)
                    pending.clear()
                    facts.records += 1
                    try:
                        value = decode_record(record)
                        consume_id(value.get('id'))
                        message = SessionMessage(types.JSONRPCMessage.model_validate(value))
                    except Rejected as exc:
                        # Raw rejections consume safe IDs too; undecodable JSON has none.
                        try: consume_id(exc.request_id)
                        except Rejected as duplicate: exc = duplicate
                        if not exc.silent: await write(error_record(exc))
                        continue
                    except Exception:
                        # Envelope was checked before SDK construction; fixed fallback only.
                        if 'id' in value: await write(error_record(Rejected(-32600, value['id'])))
                        continue
                    facts.admitted_to_r3 += 1
                    if value.get('method') == 'tools/call' and value.get('params',{}).get('name') == 'propose':
                        facts.proposal_persistence_possible = True
                    return message
                facts.termination = 'record_budget'
                raise anyio.EndOfStream

        class Outgoing:
            async def send(inner, message):
                data = message.message.root.model_dump(by_alias=True, exclude_none=True)
                try: encoded = encode_record(data)
                except Rejected:
                    encoded = encode_record({'jsonrpc':'2.0','id':data.get('id'), 'error':{
                        'code':-32603,'message':'Operation outcome unavailable; local proposal persistence may be uncertain.'}})
                await write(encoded)

        try:
            await self._bridge.run(Incoming(), Outgoing())
            if facts.termination == 'running': facts.termination = 'r3_message_budget'
        except BaseException as exc:
            if isinstance(exc, anyio.get_cancelled_exc_class()):
                facts.termination = 'cancelled'
                raise
            if facts.termination == 'running': facts.termination = 'local_failure'
            # Exception groups may hold stream failures; never retry a write.
            raise LocalFailure('Raw bridge stopped; local outcome may be uncertain.') from None
        return facts
