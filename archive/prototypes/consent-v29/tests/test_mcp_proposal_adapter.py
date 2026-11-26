"""SDK interoperability in memory only; no native host, socket or account."""
import copy
import json
import unittest
from contextlib import ExitStack

import anyio
from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage
from generic_demo import fixture
from network import Denied, digest
from mcp_proposal_adapter import create_proposal_server, SUPPORTED_VERSIONS
import test_agent_proposals as baseline


class SDKClient:
    def __init__(self, stack, adapter):
        self.portal = stack.enter_context(start_blocking_portal())
        async def session(*, task_status):
            send, server_read = anyio.create_memory_object_stream(0)
            server_write, receive = anyio.create_memory_object_stream(0)
            stop = anyio.Event()
            async with send, server_read, server_write, receive, anyio.create_task_group() as group:
                group.start_soon(adapter.run, server_read, server_write)
                async with ClientSession(receive, send, client_info=types.Implementation(
                        name='fictional-sdk-peer', version='1', title='Fictional offline peer')) as client:
                    result = await client.initialize()
                    task_status.started((client, result, stop))
                    await stop.wait()
                group.cancel_scope.cancel()
        self.future, (self.client, self.initialize, stop) = self.portal.start_task(session)
        stack.callback(lambda: self.future.result(timeout=5))
        stack.callback(lambda: self.portal.call(stop.set))

    def raw_call(self, name, arguments):
        return self.portal.call(self.client.call_tool, name, arguments)

    def call(self, command):
        result = self.raw_call(command['method'], {k:v for k,v in command.items() if k != 'method'})
        if result.isError:
            raise Denied('Restricted operation failed')
        return json.loads(result.content[0].text)

    def propose(self, envelope, proposal_id='proposal-one'):
        return self.call({'method':'propose','proposal_id':proposal_id,'envelope':envelope})
    def status(self, proposal_id='proposal-one'):
        return self.call({'method':'proposal_status','proposal_id':proposal_id})
    def inbox(self):
        return self.call({'method':'inbox'})['messages']


class SDKApplicationTests(baseline.AgentProposalProcessTests):
    """Entire owner-boundary suite via independent official SDK client."""
    def setUp(self):
        super().setUp()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.alice = self.make_client('alice')
        self.bob = self.make_client('bob')

    def make_client(self, actor):
        return SDKClient(self.stack, create_proposal_server(self.task, actor,
            lambda command: self.command('fixture_agent_call', actor=actor, command=command)))

    def test_discovery_and_ordinary_client_title(self):
        self.assertIn(self.alice.initialize.protocolVersion, SUPPORTED_VERSIONS)
        tools = self.alice.portal.call(self.alice.client.list_tools).tools
        self.assertEqual([t.name for t in tools], ['propose','proposal_status','inbox'])
        props = tools[0].inputSchema['properties']['envelope']['properties']
        self.assertEqual(props['sender'], {'const':'alice'})
        self.assertEqual(props['type'], {'const':'request'})
        caps = self.alice.initialize.capabilities.model_dump(exclude_none=True)
        self.assertEqual(set(caps), {'tools'})

    def test_reconnect_and_declined_alias_do_not_renew(self):
        card = self.resolve(self.staged(), 'decline')
        client = self.make_client('alice')
        self.assertEqual(client.propose(self.request, 'new-alias')['state'], 'declined')
        self.assertEqual(self.owner_review(proposal_id='new-alias')['request_id'], card['request_id'])

    def test_uncertain_delivery_is_not_replayed(self):
        card = self.resolve(self.staged())
        self.submit(card)
        self.delivery('fixture_fail_before_receipt', card)
        self.submit(self.resolve(self.command('request_prepare', owner='alice', action='cancel')))
        self.delivery('delivery_attempt', card)
        self.assertEqual(self.alice.status()['delivery_state'], 'stopped_uncertain')
        self.assertEqual(self.alice.propose(self.request, 'retry')['delivery_state'], 'stopped_uncertain')
        self.assertEqual(self.delivery('delivery_view', card)['attempts'], 1)
        self.assertEqual(self.bob.inbox(), [])


