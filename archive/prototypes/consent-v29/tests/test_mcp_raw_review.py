"""Independent raw-byte boundary review; fictional in-memory streams only."""
import copy
import json
import unittest
from unittest.mock import patch
import anyio
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage
from mcp_raw_codec import decode_record, encode_record
from mcp_lf_bridge import serve_lf, READ_CHUNK
from mcp_proposal_adapter import ProposalMCPAdapter
from restricted_host_protocol import MAX_INPUT, MAX_OUTPUT
from task_fixtures import fixture


def wire(method, ident=1, **params):
    return json.dumps(dict(jsonrpc='2.0', method=method, id=ident, params=params), ensure_ascii=False).encode()

INIT = wire('initialize', 'init', protocolVersion='2025-11-25', capabilities={}, clientInfo={'name':'review','version':'1'})
READY = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'


class Reader:
    def __init__(self, data, size=4096):
        self.data, self.size, self.limits = data, size, []
        self.closed = False
    async def receive(self, n):
        self.limits.append(n)
        result, self.data = self.data[:min(n,self.size)], self.data[min(n,self.size):]
        await anyio.sleep(0)
        return result
    async def aclose(self): self.closed = True

class Writer:
    def __init__(self): self.data, self.closed = [], False
    async def send(self, data): self.data.append(data)
    async def aclose(self): self.closed = True


