"""Independent lifecycle review, using fictional authenticated identities."""
import unittest

from conversation import ConversationDenied
from conversation.tests import test_ledger as fixtures
from pilot.auth import AuthError, LocalOwnerAuth


class ReviewTests(unittest.TestCase):
    def test_observed_expired_history_grant_cannot_revive_after_restart_clock_rewind(self):
        case = fixtures.LedgerCase()
        case.setUp()
        try:
            initial_time = case.now
            event = case.post('alice', 'Previously private history')
            case.join('carol')
            case.grant('alice', 'carol', [event])
            self.assertEqual(case.read('carol', event)['text'], 'Previously private history')
            case.now += 301
            with self.assertRaises(ConversationDenied):
                case.read('carol', event)
            case.ledger.close()
            for auth in case.auths.values():
                auth.close()
            case.now = initial_time + 1
            for name in case.auths:
                auth = LocalOwnerAuth(case.root / name, clock=lambda: case.now)
                case.auths[name] = auth
                case.sessions[name] = auth.login('Fictional test password')
            case.ledger = case.open_ledger()
            with self.assertRaises((ConversationDenied, AuthError)):
                case.read('carol', event)
        finally:
            case.tearDown()


if __name__ == '__main__':
    unittest.main()
