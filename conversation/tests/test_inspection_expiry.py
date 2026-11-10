"""Inspection output is fenced after final genuine actor authentication."""
import unittest
from unittest.mock import patch

from conversation import ConversationDenied
from pilot.auth import LocalOwnerAuth
import test_ledger as fixtures


class InspectionFinalExpiryTests(unittest.TestCase):
    setUp = fixtures.LedgerCase.setUp
    tearDown = fixtures.LedgerCase.tearDown
    open_ledger = fixtures.LedgerCase.open_ledger
    actor = fixtures.LedgerCase.actor
    join = fixtures.LedgerCase.join
    bind = fixtures.LedgerCase.bind
    post = fixtures.LedgerCase.post
    grant = fixtures.LedgerCase.grant

    def prepare(self, method):
        if method == 'list_invitations':
            self.ledger.create(*self.actor('bob'), 'bob_room')
            self.ledger.invite(*self.actor('bob'), 'bob_room', self.keys['carol'])
        if method == 'list_history_grants':
            event = self.post('bob', 'Bob retained history')
            self.join('carol')
            self.grant('bob', 'carol', [event])
        return lambda: getattr(self.ledger, method)(*self.actor('bob'))

    def last_auth(self, advance):
        original = self.auths['bob'].authenticate
        calls = []
        def authenticate(token):
            result = original(token)
            calls.append(token)
            if len(calls) == 2:
                advance()
            return result
        return calls, patch.object(self.auths['bob'], 'authenticate', authenticate)

    def deadline(self, method, owner):
        operation = self.prepare(method)
        self.assertTrue(operation())  # The denied result would contain real records.
        old = self.sessions[owner]
        self.sessions[owner] = self.auths[owner].login('Fictional test password', ttl=60)
        if owner == 'alice':
            self.auths['alice'].logout(old)  # No other coordinator session keeps the vault open.
        calls, auth = self.last_auth(lambda: setattr(self, 'now', self.now + 61))
        with auth, self.assertRaises(ConversationDenied):
            operation()
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], self.now)
        if owner == 'bob':
            self.assertTrue(self.auths['bob'].status()['unlocked'], 'another actor session must not extend this request')
        else:
            self.assertFalse(self.auths['alice'].status()['unlocked'])

    def test_conversation_list_actor_expiry_during_final_auth(self):
        self.deadline('list_conversations', 'bob')

    def test_invitation_list_actor_expiry_during_final_auth(self):
        self.deadline('list_invitations', 'bob')

    def test_grant_list_actor_expiry_during_final_auth(self):
        self.deadline('list_history_grants', 'bob')

    def test_conversation_list_coordinator_expiry_during_final_auth(self):
        self.deadline('list_conversations', 'alice')

    def test_invitation_list_coordinator_expiry_during_final_auth(self):
        self.deadline('list_invitations', 'alice')

    def test_grant_list_coordinator_expiry_during_final_auth(self):
        self.deadline('list_history_grants', 'alice')

    def test_another_live_coordinator_session_preserves_actual_unlock(self):
        operation = self.prepare('list_history_grants')
        self.auths['alice'].login('Fictional test password', ttl=60)
        calls, auth = self.last_auth(lambda: setattr(self, 'now', self.now + 61))
        with auth:
            self.assertEqual(operation()[0]['status'], 'active')
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.auths['alice'].status()['unlocked'])

    def test_grant_status_updates_when_expiry_crosses_last_auth(self):
        operation = self.prepare('list_history_grants')
        calls, auth = self.last_auth(lambda: setattr(self, 'now', self.now + 301))
        with auth:
            self.assertEqual(operation()[0]['status'], 'expired')
        self.assertEqual(len(calls), 2)
        observed = self.now
        self.ledger.close()
        for account in self.auths.values():
            account.close()
        self.now -= 1
        for name in self.auths:
            self.auths[name] = LocalOwnerAuth(self.root/name, clock=lambda: self.now)
            self.sessions[name] = self.auths[name].login('Fictional test password')
        self.ledger = self.open_ledger()
        with self.assertRaises(ConversationDenied):
            self.ledger.list_history_grants(*self.actor('bob'))
        self.now = observed
        self.assertEqual(self.ledger.list_history_grants(*self.actor('bob'))[0]['status'], 'expired')
