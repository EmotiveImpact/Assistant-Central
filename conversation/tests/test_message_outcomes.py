"""Exact local outcome inspection with genuine sessions and fictional owners."""
from contextlib import contextmanager
from dataclasses import replace
import sqlite3
import unittest
from unittest.mock import patch

from conversation import ConversationDenied, ConversationOutcomeUnknown
from conversation.tests import test_ledger as fixtures
from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import b64, canonical, digest


class MessageOutcomeTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.LedgerCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        return f

    def inspect(self, f, actor='bob', binding=None, **kwargs):
        request = dict({'request_id': 'request', 'text': 'Fictional message',
                        'kind': 'message', 'source_ids': []}, **kwargs)
        return f.ledger.inspect_message_outcome(
            *f.actor(actor), binding or f.bind(actor), request_id=request['request_id'],
            expected_request_digest=digest({key: request[key] for key in ('kind', 'text', 'source_ids')}))

    def rows(self, f):
        # The observed clock is the only ledger state an inspection may update.
        tables = f.ledger.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name!='conversation_clock' ORDER BY name").fetchall()
        return {row['name']: [tuple(item) for item in f.ledger.db.execute('SELECT * FROM ' + row['name'])]
                for row in tables}

    def assert_fenced(self, f):
        self.assertFalse(f.ledger.db.in_transaction)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    def restart(self, f, when):
        f.ledger.close()
        for auth in f.auths.values():
            auth.close()
        f.now = when
        for name in f.auths:
            auth = LocalOwnerAuth(f.root / name, clock=lambda: f.now)
            f.auths[name] = auth
            f.sessions[name] = auth.login('Fictional test password')
        f.ledger = f.open_ledger()

    def short_session(self, f, name, *, keep_old=False):
        old = f.sessions[name]
        f.sessions[name] = f.auths[name].login('Fictional test password', ttl=60)
        if not keep_old:
            f.auths[name].logout(old)

    @contextmanager
    def advance_last_auth(self, f, actor, *, seconds=61, refuse=False):
        original, calls = f.auths[actor].authenticate, 0
        def delayed(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now += seconds
                if refuse:
                    original(token)
            return result
        with patch.object(f.auths[actor], 'authenticate', delayed):
            yield
        self.assertEqual(calls, 2)

    @contextmanager
    def advance_final_scan(self, f, *, source_id=None, seconds=61):
        original_check, original_visible = f.ledger._assert_visible, f.ledger._visible
        checks = 0
        def visibility(event_id, *args, **kwargs):
            result = original_visible(event_id, *args, **kwargs)
            if event_id == source_id:
                f.now += seconds  # No explicit clock sample; scan must notice.
            return result
        def final_check(*args):
            nonlocal checks
            checks += 1
            if checks == 2:
                if source_id is None:
                    f.now += seconds
                with patch.object(f.ledger, '_visible', visibility):
                    return original_check(*args)
            return original_check(*args)
        with patch.object(f.ledger, '_assert_visible', final_check):
            yield
        self.assertEqual(checks, 2)

    def source_fixture(self, *, transitive=False):
        f = self.fixture()
        source = f.post('alice', 'Fictional private source', 'source')
        f.join('carol')
        review = f.ledger.prepare_history_grant(
            *f.actor('alice'), 'thread_1', f.keys['carol'], [source['id']],
            purpose='Exact fictional history', expires_at=f.now + 60)
        grant = f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest'])
        direct = source
        if transitive:
            direct = f.post('bob', 'Fictional intermediate quote', 'intermediate',
                            kind='quote', source_ids=[source['id']])
        request = dict(request_id='derived', text='Fictional summary', kind='summary', source_ids=[direct['id']])
        event = f.ledger.append(*f.actor('carol'), f.bind('carol'), **request)
        return f, source, grant, request, event

    def rewrite(self, f, event, mutate, *, resign=True):
        _, signed = f.ledger._event(event['id'])
        mutate(signed['body'])
        if resign:
            author = next(name for name, key in f.keys.items() if key == signed['body']['author'])
            signed['signature'] = b64(f.auths[author].sign(f.sessions[author], canonical(signed['body'])))
        encoded = f.ledger.storage.seal('conversation_events', event['id'], 'body', canonical(signed).decode())
        f.ledger.db.execute('UPDATE conversation_events SET body=?,request_digest=? WHERE id=?',
                            (encoded, signed['body']['request_digest'], event['id']))

    def test_lost_commit_reply_found_beyond_first_page_without_replay_or_new_rows(self):
        f = self.fixture()
        for i in range(26):
            f.post('alice', request='filler_' + str(i))
        binding, original = f.bind('bob'), f.ledger.db
        class LostAcknowledgement:
            commits = 0
            def __getattr__(self, name):
                return getattr(original, name)
            def execute(self, sql, *args):
                result = original.execute(sql, *args)
                if sql == 'COMMIT':
                    self.commits += 1
                    if self.commits == 2:
                        raise sqlite3.OperationalError('Synthetic lost message commit acknowledgement')
                return result
        request = dict(request_id='request', text='Fictional retained message')
        with patch.object(f.ledger, 'db', LostAcknowledgement()):
            with self.assertRaises(ConversationOutcomeUnknown):
                f.ledger.append(*f.actor('bob'), binding, **request)
        page = f.ledger.history(*f.actor('bob'), binding, limit=25)
        before = self.rows(f)
        f.now += 1
        with patch.object(f.ledger, 'append', side_effect=AssertionError('Inspection must not replay')):
            first = self.inspect(f, binding=binding, **request)
            self.assertEqual(self.inspect(f, binding=binding, **request), first)
        self.assertEqual(first['status'], 'committed')
        self.assertNotIn(first['event']['id'], [event['id'] for event in page])
        self.assertEqual(first['event']['text'], request['text'])
        self.assertFalse(first['event']['execution_authority'])
        self.assertEqual(first['event']['trust'], 'untrusted-message')
        self.assertEqual(set(first), {'status', 'event'})
        for hidden in ('request_id', 'request_digest', 'sequence', 'audience', 'author_epoch', 'count'):
            self.assertNotIn(hidden, first['event'])
        self.assertEqual(self.rows(f), before)
        self.assert_fenced(f)

    def test_absent_request_is_inconclusive_and_never_written_or_replayed(self):
        f = self.fixture()
        before = self.rows(f)
        f.now += 1
        with patch.object(f.ledger, 'append', side_effect=AssertionError('No replay')):
            self.assertEqual(self.inspect(f), {'status': 'inconclusive'})
            self.assertEqual(self.inspect(f, source_ids=['unknown_source']), {'status': 'inconclusive'})
        self.assertEqual(self.rows(f), before)
        self.assert_fenced(f)
        # A later independent write can still commit. Absence was no rollback proof.
        event = f.post('bob', request='request')
        self.assertEqual(self.inspect(f), {'status': 'committed', 'event': event})

    def test_changed_text_kind_source_selection_or_order_is_generic_refusal(self):
        f = self.fixture()
        sources = [f.post('alice', request='source_' + str(i))['id'] for i in range(2)]
        request = dict(request_id='request', text='Fictional summary', kind='summary', source_ids=sources)
        event = f.ledger.append(*f.actor('bob'), f.bind('bob'), **request)
        self.assertEqual(self.inspect(f, **request)['event'], event)
        before = self.rows(f)
        for change in ({'text': 'Changed'}, {'kind': 'quote'}, {'source_ids': sources[:1]},
                       {'source_ids': list(reversed(sources))}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                    self.inspect(f, **dict(request, **change))
        self.assertEqual(self.rows(f), before)

    def test_other_authors_and_rooms_do_not_reveal_request_existence(self):
        f = self.fixture()
        alice = f.post('alice', request='request')
        f.ledger.create(*f.actor('bob'), 'other_room')
        other_binding = f.bind('bob', 'other_room')
        with patch.object(f.ledger, '_event', side_effect=AssertionError('Do not open another author')):
            self.assertEqual(self.inspect(f), {'status': 'inconclusive'})
        bob = f.post('bob', request='request')
        with patch.object(f.ledger, '_event', side_effect=AssertionError('Do not open another room')):
            self.assertEqual(self.inspect(f, binding=other_binding), {'status': 'inconclusive'})
        self.assertEqual(self.inspect(f)['event'], bob)
        self.assertEqual(self.inspect(f, actor='alice')['event'], alice)
        self.assertNotEqual(bob['id'], alice['id'])

    def test_wrong_session_binding_and_foreign_or_unknown_room_refuse(self):
        f = self.fixture()
        f.post('bob', request='request')
        bob = f.bind('bob')
        with self.assertRaises(AuthError):
            f.ledger.inspect_message_outcome(f.keys['bob'], f.sessions['alice'], bob,
                                            request_id='request', expected_request_digest=digest(
                                                {'kind': 'message', 'text': 'Fictional message', 'source_ids': []}))
        f.ledger.create(*f.actor('alice'), 'alice_only')
        for binding in (f.bind('alice'), replace(bob, conversation_id='alice_only'),
                        replace(bob, conversation_id='missing_room'), replace(bob, member_epoch='fake')):
            with self.subTest(binding=binding):
                with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                    self.inspect(f, binding=binding)

    def test_stale_generation_removed_and_rejoined_member_cannot_recover_old_event(self):
        f = self.fixture()
        event = f.post('bob', request='request')
        before_join = f.bind('bob')
        f.join('carol')
        with self.assertRaises(ConversationDenied):
            self.inspect(f, binding=before_join)
        old = f.bind('bob')
        self.assertEqual(self.inspect(f, binding=old)['event'], event)
        f.ledger.remove_member(*f.actor('alice'), 'thread_1', f.keys['bob'])
        with self.assertRaises(ConversationDenied):
            self.inspect(f, binding=old)
        new = f.join('bob')
        for binding in (old, new):
            with self.assertRaises(ConversationDenied):
                self.inspect(f, binding=binding)
        f.grant('bob', 'bob', [event])  # A new, exact owner approval is required.
        self.assertEqual(self.inspect(f)['event'], event)

    def test_revocation_and_expiry_of_exact_source_grant_refuse(self):
        for cause in ('revocation', 'expiry'):
            with self.subTest(cause=cause):
                f, _, grant, request, event = self.source_fixture(transitive=True)
                binding = f.bind('carol')
                self.assertEqual(self.inspect(f, 'carol', binding, **request)['event'], event)
                if cause == 'revocation':
                    f.ledger.revoke_history_grant(*f.actor('alice'), grant)
                else:
                    f.now += 60
                with self.assertRaises(ConversationDenied):
                    self.inspect(f, 'carol', binding, **request)
                with self.assertRaises(ConversationDenied):
                    self.inspect(f, 'carol', **request)

    def test_rejoined_authors_own_grant_is_exact_revocable_and_expiring(self):
        for cause in ('revocation', 'expiry'):
            with self.subTest(cause=cause):
                f = self.fixture()
                event = f.post('bob', request='request')
                f.ledger.remove_member(*f.actor('alice'), 'thread_1', f.keys['bob'])
                f.join('bob')
                grant, _ = f.grant('bob', 'bob', [event])
                self.assertEqual(self.inspect(f)['event'], event)
                if cause == 'revocation':
                    f.ledger.revoke_history_grant(*f.actor('bob'), grant)
                else:
                    f.now += 300
                with self.assertRaises(ConversationDenied):
                    self.inspect(f)

    def test_forged_signature_and_signed_inconsistent_request_commitment_refuse(self):
        for cause in ('signature', 'signed_content', 'signed_commitment'):
            with self.subTest(cause=cause):
                f = self.fixture()
                event = f.post('bob', request='request')
                if cause == 'signed_commitment':
                    self.rewrite(f, event, lambda body: body.update(request_digest='0' * 64))
                else:
                    self.rewrite(f, event, lambda body: body.update(text='Changed signed content'),
                                 resign=cause != 'signature')
                with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                    self.inspect(f)

    def test_missing_changed_or_wrong_digest_ancestor_refuses_exact_inspection(self):
        for cause in ('missing', 'changed', 'wrong_digest'):
            with self.subTest(cause=cause):
                f, source, _, request, event = self.source_fixture(transitive=True)
                if cause == 'missing':
                    f.ledger.db.execute('DELETE FROM conversation_events WHERE id=?', (source['id'],))
                elif cause == 'changed':
                    def change(body):
                        body['text'] = 'Changed fictional source'
                        body['request_digest'] = digest({'kind': body['kind'], 'text': body['text'], 'source_ids': []})
                    self.rewrite(f, source, change)
                else:
                    self.rewrite(f, event, lambda body: body['sources'][0].update(digest='0' * 64))
                with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                    self.inspect(f, 'carol', **request)

    def test_cross_room_source_refuses_even_with_valid_signature_digest_and_sequence(self):
        f = self.fixture()
        f.ledger.create(*f.actor('bob'), 'other_room')
        other = f.post('bob', room='other_room')
        source = f.post('alice', request='source')
        request = dict(request_id='request', text='Fictional quote', kind='quote', source_ids=[source['id']])
        event = f.ledger.append(*f.actor('bob'), f.bind('bob'), **request)
        request['source_ids'] = [other['id']]
        def change(body):
            body['sources'] = [{'id': other['id'], 'digest': other['provenance_digest']}]
            body['request_digest'] = digest({key: request[key] for key in ('kind', 'text', 'source_ids')})
        self.rewrite(f, event, change)
        self.assertLess(f.ledger._event(other['id'])[0]['sequence'], f.ledger._event(event['id'])[0]['sequence'])
        with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
            self.inspect(f, **request)

    def test_locked_coordinator_and_logged_out_actor_refuse_found_and_absent(self):
        for state in ('coordinator', 'actor'):
            with self.subTest(state=state):
                f = self.fixture()
                f.post('bob', request='request')
                binding = f.bind('bob')
                if state == 'coordinator':
                    f.auths['alice'].lock()
                else:
                    f.auths['bob'].logout(f.sessions['bob'])
                for request_id in ('request', 'absent'):
                    with self.assertRaises((AuthError, ConversationDenied)):
                        self.inspect(f, binding=binding, request_id=request_id)

    def test_actor_and_coordinator_expiry_during_final_auth_refuse_found_and_absent(self):
        for owner in ('bob', 'alice'):
            for found in (True, False):
                with self.subTest(owner=owner, found=found):
                    f = self.fixture()
                    if found:
                        f.post('bob', request='request')
                    self.short_session(f, owner, keep_old=owner == 'bob')
                    binding, before = f.bind('bob'), self.rows(f)
                    with self.advance_last_auth(f, 'bob', seconds=60):
                        with self.assertRaises((AuthError, ConversationDenied)):
                            self.inspect(f, binding=binding)
                    self.assertEqual(self.rows(f), before)
                    self.assert_fenced(f)
                    self.restart(f, f.now - 1)
                    with self.assertRaises(ConversationDenied):
                        self.inspect(f, binding=binding)

    def test_actor_and_coordinator_expiry_during_final_scan_refuse_found_and_absent(self):
        for owner in ('bob', 'alice'):
            for found in (True, False):
                with self.subTest(owner=owner, found=found):
                    f = self.fixture()
                    event = f.post('bob', request='request') if found else None
                    self.short_session(f, owner, keep_old=owner == 'bob')
                    binding = f.bind('bob')
                    with self.advance_final_scan(f, source_id=event['id'] if found else None, seconds=60):
                        with self.assertRaises(ConversationDenied):
                            self.inspect(f, binding=binding)
                    self.assert_fenced(f)

    def test_grant_expiry_during_final_auth_or_transitive_scan_refuses(self):
        for stage in ('auth', 'scan'):
            with self.subTest(stage=stage):
                f, source, _, request, _ = self.source_fixture(transitive=True)
                binding, before = f.bind('carol'), self.rows(f)
                guard = self.advance_last_auth(f, 'carol', seconds=60) if stage == 'auth' else self.advance_final_scan(f, source_id=source['id'], seconds=60)
                with guard:
                    with self.assertRaises(ConversationDenied):
                        self.inspect(f, 'carol', binding, **request)
                self.assertEqual(self.rows(f), before)
                self.assert_fenced(f)
                self.restart(f, f.now - 1)
                with self.assertRaises(ConversationDenied):
                    self.inspect(f, 'carol', binding, **request)

    def test_genuine_final_auth_refusal_persists_clock(self):
        f = self.fixture()
        f.post('bob', request='request')
        self.short_session(f, 'bob')
        binding = f.bind('bob')
        with self.advance_last_auth(f, 'bob', refuse=True):
            with self.assertRaises(AuthError):
                self.inspect(f, binding=binding)
        self.assert_fenced(f)
        self.restart(f, f.now - 1)
        with self.assertRaises(ConversationDenied):
            self.inspect(f, binding=binding)

    def test_another_live_coordinator_session_preserves_exact_inspection(self):
        f = self.fixture()
        event = f.post('bob', request='request')
        self.short_session(f, 'alice', keep_old=True)
        binding = f.bind('bob')
        with self.advance_last_auth(f, 'bob'):
            self.assertEqual(self.inspect(f, binding=binding)['event'], event)
        self.assert_fenced(f)

    def test_restart_retains_exact_outcome_but_invalidates_old_sessions(self):
        f = self.fixture()
        event = f.post('bob', request='request')
        binding, old_session = f.bind('bob'), f.sessions['bob']
        self.restart(f, f.now + 1)
        with self.assertRaises(AuthError):
            f.ledger.inspect_message_outcome(f.keys['bob'], old_session, binding,
                                            request_id='request', expected_request_digest=digest(
                                                {'kind': 'message', 'text': 'Fictional message', 'source_ids': []}))
        self.assertEqual(self.inspect(f, binding=binding)['event'], event)

    def test_bad_request_identity_or_digest_is_bounded_without_mutation(self):
        f = self.fixture()
        binding, before = f.bind('bob'), self.rows(f)
        valid = dict(request_id='request', expected_request_digest='a' * 64)
        invalid = ({'request_id': 'bad:id'}, {'request_id': 'x' * 65}, {'request_id': ''},
                   {'expected_request_digest': None}, {'expected_request_digest': 1},
                   {'expected_request_digest': 'A' * 64}, {'expected_request_digest': 'g' * 64},
                   {'expected_request_digest': '0' * 63}, {'expected_request_digest': '0' * 65},
                   {'expected_request_digest': '0' * 64 + '\n'}, {'expected_request_digest': ''})
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(ConversationDenied):
                    f.ledger.inspect_message_outcome(*f.actor('bob'), binding, **dict(valid, **change))
        self.assertEqual(self.rows(f), before)

    def test_digest_uses_exact_utf8_text_without_unicode_normalisation(self):
        f = self.fixture()
        text = 'Fictional café ☕\nQuoted "text" with \\ backslash'
        event = f.post('bob', text, 'request')
        expected = digest({'kind': 'message', 'text': text, 'source_ids': []})
        result = f.ledger.inspect_message_outcome(*f.actor('bob'), f.bind('bob'),
                                                  request_id='request', expected_request_digest=expected)
        self.assertEqual(result['event'], event)
        with self.assertRaises(ConversationDenied):
            self.inspect(f, text=text.replace('é', 'e\u0301'))


if __name__ == '__main__':
    unittest.main()
