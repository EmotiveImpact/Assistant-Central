import json
import unittest
from unittest.mock import patch
import anyio
from mcp_bridge.bridge import bounded
from bridge_tests.test_bridge import BridgeTests as FixtureBase
from raw_bridge.codec import decode_record, encode_record, Rejected, RECORD_CAP, OUTPUT_CAP
from raw_bridge.transport import RawBridge, LocalFailure, MAX_RECORDS
from raw_bridge.memory import Reader, Writer, exchange, handshake, call
from facade_candidate import SnapshotPublisher

class CodecTests(unittest.TestCase):
    def reject(self, raw, code=None):
        with self.assertRaises(Rejected) as caught: decode_record(raw)
        if code is not None: self.assertEqual(caught.exception.code,code)
    def test_duplicate_keys_and_escaped_aliases(self):
        for raw in [b'{"id":1,"id":2}',b'{"id":1,"\\u0069d":2}',b'{"x":{"a":1,"a":2}}']:
            self.reject(raw,-32700)
    def test_nonfinite_and_invalid_utf8(self):
        for raw in [b'NaN',b'Infinity',b'-Infinity',b'\xff',b'"\xc0\x80"',b'\xef\xbb\xbf{}']:
            self.reject(raw,-32700)
        self.reject(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":1e999}}',-32600)
    def test_surrogates_and_non_scalar(self):
        self.reject(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"\\ud800"}}',-32600)
        value=decode_record(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"\\ud83d\\ude00"}}')
        self.assertEqual(value['params']['x'],'😀')
    def test_depth_checked_before_parser(self):
        with patch('raw_bridge.codec.json.loads',side_effect=AssertionError('parser called')):
            self.reject(b'['*10+b']'*10,-32700)
        self.assertEqual(decode_record(encode_record(call(1,'propose',{'text':'[{'*100}))[:-1])['id'],1)
    def test_batches_and_scalars(self):
        for value in [[],[{}],None,True,0,'x']: self.reject(json.dumps(value).encode(),-32600)
    def test_strict_ids(self):
        for value in [None,True,False,1.0,-1,2**31,'','a b','é','a'*65,{},[]]:
            self.reject(json.dumps({'jsonrpc':'2.0','id':value,'method':'ping'}).encode(),-32600)
        for value in [0,2**31-1,'A-z_09','x'*64]:
            self.assertEqual(decode_record(json.dumps({'jsonrpc':'2.0','id':value,'method':'ping'}).encode())['id'],value)
    def test_envelope_and_null_params(self):
        for field,value in [('owner',None),('jsonrpc',2),('method',False),('result',None)]:
            data={'jsonrpc':'2.0','id':1,'method':'ping',field:value}
            self.reject(json.dumps(data).encode(),-32600)
        self.reject(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":null}',-32602)
    def test_collection_node_integer_and_normalized_limits(self):
        for meta in [list(range(65)),{str(i):0 for i in range(65)},[[0]*64 for _ in range(8)],2**53,1e308]:
            # Finite exponent expansion is intentionally checked after normalization.
            raw=json.dumps({'jsonrpc':'2.0','id':1,'method':'ping','params':{'_meta':meta}}).encode()
            if meta == 1e308: self.assertEqual(decode_record(raw)['id'],1)
            else:self.reject(raw,-32600)
        # Input literal ASCII controls compactly escaped also has bounded normalized output.
        self.reject(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"'+b'\\u0000'*3000+b'"}}',-32700)
    def test_normalized_output_budget_is_independent(self):
        prefix=b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"n":1e-6,"x":"'
        suffix=b'"}}'
        raw=prefix+b'a'*(RECORD_CAP-len(prefix)-len(suffix))+suffix
        self.assertEqual(len(raw),RECORD_CAP)
        self.reject(raw,-32600)  # Python normalizes 1e-6 to 1e-06.
    def test_output_cap_includes_lf_exactly(self):
        self.assertEqual(len(encode_record({'x':'a'*(OUTPUT_CAP-9)})),OUTPUT_CAP)
        with self.assertRaises(Rejected):encode_record({'x':'a'*(OUTPUT_CAP-8)})
    def test_record_cap_precedes_decode(self):
        self.reject(b' '* (RECORD_CAP+1),-32700)
        raw=b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
        self.assertEqual(decode_record(raw+b' '*(RECORD_CAP-len(raw)))['id'],1)
    def test_output_limits_and_roundtrip(self):
        self.assertLessEqual(len(encode_record({'x':'x'*100})),OUTPUT_CAP)
        for value in [{'x':'x'*OUTPUT_CAP},{'x':'\ud800'},{'x':float('nan')},{'x':list(range(65))}]:
            with self.assertRaises(Rejected):encode_record(value)
    def test_notifications_are_silent_after_decoding(self):
        for data in [{'jsonrpc':'2.0','method':'tools/call','params':None},
                     {'jsonrpc':'2.0','method':'ping','owner':None}]:
            with self.assertRaises(Rejected) as caught:decode_record(json.dumps(data).encode())
            self.assertTrue(caught.exception.silent)

