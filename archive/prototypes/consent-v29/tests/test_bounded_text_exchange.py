"""Offline text capability: exact schemas and real disposable process lifecycle."""
import copy
import json
import unittest
from unittest.mock import patch
from network import Denied, digest, canonical
from generic_capabilities import BOUNDED_TEXT, validate_payload, validate_result_against_request
from generic_protocol import task_envelope, validate_task_scope
from generic_session import GenericTaskProjection
from task_composer import preview, composed_fixture, validate_spec
from owner_workspace import OwnerWorkspace
from tests import test_task_composer as composer_helpers
shortlist_spec = composer_helpers.spec
from tests import test_owner_responses as response_helpers


def spec(requester='bob', bound=16, query='Fictional greeting'):
    value=shortlist_spec(requester=requester)
    del value['max_items']
    return {**value,'capability':BOUNDED_TEXT,'max_reply_chars':bound,'query':query}


class TextValidationTests(unittest.TestCase):
    def test_closed_schema_and_bounds(self):
        for bad in (None,[],{}, {'prompt':'a'}, {'prompt':'a','max_reply_chars':1,'extra':1},
                    *({'prompt':v,'max_reply_chars':1} for v in ('',None,True,'x'*513,'\ud800')),
                    *({'prompt':'a','max_reply_chars':v} for v in (0,513,True,1.0,'1',None))):
            with self.subTest(bad=repr(bad)),self.assertRaises(Denied):validate_payload(BOUNDED_TEXT,'request',bad)
        for bad in ({},[],{'items':[]},{'text':'a','extra':1},*({'text':v} for v in ('',None,True,'x'*513,'\ud800'))):
            with self.subTest(bad=repr(bad)),self.assertRaises(Denied):validate_payload(BOUNDED_TEXT,'result',bad)
        validate_result_against_request(BOUNDED_TEXT,{'prompt':'😀'*512,'max_reply_chars':512},{'text':'😀'*512})
        with self.assertRaises(Denied):validate_result_against_request(BOUNDED_TEXT,{'prompt':'a','max_reply_chars':1},{'text':'ab'})

    def test_exact_composition_and_no_migration(self):
        value=spec();self.assertEqual(validate_spec(value),value)
        for bad in ({**value,'max_items':1},{**value,'capability':'other'},
                    {k:v for k,v in value.items() if k!='capability'},
                    {**shortlist_spec(),'capability':'public-resource-shortlist-v1'}):
            with self.assertRaises(Denied):preview(bad)
        task,_,request,_=composed_fixture(value)
        self.assertEqual(task.operation,'exchange-text')
        self.assertEqual(request['payload'],{'prompt':value['query'],'max_reply_chars':16})
        for key,val in [('max_reply_chars',17),('query','Other fictional greeting'),('requester','alice')]:
            self.assertNotEqual(preview(value)['context'],preview({**value,key:val})['context'])
        self.assertNotEqual(preview(value)['context'],preview(shortlist_spec())['context'])

    def test_projection_scope_linkage_and_terminal(self):
        task,_,request,_=composed_fixture(spec(bound=1));projection=GenericTaskProjection(task)
        result=task_envelope(task,'result',{'text':'a'},reply_to=digest(request))
        with self.assertRaises(Denied):projection._validate(result)
        projection._apply_validated(request)
        for bad in ({**result,'reply_to':'0'*64},{**result,'payload':{'text':'ab'}},
                    {**result,'capability':'public-resource-shortlist-v1','payload':{'items':[]}},
                    {**result,'operation':'find-public-resources'}):
            with self.assertRaises(Denied):projection._validate(bad)
        projection._apply_validated(result)
        with self.assertRaises(Denied):projection._validate(result)

    def test_restricted_schema_matches_text_without_new_methods(self):
        from restricted_host_protocol import RestrictedHostSession
        task=composed_fixture(spec())[0]
        for owner,key in [('bob','prompt'),('alice','text')]:
            host=RestrictedHostSession(task,owner,lambda _:None)
            self.assertEqual(set(host._schemas),{'propose','proposal_status','inbox'})
            payload=host._schemas['propose']['properties']['envelope']['properties']['payload']
            self.assertIn(key,payload['properties']);self.assertFalse(payload['additionalProperties'])


