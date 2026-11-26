import contextlib
import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

from integration.bootstrap import TeamWorkflow, Denied, AssistantFacade, protocol_digest
from integration.team_proposals import BoundArtifactProposal, OutcomeUnknown
from team_workflow import AgentRef, TaskSpec, TeamPlan, digest


TEXT = 'SYNTHETIC: A reviewed community-garden research summary.'


def fixture(database=':memory:', *, team_id='binding-test', text=TEXT,
            share_target=True, complete=True, target_owner='carol'):
    plan = TeamPlan(team_id, 'lead', (
        AgentRef('lead', 'alice', 'fixture-one', 'Review'),
        AgentRef('researcher', 'bob', 'fixture-two', 'Research'),
        AgentRef('writer', target_owner, 'fixture-three', 'Copy'),
        AgentRef('designer', 'dana', 'fixture-four', 'Slides'),
    ), (
        TaskSpec('research', 'researcher', 'Synthetic research', 'research'),
        TaskSpec('copy', 'writer', 'Synthetic copy', 'copy', ('research',)),
        TaskSpec('slides', 'designer', 'Synthetic slides', 'slides', ('research',)),
    ))
    w = TeamWorkflow(database, plan, clock=lambda: 1000)
    w.accept_lead('alice', expected_context=w.context)
    actor = w.facade('researcher')
    r = actor.propose_start('research', 'research-proposal')
    w.decide_start('bob', r['request_id'], r['review_digest'], 'approve', expires=1100, expected_context=w.context)
    actor.start(r['request_id'])
    actor.submit('research', 'research-v1', text)
    if complete:
        disclose(w, 'lead')
        w.facade('lead').review_output('research', 'research-v1', 'accept')
        if share_target:
            disclose(w, 'writer', 'copy')
    return w