class SDKStreamTests(unittest.TestCase):
    def setUp(self):
        self.task, _, self.request, _ = fixture()
        self.calls = []

    def callback(self, command):
        self.calls.append(command)
        if command['method'] == 'inbox':
            return {'messages':[], 'payload_trust':'untrusted_inert'}
        return {'proposal_id':command['proposal_id'], 'envelope_digest':digest(self.request),
                'state':'awaiting_owner_review','delivery_state':None}

    def run_raw(self, scenario, callback=None):
        async def run():
            send, server_read = anyio.create_memory_object_stream(0)
            server_write, receive = anyio.create_memory_object_stream(16)
            adapter = create_proposal_server(self.task, 'alice', callback or self.callback)
            async def write(method, ident=None, params=None):
                raw = {'jsonrpc':'2.0','method':method}
                if ident is not None: raw['id'] = ident
                if params is not None: raw['params'] = params
                await send.send(SessionMessage(types.JSONRPCMessage.model_validate(raw)))
            async def read():
                with anyio.fail_after(5):
                    return (await receive.receive()).message.model_dump(mode='json', exclude_none=True)
            async with send, server_read, server_write, receive, anyio.create_task_group() as group:
                group.start_soon(adapter.run, server_read, server_write)
                await scenario(write, read, send)
                group.cancel_scope.cancel()
        anyio.run(run)

    async def initialize(self, write, read, version='2025-06-18'):
        await write('initialize','init',{'protocolVersion':version,
            'clientInfo':{'name':'fictional','version':'1','title':'Peer','websiteUrl':'https://example.invalid'},
            'capabilities':{'roots':{'listChanged':True},'sampling':{},'elicitation':{},'experimental':{'inert':{}}}})
        response = await read()
        self.assertIn(response['result']['protocolVersion'], SUPPORTED_VERSIONS)
        await write('notifications/initialized')
        return response

    def test_all_supported_versions_and_modern_fallback(self):
        for version in (*SUPPORTED_VERSIONS, '2026-07-28'):
            async def scenario(write, read, send):
                response = await self.initialize(write, read, version)
                self.assertEqual(response['result']['protocolVersion'], version if version in SUPPORTED_VERSIONS else '2025-11-25')
                await write('tools/list','list',{'_meta':{'example':'inert'}})
                self.assertEqual(len((await read())['result']['tools']),3)
            self.run_raw(scenario)
        self.assertEqual(self.calls, [])

    def test_lifecycle_replay_metadata_and_notifications(self):
        async def scenario(write, read, send):
            await write('tools/call','early',{'name':'inbox','arguments':{}})
            self.assertIn('error', await read())
            await self.initialize(write, read)
            await write('tools/call',None,{'name':'inbox','arguments':{}})
            await write('tools/call','call',{'name':'inbox','arguments':{},'_meta':{'progressToken':'inert'}})
            self.assertFalse((await read())['result']['isError'])
            await write('tools/call','call',{'name':'inbox','arguments':{}})
            self.assertIn('error',await read())
            await write('initialize','again',{})
            self.assertIn('error',await read())
        self.run_raw(scenario)
        self.assertEqual(len(self.calls),1)

    def test_invalid_arguments_and_errors_are_redacted(self):
        secret = 'PRIVATE_DATABASE_PATH'
        def broken(command):
            raise RuntimeError(secret)
        with ExitStack() as stack:
            client = SDKClient(stack,create_proposal_server(self.task,'alice',broken))
            for name,args in [('inbox',{}),('inbox',{'owner':secret}),('sign',{}),
                              ('propose',{'proposal_id':'x','envelope':{'secret':secret}})]:
                response = client.raw_call(name,args)
                self.assertTrue(response.isError)
                self.assertNotIn(secret,response.model_dump_json())

    def test_complexity_and_output_projection(self):
        async def scenario(write, read, send):
            await self.initialize(write,read)
            await write('tools/call','huge',{'name':'inbox','arguments':{},'_meta':{'x':'s'*17000}})
            self.assertIn('error',await read())
            await write('tools/call','valid',{'name':'inbox','arguments':{}})
            self.assertTrue((await read())['result']['isError'])
        self.run_raw(scenario, lambda command: {'messages':[], 'payload_trust':'untrusted_inert', 'private':'DO_NOT_LEAK'})
        self.assertEqual(self.calls,[])

    def test_response_loss_and_cancellation_never_retry(self):
        async def scenario(write,read,send):
            await self.initialize(write,read)
            await write('tools/call','proposal',{'name':'propose','arguments':{'proposal_id':'one','envelope':self.request}})
            # Response deliberately not consumed. Cancellation or EOF cannot
            # certify rollback of an already committed synchronous callback.
            await write('notifications/cancelled',params={'requestId':'proposal','reason':'drop'})
            await write('ping','barrier')
            await read()
            await send.aclose()
        self.run_raw(scenario)
        self.assertEqual(len(self.calls),1)