class TextProcessTests(unittest.TestCase):
    action=composer_helpers.ComposedProcessTests.action
    bind=composer_helpers.ComposedProcessTests.bind
    pair=composer_helpers.ComposedProcessTests.pair
    approve_submit=composer_helpers.ComposedProcessTests.approve_submit
    send_process=composer_helpers.ComposedProcessTests.send_process
    counts=response_helpers.OwnerResponseTests.counts

    def setUp(self):
        self.w=OwnerWorkspace();self.addCleanup(self.w.close)
        self.configure(spec())

    def configure(self,value):
        self.spec=value;self.p=preview(value)
        self.w.compose(value,self.p['review_digest'],'CREATE TASK')
        self.service=self.w._slots[self.p['selector']]['service']
        self.responder='alice' if value['requester']=='bob' else 'bob'

    def ready(self):
        self.bind();self.pair();card=self.action(action='next')['card']
        self.approve_submit(card)
        self.action(action='attempt',owner=card['owner'],request_id=card['request_id'],confirmation='SEND '+card['owner'])
        with self.assertRaises(Denied):self.w.response_context(self.p['selector'],self.p['context'],self.responder)
        self.action(action='process',owner=card['owner'],request_id=card['request_id'])
        return self.w.response_context(self.p['selector'],self.p['context'],self.responder)

    def response_preview(self,text='Hello'):
        ctx=self.w.response_context(self.p['selector'],self.p['context'],self.responder)
        return self.action(action='preview_response',owner=self.responder,request_digest=ctx['request_digest'],payload={'text':text})

    def prepare(self,p):
        return self.action(action='prepare_response',owner=self.responder,request_digest=p['request_digest'],payload=p['envelope']['payload'],preview_digest=p['preview_digest'],confirmation='REVIEW RESPONSE '+self.responder)['card']

    def test_preview_pure_no_tools_and_stale_preparation(self):
        self.ready();before=self.counts();p=self.response_preview()
        self.assertEqual(before,self.counts());self.assertEqual(self.action(action='next')['kind'],'awaiting')
        bad=copy.deepcopy(p);bad['envelope']['payload']['text']='Changed'
        with self.assertRaises(Denied):self.prepare(bad)
        self.assertEqual(before,self.counts())
        for method in ('compose_task','response_context','preview_response','prepare_response','execute','browse'):
            with self.assertRaises(Denied):self.service._command('fixture_agent_call',actor=self.responder,command={'method':method})

    def test_limits_before_staging_review_and_signing(self):
        self.ready();task,_,request,_=composed_fixture(self.spec)
        for payload in ({'text':'x'*17},{'items':[]}):
            with self.assertRaises(Denied):self.action(action='preview_response',owner=self.responder,request_digest=digest(request),payload=payload)
        envelope=task_envelope(task,'result',{'text':'x'*17},reply_to=digest(request))
        with self.assertRaises(Denied):self.service._command('fixture_agent_call',actor=self.responder,command={'method':'propose','proposal_id':'oversize','envelope':envelope})
        with self.assertRaises(Denied):self.service._command('request_prepare',owner=self.responder,action='send',envelope=envelope)
        card=self.prepare(self.response_preview())
        decision=copy.deepcopy(card['decision']);decision['target']['envelope_digest']=digest(envelope)
        response=self.service.signers[self.responder].request({'decision':decision,'envelope':envelope,'confirmation':'APPROVE '+self.responder+' send '+card['request_id']})
        self.assertFalse(response['ok'])
        with self.assertRaises(Denied):self.action(action='submit',owner=self.responder,request_id=card['request_id'])

    def test_full_lifecycle_terminal_history_and_messages(self):
        self.ready();p=self.response_preview('<script>hi</script>'[:16]);card=self.prepare(p)
        with self.assertRaises(Denied):self.action(action='submit',owner=self.responder,request_id=card['request_id'])
        self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'complete')
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        with self.assertRaises(Denied):self.response_preview()
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])

    def test_decline_withdrawal_cancel_preserve_exact_history(self):
        self.ready();p=self.response_preview();card=self.prepare(p)
        for choice in ('defer','decline'):
            card=self.action(action=choice,owner=self.responder,request_id=card['request_id'],review_digest=card['review_digest'])['card']
            self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        p2=self.response_preview('Other');card2=self.prepare(p2)
        card2=self.action(action='approve',owner=self.responder,request_id=card2['request_id'],review_digest=card2['review_digest'],confirmation='APPROVE '+self.responder)['card']
        self.action(action='withdraw_unused',owner=self.responder,request_id=card2['request_id'],review_digest=card2['review_digest'],confirmation='WITHDRAW '+self.responder)
        self.assertEqual(self.prepare(p2)['state'],'withdrawn')
        p3=self.response_preview('New')
        cancel=self.action(action='cancel',owner=self.spec['requester'])['card'];self.approve_submit(cancel)
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
        with self.assertRaises(Denied):self.prepare(p3)

    def test_maximum_escaped_unicode_both_directions(self):
        for requester in ('alice','bob'):
            self.w.close();self.w=OwnerWorkspace();self.addCleanup(self.w.close)
            self.configure(spec(requester,512,'😀'*512));self.ready()
            p=self.response_preview('😀'*512);card=self.prepare(p)
            self.assertEqual(card['envelope']['payload']['text'],'😀'*512)
            self.assertLess(len(json.dumps({'ok':True,'result':card})),65536)
            self.send_process(card);self.assertEqual(self.action(action='next')['kind'],'complete')

    def test_cross_capability_proposal_rejected(self):
        self.ready();other_task,_,other_request,_=composed_fixture(shortlist_spec())
        envelope=task_envelope(other_task,'result',{'items':[]},reply_to=digest(other_request))
        with self.assertRaises(Denied):self.service._command('fixture_agent_call',actor=self.responder,command={'method':'propose','proposal_id':'wrong-capability','envelope':envelope})
        p=self.response_preview();self.service._command('fixture_agent_call',actor=self.responder,command={'method':'propose','proposal_id':'text-response','envelope':p['envelope']})
        card=self.w.import_proposal(self.p['selector'],self.p['context'],self.responder,'text-response')
        self.action(action='decline',owner=self.responder,request_id=card['request_id'],review_digest=card['review_digest'])
        self.assertEqual(self.prepare(p)['request_id'],card['request_id'])
