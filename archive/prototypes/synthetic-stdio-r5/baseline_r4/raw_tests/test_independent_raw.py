"""Independent synthetic-byte review. No process or OS-transport probes."""
if __package__:
    from . import review_bootstrap
else:
    import review_bootstrap
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import anyio
from raw_bridge.codec import decode_record, encode_record, Rejected
from raw_bridge.transport import RawBridge, LocalFailure
from facade_candidate import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher
from independent_peer.endpoint import Endpoint
from independent_peer.protocol import token, digest

# These client-side bytes deliberately do not use the candidate encoder.
def line(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
def req(i, method='ping', **kw):
    return dict(jsonrpc='2.0', id=i, method=method, **kw)
def tool(i, name, args):
    return req(i, 'tools/call', params={'name':name, 'arguments':args})
HELLO = (b'{"jsonrpc":"2.0","id":"hello","method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"independent","version":"1"}}}\n'
         b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
class Input:
    def __init__(self, data, width=4096): self.data=data; self.width=width; self.pos=0; self.calls=0
    async def receive(self,n):
        self.calls+=1
        await anyio.lowlevel.checkpoint()
        if self.pos==len(self.data): raise anyio.EndOfStream
        end=min(len(self.data),self.pos+self.width,n+self.pos)
        result=self.data[self.pos:end];self.pos=end
        return result
    async def aclose(self): raise AssertionError('Caller input closed')
class Output:
    def __init__(self): self.records=[]
    async def send(self, b): self.records.append(b)
    async def aclose(self): raise AssertionError('Caller output closed')

class CodecReview(unittest.TestCase):
    def bad(self, b, code):
        with self.assertRaises(Rejected) as e: decode_record(b)
        self.assertEqual(e.exception.code,code)
        return e.exception
    def test_limit_before_decode_and_parse(self):
        with patch('raw_bridge.codec.lexical_depth',side_effect=AssertionError('decoded')):
            self.bad(b'\xff'*16385,-32700)
        with patch('raw_bridge.codec.json.loads',side_effect=AssertionError('parsed')):
            self.bad(b'['*10+b']'*10,-32700)
    def test_duplicate_aliases_nested_and_quoted_braces(self):
        for b in (b'{"id":2,"\\u0069d":3}',b'{"params":{"a":1,"\\u0061":2}}'):
            self.assertIsNone(self.bad(b,-32700).request_id)
        raw=line(req(1,params={'x':'\\"[{]} '*100}))[:-1]
        self.assertEqual(decode_record(raw)['id'],1)
    def test_scalar_unicode_numeric_vectors(self):
        for b in (b'\xc0\xaf',b'\xed\xa0\x80',b'\xef\xbb\xbf{}',b'NaN',b'Infinity'):
            self.bad(b,-32700)
        for v in ('\\udfff','1e999','9007199254740992'):
            scalar=('"'+v+'"') if v.startswith('\\u') else v
            self.bad(('{"jsonrpc":"2.0","id":9,"method":"ping","params":{"x":'+scalar+'}}').encode(),-32600)
        self.assertEqual(decode_record(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"\\ud83d\\ude00"}}')['params']['x'],'😀')
    def test_id_types_and_envelope_strictness(self):
        for i in (None,True,False,1.0,-1,2147483648,'','é','a'*65):
            self.assertIsNone(self.bad(line(req(i))[:-1],-32600).request_id)
        for i in (0,2147483647,'0','a'*64):
            result=decode_record(line(req(i))[:-1])['id'];self.assertIs(type(result),type(i));self.assertEqual(result,i)
        self.bad(line(req(1,result=None))[:-1],-32600)
        self.bad(line(req(1,params=None))[:-1],-32602)
        self.bad(line(req(1,'unknown',params=[]))[:-1],-32601)
    def test_silent_shape_is_exact(self):
        for raw,silent in [(b'{"jsonrpc":"2.0","method":"ping","params":null}',True),(b'{"jsonrpc":"2.0","method":"ping","extra":null}',True),(b'{"method":"ping"}',False),(b'{"jsonrpc":"1.0","method":"ping"}',False),(b'{"jsonrpc":"2.0","method":"ping","id":null}',False)]:
            self.assertEqual(self.bad(raw,-32602 if b'params' in raw else -32600).silent,silent)
    def test_postparse_bounds_and_normalized_size(self):
        for value in (list(range(65)), {str(i):0 for i in range(65)}, [[0]*64 for _ in range(8)]):
            self.bad(line(req(1,params={'x':value}))[:-1],-32600)
        prefix=b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"n":1e-6,"x":"'
        suffix=b'"}}'
        self.bad(prefix+b'a'*(16384-len(prefix)-len(suffix))+suffix,-32600)
        # Exactly nine open collections reaches lexical parsing, but tree value depth is separately bounded.
        with patch('raw_bridge.codec.json.loads', wraps=json.loads) as parser:
            self.bad(b'['*9+b'0'+b']'*9,-32600)
            self.assertEqual(parser.call_count,1)
    def test_exact_output_byte_cap_including_lf(self):
        self.assertEqual(len(encode_record({'x':'a'*32759})),32768)
        with self.assertRaises(Rejected): encode_record({'x':'a'*32760})
        self.assertTrue(encode_record({'x':'😀'}).endswith(b'\n'))

class StreamReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();p=Path(self.temp.name)
        self.ep={a:Endpoint(a,p/(a+'.db')) for a in ('alice','bob')}
        public={a:e.identity.descriptor for a,e in self.ep.items()}
        task={'id':token(),'context':digest('independent raw review'),'capability':'fictional-answer/1'}
        for a,e in self.ep.items():e.handle_owner({'op':'configure','operation_id':token(),'task':task,'peer':public['bob' if a=='alice' else 'alice']})
        self.stores={a:ProposalStore(p/(a+'-proposals.db'),actor=a,task_value=task,public=public) for a in self.ep}
        self.api=AssistantFacade(self.stores['alice']);self.owner=OwnerReview(self.stores['alice'])
    def tearDown(self):
        for s in self.stores.values():s.close()
        for e in self.ep.values():e.close()
        self.temp.cleanup()
    def run_case(self,data,width=4096,reader=None,writer=None,api=None,fail=False):
        async def go():
            b=RawBridge(api or self.api);out=writer or Output();inp=reader or Input(data,width)
            with anyio.fail_after(10):
                if fail:
                    with self.assertRaisesRegex(LocalFailure,'Raw bridge stopped') as e: await b.run(inp,out)
                    self.assertNotIn('PRIVATE',str(e.exception))
                else: await b.run(inp,out)
            return [json.loads(x.decode('utf-8')) for x in out.records], b.facts, inp
        return anyio.run(go)
    def test_fragmentation_and_coalescing(self):
        for width in (1,2,3,17,4096):
            replies,facts,_=self.run_case(HELLO+line(req(1))+line(tool(2,'processed_inbox',{})),width)
            self.assertEqual([r['id'] for r in replies],['hello',1,2]);self.assertEqual(facts.records,4)
            self.assertEqual(replies[-1]['result']['structuredContent']['items'],[])
    def test_exact_record_cap_crlf_and_overflow(self):
        raw=line(req(1))[:-1]
        for suffix in (b'\n',b'\r\n'):
            data=raw+b' '*(16384-len(raw)-(len(suffix)-1))+suffix
            r,f,_=self.run_case(data,3);self.assertEqual(r[0]['result'],{});self.assertEqual(f.termination,'eof')
        data=raw+b' '*(16384-len(raw))+b'\r\n'+line(req(2))
        r,f,_=self.run_case(data);self.assertEqual(f.termination,'record_too_large');self.assertEqual(len(r),1);self.assertEqual(r[0]['error']['code'],-32700)
    def test_partial_eof_not_dispatched_and_prior_facts_remain(self):
        incomplete=line(req(2))[:-1]
        r,f,_=self.run_case(line(req(1))+incomplete,1)
        self.assertEqual(len(r),1);self.assertEqual(f.partial_eof_bytes,len(incomplete));self.assertEqual(f.admitted_to_r3,1);self.assertEqual(f.output_accepted,1);self.assertEqual(f.termination,'partial_eof')
    def test_oversize_not_drained(self):
        r,f,inp=self.run_case(b'x'*50000)
        self.assertEqual(inp.pos,20480);self.assertEqual(f.records,1);self.assertEqual(len(r),1)
    def test_bad_input_contract(self):
        for value in (b'',b'x'*4097,bytearray(b'x'),'PRIVATE',None):
            class Bad:
                async def receive(self,n):return value
            _,f,_=self.run_case(b'',reader=Bad(),fail=True)
            self.assertEqual(f.termination,'reader_contract_failure');self.assertEqual(f.admitted_to_r3,0)
    def test_raw_errors_consume_ids_but_parse_failures_do_not(self):
        data=HELLO+line(req(7,params=None))+line(tool(7,'propose',{'text':'forbidden'}))+line(tool('7','propose',{'text':'allowed'}))
        data+=b'{"jsonrpc":"2.0","id":8,"\\u0069d":9,"method":"ping"}\n'+line(req(8))
        r,f,_=self.run_case(data)
        self.assertEqual([x['error']['code'] for x in r[1:3]],[-32602,-32600]);self.assertEqual(r[3]['id'],'7');self.assertIsNone(r[4]['id']);self.assertEqual(r[5]['result'],{})
    def test_record_and_id_budgets(self):
        for data in (b'\n'*161,b'{"jsonrpc":"2.0","method":"ping","params":null}\n'*161):
            r,f,_=self.run_case(data);self.assertEqual(f.records,160);self.assertEqual(f.termination,'record_budget');self.assertEqual(f.admitted_to_r3,0)
        r,f,_=self.run_case(b''.join(line(req(i,params=None)) for i in range(128))+line(req(128)))
        self.assertEqual(r[-1]['error']['code'],-32600);self.assertEqual(f.admitted_to_r3,0)
    def test_invalid_ids_cannot_persist_and_null_is_not_notification(self):
        data=HELLO+b''.join(line(tool(i,'propose',{'text':'no'})) for i in (None,True,1.0))+line(tool(1,'propose',{'text':'yes'}))
        r,f,_=self.run_case(data)
        self.assertEqual([x['id'] for x in r[1:4]],[None]*3)
        self.assertEqual(self.stores['alice']._db.execute('select count(*) from proposals').fetchone()[0],1)
    def test_exact_1024_byte_text_and_no_owner_authority(self):
        before={a:e.snapshot() for a,e in self.ep.items()}
        for txt in ('\x00"\\\n'*256,'😀'*256):
            self.assertEqual(len(txt.encode()),1024)
            r,f,_=self.run_case(HELLO+line(tool(1,'propose',{'text':txt}))+line(tool(2,'propose',{'text':txt})),3)
            proposal=r[1]['result']['structuredContent'];self.assertEqual(proposal,r[2]['result']['structuredContent']);self.assertEqual(self.owner.review(proposal['proposal_id'])['text'],txt)
        r,_,_=self.run_case(HELLO+line(tool(1,'owner',{}))+line(tool(2,'propose',{'text':'x','actor':'bob'}))+line(req(3,'owner/approve')))
        self.assertTrue(all('error' in x for x in r[1:]));self.assertEqual(before,{a:e.snapshot() for a,e in self.ep.items()})
    def test_processed_inbox_requires_explicit_owner_and_publication(self):
        txt='\x00"\\\n'*256
        r,_,_=self.run_case(HELLO+line(tool(1,'propose',{'text':txt})))
        p=r[1]['result']['structuredContent'];grant=self.ep['bob'].handle_owner({'op':'allow_receive','operation_id':token()})['grant']
        command=self.owner.prepare_approve_and_release(p['proposal_id'],reviewed_content_digest=p['content_digest'],reviewed_grant_digest=digest(grant),grant=grant)
        release=self.ep['alice'].handle_owner(command);self.ep['bob'].handle_peer({'op':'deliver','value':release['packet']})
        api=AssistantFacade(self.stores['bob']);publisher=SnapshotPublisher(self.stores['bob']);publisher.publish(self.ep['bob'].snapshot())
        r,_,_=self.run_case(HELLO+line(tool(1,'processed_inbox',{})),api=api);self.assertEqual(r[-1]['result']['structuredContent']['items'],[])
        self.ep['bob'].handle_owner({'op':'process','operation_id':token(),'id':release['id']})
        r,_,_=self.run_case(HELLO+line(tool(1,'processed_inbox',{})),api=api);self.assertEqual(r[-1]['result']['structuredContent']['items'],[])
        publisher.publish(self.ep['bob'].snapshot())
        r,_,_=self.run_case(HELLO+line(tool(1,'processed_inbox',{})),api=api);self.assertEqual(r[-1]['result']['structuredContent']['items'][0]['payload'],txt)
    def test_writer_failure_preserves_proposal_without_retry(self):
        class Failing(Output):
            async def send(self,data):
                self.records.append(data)
                if len(self.records)==2:raise ValueError('PRIVATE')
        out=Failing();r,f,_=self.run_case(HELLO+line(tool(1,'propose',{'text':'persisted'})),writer=out,fail=True)
        self.assertEqual(len(r),2);self.assertEqual(f.output_attempts,2);self.assertEqual(f.output_accepted,1);self.assertTrue(f.output_uncertain);self.assertTrue(f.proposal_persistence_possible)
        self.assertEqual(self.stores['alice']._db.execute('select count(*) from proposals').fetchone()[0],1)
    def test_partial_writer_return_and_late_reader_exception(self):
        class Partial(Output):
            async def send(self,data):self.records.append(data);return 1
        _,f,_=self.run_case(line(req(1)),writer=Partial(),fail=True);self.assertTrue(f.output_uncertain);self.assertEqual(f.output_accepted,0)
        class Late(Input):
            async def receive(self,n):
                if self.pos:raise ValueError('PRIVATE')
                return await super().receive(n)
        _,f,_=self.run_case(b'',reader=Late(line(req(1))),fail=True);self.assertEqual(f.output_accepted,1);self.assertFalse(f.output_uncertain)
    def test_output_rejection_is_redacted(self):
        original=encode_record
        def rejected(value):
            if 'result' in value:raise Rejected(-32603)
            return original(value)
        with patch('raw_bridge.transport.encode_record',side_effect=rejected):r,f,_=self.run_case(line(req(1)))
        self.assertEqual(r[0]['error']['code'],-32603);self.assertIn('uncertain',r[0]['error']['message']);self.assertEqual(f.output_attempts,1)
    def test_silent_raw_rejections_and_malformed_version_replies(self):
        data=(b'{"jsonrpc":"2.0","method":"ping","params":null}\n'
              b'{"jsonrpc":"2.0","method":"ping","extra":null}\n'
              b'{"jsonrpc":"1.0","method":"ping"}\n'
              b'{"method":"ping"}\n')
        r,f,_=self.run_case(data)
        self.assertEqual(len(r),2);self.assertEqual(f.records,4);self.assertEqual(f.admitted_to_r3,0)
        self.assertTrue(all(x['id'] is None and x['error']['code']==-32600 for x in r))
    def test_admission_fact_is_not_persistence(self):
        r,f,_=self.run_case(line(tool(1,'propose',{'text':'before initialization'})))
        self.assertTrue(f.proposal_persistence_possible);self.assertEqual(f.admitted_to_r3,1)
        self.assertEqual(r[0]['error']['code'],-32600)
        self.assertEqual(self.stores['alice']._db.execute('select count(*) from proposals').fetchone()[0],0)
    def test_input_cancellation_does_not_claim_output_uncertainty(self):
        async def go():
            class Waiting(Input):
                async def receive(self,n):await anyio.sleep_forever()
            b=RawBridge(self.api)
            with anyio.move_on_after(.02) as scope:await b.run(Waiting(b''),Output())
            self.assertTrue(scope.cancel_called);self.assertEqual(b.facts.termination,'cancelled')
            self.assertFalse(b.facts.output_uncertain);self.assertEqual(b.facts.output_attempts,0)
        anyio.run(go)
    def test_cancellation_during_output_is_uncertain_and_single_use(self):
        async def go():
            class Waiting(Output):
                async def send(self,data):self.records.append(data);await anyio.sleep_forever()
            b=RawBridge(self.api);out=Waiting()
            with anyio.move_on_after(.02) as scope:await b.run(Input(line(req(1))),out)
            self.assertTrue(scope.cancel_called);self.assertEqual(b.facts.termination,'cancelled');self.assertTrue(b.facts.output_uncertain);self.assertEqual(b.facts.output_accepted,0);self.assertEqual(len(out.records),1)
            with self.assertRaises(LocalFailure):await b.run(Input(b''),Output())
        anyio.run(go)

if __name__=='__main__':unittest.main(verbosity=2)
