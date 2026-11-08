"""Independent response-authoring boundary review; disposable offline processes."""
import copy
import concurrent.futures
import json
import unittest
from network import Denied, digest
from tests import test_owner_responses as helpers


class ResponseComposerIndependentReview(unittest.TestCase):
    setUp = helpers.OwnerResponseTests.setUp
    action = helpers.OwnerResponseTests.action
    bind = helpers.OwnerResponseTests.bind
    pair = helpers.OwnerResponseTests.pair
    approve_submit = helpers.OwnerResponseTests.approve_submit
    send_process = helpers.OwnerResponseTests.send_process
    ready = helpers.OwnerResponseTests.ready
    preview = helpers.OwnerResponseTests.preview
    prepare = helpers.OwnerResponseTests.prepare
    prepare_body = helpers.OwnerResponseTests.prepare_body
    counts = helpers.OwnerResponseTests.counts
    item = helpers.OwnerResponseTests.item

    def test_forged_context_and_request_cannot_be_rescoped_with_rehashed_preview(self):
        self.ready()
        p = self.preview()
        before = self.counts()
        for key, value in [('context', 'f'*64), ('owner', 'bob'), ('recipient', 'alice'), ('request_digest', 'f'*64)]:
            forged = copy.deepcopy(p)
            forged[key] = value
            forged.pop('preview_digest')
            forged['preview_digest'] = digest({'domain':'agent-network-owner-response-preview/v1', **forged})
            with self.subTest(key=key), self.assertRaises(Denied):
                self.prepare(forged)
        self.assertEqual(before, self.counts())

    def test_different_previews_concurrently_allocate_only_their_own_exact_reviews(self):
        self.ready()
        previews = [self.preview({'items':[{**self.item(), 'title':str(i)}]}) for i in range(3)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            cards = list(pool.map(self.prepare, previews*3))
        self.assertEqual(len({c['request_id'] for c in cards}), 3)
        for i, card in enumerate(cards):
            self.assertEqual(card['envelope'], previews[i % 3]['envelope'])
            self.assertEqual(card['state'], 'pending')
        self.assertEqual(self.action(action='next')['card']['state'], 'pending')

    def test_first_declined_history_wins_over_later_agent_import(self):
        self.ready(); p = self.preview(); original = self.prepare(p)
        self.action(action='decline',owner='alice',request_id=original['request_id'],review_digest=original['review_digest'])
        self.service._command('fixture_agent_call',actor='alice',command={'method':'propose','proposal_id':'later-identical','envelope':p['envelope']})
        later = self.w.import_proposal(self.p['selector'],self.p['context'],'alice','later-identical')
        self.assertEqual(original['request_id'],later['request_id'])
        replay = self.prepare(p)
        self.assertEqual(replay['request_id'],original['request_id'])
        self.assertEqual(replay['state'],'declined')
        self.w.reopen_storage(self.p['selector'],self.p['context'])
        self.assertEqual(self.prepare(p)['request_id'],original['request_id'])

    def test_precomputed_new_preview_cannot_open_after_other_result_finishes(self):
        self.ready()
        old = self.preview(); alternative = self.preview({'items':[self.item()]})
        card = self.prepare(old); self.send_process(card)
        before = self.counts()
        with self.assertRaises(Denied): self.prepare(alternative)
        self.assertEqual(self.prepare(old)['request_id'],card['request_id'])
        self.assertEqual(before,self.counts())

    def test_astral_escaping_near_transport_bound_survives_full_flow(self):
        self.ready()
        # Legal inert text whose default JSON encoding is far larger than UTF-8.
        item = {'title':'😀'*128,'url':'https://'+'😀'*20,'summary':'😀'*160}
        p = self.preview({'items':[item,item]})
        self.assertGreater(len(json.dumps(p['envelope'])),7500)
        self.assertLessEqual(len(json.dumps(p['envelope'])),8300)
        card = self.prepare(p); self.send_process(card)
        self.assertEqual(self.action(action='next')['kind'],'complete')

    def test_overlarge_ingress_and_nested_invalid_payload_leave_executor_usable(self):
        self.ready(); p = self.preview(); before = self.counts()
        for payload in ({'items':[{'title':'x'*17000}]}, {'items':[{'title':{},'summary':[], 'url':None}]}, {'items':[[[[[]]]]]}):
            with self.subTest(payload=str(payload)[:50]), self.assertRaises(Denied): self.preview(payload)
        self.assertEqual(before,self.counts())
        self.assertEqual(self.preview()['preview_digest'],p['preview_digest'])
