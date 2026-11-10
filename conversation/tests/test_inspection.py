"""New inspection APIs reuse the same final authorisation/time fences."""
import unittest
from unittest.mock import patch
import test_ledger as base
from conversation import ConversationDenied
from pilot.auth import AuthError, LocalOwnerAuth


class InspectionTests(unittest.TestCase):
    setUp = base.LedgerCase.setUp
    tearDown = base.LedgerCase.tearDown
    open_ledger = base.LedgerCase.open_ledger
    actor = base.LedgerCase.actor
    join = base.LedgerCase.join
    bind = base.LedgerCase.bind
    post = base.LedgerCase.post
    grant = base.LedgerCase.grant

    def test_only_current_rooms_and_authorised_pending_invites(self):
        old=self.post('alice','Hidden prior subject')
        invite=self.ledger.invite(*self.actor('alice'),'thread_1',self.keys['carol'])
        self.assertEqual(self.ledger.list_conversations(*self.actor('carol')),[])
        incoming=self.ledger.list_invitations(*self.actor('carol'))
        self.assertEqual([i['id'] for i in incoming],[invite['id']])
        self.assertNotIn('text',str(incoming));self.assertNotIn('count',str(incoming));self.assertNotIn('Hidden',str(incoming))
        self.assertEqual(self.ledger.list_invitations(*self.actor('bob')),[])
        self.ledger.accept_invitation(*self.actor('carol'),invite['id'])
        self.assertEqual(self.ledger.list_invitations(*self.actor('carol')),[])
        self.assertEqual(len(self.ledger.list_conversations(*self.actor('carol'))),1)
        self.ledger.remove_member(*self.actor('alice'),'thread_1',self.keys['carol'])
        self.assertEqual(self.ledger.list_conversations(*self.actor('carol')),[])

    def test_grants_are_issuer_only_and_show_stale_epoch(self):
        event=self.post('bob')
        self.join('carol')
        grant,_=self.grant('bob','carol',[event])
        self.assertEqual(self.ledger.list_history_grants(*self.actor('alice'),'thread_1'),[])
        self.assertEqual(self.ledger.list_history_grants(*self.actor('carol'),'thread_1'),[])
        self.assertEqual(self.ledger.list_history_grants(*self.actor('bob'),'thread_1')[0]['status'],'active')
        self.ledger.remove_member(*self.actor('alice'),'thread_1',self.keys['carol'])
        self.join('carol')
        self.assertEqual(self.ledger.list_history_grants(*self.actor('bob'),'thread_1')[0]['status'],'inactive-membership')
        self.ledger.remove_member(*self.actor('alice'),'thread_1',self.keys['bob'])
        self.ledger.revoke_history_grant(*self.actor('bob'),grant)
        self.assertEqual(self.ledger.list_history_grants(*self.actor('bob'),'thread_1')[0]['status'],'revoked')

    def test_locked_storage_and_final_actor_expiry_fence_all_inspection(self):
        calls=[lambda:self.ledger.list_conversations(*self.actor('bob')),
               lambda:self.ledger.list_invitations(*self.actor('bob')),
               lambda:self.ledger.list_history_grants(*self.actor('bob'),'thread_1')]
        self.auths['alice'].logout(self.sessions['alice'])
        for call in calls:
            with self.assertRaises(ConversationDenied):call()
        self.sessions['alice']=self.auths['alice'].login('Fictional test password')
        for call in calls:
            self.sessions['bob']=self.auths['bob'].login('Fictional test password',ttl=1)
            original=self.ledger._now
            def expire():
                self.now+=1
                return original()
            with patch.object(self.ledger,'_now',side_effect=expire):
                with self.assertRaises(AuthError):call()

    def test_grant_expiry_survives_inspection_restart_clock_rewind(self):
        event=self.post('alice');self.join('carol');self.grant('alice','carol',[event])
        self.now+=301
        self.assertEqual(self.ledger.list_history_grants(*self.actor('alice'),'thread_1')[0]['status'],'expired')
        observed=self.now
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.now-=200
        for name in self.auths:
            self.auths[name]=LocalOwnerAuth(self.root/name,clock=lambda:self.now)
            self.sessions[name]=self.auths[name].login('Fictional test password')
        self.ledger=self.open_ledger()
        with self.assertRaises(ConversationDenied):
            self.ledger.list_history_grants(*self.actor('alice'),'thread_1')
        self.now=observed+1
        self.assertEqual(self.ledger.list_history_grants(*self.actor('alice'),'thread_1')[0]['status'],'expired')

    def test_issuer_grant_pagination_preserves_older_revocation_without_other_authors(self):
        event=self.post('alice');self.join('carol')
        oldest=None
        for _ in range(51):
            grant,_=self.grant('alice','carol',[event])
            oldest=oldest or grant
        first=self.ledger.list_history_grants(*self.actor('alice'))
        self.assertEqual(len(first),50)
        last=first[-1]['statement']['id']
        second=self.ledger.list_history_grants(*self.actor('alice'),after=last)
        self.assertEqual([x['statement']['id'] for x in second],[oldest])
        self.ledger.revoke_history_grant(*self.actor('alice'),oldest)
        self.assertEqual(self.ledger.list_history_grants(*self.actor('alice'),after=last)[0]['status'],'revoked')
        with self.assertRaises(ConversationDenied):
            self.ledger.list_history_grants(*self.actor('bob'),after=last)
        with self.assertRaises(ConversationDenied):
            self.ledger.list_history_grants(*self.actor('alice'),'other_room',after=last)
