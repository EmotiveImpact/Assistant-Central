"""Raw bytes and actual SDK client over in-memory byte endpoints, offline only."""
import json
import unittest
import anyio
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage
from generic_demo import fixture
from mcp_proposal_adapter import create_proposal_server
from mcp_raw_codec import decode_record, encode_record
from mcp_lf_bridge import serve_lf


class Reader:
    def __init__(self, stream):
        self.stream, self.pending = stream, b''
    async def receive(self, n):
        if not self.pending:
            self.pending = await self.stream.receive()
        result, self.pending = self.pending[:n], self.pending[n:]
        return result


class CodecTests(unittest.TestCase):
    def test_bad_json(self):
        for value in (b'{', b'\xff', b'{"id":1,"id":2}', b'NaN', b'1e999',
                      b'"\\ud800"', b'['*40+b']'*40, b' '*16385):
            with self.subTest(value=value[:40]):
                error = json.loads(decode_record(value).error)
                self.assertEqual(error['error']['code'], -32700)
                self.assertIsNone(error['id'])
                self.assertNotIn('ud800',error['error']['message'])

    def test_ids(self):
        for ident in ('true','false','1.0','1e0','null','9007199254740992','"\\ud800"'):
            self.assertIsNotNone(decode_record(('{"jsonrpc":"2.0","method":"ping","id":'+ident+'}').encode()).error)
        for ident in ('0','-9007199254740991','""','"x !"'):
            self.assertIsNotNone(decode_record(('{"jsonrpc":"2.0","method":"ping","id":'+ident+'}').encode()).message)

    def test_invalid_notification_silent_and_error_id(self):
        self.assertEqual(decode_record(b'{"method":"tools/call","params":false}').error, None)
        self.assertEqual(json.loads(decode_record(b'{"id":"safe","method":2}').error)['id'],'safe')

    def test_integer_types_and_metadata(self):
        raw = b'{"jsonrpc":"2.0","method":"tools/call","id":1,"extra":{"inert":true},"params":{"name":"propose","arguments":{"a":2.0,"b":2e0,"c":true,"d":2},"_meta":{"note":"ok"}}}'
        args = decode_record(raw).message.message.root.params['arguments']
        self.assertEqual([type(args[k]) for k in 'abcd'], [float,float,bool,int])

    def test_output_unicode_escaping_and_limit(self):
        raw = encode_record({'x':'雪\n😀\t"\\'})
        self.assertNotIn(b'\n', raw)
        self.assertEqual(json.loads(raw)['x'],'雪\n😀\t"\\')
        with self.assertRaises(ValueError): encode_record({'x':'a'*32768})

    def test_node_limit(self):
        self.assertIsNotNone(decode_record(b'['+b'0,'*2048+b'0]').error)


class BridgeTests(unittest.TestCase):
    def run_case(self, scenario):
        async def run():
            task, _, request, _ = fixture()
            calls = []
            def callback(command):
                calls.append(command)
                return {'messages':[], 'payload_trust':'untrusted_inert'}
            adapter = create_proposal_server(task,'alice',callback)
            send, incoming = anyio.create_memory_object_stream(0)
            outgoing, receive = anyio.create_memory_object_stream(0)
            done = []
            async def server(): done.append(await serve_lf(Reader(incoming),outgoing,adapter))
            async with send, incoming, outgoing, receive, anyio.create_task_group() as group:
                group.start_soon(server)
                with anyio.fail_after(5):
                    await scenario(send, receive, calls, done)
                group.cancel_scope.cancel()
        anyio.run(run)

    def test_fragmented_coalesced_and_duplicate(self):
        async def scenario(send, receive, calls, done):
            await send.send(b'{"jsonrpc":')
            await send.send(b'"2.0","method":"ping","id":1}\n{"jsonrpc":"2.0","method":"ping","id":1}\n')
            results = [json.loads(await receive.receive()),json.loads(await receive.receive())]
            self.assertEqual(sum('error' in r for r in results),1)
            self.assertEqual(calls,[])
        self.run_case(scenario)

    def test_partial_eof_and_oversize(self):
        for data,reason in ((b'{','partial_eof'),(b'x'*16385,'oversize_frame')):
            async def scenario(send, receive, calls, done):
                await send.send(data)
                await send.aclose()
                while not done: await anyio.sleep(0)
                self.assertEqual(done[0].reason,reason)
                self.assertFalse(done[0].outcome_unknown)
                self.assertEqual(calls,[])
            self.run_case(scenario)

    def test_actual_sdk_client(self):
        async def scenario(send, receive, calls, done):
            to_client, client_read = anyio.create_memory_object_stream(0)
            client_write, from_client = anyio.create_memory_object_stream(0)
            async def ingress():
                async for frame in receive:
                    await to_client.send(SessionMessage(types.JSONRPCMessage.model_validate_json(frame)))
            async def egress():
                async for message in from_client:
                    await send.send(encode_record(message.message.model_dump(mode='json',exclude_none=True))+b'\n')
            async with to_client, client_read, client_write, from_client, anyio.create_task_group() as group:
                group.start_soon(ingress)
                group.start_soon(egress)
                async with ClientSession(client_read,client_write) as client:
                    await client.initialize()
                    self.assertEqual([t.name for t in (await client.list_tools()).tools],['propose','proposal_status','inbox'])
                    self.assertFalse((await client.call_tool('inbox',{})).isError)
                    self.assertTrue((await client.call_tool('inbox',{'owner':True})).isError)
                    self.assertEqual(calls,[{'method':'inbox'}])
                    for numeric in (True, 2.0):
                        request = fixture()[2]
                        request['payload']['max_items'] = numeric
                        result = await client.call_tool('propose',{'proposal_id':'lexical','envelope':request})
                        self.assertTrue(result.isError)
                    self.assertEqual(calls,[{'method':'inbox'}])
                group.cancel_scope.cancel()
        self.run_case(scenario)

    def test_null_error_then_ping(self):
        async def scenario(send, receive, calls, done):
            await send.send(b'not-json\n{"jsonrpc":"2.0","method":"ping","id":"ok"}\n')
            self.assertIsNone(json.loads(await receive.receive())['id'])
            self.assertEqual(json.loads(await receive.receive())['id'],'ok')
        self.run_case(scenario)
