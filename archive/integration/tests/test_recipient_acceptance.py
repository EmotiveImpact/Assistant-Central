"""Synthetic acceptance regressions. No fixture label is human consent."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from integration.bootstrap import TeamWorkflow, Denied, canonical, digest
from integration.team_proposals import BoundArtifactProposal, OutcomeUnknown
from integration.recipient_acceptance import AcceptanceBoundary, SyntheticDelivery
from team_workflow import AgentRef, TaskSpec, TeamPlan


def make_plan(same_owner=False):
    return TeamPlan('acceptance-fixture', 'lead', (
        AgentRef('lead', 'alice', 'fixture', 'review'),
        AgentRef('source', 'bob', 'fixture', 'research'),
        AgentRef('writer', 'carol', 'fixture', 'copy'),
        AgentRef('recipient', 'carol' if same_owner else 'dana', 'fixture', 'slides'),
        AgentRef('sibling', 'carol' if same_owner else 'dana', 'fixture', 'slides'),
    ), (
        TaskSpec('source', 'source', 'SOURCE OBJECTIVE', 'research'),
        TaskSpec('copy', 'writer', 'WRITER OBJECTIVE', 'copy', ('source',)),
        TaskSpec('target', 'recipient', 'RECIPIENT OBJECTIVE', 'slides', ('copy',)),
        TaskSpec('other', 'sibling', 'OTHER OBJECTIVE', 'slides', ('copy',)),
    ))


def share(w, artifact, recipient, task=None):
    owner = w.agents[w._artifact(artifact)['producer']].owner
    review = w.disclosure_review(owner, artifact, recipient, task, expected_context=w.context)
    w.approve_disclosure(owner, artifact, recipient, review['review_digest'], task, expected_context=w.context)


def finish(w, task_id, text):
    actor = w.facade(w.tasks[task_id].assignee)
    request = actor.propose_start(task_id, 'start-' + task_id)
    w.decide_start(w._task_owner(task_id), request['request_id'], request['review_digest'], 'approve',
                   expires=1100, expected_context=w.context)
    actor.start(request['request_id'])
    actor.submit(task_id, task_id + '-out', text)
    share(w, task_id + '-out', 'lead')
    w.facade('lead').review_output(task_id, task_id + '-out', 'accept')


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'team.sqlite'
        self.plan = make_plan()
        self.now = 1000
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
        self.addCleanup(lambda: self.w.close())
        self.w.accept_lead('alice', expected_context=self.w.context)
        finish(self.w, 'source', 'SYNTHETIC ORIGINAL SOURCE')
        share(self.w, 'source-out', 'writer', 'copy')
        finish(self.w, 'copy', 'SYNTHETIC DERIVED ARTIFACT')
        share(self.w, 'copy-out', 'recipient', 'target')
        self.bound = self.bind()
        self.bound.facade.propose({'text': 'SYNTHETIC DERIVED ARTIFACT'})
        self.open_boundary()
        self.offer = self.b.register(self.bound)['offer_id']

    def bind(self, task='target'):
        bound = BoundArtifactProposal(self.w, 'copy-out', task, expected_context=self.w.context)
        self.addCleanup(bound.close)
        return bound

    def open_boundary(self):
        self.b = AcceptanceBoundary(self.w)
        self.sender = self.b.source_control('carol', expected_context=self.w.context)
        self.upstream = self.b.source_control('bob', expected_context=self.w.context)
        self.receiver = self.b.recipient_control(self.w.agents['recipient'].owner, 'recipient', expected_context=self.w.context)

    def approve(self):
        for source in (self.sender, self.upstream):
            source.decide(self.offer, source.review(self.offer)['review_digest'], 'approve', expires=1100)

    def received(self):
        self.approve()
        delivery = self.sender.release(self.offer)
        self.receiver.receive(delivery)
        return delivery, self.receiver.review(self.offer)['review_digest']

    def reopen(self):
        self.w.close()
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
        self.open_boundary()

    def test_staging_and_registration_grant_no_recipient_authority(self):
        status = self.receiver.status(self.offer)
        self.assertEqual(status['recipient_state'], 'not_received')
        with self.assertRaises(Denied): self.receiver.review(self.offer)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, self.offer, 'accept')
        with self.assertRaises(Denied): self.sender.release(self.offer)
        self.assertEqual(self.w._row('target')['state'], 'planned')

    def test_exact_acceptance_preserves_task_and_execution_boundaries(self):
        delivery, review = self.received()
        self.assertEqual(delivery.to_dict()['text'], 'SYNTHETIC DERIVED ARTIFACT')
        result = self.receiver.decide(self.offer, review, 'accept')
        self.assertEqual(result['outcome'], 'accepted')
        self.assertFalse(result['authenticated_consent'])
        self.assertFalse(result['authorises_work'])
        self.assertFalse(result['authorises_onward_disclosure'])
        self.assertEqual(self.w._row('target')['state'], 'planned')
        self.assertEqual(self.bound.facade.processed_inbox({})['items'], [])
        self.assertEqual(self.bound.facade.status({'proposal_id': self.bound.proposal_id})['state'], 'pending')
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='execution_runs'").fetchone()[0], 0)

    def test_upstream_owner_cannot_be_omitted(self):
        self.sender.decide(self.offer, self.sender.review(self.offer)['review_digest'], 'approve', expires=1100)
        with self.assertRaises(Denied): self.sender.release(self.offer)
        self.upstream.decide(self.offer, self.upstream.review(self.offer)['review_digest'], 'approve', expires=1100)
        self.assertEqual(self.sender.release(self.offer).to_dict()['offer_id'], self.offer)

    def test_source_previews_and_delivery_keep_foreign_source_text_private(self):
        upstream = json.dumps(self.upstream.review(self.offer))
        source = json.dumps(self.sender.review(self.offer))
        self.assertIn('SYNTHETIC ORIGINAL SOURCE', upstream)
        self.assertNotIn('SYNTHETIC DERIVED ARTIFACT', upstream)
        self.assertNotIn('SYNTHETIC ORIGINAL SOURCE', source)
        self.assertNotIn('RECIPIENT OBJECTIVE', upstream)
        self.approve()
        self.assertNotIn('SYNTHETIC ORIGINAL SOURCE', self.sender.release(self.offer).body)

    def test_lead_and_wrong_recipient_cannot_decide(self):
        delivery, review = self.received()
        for owner, agent in (('alice', 'lead'), ('carol', 'writer'), ('dana', 'sibling')):
            control = self.b.recipient_control(owner, agent, expected_context=self.w.context)
            for call in (lambda: control.receive(delivery), lambda: control.review(self.offer),
                         lambda: control.decide(self.offer, review, 'accept'), lambda: control.status(self.offer)):
                with self.subTest(owner=owner, agent=agent), self.assertRaises(Denied): call()
        with self.assertRaises(Denied): self.b.recipient_control('alice', 'recipient', expected_context=self.w.context)
        with self.assertRaises(Denied): self.b.recipient_control('dana', 'recipient', expected_context='0' * 64)

    def test_lead_cannot_mint_source_approval_or_release(self):
        lead = self.b.source_control('alice', expected_context=self.w.context)
        for call in (lambda: lead.review(self.offer), lambda: lead.decide(self.offer, self.offer, 'approve', expires=1100),
                     lambda: lead.release(self.offer), lambda: lead.revoke(self.offer)):
            with self.assertRaises(Denied): call()
        self.approve()
        with self.assertRaises(Denied): self.upstream.release(self.offer)

    def test_wrong_or_crossed_review_is_rejected(self):
        for value in ('0' * 64, self.sender.review(self.offer)['review_digest'], None, True):
            with self.assertRaises(Denied): self.upstream.decide(self.offer, value, 'approve', expires=1100)
        _, review = self.received()
        for value in ('0' * 64, self.sender.review(self.offer)['review_digest'], None, True):
            with self.assertRaises(Denied): self.receiver.decide(self.offer, value, 'accept')
        self.receiver.decide(self.offer, review, 'accept')

    def test_rejection_is_terminal_and_duplicate_delivery_never_renews(self):
        delivery, review = self.received()
        rejected = self.receiver.decide(self.offer, review, 'reject')
        self.assertEqual(rejected['recipient_state'], 'rejected')
        self.assertEqual(self.receiver.receive(delivery), rejected)
        self.assertEqual(self.receiver.decide(self.offer, review, 'reject'), rejected)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')
        with self.assertRaises(Denied): self.receiver.review(self.offer)
        with self.assertRaises(Denied): self.sender.release(self.offer)
        self.assertEqual(self.b.register(self.bound), rejected)

    def test_accepted_duplicates_are_metadata_only_and_count_one_receipt(self):
        delivery, review = self.received()
        result = self.receiver.decide(self.offer, review, 'accept')
        self.assertEqual(self.receiver.decide(self.offer, review, 'accept'), result)
        self.assertEqual(self.receiver.receive(delivery), result)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'reject')
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE artifact_id='copy-out' AND purpose='task:target'").fetchone()[0], 1)
        self.assertNotIn('SYNTHETIC DERIVED ARTIFACT', json.dumps(result))

    def test_source_rejection_and_revocation_cannot_be_renewed(self):
        self.upstream.decide(self.offer, self.upstream.review(self.offer)['review_digest'], 'reject')
        self.sender.decide(self.offer, self.sender.review(self.offer)['review_digest'], 'approve', expires=1100)
        with self.assertRaises(Denied): self.sender.release(self.offer)
        with self.assertRaises(Denied): self.upstream.decide(self.offer, self.upstream.review(self.offer)['review_digest'], 'approve', expires=1100)
        self.reopen()
        self.assertEqual(self.upstream.review(self.offer)['state'], 'rejected')

    def test_revocation_before_release_blocks_and_after_release_blocks_receipt(self):
        self.approve()
        self.upstream.revoke(self.offer)
        with self.assertRaises(Denied): self.sender.release(self.offer)
        with self.assertRaises(Denied): self.upstream.decide(self.offer, self.upstream.review(self.offer)['review_digest'], 'approve', expires=1100)

    def test_release_remains_uncertain_when_permission_withdrawn_before_receive(self):
        self.approve()
        delivery = self.sender.release(self.offer)
        self.sender.revoke(self.offer)
        with self.assertRaises(Denied): self.receiver.receive(delivery)
        self.assertEqual(self.sender.status(self.offer)['outcome'], 'uncertain')
        self.reopen()
        with self.assertRaises(Denied): self.sender.release(self.offer)

    def test_revocation_after_review_blocks_acceptance_but_allows_rejection(self):
        _, review = self.received()
        self.upstream.revoke(self.offer)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')
        with self.assertRaises(Denied): self.receiver.review(self.offer)
        self.assertEqual(self.receiver.decide(self.offer, review, 'reject')['recipient_state'], 'rejected')

    def test_revoked_before_preview_can_be_rejected_using_metadata(self):
        self.approve()
        received = self.receiver.receive(self.sender.release(self.offer))
        self.upstream.revoke(self.offer)
        self.receiver.decide(self.offer, received['recipient_review_digest'], 'reject')

    def test_withdrawn_historical_input_blocks_acceptance_after_completed_intermediary(self):
        _, review = self.received()
        self.w.revoke_disclosure('bob', 'source-out', 'writer', 'copy', expected_context=self.w.context)
        self.assertEqual(self.w._row('copy')['state'], 'completed')
        self.assertEqual(self.w._row('target')['state'], 'planned')
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_source_task_revocation_blocks_descendant_acceptance(self):
        _, review = self.received()
        self.w.revoke_task('bob', 'source', expected_context=self.w.context)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_same_owner_source_and_recipient_still_need_separate_decisions(self):
        plan = make_plan(same_owner=True)
        w = TeamWorkflow(':memory:', plan, clock=lambda: 1000)
        self.addCleanup(w.close)
        w.accept_lead('alice', expected_context=w.context)
        finish(w, 'source', 'SYNTHETIC ORIGINAL')
        share(w, 'source-out', 'writer', 'copy')
        finish(w, 'copy', 'SYNTHETIC DERIVED')
        share(w, 'copy-out', 'recipient', 'target')
        bound = BoundArtifactProposal(w, 'copy-out', 'target', expected_context=w.context)
        self.addCleanup(bound.close)
        bound.facade.propose({'text': 'SYNTHETIC DERIVED'})
        boundary = AcceptanceBoundary(w)
        offer_id = boundary.register(bound)['offer_id']
        for owner in ('bob', 'carol'):
            control = boundary.source_control(owner, expected_context=w.context)
            control.decide(offer_id, control.review(offer_id)['review_digest'], 'approve', expires=1100)
        receiver = boundary.recipient_control('carol', 'recipient', expected_context=w.context)
        sender = boundary.source_control('carol', expected_context=w.context)
        receiver.receive(sender.release(offer_id))
        self.assertEqual(receiver.status(offer_id)['recipient_state'], 'pending')
        receiver.decide(offer_id, receiver.review(offer_id)['review_digest'], 'accept')
        sibling = boundary.recipient_control('carol', 'sibling', expected_context=w.context)
        with self.assertRaises(Denied): sibling.status(offer_id)

    def test_direct_disclosure_revocation_blocks_acceptance(self):
        _, review = self.received()
        self.w.revoke_disclosure('carol', 'copy-out', 'recipient', 'target', expected_context=self.w.context)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_recipient_task_revocation_blocks_acceptance(self):
        _, review = self.received()
        self.w.revoke_task('dana', 'target', expected_context=self.w.context)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_lead_withdrawal_blocks_acceptance(self):
        _, review = self.received()
        self.w.withdraw_lead('alice', expected_context=self.w.context)
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_expiry_is_finite_bounded_and_cannot_be_renewed(self):
        for expiry in (None, True, 1000, 4601, float('nan'), float('inf')):
            with self.subTest(expiry=expiry), self.assertRaises(Denied):
                self.sender.decide(self.offer, self.sender.review(self.offer)['review_digest'], 'approve', expires=expiry)
        self.approve()
        self.now = 1100
        self.assertEqual(self.sender.review(self.offer)['state'], 'expired')
        with self.assertRaises(Denied): self.sender.release(self.offer)
        with self.assertRaises(Denied): self.sender.decide(self.offer, self.sender.review(self.offer)['review_digest'], 'approve', expires=1200)

    def test_expiry_after_review_blocks_acceptance_and_preserves_rejection(self):
        _, review = self.received()
        self.now = 1100
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')
        self.receiver.decide(self.offer, review, 'reject')

    def test_acceptance_does_not_renew_expired_work_approval(self):
        request = self.w.facade('recipient').propose_start('target', 'target-start')
        self.w.decide_start('dana', request['request_id'], request['review_digest'], 'approve', expires=1001, expected_context=self.w.context)
        _, review = self.received()
        self.now = 1002
        self.receiver.decide(self.offer, review, 'accept')
        with self.assertRaises(Denied): self.w.facade('recipient').start(request['request_id'])

    def test_duplicate_history_after_revocation_does_not_restore_content_access(self):
        delivery, review = self.received()
        self.receiver.decide(self.offer, review, 'accept')
        self.w.revoke_task('bob', 'source', expected_context=self.w.context)
        self.reopen()
        history = self.receiver.receive(delivery)
        self.assertEqual(history['recipient_state'], 'accepted')
        self.assertEqual(self.receiver.decide(self.offer, review, 'accept'), history)
        with self.assertRaises(Denied): self.receiver.review(self.offer)
        with self.assertRaises(Denied): self.sender.release(self.offer)

    def test_crossed_or_modified_delivery_cannot_be_received(self):
        self.approve()
        delivery = self.sender.release(self.offer)
        for key, value in (('text', 'ALTERED'), ('recipient', self.w.agents['sibling'].to_dict()),
                           ('context', '0' * 64), ('task_id', 'other'), ('artifact_id', 'source-out'),
                           ('expires', 99999), ('offer_id', 'f' * 64)):
            changed = delivery.to_dict(); changed[key] = value
            with self.subTest(key=key), self.assertRaises(Denied):
                self.receiver.receive(SyntheticDelivery(canonical(changed), digest(changed)))
        for bad in (None, {}, SyntheticDelivery('[]', digest([])), SyntheticDelivery('{', '0' * 64),
                    replace(delivery, digest='0' * 64)):
            with self.assertRaises(Denied): self.receiver.receive(bad)
        self.receiver.receive(delivery)

    def test_other_route_has_distinct_offer_and_cannot_reuse_review(self):
        share(self.w, 'copy-out', 'sibling', 'other')
        other = self.bind('other'); other.facade.propose({'text': 'SYNTHETIC DERIVED ARTIFACT'})
        other_id = self.b.register(other)['offer_id']
        self.assertNotEqual(other_id, self.offer)
        with self.assertRaises(Denied): self.sender.decide(other_id, self.sender.review(self.offer)['review_digest'], 'approve', expires=1100)

    def test_prior_declined_or_uncertain_stage_cannot_register(self):
        share(self.w, 'copy-out', 'sibling', 'other')
        other = self.bind('other'); other.facade.propose({'text': 'SYNTHETIC DERIVED ARTIFACT'})
        record = other._store._get(other.proposal_id)
        for state in ('declined', 'unknown', 'rejected', 'released'):
            record['state'] = state
            with other._store._db: other._store._save(record)
            with self.subTest(state=state), self.assertRaises(Denied): self.b.register(other)

    def test_changed_ancestral_permission_digest_blocks_release(self):
        self.approve()
        self.w.db.execute("UPDATE disclosures SET review_digest=? WHERE artifact_id='source-out' AND purpose='task:copy'", ('0' * 64,))
        with self.assertRaises(Denied): self.sender.release(self.offer)

    def test_changed_artifact_or_start_review_blocks_acceptance(self):
        _, review = self.received()
        self.w.db.execute("UPDATE requests SET review='{}' WHERE task_id='source'")
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_lost_release_return_survives_restart_without_reissue(self):
        self.approve()
        self.sender.release(self.offer)  # drop the one original envelope
        self.reopen()
        self.assertEqual(self.sender.status(self.offer)['outcome'], 'uncertain')
        with self.assertRaises(Denied): self.sender.release(self.offer)

    def test_pending_original_delivery_can_reconcile_after_restart(self):
        self.approve()
        delivery = self.sender.release(self.offer)
        self.reopen()
        self.receiver.receive(delivery)
        self.reopen()
        review = self.receiver.review(self.offer)['review_digest']
        self.receiver.decide(self.offer, review, 'accept')
        self.reopen()
        self.assertEqual(self.sender.status(self.offer)['recipient_state'], 'accepted')

    def test_rejected_decision_survives_restart(self):
        delivery, review = self.received()
        self.receiver.decide(self.offer, review, 'reject')
        self.reopen()
        self.assertEqual(self.receiver.receive(delivery)['recipient_state'], 'rejected')
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'accept')

    def test_transaction_rollback_preserves_fence_and_no_read_counter(self):
        self.approve()
        with patch.object(self.w, '_event', side_effect=RuntimeError('SECRET failure')):
            with self.assertRaises(OutcomeUnknown) as error: self.sender.release(self.offer)
        self.assertNotIn('SECRET', str(error.exception))
        self.assertEqual(self.sender.status(self.offer)['release_state'], 'pending')
        delivery = self.sender.release(self.offer)  # explicit known-rollback test, no auto retry
        with patch.object(self.w, '_event', side_effect=RuntimeError('SECRET failure')):
            with self.assertRaises(OutcomeUnknown): self.receiver.receive(delivery)
        self.assertEqual(self.receiver.status(self.offer)['recipient_state'], 'not_received')
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:target'").fetchone()[0], 0)

    def test_postcommit_release_failure_is_redacted_and_remains_uncertain(self):
        self.approve()
        transaction = self.w._transaction
        @contextmanager
        def lost_commit_ack():
            with transaction(): yield
            raise RuntimeError('SECRET commit ACK lost')
        with patch.object(self.w, '_transaction', lost_commit_ack):
            with self.assertRaises(OutcomeUnknown) as error: self.sender.release(self.offer)
        self.assertNotIn('SECRET', str(error.exception))
        self.reopen()
        self.assertEqual(self.sender.status(self.offer)['outcome'], 'uncertain')
        with self.assertRaises(Denied): self.sender.release(self.offer)

    def test_postcommit_decision_failure_reconciles_exact_result(self):
        _, review = self.received()
        transaction = self.w._transaction
        @contextmanager
        def lost_commit_ack():
            with transaction(): yield
            raise RuntimeError('SECRET commit ACK lost')
        with patch.object(self.w, '_transaction', lost_commit_ack):
            with self.assertRaises(OutcomeUnknown): self.receiver.decide(self.offer, review, 'accept')
        self.reopen()
        self.assertEqual(self.receiver.decide(self.offer, review, 'accept')['recipient_state'], 'accepted')
        with self.assertRaises(Denied): self.receiver.decide(self.offer, review, 'reject')

    def test_postcommit_receipt_loss_can_inspect_or_repeat_original_delivery(self):
        self.approve(); delivery = self.sender.release(self.offer)
        transaction = self.w._transaction
        @contextmanager
        def lost_commit_ack():
            with transaction(): yield
            raise RuntimeError('SECRET receipt ACK lost')
        with patch.object(self.w, '_transaction', lost_commit_ack):
            with self.assertRaises(OutcomeUnknown): self.receiver.receive(delivery)
        self.reopen()
        result = self.receiver.receive(delivery)
        self.assertEqual(result['recipient_state'], 'pending')
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:target'").fetchone()[0], 1)

    def test_decision_rollback_is_pending_and_does_not_report_acceptance(self):
        _, review = self.received()
        with patch.object(self.w, '_event', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(OutcomeUnknown): self.receiver.decide(self.offer, review, 'accept')
        self.reopen()
        self.assertEqual(self.receiver.status(self.offer)['recipient_state'], 'pending')

    def test_audit_and_status_contain_no_content(self):
        _, review = self.received()
        self.receiver.decide(self.offer, review, 'accept')
        output = json.dumps(self.receiver.status(self.offer)) + json.dumps([dict(row) for row in self.w.db.execute('SELECT * FROM audit')])
        for text in ('SYNTHETIC ORIGINAL SOURCE', 'SYNTHETIC DERIVED ARTIFACT', 'RECIPIENT OBJECTIVE'):
            self.assertNotIn(text, output)

    def test_schema_version_mismatch_cannot_upgrade_history(self):
        self.approve()
        self.sender.release(self.offer)
        self.w.db.execute("UPDATE acceptance_meta SET version='other'")
        with self.assertRaises(Denied): AcceptanceBoundary(self.w)
        self.assertEqual(self.sender.status(self.offer)['outcome'], 'uncertain')

    def race(self, operations):
        barrier = threading.Barrier(len(operations))
        results, errors = [], []
        def worker(operation):
            w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
            try:
                boundary = AcceptanceBoundary(w)
                receiver = boundary.recipient_control('dana', 'recipient', expected_context=w.context)
                sender = boundary.source_control('carol', expected_context=w.context)
                barrier.wait(5)
                try: results.append(operation(w, boundary, receiver, sender))
                except Denied: results.append('denied')
            except BaseException as exc: errors.append(exc)
            finally: w.close()
        threads = [threading.Thread(target=worker, args=(op,)) for op in operations]
        for thread in threads: thread.start()
        for thread in threads: thread.join(8)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        return results

    def test_concurrent_accept_and_reject_commit_one_terminal_decision(self):
        _, review = self.received()
        results = self.race([lambda w,b,r,s: r.decide(self.offer, review, 'accept'),
                             lambda w,b,r,s: r.decide(self.offer, review, 'reject')])
        self.assertEqual(results.count('denied'), 1)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='acceptance_recipient_decided'").fetchone()[0], 1)

    def test_concurrent_duplicate_delivery_commits_one_inbox_and_read(self):
        self.approve(); delivery = self.sender.release(self.offer)
        results = self.race([lambda w,b,r,s: r.receive(delivery)] * 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM acceptance_inbox').fetchone()[0], 1)
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:target'").fetchone()[0], 1)

    def test_concurrent_identical_decisions_return_one_durable_result(self):
        _, review = self.received()
        results = self.race([lambda w,b,r,s: r.decide(self.offer, review, 'accept')] * 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='acceptance_recipient_decided'").fetchone()[0], 1)

    def test_revoke_winning_transaction_blocks_competing_acceptance(self):
        _, review = self.received()
        ready, start, done = threading.Event(), threading.Event(), threading.Event()
        results, errors = [], []
        def accept():
            w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
            try:
                boundary = AcceptanceBoundary(w)
                receiver = boundary.recipient_control('dana', 'recipient', expected_context=w.context)
                ready.set(); start.wait(5)
                try: results.append(receiver.decide(self.offer, review, 'accept'))
                except Denied: results.append('denied')
            except BaseException as exc: errors.append(exc)
            finally: w.close(); done.set()
        thread = threading.Thread(target=accept); thread.start()
        self.assertTrue(ready.wait(5))
        event = self.w._event
        def revoked(name, **data):
            event(name, **data)
            if name == 'acceptance_source_revoked':
                start.set()
                self.assertFalse(done.wait(0.1))
        with patch.object(self.w, '_event', revoked): self.upstream.revoke(self.offer)
        thread.join(8)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(results, ['denied'])
        self.assertEqual(self.receiver.status(self.offer)['recipient_state'], 'pending')

    def test_concurrent_release_returns_only_one_envelope(self):
        self.approve()
        results = self.race([lambda w,b,r,s: s.release(self.offer)] * 2)
        self.assertEqual(results.count('denied'), 1)
        self.assertEqual(sum(type(result) is SyntheticDelivery for result in results), 1)

    def test_acceptance_serialises_against_revocation(self):
        _, review = self.received()
        ready, started, finished = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def revoke():
            w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
            try:
                boundary = AcceptanceBoundary(w)
                source = boundary.source_control('bob', expected_context=w.context)
                ready.set(); started.wait(5)
                source.revoke(self.offer)
            except BaseException as exc: errors.append(exc)
            finally: w.close(); finished.set()
        thread = threading.Thread(target=revoke); thread.start()
        self.assertTrue(ready.wait(5))
        permissions = self.b._permissions
        def checked(row, body):
            result = permissions(row, body)
            started.set()
            self.assertFalse(finished.wait(0.1))
            return result
        with patch.object(self.b, '_permissions', checked): self.receiver.decide(self.offer, review, 'accept')
        thread.join(8)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(self.receiver.status(self.offer)['recipient_state'], 'accepted')
        self.assertEqual(self.upstream.review(self.offer)['state'], 'revoked')


if __name__ == '__main__':
    unittest.main()