class RawIndependentReview(unittest.TestCase):
    def test_invalid_ids_are_not_coerced_and_error_id_is_null(self):
        for ident in (True, False, None, 1.0, 1.5, [], {}, 9007199254740992, '🙂'*65):
            with self.subTest(ident=ident):
                result = decode_record(wire('ping', ident))
                self.assertIsNone(result.message)
                self.assertIsNone(json.loads(result.error)['id'])
        for spelling in ('1e0','1E-0','-0.0'):
            self.assertIsNone(json.loads(decode_record(b'{"jsonrpc":"2.0","method":"ping","id":'+spelling.encode()+b'}').error)['id'])

    def test_cancellation_ids_share_pre_sdk_limits_and_notifications_stay_silent(self):
        for ident in (True,1.0,None,9007199254740992,'🙂'*65):
            result=decode_record(json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':ident}}).encode())
            self.assertIsNone(result.message)
            self.assertIsNone(result.error)
        for ident in ('',-9007199254740991,'🙂'*64):
            result=decode_record(json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':ident}}).encode())
            self.assertEqual(result.message.message.root.params['requestId'],ident)

    def test_valid_ids_preserved_on_invalid_envelopes(self):
        for ident in ('', '请求/🙂', -9007199254740991):
            result = decode_record(json.dumps({'jsonrpc':'wrong','method':'ping','id':ident}).encode())
            self.assertEqual(json.loads(result.error)['id'], ident)

    def test_duplicate_escaped_keys_nonfinite_utf8_and_trailing_garbage(self):
        for value in (b'{"id":1,"\\u0069d":2}', b'{"x":{"x":1,"x":2}}', b'{"x":NaN}', b'{"x":1e999}', b'\xff', b'{}x', b'"\\ud800"', b'\xef\xbb\xbf{}'):
            result = decode_record(value)
            self.assertIsNone(result.message)
            self.assertEqual(json.loads(result.error)['error']['code'], -32700)

    def test_recognizable_notifications_silent_despite_invalid_envelope(self):
        for method in ('tools/call','initialize','notifications/cancelled','alien'):
            for params in (None, [], True, 'secret'):
                result = decode_record(json.dumps({'jsonrpc':'2.0','method':method,'params':params}).encode())
                self.assertIsNone(result.error)
                self.assertIsNone(result.message)

    def test_exact_input_bytes_and_unicode_output_bounds(self):
        data = wire('ping')
        self.assertIsNotNone(decode_record(data+b' '*(MAX_INPUT-len(data))).message)
        self.assertIsNotNone(decode_record(data+b' '*(MAX_INPUT+1-len(data))).error)
        text = '🙂' * 10
        encoded = encode_record(text)
        self.assertEqual(len(encoded),42)
        self.assertEqual(encode_record(text,42),encoded)
        with self.assertRaises(ValueError): encode_record(text,41)
        self.assertNotIn(b'\n',encode_record({'x':'\n'}))

    def test_application_types_survive_raw_decode(self):
        for value in (True, 1.0, 1, '1', None):
            result = decode_record(wire('tools/call',name='propose',arguments={'payload':value}))
            actual = result.message.message.root.params['arguments']['payload']
            self.assertIs(type(actual),type(value))

    def test_depth_and_node_exact_boundaries(self):
        # Root depth is zero; scalar at depth 32 is accepted by tree guard.
        value = 1
        for _ in range(32): value = [value]
        self.assertEqual(encode_record(value),json.dumps(value,separators=(',',':')).encode())
        with self.assertRaises(ValueError): encode_record([value])
        self.assertTrue(encode_record([0]*2047))
        with self.assertRaises(ValueError): encode_record([0]*2048)
        # Lexical nesting inside strings does not count as depth.
        self.assertIsNotNone(decode_record(wire('ping', note='['*200+'\\"'+']'*200)).message)

    def run_bridge(self,data,size=4096,writer=None):
        calls=[]
        def dispatch(command):
            calls.append(copy.deepcopy(command))
            return {'messages':[],'payload_trust':'untrusted_inert'}
        reader=Reader(data,size)
        writer=writer or Writer()
        adapter=ProposalMCPAdapter(fixture()[0],'alice',dispatch)
        async def run():
            with anyio.fail_after(3): return await serve_lf(reader,writer,adapter)
        end=anyio.run(run)
        self.assertFalse(reader.closed)
        self.assertFalse(writer.closed)
        self.assertTrue(all(0<n<=READ_CHUNK for n in reader.limits))
        self.assertTrue(adapter._binding.application_call('inbox',{})['isError'])
        return end,b''.join(writer.data),calls

    def test_fragmentation_eof_loss_is_conservative_and_partial_eof_not_admitted(self):
        data=b'\n'.join((b'\xff',b'{"x":NaN}',wire('ping','请求/🙂'),b'{"jsonrpc":"2.0","method":"alien"}'))+b'\n'
        for size in (1,2,7,4096):
            end,out,calls=self.run_bridge(data,size)
            self.assertEqual(end.reason,'eof')
            self.assertEqual(calls,[])
            records=list(map(json.loads,out.splitlines()))
            self.assertEqual([x.get('id') for x in records[:2]],[None,None])
            self.assertIn([x.get('id') for x in records[2:]],[[],['请求/🙂']])
            self.assertTrue(end.outcome_unknown)
        end,out,calls=self.run_bridge(wire('ping'))
        self.assertEqual((end.reason,out,calls),('partial_eof',b'',[]))

    def test_lf_exact_size_cr_counts_and_oversize_stops(self):
        base=wire('ping')
        for suffix,reason in ((b'\n','eof'),(b'\r\n','oversize_frame'),(b'','partial_eof')):
            end,out,calls=self.run_bridge(base+b' '*(MAX_INPUT-len(base))+suffix)
            self.assertEqual(end.reason,reason)
        end,out,calls=self.run_bridge(b'x'*(MAX_INPUT+1)+b'\n'+INIT+b'\n'+READY+b'\n'+wire('tools/call',name='inbox',arguments={})+b'\n')
        self.assertEqual((end.reason,out,calls),('oversize_frame',b'',[]))

    def test_malformed_frames_consume_admission_budget(self):
        with patch('mcp_lf_bridge.MAX_MESSAGES',2):
            end,out,calls=self.run_bridge(b'bad\nbad\nbad\n'+INIT+b'\n')
        self.assertEqual(end.reason,'message_limit')
        self.assertEqual(len(out.splitlines()),2)
        self.assertEqual(calls,[])

    def test_output_exception_is_fixed_and_external_streams_stay_owned(self):
        class Fail(Writer):
            async def send(self,data): raise OSError('PRIVATE detail')
        end,out,calls=self.run_bridge(b'bad\n',writer=Fail())
        self.assertEqual(end.reason,'stream_or_session_failed')
        self.assertNotIn('PRIVATE',repr(end))
        self.assertEqual((out,calls),(b'',[]))

class LiveRawIndependentReview(unittest.TestCase):
    def test_sdk_client_across_independent_byte_codec(self):
        async def run():
            calls=[]
            def dispatch(command):
                calls.append(command)
                return {'messages':[],'payload_trust':'untrusted_inert'}
            to_bridge, inbound = anyio.create_memory_object_stream(0)
            output, from_bridge = anyio.create_memory_object_stream(0)
            to_client, client_input = anyio.create_memory_object_stream(0)
            class ByteReader:
                pending=b''
                async def receive(self,n):
                    if not self.pending: self.pending=await inbound.receive()
                    chunk,self.pending=self.pending[:min(n,3)],self.pending[min(n,3):]
                    return chunk
            class ClientWriter:
                async def __aenter__(self): return self
                async def __aexit__(self,*args): pass
                async def send(self,item):
                    # Deliberately not the production codec.
                    await to_bridge.send(json.dumps(item.message.model_dump(mode='json',exclude_none=True),ensure_ascii=False,allow_nan=False).encode()+b'\n')
            async def decode_output():
                async for data in from_bridge:
                    for line in data.splitlines():
                        await to_client.send(SessionMessage(types.JSONRPCMessage.model_validate(json.loads(line))))
            adapter=ProposalMCPAdapter(fixture()[0],'alice',dispatch)
            try:
                with anyio.fail_after(3):
                    async with anyio.create_task_group() as group:
                        group.start_soon(serve_lf,ByteReader(),output,adapter)
                        group.start_soon(decode_output)
                        async with ClientSession(client_input,ClientWriter()) as client:
                            await client.initialize()
                            self.assertEqual({t.name for t in (await client.list_tools()).tools},{'propose','proposal_status','inbox'})
                            self.assertFalse((await client.call_tool('inbox',{})).isError)
                        group.cancel_scope.cancel()
            finally:
                for endpoint in (to_bridge,inbound,output,from_bridge,to_client,client_input): await endpoint.aclose()
            self.assertEqual(calls,[{'method':'inbox'}])
        anyio.run(run)

    def test_live_open_fragmentation_and_coalescing_preserve_responses(self):
        async def run():
            for size in (1,2,7,4096):
                tx,rx=anyio.create_memory_object_stream(0)
                out,replies=anyio.create_memory_object_stream(4)
                class ByteReader:
                    pending=b''
                    async def receive(self,n):
                        if not self.pending: self.pending=await rx.receive()
                        k=min(size,n)
                        value,self.pending=self.pending[:k],self.pending[k:]
                        return value
                adapter=ProposalMCPAdapter(fixture()[0],'alice',lambda command: None)
                try:
                    with anyio.fail_after(3):
                        async with anyio.create_task_group() as group:
                            group.start_soon(serve_lf,ByteReader(),out,adapter)
                            await tx.send(b'bad\n'+wire('ping','请求/🙂')+b'\n'+b'{"jsonrpc":"2.0","method":"alien","params":[]}\n'+wire('ping',9)+b'\n')
                            records=[json.loads(await replies.receive()) for _ in range(3)]
                            self.assertEqual([r['id'] for r in records],[None,'请求/🙂',9])
                            self.assertEqual(records[-1]['result'],{})
                            group.cancel_scope.cancel()
                finally:
                    for endpoint in (tx,rx,out,replies): await endpoint.aclose()
        anyio.run(run)

    def test_output_loss_after_commit_returns_unknown_without_replay(self):
        async def run():
            calls=[]
            def dispatch(command):
                calls.append(command)
                return {'messages':[],'payload_trust':'untrusted_inert'}
            tx,rx=anyio.create_memory_object_stream(0)
            initial=anyio.Event()
            class ByteReader:
                pending=b''
                async def receive(self,n):
                    if not self.pending: self.pending=await rx.receive()
                    value,self.pending=self.pending[:n],self.pending[n:]
                    return value
            class LoseAfterInit:
                count=0
                async def send(self,value):
                    self.count+=1
                    if self.count==1: initial.set()
                    else: raise BrokenPipeError('PRIVATE postcommit loss')
            adapter=ProposalMCPAdapter(fixture()[0],'alice',dispatch)
            result=[]
            async def serve(): result.append(await serve_lf(ByteReader(),LoseAfterInit(),adapter))
            try:
                with anyio.fail_after(3):
                    async with anyio.create_task_group() as group:
                        group.start_soon(serve)
                        await tx.send(INIT+b'\n')
                        await initial.wait()
                        await tx.send(READY+b'\n'+wire('tools/call',name='inbox',arguments={})+b'\n')
                self.assertEqual(calls,[{'method':'inbox'}])
                self.assertEqual(result[0].reason,'stream_or_session_failed')
                self.assertTrue(result[0].outcome_unknown)
                self.assertNotIn('PRIVATE',repr(result))
                self.assertTrue(adapter._binding.application_call('inbox',{})['isError'])
            finally:
                for endpoint in (tx,rx): await endpoint.aclose()
        anyio.run(run)

    def test_cancel_after_commit_with_blocked_output_never_replays(self):
        async def run():
            calls=[]
            committed=anyio.Event()
            def dispatch(command):
                calls.append(command)
                committed.set()
                return {'messages':[],'payload_trust':'untrusted_inert'}
            tx,rx=anyio.create_memory_object_stream(0)
            output,reply=anyio.create_memory_object_stream(0)
            class ByteReader:
                pending=b''
                async def receive(self,n):
                    if not self.pending: self.pending=await rx.receive()
                    result,self.pending=self.pending[:n],self.pending[n:]
                    return result
            adapter=ProposalMCPAdapter(fixture()[0],'alice',dispatch)
            try:
                with anyio.fail_after(3):
                    async with anyio.create_task_group() as group:
                        group.start_soon(serve_lf,ByteReader(),output,adapter)
                        await tx.send(INIT+b'\n')
                        await reply.receive()
                        await tx.send(READY+b'\n'+wire('tools/call',name='inbox',arguments={})+b'\n')
                        await committed.wait()
                        group.cancel_scope.cancel()
                self.assertEqual(calls,[{'method':'inbox'}])
                self.assertTrue(adapter._binding.application_call('inbox',{})['isError'])
                with self.assertRaises(RuntimeError): await adapter.run(rx,output)
            finally:
                for endpoint in (tx,rx,output,reply): await endpoint.aclose()
        anyio.run(run)


if __name__=='__main__': unittest.main()
