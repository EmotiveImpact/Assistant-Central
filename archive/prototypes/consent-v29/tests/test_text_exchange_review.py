"""Independent offline regressions for capability isolation and exact review."""
import copy
import unittest
from dataclasses import replace
from network import Denied, digest
from generic_capabilities import BOUNDED_TEXT, validate_result_against_request
from generic_protocol import task_envelope, snapshot_task_envelope
from generic_session import GenericTaskProjection
from task_composer import composed_fixture, preview, validate_composed_request, parse_startup
from tests import test_bounded_text_exchange as helpers


def spec():
    return dict(selector='custom-review',task_id='task-review',conversation_id='conversation-review',requester='alice',query='Fictional review',capability=BOUNDED_TEXT,max_reply_chars=2)


class IndependentTextReview(unittest.TestCase):
    def test_legacy_exact_hashes_from_unmodified_v20(self):
        old=spec();del old['capability'];del old['max_reply_chars'];old['max_items']=2
        self.assertEqual(preview(old)['context'],'1892b4fd6cf16ee70dd0f7076efe38e7ac5c5a53169cf711f6bd3abef9ad2602')
        self.assertEqual(preview(old)['review_digest'],'845208f219c638686592f0d83c4be3e7f9d2586de31ecc950e5f9f19fed986ed')
        self.assertEqual(digest(composed_fixture(old)[2]),'4d0f31677546413babd4f6b4a74de9e4d1ed439155381947d584c219e25f0e46')

    def test_every_spec_field_commits_context_and_review(self):
        original=spec()
        changes=dict(selector='custom-other',task_id='task-other',conversation_id='conversation-other',requester='bob',query='Other fictional text',max_reply_chars=3)
        for key,value in changes.items():
            with self.subTest(key=key):
                changed={**original,key:value}
                self.assertNotEqual(preview(original)['context'],preview(changed)['context'])
                self.assertNotEqual(preview(original)['review_digest'],preview(changed)['review_digest'])
                foreign=composed_fixture(changed)[2]
                with self.assertRaises(Denied):validate_composed_request(original,foreign)

    def test_result_validation_checks_scope_route_linkage_and_bounds(self):
        s=spec();task,_,request,_=composed_fixture(s)
        good=task_envelope(task,'result',{'text':'😀a'},digest(request))
        validate_composed_request(s,good)
        for key,value in dict(context='0'*64,reply_to='1'*64,operation='other',sender='alice',recipient='bob',payload={'text':'😀ab'},capability='public-resource-shortlist-v1').items():
            with self.subTest(key=key),self.assertRaises(Denied):validate_composed_request(s,{**good,key:value})

    def test_request_relative_limit_not_just_global_limit(self):
        for limit in (1,2,511,512):
            request={'prompt':'inert','max_reply_chars':limit}
            validate_result_against_request(BOUNDED_TEXT,request,{'text':'😀'*limit})
            with self.assertRaises(Denied):validate_result_against_request(BOUNDED_TEXT,request,{'text':'😀'*(limit+1)})
        # Code points, not graphemes or UTF-16 units, define the bound.
        with self.assertRaises(Denied):validate_result_against_request(BOUNDED_TEXT,{'prompt':'x','max_reply_chars':1},{'text':'e\u0301'})

    def test_operation_and_closed_schema_rejected_before_projection(self):
        task,_,request,_=composed_fixture(spec())
        with self.assertRaises(Denied):replace(task,operation='find-public-resources')
        for bad in ({**request,'operation':'find-public-resources'}, {**request,'payload':{'query':'x','max_items':1}}, {**request,'payload':{**request['payload'],'tool':'execute'}}):
            with self.assertRaises(Denied):snapshot_task_envelope(bad)

    def test_projection_detaches_inert_text_and_rejects_replay(self):
        task,_,request,_=composed_fixture(spec());projection=GenericTaskProjection(task)
        projection._apply_validated(request);request['payload']['max_reply_chars']=512
        result=task_envelope(task,'result',{'text':'abc'},digest(projection.request))
        with self.assertRaises(Denied):projection._apply_validated(result)
        result['payload']['text']='<>'
        projection._apply_validated(result);result['payload']['text']='changed'
        self.assertEqual(projection.result['payload']['text'],'<>')
        with self.assertRaises(Denied):projection._apply_validated(projection.result)

    def test_duplicate_startup_keys_and_boolean_bounds_fail_closed(self):
        import json
        source=json.dumps(spec())
        for body in (source[:-1]+',"max_reply_chars":1}',source[:-1]+',"capability":"public-resource-shortlist-v1"}'):
            with self.assertRaises(Denied):parse_startup(body)
        for bound in (True,False,2.0,'2',None):
            with self.assertRaises(Denied):preview({**spec(),'max_reply_chars':bound})

    def test_signer_rejects_wrong_linkage_even_when_digest_matches_modified_envelope(self):
        # Reuse lifecycle setup only; this is a new independent signer attack.
        h=helpers.TextProcessTests();h.setUp();self.addCleanup(h.doCleanups)
        h.ready();p=h.response_preview();card=h.prepare(p)
        bad=copy.deepcopy(p['envelope']);bad['reply_to']='a'*64
        decision=copy.deepcopy(card['decision']);decision['target']['envelope_digest']=digest(bad)
        outcome=h.service.signers[h.responder].request({'decision':decision,'envelope':bad,'confirmation':'APPROVE '+h.responder+' send '+card['request_id']})
        self.assertFalse(outcome['ok'])
        with self.assertRaises(Denied):h.action(action='submit',owner=h.responder,request_id=card['request_id'])
        # The rejected attempt must not consume or approve the original review.
        h.send_process(card);self.assertEqual(h.action(action='next')['kind'],'complete')
