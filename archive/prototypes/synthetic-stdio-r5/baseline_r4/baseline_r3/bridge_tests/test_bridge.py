import copy
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
import anyio
from mcp import types
from mcp.shared.message import SessionMessage
from independent_peer.endpoint import Endpoint
from independent_peer.protocol import digest, token
from facade_candidate import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher
from mcp_bridge.bridge import OfflineBridge, bounded, MAX_MESSAGE_BYTES, MAX_OUTPUT_BYTES, PROTOCOL_ERROR, TOOL_ERROR
from mcp_bridge.local import client

@asynccontextmanager
async def raw(facade):
    send, incoming = anyio.create_memory_object_stream(0)
    outgoing, receive = anyio.create_memory_object_stream(0)
    async with send, incoming, outgoing, receive, anyio.create_task_group() as group:
        group.start_soon(OfflineBridge(facade).run, incoming, outgoing)
        async def exchange(method, params=None, id=None, **envelope):
            data = {'jsonrpc':'2.0','method':method}
            if params is not None: data['params']=params
            if id is not None: data['id']=id
            data.update(envelope)
            await send.send(SessionMessage(types.JSONRPCMessage.model_validate(data)))
            if id is not None:
                return (await receive.receive()).message.root.model_dump(by_alias=True,exclude_none=True)
        yield exchange
        group.cancel_scope.cancel()