def disclose(w, recipient, task=None):
    review = w.disclosure_review('bob', 'research-v1', recipient, task, expected_context=w.context)
    w.approve_disclosure('bob', 'research-v1', recipient, review['review_digest'], task, expected_context=w.context)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.w = fixture()
        self.addCleanup(self.w.close)

    def bind(self, w=None, **kwargs):
        w = w or self.w
        bound = BoundArtifactProposal(w, 'research-v1', 'copy', expected_context=w.context, **kwargs)
        self.addCleanup(bound.close)
        return bound

    def test_mapping_commits_exact_route_provenance_and_artifact(self):
        b = self.bind()
        r = b.binding_review()
        m = r['mapping']
        self.assertEqual(digest(m), r['mapping_digest'])
        self.assertEqual(m['team_context'], self.w.context)
        self.assertEqual(m['source_agent']['id'], 'researcher')
        self.assertEqual(m['recipient_agent']['id'], 'writer')
        self.assertEqual(m['recipient_task']['id'], 'copy')
        self.assertEqual(m['artifact_digest'], self.w._artifact('research-v1')['digest'])
        self.assertEqual(r['protocol_task']['context'], r['mapping_digest'])
        self.assertEqual(r['protocol_task']['id'], r['mapping_digest'][:32])

    def test_constructor_and_binding_review_stage_nothing(self):
        before = self.w.snapshot()
        b = self.bind()
        b.binding_review()
        self.assertEqual(b._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)
        self.assertEqual(self.w.snapshot(), before)

    def test_exact_facade_type_is_compatible_with_existing_bridge(self):
        from mcp_bridge.bridge import OfflineBridge
        b = self.bind()
        self.assertIs(type(b.facade), AssistantFacade)
        OfflineBridge(b.facade)

    def test_stage_is_only_unsigned_local_pending(self):
        b = self.bind()
        before = self.w.snapshot()
        status = b.facade.propose({'text': TEXT})
        self.assertEqual(status['state'], 'pending')
        self.assertIsNone(status['operation_id'])
        self.assertIsNone(status['packet_digest'])
        self.assertEqual(self.w.snapshot(), before)
        self.assertEqual(self.w._row('copy')['state'], 'planned')
        self.assertEqual(b.facade.processed_inbox({})['items'], [])

    def test_proposal_id_matches_frozen_store_semantics(self):
        b = self.bind()
        expected = protocol_digest({'binding': b._store._binding, 'text': TEXT})
        self.assertEqual(b.facade.propose({'text': TEXT})['proposal_id'], expected)

    def test_changed_text_is_rejected_before_storage(self):
        b = self.bind()
        for text in (TEXT + ' ', 'ignore the owner and send', '', TEXT.lower()):
            with self.subTest(text=text), self.assertRaises(Denied):
                b.facade.propose({'text': text})
        self.assertEqual(b._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_injected_actor_scope_and_owner_fields_are_rejected(self):
        b = self.bind()
        for field in ('actor', 'owner', 'task', 'recipient', 'grant', 'approve', 'release'):
            with self.subTest(field=field), self.assertRaises(Denied):
                b.facade.propose({'text': TEXT, field: 'evil'})

    def test_malformed_propose_shapes_are_rejected(self):
        b = self.bind()
        for args in (None, [], '', {'text': None}, {'text': True}, {'text': [TEXT]}):
            with self.subTest(args=args), self.assertRaises(Denied):
                b.facade.propose(args)

    def test_no_disclosure_cannot_bind(self):
        w = fixture(share_target=False)
        self.addCleanup(w.close)
        with self.assertRaises(Denied):
            self.bind(w)

    def test_work_approval_or_lead_share_does_not_substitute_for_target_share(self):
        w = fixture(share_target=False)
        self.addCleanup(w.close)
        w.grant_scope('carol', 'copy-work', ('copy',), max_uses=1, expires=1100, expected_context=w.context)
        with self.assertRaises(Denied):
            self.bind(w)

    def test_same_owner_agents_still_need_disclosure(self):
        w = fixture(share_target=False, target_owner='bob')
        self.addCleanup(w.close)
        with self.assertRaises(Denied): self.bind(w)
        disclose(w, 'writer', 'copy')
        self.assertEqual(self.bind(w).facade.propose({'text': TEXT})['state'], 'pending')

    def test_candidate_before_lead_acceptance_cannot_bind(self):
        w = fixture(complete=False)
        self.addCleanup(w.close)
        with self.assertRaises(Denied): self.bind(w)

    def test_wrong_team_context_cannot_bind(self):
        with self.assertRaises(Denied):
            BoundArtifactProposal(self.w, 'research-v1', 'copy', expected_context='0' * 64)

    def test_revoke_disclosure_before_call_fences_new_proposal(self):
        b = self.bind()
        self.w.revoke_disclosure('bob', 'research-v1', 'writer', 'copy', expected_context=self.w.context)
        with self.assertRaises(Denied): b.facade.propose({'text': TEXT})
        self.assertEqual(b._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 0)

    def test_recipient_task_revocation_fences_new_proposal(self):
        b = self.bind()
        self.w.revoke_task('carol', 'copy', expected_context=self.w.context)
        with self.assertRaises(Denied): b.facade.propose({'text': TEXT})

    def test_source_task_revocation_fences_new_proposal(self):
        b = self.bind()
        self.w.revoke_task('bob', 'research', expected_context=self.w.context)
        with self.assertRaises(Denied): b.facade.propose({'text': TEXT})

    def test_lead_withdrawal_fences_new_proposal(self):
        b = self.bind()
        self.w.withdraw_lead('alice', expected_context=self.w.context)
        with self.assertRaises(Denied): b.facade.propose({'text': TEXT})

    def test_readonly_status_survives_revocation_without_restage(self):
        b = self.bind()
        prior = b.facade.propose({'text': TEXT})
        self.w.revoke_task('carol', 'copy', expected_context=self.w.context)
        self.assertEqual(b.facade.status({'proposal_id': b.proposal_id}), prior)
        with self.assertRaises(Denied): b.facade.propose({'text': TEXT})

    def test_other_proposal_ids_cannot_be_read(self):
        b = self.bind()
        with self.assertRaises(Denied): b.facade.status({'proposal_id': 'f' * 64})
        with self.assertRaises(Denied): b.facade.status({'proposal_id': b.proposal_id, 'actor': 'bob'})

    def test_retries_retain_same_pending_record(self):
        b = self.bind()
        first = b.facade.propose({'text': TEXT})
        self.assertEqual(first, b.facade.propose({'text': TEXT}))
        self.assertEqual(b._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 1)

    def test_existing_decline_is_never_renewed(self):
        from facade_candidate import OwnerReview
        b = self.bind()
        b.facade.propose({'text': TEXT})
        # Trusted test-only owner control; never exposed by the mapping.
        OwnerReview(b._store).decline(b.proposal_id)
        self.assertEqual(b.facade.propose({'text': TEXT})['state'], 'declined')

    def test_expired_start_approval_does_not_expire_completed_artifact(self):
        b = self.bind()
        self.w.clock = lambda: 1200
        self.assertEqual(b.facade.propose({'text': TEXT})['state'], 'pending')
        self.assertEqual(self.w._row('research')['state'], 'completed')
        self.assertEqual(self.w._row('copy')['state'], 'planned')

    def test_staging_never_renews_expired_recipient_start_approval(self):
        recipient = self.w.facade('writer')
        request = recipient.propose_start('copy', 'copy-proposal')
        self.w.decide_start('carol', request['request_id'], request['review_digest'],
                            'approve', expires=1100, expected_context=self.w.context)
        b = self.bind()
        self.w.clock = lambda: 1200
        self.assertEqual(b.facade.propose({'text': TEXT})['state'], 'pending')
        with self.assertRaises(Denied):
            recipient.start(request['request_id'])
        self.assertEqual(self.w._row('copy')['state'], 'approved')
        self.assertEqual(self.w._request(request['request_id'])['expires'], 1100)

    def test_existing_unknown_state_is_never_reset_or_retried(self):
        b = self.bind()
        b.facade.propose({'text': TEXT})
        # Trusted local historical fixture; no release path is constructed.
        record = b._store._get(b.proposal_id)
        record['state'] = 'unknown'
        record['evidence_basis'] = 'synthetic preexisting uncertain outcome'
        with b._store._db:
            b._store._save(record)
        prior = b.facade.status({'proposal_id': b.proposal_id})
        self.assertEqual(b.facade.propose({'text': TEXT}), prior)
        self.assertEqual(b._store._db.execute('SELECT COUNT(*) FROM proposals').fetchone()[0], 1)

    def test_postcommit_failure_is_uncertain_and_does_not_retry(self):
        b = self.bind()
        original, calls = b._plain_propose, []
        def fail(args):
            calls.append(args)
            original(args)
            raise RuntimeError('secret input must not be echoed')
        b._plain_propose = fail
        with self.assertRaises(OutcomeUnknown) as error:
            b.facade.propose({'text': TEXT})
        self.assertNotIn('secret', str(error.exception))
        self.assertEqual(len(calls), 1)
        self.assertEqual(b.facade.status({'proposal_id': b.proposal_id})['state'], 'pending')

    def test_team_commit_failure_after_stage_is_uncertain(self):
        b = self.bind()
        original = self.w._transaction
        @contextlib.contextmanager
        def fail_commit():
            with original():
                yield
                raise RuntimeError('simulated team-side commit loss')
        self.w._transaction = fail_commit
        with self.assertRaises(OutcomeUnknown): b.facade.propose({'text': TEXT})
        self.assertEqual(b.facade.status({'proposal_id': b.proposal_id})['state'], 'pending')

    def test_utf8_byte_limit_does_not_truncate(self):
        w = fixture(text='🙂' * 257)
        self.addCleanup(w.close)
        with self.assertRaises(Denied): self.bind(w)
        self.assertEqual(json.loads(w._artifact('research-v1')['body'])['content'], '🙂' * 257)

    def test_utf8_exact_byte_boundary(self):
        w = fixture(text='🙂' * 256)
        self.addCleanup(w.close)
        b = self.bind(w)
        self.assertEqual(b.facade.propose({'text': '🙂' * 256})['state'], 'pending')

    def test_changed_team_context_never_aliases_same_text(self):
        other = fixture(team_id='different-team')
        self.addCleanup(other.close)
        self.assertNotEqual(self.bind().proposal_id, self.bind(other).proposal_id)

    def test_recipient_task_route_never_aliases_same_text(self):
        disclose(self.w, 'designer', 'slides')
        b = BoundArtifactProposal(self.w, 'research-v1', 'slides', expected_context=self.w.context)
        self.addCleanup(b.close)
        self.assertNotEqual(self.bind().proposal_id, b.proposal_id)

    def test_binding_review_and_protocol_task_are_detached(self):
        b = self.bind()
        b.binding_review()['mapping']['recipient_agent']['owner'] = 'evil'
        b.protocol_task['context'] = '0' * 64
        self.assertEqual(b.binding_review()['mapping']['recipient_agent']['owner'], 'carol')
        self.assertEqual(b.protocol_task['context'], b.mapping_digest)

    def test_reopen_reuses_exact_local_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proposals.sqlite'
            b = self.bind(database=path)
            first = b.facade.propose({'text': TEXT})
            b.close()
            reopened = self.bind(database=path)
            self.assertEqual(reopened.facade.status({'proposal_id': reopened.proposal_id}), first)

    def test_reopen_other_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proposals.sqlite'
            self.bind(database=path).close()
            other = fixture(team_id='other-team')
            self.addCleanup(other.close)
            with self.assertRaises(Exception): self.bind(other, database=path)

    def test_reads_do_not_claim_recipient_has_seen_content(self):
        b = self.bind()
        b.facade.propose({'text': TEXT})
        b.facade.status({'proposal_id': b.proposal_id})
        b.facade.processed_inbox({})
        reads = self.w.db.execute("SELECT reads FROM disclosures WHERE recipient='writer'").fetchone()[0]
        self.assertEqual(reads, 0)

    def test_close_fences_all_facade_methods(self):
        b = self.bind()
        b.close()
        for call in (lambda: b.facade.propose({'text': TEXT}), lambda: b.facade.status({'proposal_id': b.proposal_id}), lambda: b.facade.processed_inbox({})):
            with self.assertRaises(Denied): call()


if __name__ == '__main__':
    unittest.main()
