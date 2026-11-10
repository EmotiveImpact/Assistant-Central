"""Independent disclosure boundary review, with fictional genuine local sessions."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from conversation import ConversationDenied
from conversation.disclosure_review import ConversationDisclosureReviews, fixture_route
from conversation.tests import test_ledger as fixtures
from pilot.crypto import b64, canonical
from pilot.source_grants import commitment


class IndependentDisclosureBoundaries(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.LedgerCase(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def prepare(self, f, events, **overrides):
        arguments = dict(event_ids=[event['id'] for event in events], operation_id='independent_review',
                         route=fixture_route(), review_deadline=f.now + 300)
        arguments.update(overrides)
        return ConversationDisclosureReviews(f.ledger).prepare(*f.actor('alice'), f.bind('alice'), **arguments)

    def reinspect(self, f, review, expected=None):
        return ConversationDisclosureReviews(f.ledger).reinspect(
            *f.actor('bob'), f.bind('bob'), review,
            expected if expected is not None else review['review_commitment'])

    def rewrite(self, f, event, update):
        _, signed = f.ledger._event(event['id'])
        update(signed['body'])
        author = next(name for name, principal in f.keys.items() if principal == signed['body']['author'])
        signed['signature'] = b64(f.auths[author].sign(f.sessions[author], canonical(signed['body'])))
        encoded = f.ledger.storage.seal('conversation_events', event['id'], 'body', canonical(signed).decode())
        f.ledger.db.execute('UPDATE conversation_events SET body=? WHERE id=?', (encoded, event['id']))

    def test_selected_ancestor_is_payload_once_and_does_not_duplicate_evidence(self):
        f = self.fixture()
        source = f.post('bob', 'Fictional source', 'source')
        derived = f.post('alice', 'Fictional derived output', 'derived', kind='summary', source_ids=[source['id']])
        review = self.prepare(f, [derived, source])
        self.assertEqual([part['content'][0]['text'] for part in review['body']['request']['input']],
                         [derived['text'], source['text']])
        self.assertEqual(len(review['body']['evidence']), 2)
        self.assertEqual(len(review['body']['plan']['sources']), 2)
        self.assertEqual(self.reinspect(f, review), review)

    def test_plain_message_with_declared_sources_cannot_skip_ancestor_reviewers(self):
        f = self.fixture()
        source = f.post('bob', 'Fictional prior text', 'source')
        derived = f.post('alice', 'Fictional message with declared source', 'derived',
                         kind='message', source_ids=[source['id']])
        review = self.prepare(f, [derived])
        self.assertEqual({item['principal'] for item in review['body']['context']['source_reviewers']},
                         {f.keys['alice'], f.keys['bob']})
        self.assertEqual({item['id'] for item in review['body']['evidence']}, {source['id'], derived['id']})

    def test_supplied_owner_map_and_rehashed_ancestor_omission_cannot_replace_ledger(self):
        f = self.fixture()
        source = f.post('bob', 'Fictional source', 'source')
        derived = f.post('alice', 'Fictional output', 'derived', kind='summary', source_ids=[source['id']])
        review = self.prepare(f, [derived])
        altered = deepcopy(review)
        altered['body']['evidence'] = [item for item in altered['body']['evidence'] if item['id'] != source['id']]
        altered['body']['context']['source_reviewers'] = [item for item in altered['body']['context']['source_reviewers']
                                                         if item['principal'] != f.keys['bob']]
        altered['body']['context']['graph_digest'] = commitment(altered['body']['evidence'])
        altered['body']['plan']['sources'] = [item for item in altered['body']['plan']['sources'] if item['source_id'] != source['id']]
        altered['body']['plan']['context'] = commitment(altered['body']['context'])
        altered['review_commitment'] = commitment(altered['body'])
        # Even mistakenly trusting the attacker-rehashed commitment must not
        # permit an incomplete source graph to masquerade as fresh host output.
        with self.assertRaises(ConversationDenied):
            self.reinspect(f, altered)

    def test_returned_reviews_and_input_arguments_are_independent_snapshots(self):
        f = self.fixture()
        source = f.post('bob', 'Original fictional text', 'source')
        route = fixture_route()
        selected = [source['id']]
        review = self.prepare(f, [source], route=route, event_ids=selected)
        expected = deepcopy(review)
        inspected = self.reinspect(f, review)
        inspected['body']['evidence'][0]['text'] = 'Changed returned evidence'
        inspected['body']['request']['input'][0]['content'][0]['text'] = 'Changed returned payload'
        route['account'] = 'changed-caller-account'
        selected[:] = ['changed-caller-selection']
        self.assertEqual(review, expected)
        self.assertEqual(self.reinspect(f, review), expected)
        self.assertEqual(self.prepare(f, [source]), expected)
        self.assertEqual(f.ledger.read(*f.actor('bob'), f.bind('bob'), source['id'])['text'], source['text'])

    def test_signed_duplicate_and_malformed_edges_refuse_before_visibility(self):
        for label in ('duplicate', 'extra_field', 'wrong_id_type', 'bad_digest', 'too_many'):
            with self.subTest(label=label):
                f = self.fixture()
                source = f.post('bob', 'Fictional source', 'source')
                derived = f.post('alice', 'Fictional output', 'derived', kind='quote', source_ids=[source['id']])
                edge = deepcopy(f.ledger._event(derived['id'])[1]['body']['sources'][0])
                if label == 'duplicate':
                    edges = [edge, deepcopy(edge)]
                elif label == 'extra_field':
                    edges = [dict(edge, owner=f.keys['carol'])]
                elif label == 'wrong_id_type':
                    edges = [dict(edge, id=5)]
                elif label == 'bad_digest':
                    edges = [dict(edge, digest='A' * 64)]
                else:
                    edges = [dict(edge, id='source_' + str(index)) for index in range(17)]
                self.rewrite(f, derived, lambda body: body.update(sources=edges))
                with patch.object(f.ledger, '_assert_visible', side_effect=AssertionError('Closure must refuse first')):
                    with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                        self.prepare(f, [derived])

    def test_non_ascii_request_commitment_is_exact_canonical_payload(self):
        f = self.fixture()
        text = 'Fictional café, quotation “hello”, and tea 🍵\nnext line\u0000'
        event = f.post('bob', text, 'unicode')
        review = self.prepare(f, [event])
        request = review['body']['request']
        self.assertEqual(request['input'][0]['content'][0]['text'], text)
        self.assertEqual(review['body']['plan']['payload_digest'], commitment(request))
        self.assertEqual(json.loads(canonical(request))['input'][0]['content'][0]['text'], text)
        altered = deepcopy(review)
        altered['body']['request']['input'][0]['content'][0]['text'] = text.replace('é', 'e\u0301')
        altered['body']['plan']['payload_digest'] = commitment(altered['body']['request'])
        altered['review_commitment'] = commitment(altered['body'])
        with self.assertRaises(ConversationDenied):
            self.reinspect(f, altered)

    def test_reinspection_requires_current_policy_for_every_other_reviewer(self):
        f = self.fixture()
        old = f.post('bob', 'Fictional old text', 'old')
        f.join('carol')
        grant, _ = f.grant('bob', 'carol', [old])
        selected = f.post('carol', 'Fictional quote', 'selected', kind='quote', source_ids=[old['id']])
        review = self.prepare(f, [selected])
        f.ledger.revoke_history_grant(*f.actor('bob'), grant)
        # Bob still sees every event. A fresh review must nevertheless refuse
        # because Carol, another required reviewer, lost access to the ancestry.
        self.assertEqual(f.ledger.read(*f.actor('bob'), f.bind('bob'), selected['id'])['text'], selected['text'])
        with self.assertRaises(ConversationDenied):
            self.reinspect(f, review)
        with self.assertRaises(ConversationDenied):
            self.prepare(f, [selected])

    def test_reordered_sources_changes_review_even_when_selected_payload_does_not(self):
        f = self.fixture()
        first = f.post('bob', 'First fictional source', 'first')
        second = f.post('alice', 'Second fictional source', 'second')
        derived = f.post('alice', 'Same fictional output', 'derived', kind='summary', source_ids=[first['id'], second['id']])
        review = self.prepare(f, [derived])
        self.rewrite(f, derived, lambda body: body['sources'].reverse())
        fresh = self.prepare(f, [derived])
        self.assertEqual(fresh['body']['request'], review['body']['request'])
        self.assertNotEqual(fresh['review_commitment'], review['review_commitment'])
        with self.assertRaises(ConversationDenied):
            self.reinspect(f, review)

    def test_oversized_multibyte_combined_envelope_is_never_truncated(self):
        f = self.fixture()
        event = f.post('bob', '🍵' * 2000, 'multibyte')
        with self.assertRaises(ConversationDenied):
            self.prepare(f, [event])
        self.assertEqual(f.ledger.read(*f.actor('bob'), f.bind('bob'), event['id'])['text'], event['text'])

    def test_oversized_integer_deadline_is_a_generic_refusal(self):
        f = self.fixture()
        event = f.post('bob', 'Fictional event', 'oversized_deadline')
        with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
            self.prepare(f, [event], review_deadline=10**500)
        self.assertFalse(f.ledger.db.in_transaction)