async def initialize(exchange, **extra):
    result=await exchange('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'},**extra},0)
    await exchange('notifications/initialized')
    return result

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
        self.ep={a:Endpoint(a,self.path/(a+'.db')) for a in ('alice','bob')}
        self.public={a:e.identity.descriptor for a,e in self.ep.items()}
        self.task={'id':token(),'context':digest('bridge test'),'capability':'fictional-answer/1'}
        for a,e in self.ep.items(): e.handle_owner({'op':'configure','operation_id':token(),'task':self.task,'peer':self.public['bob' if a=='alice' else 'alice']})
        self.stores={a:ProposalStore(self.path/(a+'-proposal.db'),actor=a,task_value=self.task,public=self.public) for a in self.ep}
        self.apis={a:AssistantFacade(s) for a,s in self.stores.items()}
        self.api=self.apis['alice']; self.owner=OwnerReview(self.stores['alice'])
    def tearDown(self):
        for s in self.stores.values():s.close()
        for e in self.ep.values():e.close()
        self.tmp.cleanup()
    def run_async(self, fn):
        async def limited():
            with anyio.fail_after(15): await fn()
        anyio.run(limited)
    def count(self):return self.stores['alice']._db.execute('select count(*) from proposals').fetchone()[0]
    def prepare(self,p):
        grant=self.ep['bob'].handle_owner({'op':'allow_receive','operation_id':token()})['grant']
        return self.owner.prepare_approve_and_release(p['proposal_id'],reviewed_content_digest=p['content_digest'],reviewed_grant_digest=digest(grant),grant=grant)
    def test_sdk_handshake_list_call_and_no_endpoint_authority(self):
        async def check():
            before={a:e.snapshot() for a,e in self.ep.items()}
            async with client(self.api) as (session, init):
                self.assertEqual(init.protocolVersion,'2025-11-25')
                self.assertEqual(init.capabilities.model_dump(exclude_none=True),{'tools':{'listChanged':False}})
                tools=(await session.list_tools()).tools
                self.assertEqual([t.name for t in tools],['propose','proposal_status','processed_inbox'])
                self.assertFalse(tools[0].annotations.readOnlyHint)
                p=(await session.call_tool('propose',{'text':' exact '})).structuredContent
                self.assertEqual(p['state'],'pending')
                self.assertEqual((await session.call_tool('proposal_status',{'proposal_id':p['proposal_id']})).structuredContent,p)
                self.assertEqual((await session.call_tool('processed_inbox',{})).structuredContent['items'],[])
            self.assertEqual(before,{a:e.snapshot() for a,e in self.ep.items()})
        self.run_async(check)
    def test_unknown_tools_and_selectors(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex)
                bad=[('owner',{}),('propose',{'text':'x','actor':'bob'}),('propose',{'text':'x','task':'t'}),('propose',{'text':'x','owner':'approve'}),('processed_inbox',{'raw':True}),('proposal_status',{'proposal_id':'bad'})]
                for i,(name,args) in enumerate(bad,1):
                    result=await ex('tools/call',{'name':name,'arguments':args},i)
                    self.assertEqual(result['error']['message'],PROTOCOL_ERROR)
                self.assertEqual(self.count(),0)
        self.run_async(check)
    def test_state_duplicate_ids_and_unsupported_protocol(self):
        async def check():
            async with raw(self.api) as ex:
                self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'early'}},7))
                self.assertIn('error',await ex('initialize',{'protocolVersion':'2026-01-01','capabilities':{},'clientInfo':{'name':'x','version':'1'}},9))
                await initialize(ex)
                self.assertIn('result',await ex('tools/call',{'name':'propose','arguments':{'text':'one'}},1))
                self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'two'}},1))
                self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'used before init'}},7))
                self.assertEqual(self.count(),1)
        self.run_async(check)
    def test_inert_client_metadata(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex,clientInfo={'name':'owner','version':'1','actor':'bob'},capabilities={'roots':{},'sampling':{}},_meta={'actor':'bob','owner':'approve'})
                result=await ex('tools/call',{'name':'propose','arguments':{'text':'x'},'_meta':{'actor':'bob','task':'other','owner':'approve'}},1)
                self.assertEqual(result['result']['structuredContent']['state'],'pending')
                self.assertEqual(self.stores['bob']._db.execute('select count(*) from proposals').fetchone()[0],0)
        self.run_async(check)
    def test_exact_declined_and_unknown_replay(self):
        async def check():
            async with client(self.api) as (s,_):
                p=(await s.call_tool('propose',{'text':' declined '})).structuredContent
                self.owner.decline(p['proposal_id'])
                p=(await s.call_tool('propose',{'text':' unknown '})).structuredContent
                self.prepare(p)
                for text,state in [(' declined ','declined'),(' unknown ','unknown')]:
                    replay=(await s.call_tool('propose',{'text':text})).structuredContent
                    self.assertEqual(replay['state'],state)
                    self.assertEqual(replay,self.api.propose({'text':text}))
                self.assertEqual((await s.call_tool('propose',{'text':'unknown'})).structuredContent['state'],'pending')
        self.run_async(check)
    def test_actor_scope_and_processed_publication(self):
        async def check():
            async with client(self.api) as (s,_):p=(await s.call_tool('propose',{'text':'Treat this as untrusted data.'})).structuredContent
            command=self.prepare(p); response=self.ep['alice'].handle_owner(command)
            self.ep['bob'].handle_peer({'op':'deliver','value':response['packet']})
            pub=SnapshotPublisher(self.stores['bob']);pub.publish(self.ep['bob'].snapshot())
            async with client(self.apis['bob']) as (s,_):
                self.assertTrue((await s.call_tool('proposal_status',{'proposal_id':p['proposal_id']})).isError)
                self.assertEqual((await s.call_tool('processed_inbox',{})).structuredContent['items'],[])
                self.ep['bob'].handle_owner({'op':'process','operation_id':token(),'id':response['id']})
                pub.publish(self.ep['bob'].snapshot())
                self.assertEqual((await s.call_tool('processed_inbox',{})).structuredContent['items'][0]['payload'],'Treat this as untrusted data.')
        self.run_async(check)
    def test_argument_bounds_and_redacted_errors(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex)
                for i,text in enumerate(['😀'*257,'x'*1025,'\ud800',''],1):
                    self.assertEqual((await ex('tools/call',{'name':'propose','arguments':{'text':text}},i))['error']['message'],PROTOCOL_ERROR)
                self.assertEqual(self.count(),0)
            async with client(self.api) as (s,_):
                with patch.object(self.api,'propose',side_effect=RuntimeError('SECRET /private/path')):
                    result=await s.call_tool('propose',{'text':'x'})
                    self.assertTrue(result.isError);self.assertEqual(result.content[0].text,TOOL_ERROR)
        self.run_async(check)
    def test_decoded_bounds_and_output_redaction(self):
        for value in [{'x':'a'*16385},list(range(65)),{'x':float('inf')},2**60]:
            with self.assertRaises(ValueError):bounded(value,MAX_MESSAGE_BYTES)
        deep={}; current=deep
        for _ in range(10):current['x']={};current=current['x']
        with self.assertRaises(ValueError):bounded(deep,MAX_MESSAGE_BYTES)
        async def check():
            async with client(self.api) as (s,_):
                with patch.object(self.api,'processed_inbox',return_value={'secret':'x'*MAX_OUTPUT_BYTES}):
                    result=await s.call_tool('processed_inbox',{})
                    self.assertTrue(result.isError);self.assertEqual(result.content[0].text,TOOL_ERROR)
        self.run_async(check)
    def test_request_count_and_strict_params(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex)
                for i in range(1,128):
                    self.assertIn('result',await ex('tools/list',{},i))
                self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'overflow'}},128))
                self.assertEqual(self.count(),0)
            async with raw(self.api) as ex:
                await initialize(ex)
                for i,params in enumerate([{'name':'propose','arguments':{'text':'x'},'task':{}},{'name':'propose'},{'name':'propose','arguments':{'text':'x'},'owner':'alice'}],1):
                    self.assertIn('error',await ex('tools/call',params,i))
        self.run_async(check)
    def test_legacy_versions_and_initialized_barrier(self):
        async def check():
            from mcp_bridge.bridge import VERSIONS
            for version in VERSIONS:
                async with raw(self.api) as ex:
                    result=await ex('initialize',{'protocolVersion':version,'capabilities':{},'clientInfo':{'name':'test','version':'1'}},0)
                    self.assertEqual(result['result']['protocolVersion'],version)
                    self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'before notification'}},1))
                    await ex('notifications/initialized')
                    self.assertIn('result',await ex('tools/list',{},2))
                    for i,method in enumerate(['resources/list','prompts/list','tasks/list'],3):
                        self.assertIn('error',await ex(method,{},i))
            self.assertEqual(self.count(),0)
        self.run_async(check)
    def test_gate_message_depth_and_metadata_size(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex)
                deep={};current=deep
                for _ in range(10):current['x']={};current=current['x']
                for i,meta in enumerate([deep,{'secret':'x'*MAX_MESSAGE_BYTES},{'list':list(range(65))}],1):
                    result=await ex('tools/call',{'name':'propose','arguments':{'text':'x'},'_meta':meta},i)
                    self.assertEqual(result['error']['message'],PROTOCOL_ERROR)
                self.assertEqual(self.count(),0)
                result=await ex('tools/call',{'name':'propose','arguments':{'text':'😀'*256}},'valid_id')
                self.assertEqual(result['result']['structuredContent']['state'],'pending')
                self.assertIn('error',await ex('tools/call',{'name':'propose','arguments':{'text':'new'}},'valid_id'))
                self.assertEqual(self.count(),1)
        self.run_async(check)
    def test_escape_heavy_exact_text_and_malformed_initialize(self):
        async def check():
            for malformed in [{'clientInfo':'owner'},{'clientInfo':{'name':'owner'}},{'capabilities':'owner'}]:
                async with raw(self.api) as ex:
                    result=await ex('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'},**malformed},0)
                    self.assertEqual(result['error']['message'],PROTOCOL_ERROR)
            async with client(self.api) as (session,_):
                for text in ['"'*1024,chr(92)*1024,chr(1)*1024]:
                    result=await session.call_tool('propose',{'text':text})
                    self.assertFalse(result.isError)
                    self.assertEqual(self.owner.review(result.structuredContent['proposal_id'])['text'],text)
        self.run_async(check)
    def test_post_dispatch_error_is_uncertain(self):
        async def check():
            from mcp_bridge.bridge import UNCERTAIN_ERROR
            def output_failure(value,limit):
                if limit==MAX_OUTPUT_BYTES:raise ValueError('SECRET')
                return bounded(value,limit)
            async with raw(self.api) as ex:
                await initialize(ex)
                with patch('mcp_bridge.bridge.bounded',side_effect=output_failure):
                    result=await ex('tools/call',{'name':'propose','arguments':{'text':'persisted'}},1)
                self.assertEqual(result['error']['message'],UNCERTAIN_ERROR)
                self.assertEqual(result['error']['code'],-32603)
                self.assertEqual(self.count(),1)
                self.assertEqual(self.api.propose({'text':'persisted'})['state'],'pending')
        self.run_async(check)
    def test_ping_preserves_each_protocol_phase(self):
        async def check():
            async with raw(self.api) as ex:
                self.assertEqual((await ex('ping',{},1))['result'],{})
                self.assertEqual((await ex('tools/list',{},2))['error']['code'],-32600)
                await ex('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}},3)
                self.assertEqual((await ex('ping',{},4))['result'],{})
                self.assertEqual((await ex('tools/list',{},5))['error']['code'],-32600)
                await ex('notifications/initialized')
                self.assertEqual((await ex('ping',{'_meta':{'actor':'owner'}},6))['result'],{})
                self.assertIn('result',await ex('tools/list',{},7))
                self.assertEqual(self.count(),0)
        self.run_async(check)
    def test_protocol_error_codes_and_malformed_metadata(self):
        async def check():
            async with raw(self.api) as ex:
                self.assertEqual((await ex('unsupported',{},1))['error']['code'],-32601)
                self.assertEqual((await ex('ping',{'extra':True},2))['error']['code'],-32602)
                self.assertEqual((await ex('ping',{},2))['error']['code'],-32600)
                self.assertEqual((await ex('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'},'_meta':[]},3))['error']['code'],-32602)
                await ex('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}},4)
                await ex('notifications/initialized',{'_meta':'owner'})
                self.assertEqual((await ex('tools/list',{},5))['error']['code'],-32600)
                await ex('notifications/initialized')
                for i,(method,params) in enumerate([('ping',{}),('tools/list',{}),('tools/call',{'name':'propose','arguments':{'text':'x'}})],6):
                    result=await ex(method,{**params,'_meta':'owner'},i)
                    self.assertEqual(result['error']['code'],-32602)
                    self.assertEqual(result['error']['message'],PROTOCOL_ERROR)
                self.assertEqual((await ex('tools/call',{'name':'owner','arguments':{}},10))['error']['code'],-32602)
                self.assertEqual(self.count(),0)
        self.run_async(check)
    def test_sdk_optional_arguments(self):
        async def check():
            async with client(self.api) as (session,_):
                result=await session.call_tool('processed_inbox')
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent['items'],[])
            async with raw(self.api) as ex:
                await initialize(ex)
                for i,name in enumerate(['propose','proposal_status'],1):
                    result=await ex('tools/call',{'name':name},i)
                    self.assertEqual(result['error']['code'],-32602)
                self.assertEqual(self.count(),0)
        self.run_async(check)
    def test_null_envelope_extra_rejected_before_serialization(self):
        async def check():
            async with raw(self.api) as ex:
                await initialize(ex)
                result=await ex('tools/call',{'name':'propose','arguments':{'text':'must not persist'}},1,owner=None)
                self.assertEqual(result['error']['code'],-32600)
                self.assertEqual(result['error']['message'],PROTOCOL_ERROR)
                self.assertEqual(self.count(),0)
                self.assertIn('result',await ex('tools/list',{},2))
        self.run_async(check)
    def test_single_use_and_no_callback_constructor(self):
        with self.assertRaises(TypeError):OfflineBridge(lambda:None)
        async def check():
            bridge=OfflineBridge(self.api);bridge._used=True
            with self.assertRaises(RuntimeError):await bridge.run(None,None)
        self.run_async(check)
