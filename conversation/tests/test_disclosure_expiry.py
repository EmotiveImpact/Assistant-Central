"""Whole-review deadline fences, real local sessions and durable refused time."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from conversation import ConversationDenied
from conversation.disclosure_review import ConversationDisclosureReviews, fixture_route
from conversation.tests import test_disclosure_review as fixtures
from pilot.auth import AuthError, LocalOwnerAuth


class DisclosureExpiryTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.DisclosureReviewTests(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        return f

    def assert_fenced(self, f):
        self.assertFalse(f.ledger.db.in_transaction)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    def restart(self, f, when):
        f.ledger.close()
        for auth in f.auths.values():
            auth.close()
        f.now = when
        for name in f.auths:
            f.auths[name] = LocalOwnerAuth(f.root / name, clock=lambda: f.now)
            f.sessions[name] = f.auths[name].login('Fictional test password')
        f.ledger = f.open_ledger()

    def operation(self, f, mode, *, deadline=None):
        event = f.post('bob')
        api, binding = f.api, f.bind('bob')
        options = dict(event_ids=[event['id']], operation_id='expiry', route=fixture_route(),
                       review_deadline=f.now + 300 if deadline is None else deadline)
        review = api.prepare(*f.actor('bob'), binding, **options)
        if mode == 'prepare':
            return lambda: api.prepare(*f.actor('bob'), binding, **options), api, review
        return lambda: api.reinspect(*f.actor('bob'), binding, review, review['review_commitment']), api, review

    @contextmanager
    def last_auth(self, f, seconds, *, refuse=False):
        original, calls = f.auths['bob'].authenticate, []
        def delayed(token):
            result = original(token)
            calls.append(token)
            if len(calls) == 2:
                f.now += seconds
                if refuse:
                    original(token)
            return result
        with patch.object(f.auths['bob'], 'authenticate', delayed):
            yield
        self.assertEqual(len(calls), 2)

    def short_session(self, f, name, *, keep_old):
        old = f.sessions[name]
        f.sessions[name] = f.auths[name].login('Fictional test password', ttl=60)
        if not keep_old:
            f.auths[name].logout(old)

    def test_prepare_and_reinspect_refuse_final_actor_and_coordinator_expiry(self):
        for mode in ('prepare', 'reinspect'):
            for owner in ('bob', 'alice'):
                with self.subTest(mode=mode, owner=owner):
                    f = self.fixture()
                    self.short_session(f, owner, keep_old=owner == 'bob')
                    operation, _, _ = self.operation(f, mode)
                    before = f.tables()
                    with self.last_auth(f, 61), self.assertRaises(AuthError if owner == 'alice' else ConversationDenied):
                        operation()
                    self.assertEqual(before, f.tables())
                    self.assert_fenced(f)
                    if owner == 'bob':
                        self.assertTrue(f.auths[owner].status()['unlocked'], 'Another session cannot extend this actor request')
                    else:
                        self.assertFalse(f.auths[owner].status()['unlocked'])

    def test_actor_and_coordinator_deadlines_cover_final_reconstruction(self):
        for mode in ('prepare', 'reinspect'):
            for owner in ('bob', 'alice'):
                with self.subTest(mode=mode, owner=owner):
                    f = self.fixture()
                    self.short_session(f, owner, keep_old=owner == 'bob')
                    operation, api, _ = self.operation(f, mode)
                    original, calls = f.ledger._public_event, []
                    def projection(*args):
                        result = original(*args)
                        calls.append(True)
                        if len(calls) == 2:
                            # After the last decryption, only the captured
                            # actor/coordinator deadlines fence this output.
                            f.now += 61
                        return result
                    with patch.object(f.ledger, '_public_event', projection), f.denied():
                        operation()
                    self.assertEqual(len(calls), 2)
                    self.assert_fenced(f)

    def test_current_extra_coordinator_session_preserves_unlock(self):
        f = self.fixture()
        self.short_session(f, 'alice', keep_old=True)
        operation, _, review = self.operation(f, 'reinspect')
        with self.last_auth(f, 61):
            self.assertEqual(operation(), review)
        self.assertTrue(f.auths['alice'].status()['unlocked'])
        self.assert_fenced(f)

    def test_review_deadline_is_exclusive_at_final_authentication(self):
        for mode in ('prepare', 'reinspect'):
            with self.subTest(mode=mode):
                f = self.fixture()
                operation, _, _ = self.operation(f, mode, deadline=f.now + 60)
                with self.last_auth(f, 60), f.denied():
                    operation()
                self.assert_fenced(f)

    def test_deadline_covers_public_projection_and_final_envelope_work(self):
        for mode in ('prepare', 'reinspect'):
            with self.subTest(mode=mode):
                f = self.fixture()
                operation, api, _ = self.operation(f, mode, deadline=f.now + 60)
                original, projections = f.ledger._public_event, []
                def delayed(event_id):
                    result = original(event_id)
                    projections.append(event_id)
                    if len(projections) == 2:
                        f.now += 60
                    return result
                with patch.object(f.ledger, '_public_event', delayed), f.denied():
                    operation()
                self.assertEqual(len(projections), 2)
                self.assert_fenced(f)

    def source_fixture(self):
        f = self.fixture()
        # Fingerprints are random: choose ordering dynamically so the reader
        # whose history grant expires is definitely scanned before the author.
        early, late = sorted(('bob', 'carol'), key=lambda name: f.keys[name])
        room = 'expiry_room'
        f.ledger.create(*f.actor(late), room)
        source = f.post(late, 'Earlier fictional source', 'earlier', room=room)
        invite = f.ledger.invite(*f.actor(late), room, f.keys[early])
        f.ledger.accept_invitation(*f.actor(early), invite['id'])
        history = f.ledger.prepare_history_grant(*f.actor(late), room, f.keys[early], [source['id']],
            purpose='Exact fictional source', expires_at=f.now + 60)
        f.ledger.approve_history_grant(*f.actor(late), history, history['review_digest'])
        selected = f.post(early, 'Later fictional summary', 'selected', room=room,
                          kind='summary', source_ids=[source['id']])
        api = f.api
        binding = f.bind(late, room)
        options = dict(event_ids=[selected['id']], operation_id='expiry_review', route=fixture_route(),
                       review_deadline=f.now + 300)
        review = api.prepare(*f.actor(late), binding, **options)
        return f, api, early, late, room, binding, options, review

    def test_outer_fence_catches_early_and_late_multi_reviewer_expiry_and_durable_rollback(self):
        for mode in ('prepare', 'reinspect'):
            for after in ('early', 'late'):
                with self.subTest(mode=mode, after=after):
                    f, api, early, late, room, binding, options, review = self.source_fixture()
                    original_scan, original_visibility = api._scan, f.ledger._assert_visible
                    scans, completed = [], []
                    before = f.tables()
                    target = f.keys[early if after == 'early' else late]
                    def visibility(principal, *args):
                        result = original_visibility(principal, *args)
                        completed.append((len(scans), principal))
                        if len(scans) == 2 and principal == target:
                            # Both per-reader scans succeed. Only the enclosing
                            # multi-reader fence sees this expired early grant.
                            f.now += 61
                        return result
                    def scan(*args):
                        scans.append(True)
                        return original_scan(*args)
                    def run():
                        if mode == 'prepare':
                            return api.prepare(*f.actor(late), binding, **options)
                        return api.reinspect(*f.actor(late), binding, review, review['review_commitment'])
                    with patch.object(api, '_scan', scan), patch.object(f.ledger, '_assert_visible', visibility), f.denied():
                        run()
                    self.assertEqual(len(scans), 2)
                    self.assertEqual(len(completed), 4, 'All individual visibility scans completed before outer refusal')
                    self.assertEqual(before, f.tables())
                    self.assert_fenced(f)
                    observed = f.now
                    self.restart(f, observed - 1)
                    new_api = ConversationDisclosureReviews(f.ledger)
                    with f.denied():
                        new_api.reinspect(*f.actor(late), binding, review, review['review_commitment'])
                    f.now = observed
                    with f.denied():
                        new_api.prepare(*f.actor(late), binding, **options)

    def test_source_expiry_during_last_authentication(self):
        for mode in ('prepare', 'reinspect'):
            with self.subTest(mode=mode):
                f, api, early, late, room, binding, options, review = self.source_fixture()
                original, calls = f.auths[late].authenticate, []
                def delayed(token):
                    result = original(token)
                    calls.append(True)
                    if len(calls) == 2:
                        f.now += 61
                    return result
                with patch.object(f.auths[late], 'authenticate', delayed), f.denied():
                    if mode == 'prepare':
                        api.prepare(*f.actor(late), binding, **options)
                    else:
                        api.reinspect(*f.actor(late), binding, review, review['review_commitment'])
                self.assertEqual(len(calls), 2)
                self.assert_fenced(f)

    def test_body_and_final_auth_refusals_preserve_observed_time_across_restart(self):
        for mode in ('prepare', 'reinspect'):
            for stage in ('body', 'final'):
                with self.subTest(mode=mode, stage=stage):
                    f = self.fixture()
                    operation, _, review = self.operation(f, mode)
                    binding = f.bind('bob')
                    original = f.ledger._public_event
                    def projection(event_id):
                        result = original(event_id)
                        f.now += 901
                        f.auths['bob'].authenticate(f.sessions['bob'])
                        return result
                    guard = patch.object(f.ledger, '_public_event', projection) if stage == 'body' else self.last_auth(f, 901, refuse=True)
                    with guard, self.assertRaises(AuthError):
                        operation()
                    self.assert_fenced(f)
                    observed = f.now
                    self.restart(f, observed - 1)
                    with f.denied():
                        f.api.reinspect(*f.actor('bob'), binding, review, review['review_commitment'])
