"""Independent no-revival checks for signed source-grant supersession."""
import copy
import unittest

from pilot.source_grants import GrantDenied
from pilot.tests import test_source_grants as fixtures


class IndependentGrantReview(unittest.TestCase):
    setUp = fixtures.SourceGrantTests.setUp
    new_ledger = fixtures.SourceGrantTests.new_ledger
    body = fixtures.SourceGrantTests.body
    signed = fixtures.SourceGrantTests.signed
    observe = fixtures.SourceGrantTests.observe
    consume = fixtures.SourceGrantTests.consume
    count = fixtures.SourceGrantTests.count

    def assert_old_fenced_after_observation(self, newer):
        try:
            self.ledger.observe(self.session, newer)
        except GrantDenied:
            pass  # Unusable new authority may be reported after durable fencing.
        with self.assertRaises(GrantDenied):
            self.consume()
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied):
            self.consume()
        self.assertEqual(self.count(), 0)

    def test_expired_newer_revision_never_revives_older_longer_grant(self):
        self.observe()
        newer = self.signed('alice', revision=2, issued_at=1000, expires_at=1100)
        self.now = 1200
        self.assert_old_fenced_after_observation(newer)

    def test_changed_unpinned_recipient_never_revives_previous_route(self):
        self.observe()
        plan = copy.deepcopy(self.plan)
        plan['recipient'] = 'a' * 64
        self.assert_old_fenced_after_observation(self.signed('alice', plan=plan, revision=2))

    def test_changed_executor_never_revives_previous_executor_grant(self):
        self.observe()
        plan = copy.deepcopy(self.plan)
        plan['executor'] = self.fps['recipient']
        self.assert_old_fenced_after_observation(self.signed('alice', plan=plan, revision=2))


if __name__ == '__main__':
    unittest.main()
