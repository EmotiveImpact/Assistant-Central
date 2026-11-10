"""Independent final-commit clock boundary regression for exact approvals."""
import unittest
from unittest.mock import patch

from conversation import ConversationDenied
from conversation.tests import test_proposals as fixtures


class ProposalFinalCommitReview(unittest.TestCase):
    def test_expiry_during_last_authentication_refuses_stale_unanimous_approval(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        proposal = f.make()
        f.approve('bob', proposal)
        review = f.review('alice', proposal)
        binding = f.bind('alice')
        original = f.auths['alice'].authenticate
        calls = 0

        def final_authentication(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now = proposal['proposal']['statement']['expires_at'] + 1
            return result

        with patch.object(f.auths['alice'], 'authenticate', final_authentication):
            with self.assertRaises(ConversationDenied):
                f.api.approve(*f.actor('alice'), binding, review, review['review_digest'])
        self.assertEqual(calls, 2)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 1)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    def test_expiry_during_last_authentication_refuses_stale_inspection(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        proposal = f.make()
        f.approve('alice', proposal)
        f.approve('bob', proposal)
        binding = f.bind('alice')
        original = f.auths['alice'].authenticate
        calls = 0

        def final_authentication(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now = proposal['proposal']['statement']['expires_at'] + 1
            return result

        with patch.object(f.auths['alice'], 'authenticate', final_authentication):
            with self.assertRaises(ConversationDenied):
                f.api.inspect(*f.actor('alice'), binding, f.pid(proposal))
        self.assertEqual(calls, 2)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        observed = f.now
        f.restart_at(observed - 1)
        with self.assertRaises(ConversationDenied):
            fixtures.LocalProposals(f.ledger, *f.actor('storage'))
        f.now = observed
        f.api = fixtures.LocalProposals(f.ledger, *f.actor('storage'))
        self.assertFalse(f.inspect('alice', proposal)['all_owners_approved'])

    def test_source_expiry_during_last_authentication_refuses_source_derived_output(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        _, _, _, proposal = f.source_fixture()
        binding = f.bind('carol')
        original = f.auths['carol'].authenticate
        calls = 0

        def final_authentication(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now += 61
            return result

        with patch.object(f.auths['carol'], 'authenticate', final_authentication):
            with self.assertRaises(ConversationDenied):
                f.api.inspect(*f.actor('carol'), binding, f.pid(proposal))
        self.assertEqual(calls, 2)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        historical = f.inspect('alice', proposal)
        self.assertEqual(len(historical['approvals']), 3)
        self.assertFalse(historical['all_owners_approved'])

    def test_last_authentication_refusal_still_persists_observed_clock(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        proposal = f.make()
        review = f.review('alice', proposal)
        binding = f.bind('alice')
        original = f.auths['alice'].authenticate
        calls = 0

        def final_authentication(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now += 901
                original(token)  # Real session expiry, not a manufactured exception.
            return result

        with patch.object(f.auths['alice'], 'authenticate', final_authentication):
            with self.assertRaises(fixtures.AuthError):
                f.api.approve(*f.actor('alice'), binding, review, review['review_digest'])
        self.assertEqual(calls, 2)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 0)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        f.restart_at(f.now - 1)
        with self.assertRaises(ConversationDenied):
            fixtures.LocalProposals(f.ledger, *f.actor('storage'))

    def test_session_deadline_observed_during_extra_final_checks_refuses_commit(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        proposal = f.make()
        f.sessions['alice'] = f.auths['alice'].login('Fictional password only', ttl=60)
        review = f.review('alice', proposal)
        binding = f.bind('alice')
        original = f.api._check_view
        checks = 0

        def delayed_final_check(*args):
            nonlocal checks
            checks += 1
            if checks == 2:
                f.now += 61
            # The policy check observes the advanced clock. The proposal remains
            # unexpired, so only the captured actor-session deadline can refuse.
            return original(*args)

        with patch.object(f.api, '_check_view', delayed_final_check):
            with self.assertRaises(ConversationDenied):
                f.api.approve(*f.actor('alice'), binding, review, review['review_digest'])
        self.assertEqual(checks, 2)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 0)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        f.restart_at(f.now - 1)
        with self.assertRaises(ConversationDenied):
            fixtures.LocalProposals(f.ledger, *f.actor('storage'))

    def test_proposal_deadline_observed_inside_last_source_check_refuses_commit(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        source = f.post('alice', 'source')
        proposal = f.make(source_ids=[source['id']])
        f.approve('bob', proposal)
        review, binding = f.review('alice', proposal), f.bind('alice')
        original_check, original_visible = f.api._check_view, f.ledger._visible
        checks, reads = 0, 0

        def source_read(*args, **kwargs):
            nonlocal reads
            result = original_visible(*args, **kwargs)
            reads += 1
            if reads == 3:
                f.now = proposal['proposal']['statement']['expires_at'] + 1
                f.ledger._now()
            return result

        def final_check(*args):
            nonlocal checks
            checks += 1
            if checks == 2:
                with patch.object(f.ledger, '_visible', source_read):
                    return original_check(*args)
            return original_check(*args)

        with patch.object(f.api, '_check_view', final_check):
            with self.assertRaises(ConversationDenied):
                f.api.approve(*f.actor('alice'), binding, review, review['review_digest'])
        self.assertEqual(reads, 3)
        self.assertEqual(f.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 1)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    def test_source_deadline_observed_after_last_visibility_check_refuses_output(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        _, _, _, proposal = f.source_fixture()
        binding = f.bind('carol')
        original_check, original_visible = f.api._check_view, f.ledger._visible
        checks = 0
        members = proposal['proposal']['statement']['audience']
        last_member = members[-1]['principal']
        direct_source = proposal['proposal']['statement']['sources'][0]['id']
        reads = 0

        def source_read(event_id, principal, *args, **kwargs):
            nonlocal reads
            result = original_visible(event_id, principal, *args, **kwargs)
            if event_id == direct_source and principal == last_member:
                reads += 1
                # Carol may also be last by fingerprint; her caller-read precedes
                # the roster scan, so skip that first match in that case.
                target = 2 if last_member == f.keys['carol'] else 1
                if reads == target:
                    f.now += 61
                    f.ledger._now()
            return result

        def final_check(*args):
            nonlocal checks
            checks += 1
            if checks == 2:
                with patch.object(f.ledger, '_visible', source_read):
                    return original_check(*args)
            return original_check(*args)

        with patch.object(f.api, '_check_view', final_check):
            with self.assertRaises(ConversationDenied):
                f.api.inspect(*f.actor('carol'), binding, f.pid(proposal))
        self.assertEqual(checks, 2)
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        self.assertFalse(f.inspect('alice', proposal)['all_owners_approved'])

    def test_coordinator_deadline_during_last_authentication_refuses_plaintext(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        old_session = f.sessions['storage']
        f.sessions['storage'] = f.auths['storage'].login('Fictional password only', ttl=60)
        f.auths['storage'].logout(old_session)
        proposal = f.make()  # No approvals or sources cause storage reads later.
        binding = f.bind('alice')
        original = f.auths['alice'].authenticate
        calls = 0

        def final_authentication(token):
            nonlocal calls
            result = original(token)
            calls += 1
            if calls == 2:
                f.now += 61
            return result

        with patch.object(f.auths['alice'], 'authenticate', final_authentication):
            with self.assertRaises(ConversationDenied):
                f.api.inspect(*f.actor('alice'), binding, f.pid(proposal))
        self.assertEqual(calls, 2)
        self.assertFalse(f.auths['storage'].status()['unlocked'])
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)
        f.restart_at(f.now - 1)
        with self.assertRaises(ConversationDenied):
            fixtures.LocalProposals(f.ledger, *f.actor('storage'))

    def test_coordinator_deadline_observed_inside_final_checks_refuses_output(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        old_session = f.sessions['storage']
        f.sessions['storage'] = f.auths['storage'].login('Fictional password only', ttl=60)
        f.auths['storage'].logout(old_session)
        proposal, binding = f.make(), f.bind('alice')
        original = f.api._check_view
        checks = 0

        def final_check(*args):
            nonlocal checks
            checks += 1
            if checks == 2:
                f.now += 61
            return original(*args)

        with patch.object(f.api, '_check_view', final_check):
            with self.assertRaises(ConversationDenied):
                f.api.inspect(*f.actor('alice'), binding, f.pid(proposal))
        self.assertEqual(checks, 2)
        self.assertFalse(f.auths['storage'].status()['unlocked'])
        self.assertEqual(f.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], f.now)

    def test_other_unexpired_coordinator_session_preserves_actual_unlock(self):
        f = fixtures.ProposalCase(methodName='runTest')
        f.setUp()
        self.addCleanup(f.tearDown)
        # Retain the original long session as well as the shorter new session.
        f.auths['storage'].login('Fictional password only', ttl=60)
        proposal = f.make()
        f.now += 61
        self.assertTrue(f.auths['storage'].status()['unlocked'])
        self.assertTrue(f.inspect('alice', proposal)['proposal_current'])
