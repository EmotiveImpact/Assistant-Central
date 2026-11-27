"""Room records over a real local relay: notes, changes of mind and votes."""
import hashlib
import time
import unittest

from pilot import room
from pilot.runtime import RuntimeDenied
from pilot.tests.test_relay_link import RelayLinkTests


class RoomRecordTests(RelayLinkTests):
    def setUp(self):
        super().setUp()
        self.connect(self.edem, self.maya)
        self.context = hashlib.sha256(b'Fictional Nana 80th').hexdigest()

    def send(self, sender, recipient, title, text, task_id, kind='task', parent_id=None):
        item = sender.runtime.propose(sender.session, recipient.fingerprint, kind, title, text, self.context,
                                      task_id, time.time() + 3000, parent_id=parent_id)
        review = sender.runtime.review(sender.session, item['id'])
        sender.runtime.release(sender.session, item['id'], review['review_digest'])
        self.assertEqual(sender.sync(send=True)['sent'], 1)
        self.assertEqual(recipient.sync(send=False)['received'], 1)
        return item['id']

    def decide(self, owner, item_id, decision):
        review = owner.runtime.review(owner.session, item_id)
        return owner.runtime.decide(owner.session, item_id, review['review_digest'], decision)

    def test_a_note_and_a_change_of_mind_reach_the_other_side(self):
        first = room.note_text("Nana's 80th", 'Where to stay', 'SYNTHETIC ONLY: the Station Hotel has six rooms.', 'idea')
        self.send(self.maya, self.edem, 'Where to stay: Station Hotel', first, 'note-hotel')
        change = room.note_text("Nana's 80th", 'Where to stay', 'SYNTHETIC ONLY: two cottages instead.', 'change',
                                'doing', replaces='note-hotel', why='Cheaper, and Nana can rest in the afternoon.')
        item = self.send(self.maya, self.edem, 'Where to stay: two cottages', change, 'note-cottages')
        seen = self.edem.runtime.status(self.edem.session, item)['room']
        self.assertEqual((seen['record'], seen['note'], seen['replaces'], seen['stage']), ('note', 'change', 'note-hotel', 'doing'))
        self.assertEqual(seen['why'], 'Cheaper, and Nana can rest in the afternoon.')

    def test_each_answer_to_a_vote_is_the_recipients_own_signed_decision(self):
        text = room.vote_text("Nana's 80th", 'Food', 'SYNTHETIC ONLY: lunch at 1pm, not 12?', 'vote-lunch', 'all')
        item = self.send(self.edem, self.maya, 'Vote: lunch at 1pm', text, 'vote-lunch-maya')
        incoming = self.maya.runtime.status(self.maya.session, item)
        self.assertEqual((incoming['room']['record'], incoming['room']['rule'], incoming['room']['stance']), ('vote', 'all', 'yes'))
        self.decide(self.maya, item, 'accept')
        self.maya.sync(send=True)
        self.edem.sync(send=False)
        answered = self.edem.runtime.status(self.edem.session, item)
        self.assertEqual(answered['historical_state'], 'accepted')
        self.assertEqual(answered['room']['vote_id'], 'vote-lunch')

    def test_malformed_records_and_returned_records_are_refused(self):
        bad = [
            room.NOTE + '{"room":"A"}',
            room.NOTE + 'not json',
            room.VOTE + '{"room":"A","thread":"B","question":"Q","rule":"some","stance":"yes","vote_id":"v1","why":null}',
            # A change of mind must name what it replaces and why.
            room.NOTE + '{"note":"change","replaces":null,"room":"A","stage":"doing","summary":"S","thread":"B","why":null}',
        ]
        for index, text in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(RuntimeDenied):
                self.edem.runtime.propose(self.edem.session, self.maya.fingerprint, 'task', 'Room record', text,
                                          self.context, f'bad-{index}', time.time() + 3000)
        task = self.send(self.edem, self.maya, 'Plan the day', 'SYNTHETIC ONLY: plan the day.', 'plan-day')
        self.decide(self.maya, task, 'accept')
        self.maya.sync(send=True)
        self.edem.sync(send=False)
        note = room.note_text('A', 'B', 'SYNTHETIC ONLY: done.', stage='done')
        with self.assertRaises(RuntimeDenied):
            self.maya.runtime.propose(self.maya.session, self.edem.fingerprint, 'artifact', 'Result', note,
                                      self.context, 'plan-day', time.time() + 2000, parent_id=task)

    def test_helpers_check_what_they_write(self):
        with self.assertRaises(room.RoomDenied):
            room.note_text('A', 'B', 'S', 'change', 'doing')
        with self.assertRaises(room.RoomDenied):
            room.vote_text('A', 'B', 'Q', 'bad id with spaces')
        self.assertIsNone(room.kind_of('SYNTHETIC ONLY: an ordinary task'))


def load_tests(loader, tests, pattern):
    # Only this file's tests: the relay link tests already run on their own.
    return loader.loadTestsFromNames([f'{__name__}.RoomRecordTests.{name}' for name in
                                      loader.getTestCaseNames(RoomRecordTests) if name in RoomRecordTests.__dict__])


if __name__ == '__main__':
    unittest.main()
