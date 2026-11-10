"""Final-boundary regressions using genuine sessions and fictional local owners."""
from contextlib import contextmanager
import sqlite3
import unittest
from unittest.mock import patch

from conversation import ConversationDenied, ConversationOutcomeUnknown
from conversation.tests import test_ledger as fixtures
from pilot.auth import AuthError, LocalOwnerAuth


class LedgerFinalSourceExpiry(unittest.TestCase):
    def fixture(self):
        f = fixtures.LedgerCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        return f

    def review(self, f, event):
        return f.ledger.prepare_history_grant(*f.actor('alice'), 'thread_1', f.keys['carol'], [event['id']],
                                             purpose='Exact fictional history', expires_at=f.now + 60)

    def source_fixture(self):
        f = self.fixture()
        source = f.post('alice', 'Earlier fictional private message', 'source')
        f.join('carol')
        review = self.review(f, source)
        f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest'])
        return f, source, f.bind('carol')

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

    def assert_fenced(self, f):
        self.assertFalse(f.ledger.db.in_transaction)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    @contextmanager
    def advance_last_auth(self, f, actor, seconds=61, *, refuse=False):
        original, calls = f.auths[actor].authenticate, 0
        def delayed(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now += seconds
                if refuse:
                    original(token)  # A genuine authentication refusal.
            return result
        with patch.object(f.auths[actor], 'authenticate', delayed):
            yield
        self.assertEqual(calls, 2)

    def test_reads_refuse_grant_expiry_during_last_authentication(self):
        for operation in ('read', 'history', 'search', 'context', 'cursor'):
            with self.subTest(operation=operation):
                f, source, binding = self.source_fixture()
                with self.advance_last_auth(f, 'carol'):
                    with self.assertRaises(ConversationDenied):
                        if operation == 'read':
                            f.ledger.read(*f.actor('carol'), binding, source['id'])
                        elif operation == 'context':
                            f.ledger.context(*f.actor('carol'), binding, [source['id']])
                        else:
                            kwargs = {'after': source['id'], 'query': 'absent'} if operation == 'cursor' else {'query': 'private' if operation == 'search' else None}
                            f.ledger.history(*f.actor('carol'), binding, **kwargs)
                self.assert_fenced(f)
                observed = f.now
                self.restart(f, observed - 1)
                with self.assertRaises(ConversationDenied):
                    f.ledger.history(*f.actor('carol'), binding)
                f.now = observed
                self.assertEqual(f.ledger.history(*f.actor('carol'), binding), [])

    def test_new_and_duplicate_append_refuse_last_auth_source_expiry(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                f, source, binding = self.source_fixture()
                kwargs = dict(request_id='derived', text='Fictional quote', kind='quote', source_ids=[source['id']])
                if duplicate:
                    f.ledger.append(*f.actor('carol'), binding, **kwargs)
                before = f.ledger.db.execute('SELECT COUNT(*) FROM conversation_events').fetchone()[0]
                with self.advance_last_auth(f, 'carol'):
                    with self.assertRaises(ConversationDenied):
                        f.ledger.append(*f.actor('carol'), binding, **kwargs)
                self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_events').fetchone()[0], before)
                self.assert_fenced(f)

    def test_review_preparation_refuses_expiry_during_last_authentication(self):
        f = self.fixture()
        source = f.post('alice')
        f.join('carol')
        with self.advance_last_auth(f, 'alice'):
            with self.assertRaises(ConversationDenied):
                self.review(f, source)
        self.assert_fenced(f)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_grants').fetchone()[0], 0)

    def test_new_and_duplicate_grant_approval_refuse_last_auth_expiry(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                f = self.fixture()
                source = f.post('alice')
                f.join('carol')
                review = self.review(f, source)
                if duplicate:
                    f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest'])
                generation = f.bind('alice').policy_generation
                audits = f.ledger.db.execute('SELECT COUNT(*) FROM conversation_audit').fetchone()[0]
                with self.advance_last_auth(f, 'alice'):
                    with self.assertRaises(ConversationDenied):
                        f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest'])
                self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_grants').fetchone()[0], int(duplicate))
                self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_audit').fetchone()[0], audits)
                self.assertEqual(f.bind('alice').policy_generation, generation)
                self.assert_fenced(f)

    def test_whole_final_scan_refuses_early_last_and_transitive_source_expiry(self):
        for which in ('early', 'last', 'transitive', 'unsampled'):
            with self.subTest(which=which):
                f, source, binding = self.source_fixture()
                later = f.post('bob', 'Future fictional message', 'later')
                events = [source['id'], later['id']]
                if which == 'transitive':
                    quote = f.post('bob', 'Fictional quote', 'quote', kind='quote', source_ids=[source['id']])
                    summary = f.post('bob', 'Fictional summary', 'summary', kind='summary', source_ids=[quote['id']])
                    events = [summary['id'], quote['id']]
                original_check, original_visible = f.ledger._assert_visible, f.ledger._visible
                checks = 0
                target = later['id'] if which == 'last' else source['id']
                def visibility(event_id, *args, **kwargs):
                    result = original_visible(event_id, *args, **kwargs)
                    if event_id == target:
                        f.now += 61
                        if which != 'unsampled':
                            f.ledger._now()
                    return result
                def final_check(*args):
                    nonlocal checks
                    checks += 1
                    if checks == 2:
                        with patch.object(f.ledger, '_visible', visibility):
                            return original_check(*args)
                    return original_check(*args)
                with patch.object(f.ledger, '_assert_visible', final_check):
                    with self.assertRaises(ConversationDenied):
                        f.ledger.context(*f.actor('carol'), binding, events)
                self.assertEqual(checks, 2)
                self.assert_fenced(f)

    def short_session(self, f, name, *, keep_old=False):
        old = f.sessions[name]
        f.sessions[name] = f.auths[name].login('Fictional test password', ttl=60)
        if not keep_old:
            f.auths[name].logout(old)

    def test_empty_outputs_refuse_actor_and_coordinator_last_auth_expiry(self):
        for owner in ('bob', 'alice'):
            with self.subTest(owner=owner):
                f = self.fixture()
                self.short_session(f, owner, keep_old=owner == 'bob')
                binding = f.bind('bob')
                with self.advance_last_auth(f, 'bob'):
                    with self.assertRaises(ConversationDenied):
                        f.ledger.history(*f.actor('bob'), binding, query='absent')
                self.assert_fenced(f)
                self.restart(f, f.now - 1)
                with self.assertRaises(ConversationDenied):
                    f.ledger.history(*f.actor('bob'), binding)

    def test_empty_outputs_refuse_session_expiry_inside_final_checks(self):
        for owner in ('bob', 'alice'):
            with self.subTest(owner=owner):
                f = self.fixture()
                self.short_session(f, owner, keep_old=owner == 'bob')
                binding = f.bind('bob')
                original, checks = f.ledger._assert_visible, 0
                def final_check(*args):
                    nonlocal checks
                    checks += 1
                    if checks == 2:
                        f.now += 61
                    return original(*args)
                with patch.object(f.ledger, '_assert_visible', final_check):
                    with self.assertRaises(ConversationDenied):
                        f.ledger.history(*f.actor('bob'), binding)
                self.assertEqual(checks, 2)
                self.assert_fenced(f)

    def test_another_current_coordinator_session_preserves_unlock(self):
        f = self.fixture()
        self.short_session(f, 'alice', keep_old=True)
        binding = f.bind('bob')
        with self.advance_last_auth(f, 'bob'):
            self.assertEqual(f.ledger.history(*f.actor('bob'), binding), [])
        self.assertTrue(f.auths['alice'].status()['unlocked'])
        self.assert_fenced(f)

    def test_grant_deadline_is_exclusive_at_exact_expiry(self):
        f, source, binding = self.source_fixture()
        with self.advance_last_auth(f, 'carol', seconds=60):
            with self.assertRaises(ConversationDenied):
                f.ledger.read(*f.actor('carol'), binding, source['id'])
        self.assert_fenced(f)

    def test_conservative_unrelated_and_overlapping_crossings_allow_fresh_inspection(self):
        for overlapping in (False, True):
            with self.subTest(overlapping=overlapping):
                f, source, _ = self.source_fixture()
                actor = 'carol' if overlapping else 'bob'
                if overlapping:
                    f.grant('alice', 'carol', [source])  # A second, longer grant.
                binding = f.bind(actor)
                original_check, original_visible = f.ledger._assert_visible, f.ledger._visible
                checks = 0
                def visibility(*args, **kwargs):
                    result = original_visible(*args, **kwargs)
                    f.now += 61
                    return result
                def final_check(*args):
                    nonlocal checks
                    checks += 1
                    if checks == 2:
                        with patch.object(f.ledger, '_visible', visibility):
                            return original_check(*args)
                    return original_check(*args)
                with patch.object(f.ledger, '_assert_visible', final_check):
                    with self.assertRaisesRegex(ConversationDenied, '^Conversation operation unavailable$'):
                        f.ledger.read(*f.actor(actor), binding, source['id'])
                self.assertEqual(checks, 2)
                self.assert_fenced(f)
                self.assertEqual(f.ledger.read(*f.actor(actor), binding, source['id'])['id'], source['id'])

    def test_authentication_refusals_persist_observed_time_across_restart(self):
        for stage in ('body', 'final'):
            with self.subTest(stage=stage):
                f = self.fixture()
                event = f.post('alice')
                binding = f.bind('bob')
                original = f.ledger._public_event
                def delayed(event_id):
                    result = original(event_id)
                    f.now += 901
                    f.auths['bob'].authenticate(f.sessions['bob'])
                    return result
                guard = patch.object(f.ledger, '_public_event', delayed) if stage == 'body' else self.advance_last_auth(f, 'bob', seconds=901, refuse=True)
                with guard:
                    with self.assertRaises(AuthError):
                        f.ledger.read(*f.actor('bob'), binding, event['id'])
                self.assert_fenced(f)
                self.restart(f, f.now - 1)
                with self.assertRaises(ConversationDenied):
                    f.ledger.history(*f.actor('bob'), binding)

    def test_identical_retries_stay_idempotent_and_changed_retries_fail(self):
        f, source, binding = self.source_fixture()
        kwargs = dict(request_id='repeat', text='Fictional quote', kind='quote', source_ids=[source['id']])
        first = f.ledger.append(*f.actor('carol'), binding, **kwargs)
        self.assertEqual(f.ledger.append(*f.actor('carol'), binding, **kwargs), first)
        with self.assertRaises(ConversationDenied):
            f.ledger.append(*f.actor('carol'), binding, **dict(kwargs, text='Changed'))
        review = self.review(f, source)
        grant = f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest'])
        before = f.ledger.db.execute('SELECT COUNT(*) FROM conversation_audit').fetchone()[0]
        self.assertEqual(f.ledger.approve_history_grant(*f.actor('alice'), review, review['review_digest']), grant)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_audit').fetchone()[0], before)

    def test_lost_commit_acknowledgement_retains_unknown_and_exact_request(self):
        self.lost_acknowledgement()

    def test_clock_refusal_cannot_mask_an_uncertain_commit(self):
        self.lost_acknowledgement(rewind=True)

    def lost_acknowledgement(self, *, rewind=False):
        f = self.fixture()
        binding = f.bind('bob')
        original = f.ledger.db
        class LostAcknowledgement:
            def __init__(self):
                self.commits = 0
            def __getattr__(self, name):
                return getattr(original, name)
            def execute(self, sql, *args):
                result = original.execute(sql, *args)
                if sql == 'COMMIT':
                    self.commits += 1
                    if self.commits == 2:  # Clock fence precedes message commit.
                        if rewind:
                            f.now -= 1
                        raise sqlite3.OperationalError('Synthetic lost commit acknowledgement')
                return result
        kwargs = dict(request_id='uncertain', text='Fictional retained message')
        with patch.object(f.ledger, 'db', LostAcknowledgement()):
            with self.assertRaises(ConversationOutcomeUnknown):
                f.ledger.append(*f.actor('bob'), binding, **kwargs)
        if rewind:
            f.now += 1
        retained = f.ledger.history(*f.actor('bob'), binding)
        self.assertEqual(len(retained), 1)
        self.assertEqual(f.ledger.append(*f.actor('bob'), binding, **kwargs), retained[0])
        self.assert_fenced(f)
