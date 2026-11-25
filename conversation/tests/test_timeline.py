"""One owner timeline across inbox, desk, drafts and questions; fictional identities."""
import sqlite3
import unittest
from contextlib import closing

from conversation import ConversationDenied
from conversation.autonomy import OwnerDesk
from conversation.inbox import InboxAccess
from conversation.proposals import LocalProposals
from conversation.shared_draft import DraftAccess
from conversation.timeline import OwnerTimeline
from conversation.tests.test_inbox import InboxCase
from mission_cards.log import ActivityLog
from owner_phone.questions import OwnerQuestions


class TimelineCase(InboxCase):
    def setUp(self):
        super().setUp()
        self.timeline = OwnerTimeline(self.root / 'timeline_bob', self.auths['bob'], self.keys['bob'], lambda: self.now)
        self.bob_lease = self.lease()

    def tearDown(self):
        self.timeline.close()
        super().tearDown()

    def kinds(self, **kwargs):
        return [(e['role'], e['kind']) for e in self.timeline.read(self.sessions['bob'], **kwargs)['entries']]


class TimelineTests(TimelineCase):
    def test_everything_lands_in_one_ordered_timeline(self):
        inbox = InboxAccess(self.inbox, self.bob_lease, lambda: self.sessions['bob'], timeline=self.timeline)
        desk = OwnerDesk(self.root / 'desk', self.ledger, self.inbox, self.keys['bob'], timeline=self.timeline)
        questions = OwnerQuestions(self.root / 'questions', self.inbox, self.keys['bob'], timeline=self.timeline)
        drafts = DraftAccess(LocalProposals(self.ledger, *self.actor('alice')), self.inbox, self.bob_lease,
                             lambda: self.sessions['bob'], timeline=self.timeline)
        try:
            self.post('alice', 'Fictional: where shall we go?', 'r1')
            inbox.pending()
            inbox.pending()  # Re-reading the same message does not add a second entry.
            desk.set_policy(self.sessions['bob'], 'bob_assistant', 'thread_1', mode='within_limits', max_auto=1)
            desk.propose(self.sessions['bob'], self.bob_lease, request_id='p1', text='Fictional: the coast')
            desk.propose(self.sessions['bob'], self.bob_lease, request_id='p2', text='Fictional: or the hills')
            [waiting] = desk.drafts(self.sessions['bob'])
            desk.approve(self.sessions['bob'], waiting['draft_id'], waiting['digest'])
            asked = questions.ask(self.sessions['bob'], self.bob_lease, request_id='q1',
                                  question='Fictional: budget?', options=['Low', 'High'])
            questions.answer(self.sessions['bob'], asked['question_id'], 0)
            drafts.start('d1', 'Fictional itinerary')
        finally:
            desk.close()
            questions.close()
        self.assertEqual(self.kinds(), [
            ('someone_else', 'message_received'),
            ('you', 'policy_changed'),
            ('your_assistant', 'message_proposed'),
            ('your_assistant', 'message_sent_by_assistant'),
            ('your_assistant', 'message_proposed'),
            ('you', 'message_approved'),
            ('your_assistant', 'question_asked'),
            ('you', 'question_answered'),
            ('your_assistant', 'draft_started'),
        ])
        entries = self.timeline.read(self.sessions['bob'])['entries']
        self.assertTrue(all('text' not in e['detail'] for e in entries))
        self.assertEqual(entries[7]['detail']['via'], 'central')

    def test_paging_and_filter(self):
        for i in range(5):
            self.timeline.record('mission_activity', 'thread_1' if i % 2 else 'thread_2', role='system', ref=f'm:{i}')
        page = self.timeline.read(self.sessions['bob'], limit=2)
        self.assertEqual(([e['seq'] for e in page['entries']], page['more']), ([1, 2], True))
        rest = self.timeline.read(self.sessions['bob'], after=page['next_after'])
        self.assertEqual([e['seq'] for e in rest['entries']], [3, 4, 5])
        self.assertEqual(len(self.timeline.read(self.sessions['bob'], conversation_id='thread_1')['entries']), 2)

    def test_only_the_owner_can_read(self):
        self.timeline.record('mission_activity', 'thread_1', role='system', ref='m:1')
        with self.assertRaises(Exception):
            self.timeline.read(self.sessions['alice'])

    def test_tampering_is_detected(self):
        for i in range(3):
            self.timeline.record('mission_activity', 'thread_1', role='system', ref=f'm:{i}')
        with closing(sqlite3.connect(self.root / 'timeline_bob' / 'timeline.sqlite')) as db:
            db.execute("UPDATE timeline SET role='you' WHERE seq=2")
            db.commit()
        with self.assertRaises(ConversationDenied):
            self.timeline.read(self.sessions['bob'])

    def test_deleted_entry_is_detected(self):
        for i in range(3):
            self.timeline.record('mission_activity', 'thread_1', role='system', ref=f'm:{i}')
        with closing(sqlite3.connect(self.root / 'timeline_bob' / 'timeline.sqlite')) as db:
            db.execute('DELETE FROM timeline WHERE seq=2')
            db.commit()
        with self.assertRaises(ConversationDenied):
            self.timeline.verify()

    def test_time_never_runs_backwards_and_bad_input_is_refused(self):
        self.timeline.record('mission_activity', 'thread_1', role='system', ref='m:1')
        self.now -= 100
        self.timeline.record('mission_activity', 'thread_1', role='system', ref='m:2')
        self.now += 100  # Owner sign-in refuses a clock that runs backwards, so restore it to read.
        first, second = self.timeline.read(self.sessions['bob'])['entries']
        self.assertGreaterEqual(second['at'], first['at'])
        for kwargs in ({'kind': 'nonsense', 'role': 'system', 'ref': 'x'},
                       {'kind': 'mission_activity', 'role': 'boss', 'ref': 'x'},
                       {'kind': 'mission_activity', 'role': 'system', 'ref': 'bad ref with spaces'}):
            kind = kwargs.pop('kind')
            with self.subTest(kind=kind, **kwargs), self.assertRaises(ConversationDenied):
                self.timeline.record(kind, 'thread_1', **kwargs)

    def test_mission_activity_import_is_idempotent_and_body_free(self):
        log = ActivityLog('mission-1', {'bob', 'alice'}, clock=lambda: int(self.now))
        log.append('mission-1', 'alice', 'card_created', {'title': 'Fictional card'})
        log.append('mission-1', 'bob', 'acknowledged', {})
        self.assertEqual(self.timeline.record_mission_activity('thread_1', log, owner_label='bob'), 2)
        self.timeline.record_mission_activity('thread_1', log, owner_label='bob')
        entries = self.timeline.read(self.sessions['bob'])['entries']
        self.assertEqual([(e['role'], e['detail']['event']) for e in entries],
                         [('someone_else', 'card_created'), ('you', 'acknowledged')])
        self.assertNotIn('Fictional card', str(entries))

    def test_details_are_encrypted_at_rest(self):
        self.timeline.record('mission_activity', 'thread_1', role='system', ref='m:1', detail={'note': 'fictional-marker'})
        with closing(sqlite3.connect(self.root / 'timeline_bob' / 'timeline.sqlite')) as db:
            raw = db.execute('SELECT detail FROM timeline').fetchall()
        self.assertNotIn('fictional-marker', str(raw))


if __name__ == '__main__':
    unittest.main()