# Inherit setup helpers only; avoid rerunning the baseline test methods here.
class StreamTests(unittest.TestCase):
    setUp=FixtureBase.setUp
    tearDown=FixtureBase.tearDown
    run_async=FixtureBase.run_async
    count=FixtureBase.count
    prepare=FixtureBase.prepare
    def run_bytes(self,data,fragment=4096,reader=None,writer=None):
        async def check():
            out=writer if writer is not None else Writer()
            bridge=RawBridge(self.api)
            await bridge.run(reader or Reader(data,fragment),out)
            return out,bridge
        return anyio.run(check)
    def test_fragmented_coalesced_and_crlf(self):
        for fragment in [1,2,7,4096]:
            messages=handshake()+[call(1,'processed_inbox',{})]
            data=b''.join(encode_record(m)[:-1]+b'\r\n' for m in messages)
            out,b=self.run_bytes(data,fragment)
            self.assertEqual(len(out.records),2)
            self.assertEqual(json.loads(out.records[-1])['result']['structuredContent']['items'],[])
            self.assertEqual(b.facts.records,3)
    def test_empty_lines_and_partial_eof(self):
        out,b=self.run_bytes(b'\n\r\n'+encode_record({'jsonrpc':'2.0','id':1,'method':'ping'})[:-1])
        self.assertEqual(len(out.records),2)
        self.assertTrue(all(json.loads(x)['id'] is None for x in out.records))
        self.assertEqual(b.facts.termination,'partial_eof')
        self.assertEqual(b.facts.admitted_to_r3,0)
    def test_raw_record_budget_includes_ignored_and_malformed(self):
        for line in [b'\n',b'{"jsonrpc":"2.0","method":"unknown"}\n']:
            out,b=self.run_bytes(line*(MAX_RECORDS+1))
            self.assertEqual(b.facts.records,MAX_RECORDS)
            self.assertIn(b.facts.termination,['record_budget','r3_message_budget'])
    def test_oversized_record_stops_without_draining(self):
        reader=Reader(b'x'*(RECORD_CAP+10000))
        out,b=self.run_bytes(b'',reader=reader)
        self.assertEqual(b.facts.termination,'record_too_large')
        self.assertLess(reader.position,len(reader.data))
        self.assertEqual(len(out.records),1)
    def test_lying_and_empty_readers_fail_locally(self):
        for value in [b'x'*4097,'text',bytearray(b'x'),None,b'']:
            class BadReader:
                async def receive(self,n):return value
            with self.assertRaisesRegex(LocalFailure,'Raw bridge stopped'):
                self.run_bytes(b'',reader=BadReader())
    def test_writer_failure_no_retry_and_persistence_uncertain(self):
        async def check():
            class BadWriter(Writer):
                async def send(self,data):
                    self.records.append(data)
                    if len(self.records)==2:raise RuntimeError('SECRET')
            writer=BadWriter();b=RawBridge(self.api)
            with self.assertRaisesRegex(LocalFailure,'Raw bridge stopped'):
                await b.run(Reader(b''.join(encode_record(m) for m in handshake()+[call(1,'propose',{'text':'persisted'})])),writer)
            self.assertEqual(len(writer.records),2)
            self.assertEqual(self.count(),1)
            self.assertTrue(b.facts.output_uncertain)
            self.assertEqual(b.facts.output_accepted,1)
            self.assertTrue(b.facts.proposal_persistence_possible)
        self.run_async(check)
    def test_partial_write_return_rejected(self):
        class BadWriter:
            async def send(self,data):return 1
        with self.assertRaises(LocalFailure):self.run_bytes(encode_record({'jsonrpc':'2.0','id':1,'method':'ping'}),writer=BadWriter())
    def test_error_distinctions_and_notifications(self):
        messages=handshake()+[{'jsonrpc':'2.0','method':'tools/call','params':{'name':'propose','arguments':{'text':'silent'}}},
            {'jsonrpc':'2.0','id':1,'method':'unknown'},call(2,'propose',{}),call(3,'owner',{}),call(4,'propose',{'text':'x','actor':'bob'})]
        out,b=self.run_bytes(b''.join(encode_record(m) for m in messages))
        errors=[json.loads(r)['error']['code'] for r in out.records[1:]]
        self.assertEqual(errors,[-32601,-32602,-32602,-32602]);self.assertEqual(self.count(),0)
    def test_exact_text_replay_and_owner_separation(self):
        async def check():
            before={a:e.snapshot() for a,e in self.ep.items()}
            texts=['\x00'*1024,'"'*1024,'\\'*1024,'\n'*1024,'😀'*256,'exact \x00"\\\n']
            for text in texts:
                out,facts=await exchange(self.api,handshake()+[call(1,'propose',{'text':text}),call(2,'propose',{'text':text})],3)
                first=out[1]['result']['structuredContent']
                self.assertEqual(first,out[2]['result']['structuredContent'])
                self.assertEqual(self.owner.review(first['proposal_id'])['text'],text)
                self.assertEqual(first['state'],'pending')
            self.assertEqual(before,{a:e.snapshot() for a,e in self.ep.items()})
        self.run_async(check)
    def test_bytes_to_processed_inbox(self):
        async def check():
            out,_=await exchange(self.api,handshake()+[call(1,'propose',{'text':'untrusted \x00 text'})])
            proposal=out[1]['result']['structuredContent']
            command=self.prepare(proposal);release=self.ep['alice'].handle_owner(command)
            self.ep['bob'].handle_peer({'op':'deliver','value':release['packet']})
            publisher=SnapshotPublisher(self.stores['bob']);publisher.publish(self.ep['bob'].snapshot())
            out,_=await exchange(self.apis['bob'],handshake()+[call(1,'processed_inbox',{})])
            self.assertEqual(out[1]['result']['structuredContent']['items'],[])
            self.ep['bob'].handle_owner({'op':'process','operation_id':__import__('independent_peer.protocol',fromlist=['token']).token(),'id':release['id']})
            publisher.publish(self.ep['bob'].snapshot())
            out,_=await exchange(self.apis['bob'],handshake()+[call(1,'processed_inbox',{})])
            self.assertEqual(out[1]['result']['structuredContent']['items'][0]['payload'],'untrusted \x00 text')
        self.run_async(check)
    def test_cancellation_propagates_and_streams_not_closed(self):
        async def check():
            class WaitingReader:
                async def receive(self,n):await anyio.sleep_forever()
                async def aclose(self):raise AssertionError('caller stream closed')
            b=RawBridge(self.api)
            with anyio.move_on_after(.01) as scope:await b.run(WaitingReader(),Writer())
            self.assertTrue(scope.cancel_called)
            self.assertEqual(b.facts.termination,'cancelled')
        self.run_async(check)
    def test_raw_rejected_ids_are_consumed_and_types_distinct(self):
        messages=handshake()+[
            {'jsonrpc':'2.0','id':1,'method':'tools/call','params':'bad'},
            call(1,'propose',{'text':'must not persist'}),
            call('1','propose',{'text':'string ID differs'})]
        out,b=self.run_bytes(b''.join(encode_record(m) for m in messages))
        replies=[json.loads(r) for r in out.records]
        self.assertEqual(replies[1]['error']['code'],-32602)
        self.assertEqual(replies[2]['error']['code'],-32600)
        self.assertEqual(replies[3]['result']['structuredContent']['state'],'pending')
        self.assertEqual(self.count(),1)
    def test_safe_id_budget_includes_raw_rejections(self):
        messages=[{'jsonrpc':'2.0','id':i,'method':'ping','params':None} for i in range(128)]
        messages.append({'jsonrpc':'2.0','id':128,'method':'ping'})
        out,b=self.run_bytes(b''.join(encode_record(m) for m in messages))
        self.assertEqual(json.loads(out.records[-1])['error']['code'],-32600)
        self.assertEqual(b.facts.admitted_to_r3,0)
    def test_duplicate_key_does_not_trust_id(self):
        data=b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n'
        data+=encode_record({'jsonrpc':'2.0','id':1,'method':'ping'})
        out,b=self.run_bytes(data)
        self.assertIsNone(json.loads(out.records[0])['id'])
        self.assertEqual(json.loads(out.records[1])['result'],{})
    def test_reader_failure_preserves_prior_output_facts(self):
        async def check():
            class BrokenReader:
                calls=0
                async def receive(self,n):
                    self.calls+=1
                    if self.calls==1:return encode_record({'jsonrpc':'2.0','id':1,'method':'ping'})
                    raise RuntimeError('SECRET')
            b=RawBridge(self.api);writer=Writer()
            with self.assertRaisesRegex(LocalFailure,'Raw bridge stopped'):
                await b.run(BrokenReader(),writer)
            self.assertEqual(b.facts.output_accepted,1)
            self.assertFalse(b.facts.output_uncertain)
            self.assertEqual(json.loads(writer.records[0])['result'],{})
        self.run_async(check)
    def test_raw_output_failure_uses_fixed_uncertain_error(self):
        async def check():
            def limited(value):
                if 'result' in value:raise Rejected(-32603)
                return encode_record(value)
            with patch('raw_bridge.transport.encode_record',side_effect=limited):
                writer=Writer();b=RawBridge(self.api)
                await b.run(Reader(encode_record({'jsonrpc':'2.0','id':1,'method':'ping'})),writer)
            reply=json.loads(writer.records[0])
            self.assertEqual(reply['error']['code'],-32603)
            self.assertEqual(reply['error']['message'],'Operation outcome unavailable; local proposal persistence may be uncertain.')
            self.assertEqual(b.facts.output_attempts,1)
        self.run_async(check)
    def test_coercible_ids_cannot_persist(self):
        messages=handshake()+[call(i,'propose',{'text':'unsafe'}) for i in [True,1.0,None]]
        messages.append(call(1,'propose',{'text':'safe'}))
        out,b=self.run_bytes(b''.join(encode_record(m) for m in messages))
        replies=[json.loads(r) for r in out.records]
        self.assertEqual([r['id'] for r in replies[1:4]],[None,None,None])
        self.assertEqual(replies[4]['result']['structuredContent']['state'],'pending')
        self.assertEqual(self.count(),1)
    def test_real_sdk_client_over_fragmented_utf8_lf_bytes(self):
        # Independent client JSON/LF pumps intentionally do not use server codec.
        from mcp import ClientSession, types
        from mcp.shared.message import SessionMessage
        async def check():
            client_send, serialize_read = anyio.create_memory_object_stream(0)
            parse_send, client_read = anyio.create_memory_object_stream(0)
            request_send, request_read = anyio.create_memory_object_stream(0)
            response_send, response_read = anyio.create_memory_object_stream(0)
            request_fragments=[]; response_fragments=[]
            class ByteReader:
                async def receive(self,n):
                    chunk=await request_read.receive()
                    self_test.assertLessEqual(len(chunk),n)
                    return chunk
            class ByteWriter:
                async def send(self,data):
                    # Writer accepts a full message, then the channel fragments it.
                    for offset in range(0,len(data),5):
                        part=data[offset:offset+5]
                        response_fragments.append(part)
                        await response_send.send(part)
            async def serialize_requests():
                async for message in serialize_read:
                    value=message.message.root.model_dump(by_alias=True,exclude_none=True)
                    record=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
                    for offset in range(0,len(record),3):
                        part=record[offset:offset+3]
                        request_fragments.append(part)
                        await request_send.send(part)
            async def parse_responses():
                pending=bytearray()
                async for part in response_read:
                    pending.extend(part)
                    while b'\n' in pending:
                        record,_,remaining=pending.partition(b'\n')
                        pending[:]=remaining
                        value=json.loads(record.decode('utf-8'))
                        await parse_send.send(SessionMessage(types.JSONRPCMessage.model_validate(value)))
            self_test=self
            bridge=RawBridge(self.api)
            before={a:e.snapshot() for a,e in self.ep.items()}
            async with client_send,serialize_read,parse_send,client_read,request_send,request_read,response_send,response_read,anyio.create_task_group() as group:
                group.start_soon(serialize_requests)
                group.start_soon(parse_responses)
                group.start_soon(bridge.run,ByteReader(),ByteWriter())
                async with ClientSession(client_read,client_send) as session:
                    initialized=await session.initialize()
                    self.assertEqual(initialized.protocolVersion,'2025-11-25')
                    await session.send_ping()
                    listed=await session.list_tools()
                    self.assertEqual([tool.name for tool in listed.tools],['propose','proposal_status','processed_inbox'])
                    text='exact 😀 text \x00"\\\n'
                    result=await session.call_tool('propose',{'text':text})
                    self.assertFalse(result.isError)
                    proposal=result.structuredContent
                    self.assertEqual(self.owner.review(proposal['proposal_id'])['text'],text)
                    status=await session.call_tool('proposal_status',{'proposal_id':proposal['proposal_id']})
                    self.assertEqual(status.structuredContent,proposal)
                    inbox=await session.call_tool('processed_inbox',{})
                    self.assertEqual(inbox.structuredContent['items'],[])
                    self.assertEqual(before,{a:e.snapshot() for a,e in self.ep.items()})
                group.cancel_scope.cancel()
            self.assertGreater(len(request_fragments),7)
            self.assertGreater(len(response_fragments),6)
            self.assertEqual(bridge.facts.admitted_to_r3,7)
            self.assertEqual(bridge.facts.output_attempts,6)
            # SDK receipt is checked above; cancellation may occur before send's
            # return checkpoint, so acceptance is not assumed to be fully drained.
            self.assertLessEqual(bridge.facts.output_accepted,6)
        self.run_async(check)
    def test_single_use(self):
        async def check():
            b=RawBridge(self.api);await b.run(Reader(b''),Writer())
            with self.assertRaises(LocalFailure):await b.run(Reader(b''),Writer())
        self.run_async(check)

# Keep the imported fixture class out of unittest discovery.
del FixtureBase
