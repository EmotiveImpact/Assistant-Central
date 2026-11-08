"""Independent offline adversarial review of processed inbound owner reads."""
import json
import pathlib
import sqlite3
import unittest
from network import Denied, canonical
from tests import test_owner_messages as helpers

class IndependentMessageReview(unittest.TestCase):
    setUp = helpers.OwnerMessageTests.setUp
    action = helpers.OwnerMessageTests.action
    bind = helpers.OwnerMessageTests.bind
    pair = helpers.OwnerMessageTests.pair
    approve_submit = helpers.OwnerMessageTests.approve_submit
    send_process = helpers.OwnerMessageTests.send_process
    counts = helpers.OwnerMessageTests.counts
    received = helpers.OwnerMessageTests.received
    preview = helpers.OwnerMessageTests.preview
    prepare = helpers.OwnerMessageTests.prepare
    prepare_body = helpers.OwnerMessageTests.prepare_body

    def processed(self):
        self.bind(); self.pair()
        card = self.action(action='next')['card']; self.send_process(card)
        return card

    def database(self):
        for p in pathlib.Path(self.service.directory.name).glob('*.sqlite3'):
            with sqlite3.connect(p) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='transitions'").fetchone(): return p
        self.fail('No session database')

    def test_pending_authorization_read_never_reconciles_or_creates_tables(self):
        self.bind(); self.pair(); card=self.action(action='next')['card']
        self.action(action='approve',owner='bob',request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE bob')
        before=self.counts()
        for owner in ('alice','bob'):
            self.assertEqual(self.received(owner)['messages'],[])
        self.assertEqual(before,self.counts())

    def test_corrupted_later_projection_fails_before_earlier_message_disclosure(self):
        self.processed(); result=self.prepare(self.preview());self.send_process(result)
        with sqlite3.connect(self.database()) as db:
            seq,body=db.execute('SELECT seq,body FROM transitions ORDER BY seq DESC LIMIT 1').fetchone()
            value=json.loads(body);value['reply_to']='0'*64
            db.execute('UPDATE transitions SET body=? WHERE seq=?',(canonical(value),seq))
        before=self.counts()
        for owner in ('alice','bob'):
            with self.assertRaises(Denied):self.received(owner)
        self.assertEqual(before,self.counts())

    def test_mismatching_session_context_denied_without_repair(self):
        self.processed()
        with sqlite3.connect(self.database()) as db:db.execute('UPDATE sessions SET context=?',('0'*64,))
        before=self.counts()
        with self.assertRaises(Denied):self.received('alice')
        self.assertEqual(before,self.counts())

    def test_corrupt_recipient_denied_without_cross_owner_content(self):
        self.processed()
        with sqlite3.connect(self.database()) as db:
            seq,body=db.execute('SELECT seq,body FROM transitions LIMIT 1').fetchone()
            value=json.loads(body);value['recipient']='bob'
            db.execute('UPDATE transitions SET body=? WHERE seq=?',(canonical(value),seq))
        for owner in ('alice','bob'):
            with self.assertRaises(Denied):self.received(owner)

    def test_large_unicode_processed_response_fits_frame_and_next_read(self):
        self.processed()
        item={'title':'😀'*128,'url':'https://example.invalid','summary':'😀'*512}
        card=self.prepare(self.preview({'items':[item]}));self.send_process(card)
        value=self.received('bob')
        self.assertEqual(value['messages'][0]['envelope']['payload']['items'],[item])
        self.assertGreater(len(json.dumps(value)),4000)
        self.assertEqual(self.received('bob'),value)
        self.assertEqual(len(self.received('alice')['messages']),1)

    def test_both_agent_actors_cannot_read_even_own_received_history(self):
        self.processed()
        for actor in ('alice','bob'):
            for owner in ('alice','bob'):
                with self.assertRaises(Denied):
                    self.service._command('fixture_agent_call',actor=actor,command={'method':'received_messages','owner':owner})
        self.assertEqual(len(self.received('alice')['messages']),1)
        self.assertEqual(self.received('bob')['messages'],[])
