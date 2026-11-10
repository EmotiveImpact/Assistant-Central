"""Adversarial exact proposal tests using fictional owners and genuine sessions."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import canonical, digest, fingerprint
from pilot.storage import StorageDenied
from conversation import ConversationLedger, ConversationDenied, ConversationOutcomeUnknown
from conversation.proposals import LocalProposals, TABLES, VERSION, content_digest


class ProposalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 2000000000.0
        self.auths, self.keys, self.sessions = {}, {}, {}
        for name in ('alice', 'bob', 'carol', 'storage'):
            auth = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            auth.bootstrap(name, name + '_assistant', 'Fictional password only')
            self.auths[name] = auth
            self.keys[name] = fingerprint(auth.public_identity())
            self.sessions[name] = auth.login('Fictional password only')
        self.ledger = self.open_ledger()
        self.api = LocalProposals(self.ledger, *self.actor('storage'))
        self.ledger.create(*self.actor('alice'), 'room')
        self.join('bob')

    def tearDown(self):
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.tmp.cleanup()

    def actor(self, name):
        return self.keys[name], self.sessions[name]

    def open_ledger(self):
        return ConversationLedger(self.root / 'ledger', self.auths['storage'],
                                  {self.keys[n]: a for n, a in self.auths.items()}, clock=lambda: self.now)

    def reopen(self):
        self.ledger.close()
        self.ledger = self.open_ledger()
        self.api = LocalProposals(self.ledger, *self.actor('storage'))

    def restart_at(self, value):
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.now = value
        for name in self.auths:
            self.auths[name] = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            self.sessions[name] = self.auths[name].login('Fictional password only')
        self.ledger = self.open_ledger()

    def bind(self, name):
        return self.ledger.bind_context(*self.actor(name), 'room')

    def join(self, name):
        invitation = self.ledger.invite(*self.actor('alice'), 'room', self.keys[name])
        self.ledger.accept_invitation(*self.actor(name), invitation['id'])

    def make(self, name='alice', request='proposal_1', **kwargs):
        return self.api.create(*self.actor(name), self.bind(name), request_id=request,
                               content=kwargs.pop('content', 'Fictional local plan'),
                               expires_at=kwargs.pop('expires_at', self.now + 300), **kwargs)

    @staticmethod
    def pid(view):
        return view['proposal']['statement']['id']

    def inspect(self, name, view):
        return self.api.inspect(*self.actor(name), self.bind(name), self.pid(view))

    def review(self, name, view):
        return self.api.prepare_approval(*self.actor(name), self.bind(name), self.pid(view))

    def approve(self, name, view):
        review = self.review(name, view)
        return self.api.approve(*self.actor(name), self.bind(name), review, review['review_digest'])

    def revoke(self, name, view):
        return self.api.revoke(*self.actor(name), self.bind(name), self.pid(view))

    def post(self, name, request, text='Fictional source', **kwargs):
        return self.ledger.append(*self.actor(name), self.bind(name), request_id=request, text=text, **kwargs)

    def grant(self, owner, name, source, expiry=None):
        review = self.ledger.prepare_history_grant(*self.actor(owner), 'room', self.keys[name], [source['id']],
                                                  purpose='Fictional reviewed history', expires_at=expiry or self.now + 300)
        return self.ledger.approve_history_grant(*self.actor(owner), review, review['review_digest'])

    def source_fixture(self):
        source = self.post('alice', 'source')
        self.join('carol')
        grant = self.grant('alice', 'carol', source, self.now + 60)
        derived = self.post('bob', 'summary', kind='summary', source_ids=[source['id']])
        view = self.make(source_ids=[derived['id']])
        for name in ('alice', 'bob', 'carol'):
            self.approve(name, view)
        return source, derived, grant, view

    def test_all_room_owners_not_coordinating_storage_owner(self):
        view = self.make()
        self.assertFalse(view['all_owners_approved'])
        self.assertEqual(len(view['proposal']['statement']['audience']), 2)
        self.assertFalse(self.approve('alice', view)['all_owners_approved'])
        both = self.approve('bob', view)
        self.assertTrue(both['all_owners_approved'])
        self.assertEqual(set(both['current_approval_owners']), {self.keys['alice'], self.keys['bob']})
        for flag in ('execution_authority', 'provider_disclosure_authority', 'external_agreement'):
            self.assertFalse(both[flag])
        with self.assertRaises(ConversationDenied):
            self.api.inspect(*self.actor('storage'), replace(self.bind('alice'), principal=self.keys['storage']), self.pid(view))

    def test_approval_and_proposal_signatures_verify_independently(self):
        view = self.approve('alice', self.make())
        for record, signer in ((view['proposal'], 'author'), (view['approvals'][0], 'owner')):
            self.ledger._verify(record['statement'][signer], record['statement'], record['signature'])
        approval = view['approvals'][0]['statement']
        body = view['proposal']['statement']
        for field in ('conversation_id', 'series_id', 'revision', 'sources', 'audience', 'policy_generation', 'expires_at', 'content_digest'):
            self.assertEqual(approval[field], body[field])
        self.assertEqual(approval['proposal_digest'], digest(body))

    def test_wrong_owner_session_cannot_approve_or_generate_other_owner_review(self):
        view = self.make()
        review = self.review('alice', view)
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('bob'), self.bind('bob'), review, review['review_digest'])
        with self.assertRaises(AuthError):
            self.api.approve(self.keys['alice'], self.sessions['bob'], self.bind('alice'), review, review['review_digest'])
        self.assertEqual(self.inspect('alice', view)['approvals'], [])

    def test_forged_owner_claim_and_changed_review_digest_are_inert(self):
        view = self.make()
        for field, value in [('owner', self.keys['bob']), ('expires_at', self.now + 400), ('scope', 'execute'),
                             ('revision', 2), ('proposal_id', 'other'), ('policy_generation', 99), ('sources', []),
                             ('content_digest', '0' * 64), ('audience', []), ('owner_epoch', 'fake')]:
            review = self.review('alice', view)
            if review['statement'][field] == value:
                value = [{'id': 'fake', 'digest': '0' * 64}]
            review['statement'][field] = value
            review['review_digest'] = digest(review['statement'])
            with self.subTest(field=field), self.assertRaises(ConversationDenied):
                self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        review = self.review('alice', view)
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, '0' * 64)

    def test_review_must_show_exact_original_content(self):
        view = self.make(content='First\r\nSecond é')
        review = self.review('alice', view)
        review['proposal']['statement']['content'] = 'First\nSecond é'
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        self.assertNotEqual(content_digest('é'), content_digest('e\u0301'))
        self.assertNotEqual(content_digest('a\n'), content_digest('a\r\n'))

    def test_generation_requires_fresh_approval_even_identical_content(self):
        first = self.make()
        for name in ('alice', 'bob'):
            self.approve(name, first)
        second = self.make(request='proposal_2', replaces=self.pid(first))
        self.assertEqual(second['proposal']['statement']['revision'], 2)
        self.assertEqual(second['approvals'], [])
        old = self.inspect('alice', first)
        self.assertEqual(len(old['approvals']), 2)
        self.assertFalse(old['all_owners_approved'])
        self.assertEqual(old['current_approval_owners'], [])
        self.assertFalse(old['proposal_current'])

    def test_stale_review_and_idempotent_old_approval_cannot_approve_new_revision(self):
        first = self.make()
        review = self.review('alice', first)
        self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        second = self.make(request='proposal_2', replaces=self.pid(first), content='Changed')
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        self.assertEqual(self.inspect('alice', second)['approvals'], [])

    def test_only_original_proposer_can_revise_and_only_latest_revision(self):
        first = self.make()
        with self.assertRaises(ConversationDenied):
            self.make('bob', 'other', replaces=self.pid(first))
        self.make(request='revision_2', replaces=self.pid(first))
        with self.assertRaises(ConversationDenied):
            self.make(request='fork', replaces=self.pid(first))

    def test_membership_change_invalidates_existing_approvals_and_stale_review(self):
        first = self.make()
        review = self.review('bob', first)
        self.approve('alice', first)
        stale_binding = self.bind('bob')
        self.join('carol')
        self.assertFalse(self.inspect('alice', first)['proposal_current'])
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('bob'), stale_binding, review, review['review_digest'])
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('bob'), self.bind('bob'), review, review['review_digest'])
        with self.assertRaises(ConversationDenied):
            self.inspect('carol', first)
        with self.assertRaises(ConversationDenied):
            self.make(request='new_audience', replaces=self.pid(first))

    def test_removed_rejoined_owner_cannot_read_or_reuse_approval(self):
        first = self.make()
        review = self.review('bob', first)
        self.approve('bob', first)
        self.ledger.remove_member(*self.actor('alice'), 'room', self.keys['bob'])
        self.join('bob')
        with self.assertRaises(ConversationDenied):
            self.inspect('bob', first)
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('bob'), self.bind('bob'), review, review['review_digest'])
        self.assertFalse(self.inspect('alice', first)['all_owners_approved'])

    def test_revoke_is_signed_final_and_idempotent(self):
        view = self.make()
        review = self.review('alice', view)
        self.approve('alice', view)
        self.approve('bob', view)
        revoked = self.revoke('alice', view)
        self.assertFalse(revoked['all_owners_approved'])
        self.assertEqual(len(revoked['approvals']), 2)
        record = revoked['revocations'][0]
        self.ledger._verify(self.keys['alice'], record['statement'], record['signature'])
        self.assertEqual(self.revoke('alice', view), revoked)
        with self.assertRaises(ConversationDenied):
            self.review('alice', view)
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        fresh = self.make(request='fresh', replaces=self.pid(view))
        self.assertEqual(len(self.approve('alice', fresh)['approvals']), 1)

    def test_no_one_can_revoke_another_owners_record(self):
        view = self.approve('alice', self.make())
        with self.assertRaises(ConversationDenied):
            self.revoke('bob', view)
        self.assertEqual(self.inspect('alice', view)['revocations'], [])

    def test_source_requires_every_current_audience_read_permission(self):
        old = self.post('alice', 'old')
        self.join('carol')
        with self.assertRaises(ConversationDenied):
            self.make(source_ids=[old['id']])
        self.grant('alice', 'carol', old)
        self.assertTrue(self.make(source_ids=[old['id']])['proposal_current'])

    def test_transitive_source_revocation_removes_current_consensus_and_read(self):
        _, _, grant, view = self.source_fixture()
        self.assertTrue(self.inspect('carol', view)['all_owners_approved'])
        self.ledger.revoke_history_grant(*self.actor('alice'), grant)
        historical = self.inspect('alice', view)
        self.assertEqual(len(historical['approvals']), 3)
        self.assertFalse(historical['all_owners_approved'])
        with self.assertRaises(ConversationDenied):
            self.inspect('carol', view)
        with self.assertRaises(ConversationDenied):
            self.review('bob', view)

    def test_transitive_expiry_changes_consensus_without_generation_change(self):
        _, _, _, view = self.source_fixture()
        self.now += 61
        historical = self.inspect('alice', view)
        self.assertFalse(historical['proposal_current'])
        self.assertFalse(historical['all_owners_approved'])
        self.assertEqual(len(historical['approvals']), 3)
        with self.assertRaises(ConversationDenied):
            self.inspect('carol', view)

    def test_revisions_automatically_preserve_declared_source_ancestry(self):
        source = self.post('alice', 'source')
        first = self.make(source_ids=[source['id']])
        second = self.make(request='second', replaces=self.pid(first), source_ids=[])
        self.assertEqual(second['proposal']['statement']['sources'], first['proposal']['statement']['sources'])

    def test_source_modified_or_deleted_fails_closed_on_inspection(self):
        source = self.post('alice', 'source')
        view = self.make(source_ids=[source['id']])
        self.ledger.db.execute('DELETE FROM conversation_events WHERE id=?', (source['id'],))
        with self.assertRaises(ConversationDenied):
            self.inspect('alice', view)

    def test_proposal_expiry_preserves_history_but_not_current_approval(self):
        view = self.make(expires_at=self.now + 5)
        review = self.review('bob', view)
        self.approve('alice', view)
        self.now += 5
        expired = self.inspect('alice', view)
        self.assertEqual(len(expired['approvals']), 1)
        self.assertFalse(expired['proposal_current'])
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('bob'), self.bind('bob'), review, review['review_digest'])

    def test_expiry_cannot_revive_on_rewind_or_restart(self):
        view = self.make(expires_at=self.now + 5)
        review = self.review('alice', view)
        self.now += 5
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])
        observed = self.now
        self.restart_at(observed - 1)
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))
        self.now = observed
        self.api = LocalProposals(self.ledger, *self.actor('storage'))
        self.assertFalse(self.inspect('alice', view)['proposal_current'])

    def test_denied_final_commit_observation_persists_time_and_rolls_back_approval(self):
        view = self.make(expires_at=self.now + 5)
        review = self.review('alice', view)
        binding = self.bind('alice')
        original = self.api._view
        def crosses_expiry(*args):
            result = original(*args)
            self.now += 6
            return result
        with patch.object(self.api, '_view', crosses_expiry), self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), binding, review, review['review_digest'])
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 0)
        self.assertEqual(self.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], self.now)
        observed = self.now
        self.restart_at(observed - 1)
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))

    def test_denied_final_output_observation_persists_time(self):
        _, _, _, view = self.source_fixture()
        binding = self.bind('carol')
        original = self.api._view
        advanced = False
        def crosses_source_expiry(*args):
            nonlocal advanced
            result = original(*args)
            if not advanced:
                self.now += 61
                advanced = True
            return result
        with patch.object(self.api, '_view', crosses_source_expiry), self.assertRaises(ConversationDenied):
            self.api.inspect(*self.actor('carol'), binding, self.pid(view))
        self.assertEqual(self.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], self.now)
        observed = self.now
        self.restart_at(observed - 1)
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))

    def test_concurrent_approvals_are_single_records_and_independent(self):
        view = self.make()
        reviews = {n: self.review(n, view) for n in ('alice', 'bob')}
        bindings = {n: self.bind(n) for n in reviews}
        def approve(n):
            review = reviews[n]
            return self.api.approve(*self.actor(n), bindings[n], review, review['review_digest'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(approve, ['alice', 'bob'] * 8))
        result = self.inspect('alice', view)
        self.assertEqual(len(result['approvals']), 2)
        self.assertTrue(result['all_owners_approved'])

    def test_concurrent_revision_has_one_winner(self):
        view = self.make()
        binding = self.bind('alice')
        def revise(n):
            try:
                return self.api.create(*self.actor('alice'), binding, request_id='revision_' + str(n),
                                       content='New', expires_at=self.now + 300, replaces=self.pid(view))
            except ConversationDenied:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(revise, range(8)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_lost_response_inspection_and_same_request_never_duplicates(self):
        first = self.make()
        pid = self.pid(first)
        self.approve('alice', first)  # Pretend the caller never received this response.
        self.reopen()
        recovered = self.api.inspect_request(*self.actor('alice'), self.bind('alice'), 'proposal_1')
        self.assertEqual(self.pid(recovered), pid)
        self.assertEqual(len(recovered['approvals']), 1)
        self.assertEqual(len(self.approve('alice', recovered)['approvals']), 1)
        self.assertEqual(self.pid(self.make()), pid)
        self.assertIsNone(self.api.inspect_request(*self.actor('bob'), self.bind('bob'), 'proposal_1'))
        with self.assertRaises(ConversationDenied):
            self.make(content='Changed retry')

    def test_old_create_retry_returns_historical_status_not_current_revision(self):
        first = self.make()
        self.make(request='second', replaces=self.pid(first))
        retried = self.make()
        self.assertEqual(self.pid(retried), self.pid(first))
        self.assertFalse(retried['proposal_current'])

    def test_post_commit_failure_reports_uncertainty_and_reconciles_one_approval(self):
        view = self.make()
        review = self.review('alice', view)
        binding = self.bind('alice')
        original = self.ledger.db
        class LostCommit:
            def __init__(self):
                self.fired = False
            def __getattr__(self, name):
                return getattr(original, name)
            def execute(self, sql, *args):
                result = original.execute(sql, *args)
                # First commit persists the clock, second is the approval commit.
                if sql == 'COMMIT' and not self.fired and original.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0]:
                    self.fired = True
                    raise sqlite3.OperationalError('Synthetic lost commit response')
                return result
        self.ledger.db = LostCommit()
        try:
            with self.assertRaises(ConversationOutcomeUnknown):
                self.api.approve(*self.actor('alice'), binding, review, review['review_digest'])
        finally:
            self.ledger.db = original
        self.reopen()
        result = self.inspect('alice', view)
        self.assertEqual(len(result['approvals']), 1)
        self.assertEqual(len(self.approve('alice', view)['approvals']), 1)

    def test_locked_actor_storage_and_logged_out_session_all_fail(self):
        view = self.make()
        binding = self.bind('bob')
        review = self.review('bob', view)
        self.auths['bob'].lock()
        with self.assertRaises(AuthError):
            self.api.approve(*self.actor('bob'), binding, review, review['review_digest'])
        self.sessions['bob'] = self.auths['bob'].login('Fictional password only')
        self.auths['storage'].lock()
        for operation in (lambda: self.api.inspect(*self.actor('bob'), binding, self.pid(view)),
                          lambda: self.api.inspect_request(*self.actor('bob'), binding, 'absent'),
                          lambda: LocalProposals(self.ledger, *self.actor('storage'))):
            with self.assertRaises((ConversationDenied, AuthError)):
                operation()
        self.sessions['storage'] = self.auths['storage'].login('Fictional password only')
        self.auths['bob'].logout(self.sessions['bob'])
        with self.assertRaises(AuthError):
            self.api.inspect_request(*self.actor('bob'), binding, 'absent')

    def test_session_expires_before_approval_commit(self):
        view = self.make()
        self.sessions['bob'] = self.auths['bob'].login('Fictional password only', ttl=60)
        review = self.review('bob', view)
        binding = self.bind('bob')
        original = self.api._view
        def delayed(*args):
            result = original(*args)
            self.now += 61
            return result
        with patch.object(self.api, '_view', delayed), self.assertRaises(AuthError):
            self.api.approve(*self.actor('bob'), binding, review, review['review_digest'])
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM conversation_approvals').fetchone()[0], 0)
        self.assertEqual(self.ledger.db.execute('SELECT observed FROM conversation_clock').fetchone()[0], self.now)
        self.restart_at(self.now - 1)
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))

    def test_approval_revocation_and_content_are_encrypted_at_rest(self):
        view = self.make(content='Unique private proposal zebra')
        self.approve('alice', view)
        self.revoke('alice', view)
        for table in TABLES:
            raw = self.ledger.db.execute('SELECT body FROM ' + table).fetchone()[0]
            self.assertTrue(raw.startswith('ac-storage-v1:'))
            self.assertNotIn('Unique private', raw)
        self.assertNotIn(b'Unique private proposal zebra', (self.root / 'ledger/conversation.sqlite').read_bytes())

    def test_tampered_signature_fails_despite_valid_encryption(self):
        view = self.approve('alice', self.make())
        signed = deepcopy(view['approvals'][0])
        signed['signature'] = view['proposal']['signature']
        approval_id = signed['statement']['id']
        encrypted = self.api.storage.seal(TABLES[1], approval_id, 'body', canonical(signed).decode())
        self.ledger.db.execute('UPDATE conversation_approvals SET body=? WHERE id=?', (encrypted, approval_id))
        with self.assertRaises(ConversationDenied):
            self.inspect('alice', view)

    def test_cross_record_ciphertext_substitution_fails(self):
        first = self.make()
        second = self.make(request='second')
        raw = self.ledger.db.execute('SELECT body FROM conversation_proposals WHERE id=?', (self.pid(first),)).fetchone()[0]
        self.ledger.db.execute('UPDATE conversation_proposals SET body=? WHERE id=?', (raw, self.pid(second)))
        with self.assertRaises(StorageDenied):
            self.inspect('alice', second)

    def test_missing_format_sentinel_or_partial_schema_fails_reopen(self):
        self.ledger.db.execute('DELETE FROM conversation_proposal_meta')
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))
        self.ledger.db.execute('DROP TABLE conversation_proposal_meta')
        with self.assertRaises(ConversationDenied):
            LocalProposals(self.ledger, *self.actor('storage'))

    def test_base_ledger_missing_sentinels_still_fails_with_proposal_tables(self):
        self.make()
        self.ledger.db.execute('DELETE FROM conversation_meta')
        self.ledger.db.execute('DELETE FROM conversation_clock')
        self.ledger.close()
        with self.assertRaises(ConversationDenied):
            self.open_ledger()

    def test_nonmember_and_cross_room_cannot_inspect_or_prepare(self):
        view = self.make()
        self.ledger.create(*self.actor('carol'), 'other_room')
        other = self.ledger.bind_context(*self.actor('carol'), 'other_room')
        for operation in (self.api.inspect, self.api.prepare_approval):
            with self.assertRaises(ConversationDenied):
                operation(*self.actor('carol'), other, self.pid(view))

    def test_group_requires_each_of_three_current_owners(self):
        self.join('carol')
        view = self.make()
        for name in ('alice', 'bob'):
            self.assertFalse(self.approve(name, view)['all_owners_approved'])
        final = self.approve('carol', view)
        self.assertTrue(final['all_owners_approved'])
        self.assertEqual(len(final['approvals']), 3)

    def test_concurrent_approval_and_removal_have_no_stale_consensus(self):
        view = self.make()
        review = self.review('bob', view)
        binding = self.bind('bob')
        self.approve('alice', view)
        def approve():
            try:
                return self.api.approve(*self.actor('bob'), binding, review, review['review_digest'])
            except ConversationDenied:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            approval = pool.submit(approve)
            removal = pool.submit(self.ledger.remove_member, *self.actor('alice'), 'room', self.keys['bob'])
            approval.result(timeout=5)
            removal.result(timeout=5)
        self.assertFalse(self.inspect('alice', view)['all_owners_approved'])

    def test_revoked_approval_survives_full_authentication_restart(self):
        view = self.make()
        review = self.review('alice', view)
        self.approve('alice', view)
        self.revoke('alice', view)
        old_session = self.sessions['alice']
        self.restart_at(self.now)
        self.api = LocalProposals(self.ledger, *self.actor('storage'))
        self.assertEqual(len(self.inspect('alice', view)['revocations']), 1)
        with self.assertRaises(AuthError):
            self.api.approve(self.keys['alice'], old_session, self.bind('alice'), review, review['review_digest'])
        with self.assertRaises(ConversationDenied):
            self.api.approve(*self.actor('alice'), self.bind('alice'), review, review['review_digest'])

    def test_input_bounds_and_expiry_fail_closed(self):
        for kwargs in ({'content': ''}, {'content': 'a' * 16385}, {'content': '\ud800'},
                       {'expires_at': True}, {'expires_at': float('nan')}, {'expires_at': self.now},
                       {'expires_at': self.now + 86401}, {'source_ids': ['bad/id']},
                       {'source_ids': ['same', 'same']}, {'source_ids': 'not-a-list'}):
            with self.subTest(kwargs=repr(kwargs)[:60]), self.assertRaises(ConversationDenied):
                self.make(**kwargs)

    def test_malformed_reviews_are_generic_denials(self):
        for review in ({}, {'proposal': {}, 'statement': [], 'review_digest': 'x'},
                       {'proposal': {}, 'statement': {}, 'review_digest': digest({})}):
            with self.assertRaises(ConversationDenied):
                self.api.approve(*self.actor('alice'), self.bind('alice'), review, review.get('review_digest', 'x'))


if __name__ == '__main__':
    unittest.main()
