"""One approval inbox over real HTTP, real accounts and the real stores. Fictional people."""
import unittest

from conversation.autonomy import DeskAccess
from conversation.shared_draft import DraftAccess
from owner_phone.questions import QuestionAccess
from workspace_ui.tests.test_conversation_service import ConversationHTTPTests as Base


class ApprovalInboxTests(Base):
    def setUp(self):
        super().setUp()
        self.create(); self.join('bob')
        self.host = self.server.owner
        self.approvals = self.host.approvals

    def run_on_owner(self, fn):
        return self.server.owner_worker.submit(fn).result()

    def assistant(self, name):
        """What a trusted assistant host would hold: a lease and the owner's live session."""
        principal, token = self.keys[name], self.tokens[name]
        def make():
            lease = self.approvals.inbox.provision(principal, token, name + '_assistant', 'thread_1')
            desk, questions, _ = self.approvals.owner(principal)
            return (DeskAccess(desk, lease, lambda: token), QuestionAccess(questions, lease, lambda: token),
                    DraftAccess(self.host.missions.proposals or self._proposals(), self.approvals.inbox, lease, lambda: token))
        return self.run_on_owner(make)

    def _proposals(self):
        return self.approvals._proposals(self.keys['alice'], self.tokens['alice'])

    def test_empty_inbox_is_explicit(self):
        result = self.call('bob', '/api/approvals')
        self.assertEqual(result['count'], 0)
        self.assertIn('until you choose', result['note'])

    def test_assistant_message_waits_then_owner_approves_exact_text(self):
        desk, _, _ = self.assistant('bob')
        self.run_on_owner(lambda: desk.propose('p1', 'Fictional: Friday works for me'))
        waiting = self.call('bob', '/api/approvals')
        [message] = waiting['messages']
        self.assertEqual((message['text'], waiting['count']), ('Fictional: Friday works for me', 1))
        self.call('bob', f"/api/approvals/messages/{message['draft_id']}/approve", {'digest': 'f' * 64}, expect=400)
        sent = self.call('bob', f"/api/approvals/messages/{message['draft_id']}/approve", {'digest': message['digest']})
        self.assertEqual(sent['state'], 'sent')
        self.assertEqual([m['text'] for m in self.history('alice')], ['Fictional: Friday works for me'])
        self.assertEqual(self.call('bob', '/api/approvals')['count'], 0)
        # Alice cannot see or decide Bob's drafts.
        self.assertEqual(self.call('alice', '/api/approvals')['messages'], [])

    def test_decline_question_answer_and_timeline(self):
        desk, questions, _ = self.assistant('bob')
        self.run_on_owner(lambda: desk.propose('p1', 'Fictional: maybe not'))
        asked = self.run_on_owner(lambda: questions.ask('q1', 'Fictional: train or coach?', ['Train', 'Coach']))
        listing = self.call('bob', '/api/approvals')
        self.assertEqual(listing['count'], 2)
        self.call('bob', f"/api/approvals/messages/{listing['messages'][0]['draft_id']}/decline", {})
        answer = self.call('bob', f"/api/approvals/questions/{asked['question_id']}/answer", {'option': 1})
        self.assertEqual(answer['answer'], 'Coach')
        self.assertEqual(self.run_on_owner(lambda: questions.answer('q1'))['answer'], 'Coach')
        timeline = self.call('bob', '/api/approvals/timeline', {})
        self.assertEqual([e['kind'] for e in timeline['entries']],
                         ['message_proposed', 'question_asked', 'message_declined', 'question_answered'])
        self.assertEqual(self.history('alice'), [])

    def test_shared_draft_review_and_approval(self):
        self.call('alice', '/api/approvals')  # The coordinating owner opens the draft store.
        _, _, drafts = self.assistant('alice')
        draft = self.run_on_owner(lambda: drafts.start('d1', 'Fictional itinerary: train at nine'))
        waiting = self.call('bob', '/api/approvals')['drafts']
        self.assertEqual([d['draft_id'] for d in waiting], [draft['draft_id']])
        self.assertEqual(waiting[0]['author_name'], 'alice')
        review = self.call('bob', f"/api/approvals/drafts/{draft['draft_id']}/review", {'conversation_id': 'thread_1'})
        self.assertEqual(review['text'], 'Fictional itinerary: train at nine')
        self.assertIn('pays for nothing', review['scope'])
        approved = self.call('bob', f"/api/approvals/drafts/{draft['draft_id']}/approve", {'review_digest': review['review_digest']})
        self.assertEqual(approved['approved_by'], [self.keys['bob']])
        self.assertEqual(self.call('bob', '/api/approvals')['drafts'], [])
        # A second approval without a fresh review is refused.
        self.call('bob', f"/api/approvals/drafts/{draft['draft_id']}/approve", {'review_digest': review['review_digest']}, expect=400)

    def test_policy_and_guidance_settings(self):
        policy = self.call('bob', '/api/approvals/policy', {'assistant_id': 'bob_assistant', 'conversation_id': 'thread_1',
                                                            'mode': 'within_limits', 'max_auto': 1})
        self.assertTrue(policy['standing'])
        desk, _, _ = self.assistant('bob')
        self.assertTrue(self.run_on_owner(lambda: desk.propose('p1', 'Fictional hello'))['sent_without_review'])
        self.assertEqual(self.history('alice')[0]['kind'], 'assistant')
        cleared = self.call('bob', '/api/approvals/policy', {'assistant_id': 'bob_assistant', 'conversation_id': 'thread_1',
                                                             'mode': 'review_each'})
        self.assertFalse(cleared['standing'])
        notes = self.call('bob', '/api/approvals/guidance', {'assistant_id': 'bob_assistant', 'conversation_id': 'thread_1',
                                                             'add': 'Fictional: keep replies short'})
        self.assertEqual([n['text'] for n in notes['notes']], ['Fictional: keep replies short'])
        self.assertEqual(self.run_on_owner(lambda: desk.guidance())['notes'][0]['text'], 'Fictional: keep replies short')

    def test_unauthenticated_and_unknown_routes_are_refused(self):
        status, _ = self.request('GET', '/api/approvals')
        self.assertNotEqual(status, 200)
        self.call('bob', '/api/approvals/messages/x/explode', {}, expect=400)


# Run only the approval tests from this module.
for _name in [n for n in vars(Base) if n.startswith('test_')]:
    setattr(ApprovalInboxTests, _name, None)
del Base

if __name__ == '__main__':
    unittest.main()
