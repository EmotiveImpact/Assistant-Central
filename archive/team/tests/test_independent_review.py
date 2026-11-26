"""Independent adversarial tests. Fictional agents; temporary local SQLite only."""
import tempfile
import unittest
from pathlib import Path
from team_workflow import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied


class IndependentReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.plan = TeamPlan('demo', 'lead', (
            AgentRef('lead', 'lead-owner', 'fictional', 'review'),
            AgentRef('writer', 'shared-owner', 'fictional', 'copy'),
            AgentRef('reader', 'shared-owner', 'fictional', 'slides'),
        ), (
            TaskSpec('source', 'writer', 'Produce copy', 'copy', resources=('editor',)),
            TaskSpec('dependent', 'reader', 'Produce slides', 'slides', dependencies=('source',)),
            TaskSpec('parallel', 'reader', 'Research independently', 'research', resources=('editor',)),
        ))
        self.path = Path(self.tmp.name) / 'fixture.sqlite'
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
        self.ctx = {'expected_context': self.w.context}
        self.w.accept_lead('lead-owner', **self.ctx)
        self.writer = self.w.facade('writer')
        self.reader = self.w.facade('reader')
        self.lead = self.w.facade('lead')

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def request(self, task='source', facade=None):
        return (facade or self.writer).propose_start(task, 'proposal-' + task)

    def approve(self, request, expires=1100):
        self.w.decide_start('shared-owner', request['request_id'], request['review_digest'], 'approve', expires=expires, **self.ctx)

    def start_source(self):
        r = self.request()
        self.approve(r)
        self.writer.start(r['request_id'])
        return r

    def disclose(self, artifact='output', recipient='lead', purpose=None):
        r = self.w.disclosure_review('shared-owner', artifact, recipient, purpose, **self.ctx)
        self.w.approve_disclosure('shared-owner', artifact, recipient, r['review_digest'], purpose, **self.ctx)
        return r

    def accepted_source(self):
        self.start_source()
        self.writer.submit('source', 'output', 'Untrusted fictional copy')
        self.disclose()
        self.lead.review_output('source', 'output', 'accept')

    def ready_dependent(self):
        self.accepted_source()
        self.disclose(recipient='reader', purpose='dependent')
        r = self.request('dependent', self.reader)
        self.approve(r)
        self.reader.start(r['request_id'])
        return r

    def state(self, task):
        return next(t['state'] for t in self.w.snapshot()['tasks'] if t['id'] == task)

    def test_no_permission_no_start(self):
        r = self.request()
        with self.assertRaises(Denied): self.writer.start(r['request_id'])
        self.assertEqual(self.state('source'), 'awaiting_approval')

    def test_same_owner_not_same_agent_authority(self):
        r = self.request(); self.approve(r)
        with self.assertRaises(Denied): self.reader.start(r['request_id'])
        with self.assertRaises(Denied): self.reader.submit('source', 'wrong', 'content')

    def test_manual_permission_does_not_disclose_to_lead(self):
        self.start_source(); self.writer.submit('source', 'output', 'secret')
        with self.assertRaises(Denied): self.lead.read_artifact('output')
        with self.assertRaises(Denied): self.lead.review_output('source', 'output', 'accept')

    def test_same_owner_still_requires_separate_disclosure(self):
        self.accepted_source()
        with self.assertRaises(Denied): self.reader.read_artifact('output', 'dependent')
        with self.assertRaises(Denied): self.request('dependent', self.reader)

    def test_wrong_owner_and_context_denied(self):
        r = self.request()
        with self.assertRaises(Denied): self.w.decide_start('lead-owner', r['request_id'], r['review_digest'], 'approve', expires=1100, **self.ctx)
        with self.assertRaises(Denied): self.w.decide_start('shared-owner', r['request_id'], r['review_digest'], 'approve', expires=1100, expected_context='wrong')

    def test_wrong_disclosure_digest_and_recipient_denied(self):
        self.start_source(); self.writer.submit('source', 'output', 'secret')
        r = self.w.disclosure_review('shared-owner', 'output', 'lead', **self.ctx)
        with self.assertRaises(Denied): self.w.approve_disclosure('shared-owner', 'output', 'lead', 'wrong', **self.ctx)
        with self.assertRaises(Denied): self.w.approve_disclosure('shared-owner', 'output', 'reader', r['review_digest'], **self.ctx)

    def test_artifact_immutable_and_returned_data_detached(self):
        self.start_source(); self.writer.submit('source', 'output', 'original')
        with self.assertRaises(Denied): self.writer.submit('source', 'output', 'replacement')
        body = self.writer.read_artifact('output'); body['artifact']['content'] = 'mutated'
        self.assertEqual(self.writer.read_artifact('output')['artifact']['content'], 'original')

    def test_review_changes_requires_fresh_disclosure(self):
        self.start_source(); self.writer.submit('source', 'output', 'v1'); self.disclose()
        self.lead.review_output('source', 'output', 'changes')
        self.writer.submit('source', 'output-two', 'v2')
        with self.assertRaises(Denied): self.lead.review_output('source', 'output-two', 'accept')
        with self.assertRaises(Denied): self.lead.review_output('source', 'output', 'accept')

    def test_refusal_is_terminal_and_cascades(self):
        r = self.request()
        self.w.decide_start('shared-owner', r['request_id'], r['review_digest'], 'refuse', **self.ctx)
        self.assertEqual(self.state('dependent'), 'stopped')
        with self.assertRaises(Denied): self.writer.start(r['request_id'])
        with self.assertRaises(Denied): self.w.grant_scope('shared-owner', 'scope', ['source'], max_uses=1, expires=1100, **self.ctx)

    def test_resource_conflict_does_not_consume_scope(self):
        self.start_source()
        r = self.request('parallel', self.reader)
        self.w.grant_scope('shared-owner', 'scope', ['parallel'], max_uses=1, expires=1100, **self.ctx)
        with self.assertRaises(Denied): self.reader.start(r['request_id'], 'scope')
        self.assertEqual(self.w.scope_status('shared-owner', 'scope', **self.ctx)['uses'], 0)
        self.w.revoke_task('shared-owner', 'source', **self.ctx)
        self.reader.start(r['request_id'], 'scope')
        self.assertEqual(self.w.scope_status('shared-owner', 'scope', **self.ctx)['uses'], 1)

    def test_scoped_task_list_cannot_expand(self):
        self.w.grant_scope('shared-owner', 'scope', ['parallel'], max_uses=1, expires=1100, **self.ctx)
        r = self.request()
        with self.assertRaises(Denied): self.writer.start(r['request_id'], 'scope')
        with self.assertRaises(Denied): self.w.grant_scope('shared-owner', 'scope', ['source'], max_uses=1, expires=1100, **self.ctx)

    def test_duplicate_start_consumes_one_use(self):
        self.w.grant_scope('shared-owner', 'scope', ['source'], max_uses=1, expires=1100, **self.ctx)
        r = self.request(); self.writer.start(r['request_id'], 'scope')
        self.assertTrue(self.writer.start(r['request_id'], 'scope')['already_started'])
        self.assertEqual(self.w.scope_status('shared-owner', 'scope', **self.ctx)['uses'], 1)

    def test_scope_revoke_stops_work_and_releases_lock(self):
        self.w.grant_scope('shared-owner', 'scope', ['source'], max_uses=1, expires=1100, **self.ctx)
        r = self.request(); self.writer.start(r['request_id'], 'scope')
        self.w.revoke_scope('shared-owner', 'scope', **self.ctx)
        self.assertEqual(self.state('source'), 'revoked')
        self.assertEqual(self.w.snapshot()['locks'], [])
        with self.assertRaises(Denied): self.writer.submit('source', 'output', 'late')

    def test_expired_permission_blocks_new_start(self):
        r = self.request(); self.approve(r); self.now = 1100
        with self.assertRaises(Denied): self.writer.start(r['request_id'])

    def test_expiry_does_not_stop_running_work(self):
        self.start_source(); self.now = 1200
        self.writer.submit('source', 'output', 'valid continuation')
        self.assertEqual(self.state('source'), 'awaiting_review')

    def test_disclosure_revoke_stops_consumer_and_future_reads(self):
        self.ready_dependent()
        self.w.revoke_disclosure('shared-owner', 'output', 'reader', 'dependent', **self.ctx)
        self.assertEqual(self.state('dependent'), 'stopped')
        with self.assertRaises(Denied): self.reader.read_artifact('output', 'dependent')
        with self.assertRaises(Denied): self.reader.submit('dependent', 'slides', 'late')
        with self.assertRaises(Denied): self.disclose(recipient='reader', purpose='dependent')

    def test_revoked_task_cannot_keep_reading_inputs(self):
        self.ready_dependent()
        self.w.revoke_task('shared-owner', 'dependent', **self.ctx)
        with self.assertRaises(Denied): self.reader.read_artifact('output', 'dependent')

    def test_withdrawn_lead_stops_dependent_input_reads(self):
        self.ready_dependent()
        self.w.withdraw_lead('lead-owner', **self.ctx)
        self.assertEqual(self.state('dependent'), 'stopped')
        with self.assertRaises(Denied): self.reader.read_artifact('output', 'dependent')

    def test_proposal_alias_cannot_change_task(self):
        self.request('parallel', self.reader)
        self.accepted_source(); self.disclose(recipient='reader', purpose='dependent')
        with self.assertRaises(Denied): self.reader.propose_start('dependent', 'proposal-parallel')

    def test_plan_cycle_denied(self):
        with self.assertRaises(Denied): TeamPlan('cycle', 'lead', self.plan.agents, (
            TaskSpec('one', 'writer', 'one', 'copy', ('two',)),
            TaskSpec('two', 'reader', 'two', 'slides', ('one',)),
        ))

    def test_reopen_preserves_decisions_and_rejects_changed_plan(self):
        self.start_source(); self.w.close()
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: self.now)
        self.assertEqual(self.state('source'), 'running')
        changed = TeamPlan('different', 'lead', self.plan.agents, self.plan.tasks)
        with self.assertRaises(Denied): TeamWorkflow(self.path, changed, clock=lambda: self.now)

    def test_invalid_expiry_types(self):
        r = self.request()
        for expiry in (True, float('nan'), float('inf'), 1000, 4601):
            with self.subTest(expiry=expiry), self.assertRaises(Denied): self.approve(r, expiry)

    def test_nonlead_cannot_review_even_with_content(self):
        self.start_source(); self.writer.submit('source', 'output', 'copy')
        with self.assertRaises(Denied): self.writer.review_output('source', 'output', 'accept')

    def test_duplicate_review_cannot_change_accepted_output(self):
        self.accepted_source()
        with self.assertRaises(Denied): self.lead.review_output('source', 'output', 'changes')
        self.assertEqual(self.state('source'), 'completed')

    def test_artifact_commits_exact_approved_input_provenance(self):
        r = self.ready_dependent()
        self.reader.submit('dependent', 'slides', 'derived content')
        artifact = self.reader.read_artifact('slides')['artifact']
        self.assertEqual(artifact['start_review_digest'], r['review_digest'])
        self.assertEqual(r['review']['inputs'][0]['artifact_id'], 'output')
        self.assertEqual(r['review']['inputs'][0]['digest'], self.writer.read_artifact('output')['digest'])

    def test_withdraw_lead_revokes_completed_source_review_access(self):
        self.accepted_source()
        self.w.withdraw_lead('lead-owner', **self.ctx)
        with self.assertRaises(Denied): self.lead.read_artifact('output')
        self.assertEqual(self.writer.read_artifact('output')['state'], 'accepted')

    def test_lead_review_task_name_cannot_reuse_review_consent(self):
        self.w.close()
        self.plan = TeamPlan('collision', 'lead', self.plan.agents, (
            TaskSpec('source', 'writer', 'Source', 'copy'),
            TaskSpec('lead-review', 'lead', 'Dependent task', 'research', ('source',)),
        ))
        self.w = TeamWorkflow(Path(self.tmp.name) / 'collision.sqlite', self.plan, clock=lambda: self.now)
        self.ctx = {'expected_context': self.w.context}
        self.w.accept_lead('lead-owner', **self.ctx)
        self.writer, self.lead = self.w.facade('writer'), self.w.facade('lead')
        self.accepted_source()
        with self.assertRaises(Denied): self.lead.read_artifact('output', 'lead-review')
        with self.assertRaises(Denied): self.lead.propose_start('lead-review', 'p')
        self.disclose(recipient='lead', purpose='lead-review')
        self.w.revoke_disclosure('shared-owner', 'output', 'lead', **self.ctx)
        self.assertEqual(self.lead.read_artifact('output', 'lead-review')['artifact_id'], 'output')
        self.assertEqual(self.state('lead-review'), 'planned')

    def test_scope_revocation_preserves_already_accepted_result(self):
        self.w.grant_scope('shared-owner', 'scope', ['source'], max_uses=1, expires=1100, **self.ctx)
        r = self.request(); self.writer.start(r['request_id'], 'scope')
        self.writer.submit('source', 'output', 'copy'); self.disclose()
        self.lead.review_output('source', 'output', 'accept')
        self.w.revoke_scope('shared-owner', 'scope', **self.ctx)
        self.assertEqual(self.state('source'), 'completed')
        self.assertEqual(self.writer.read_artifact('output')['state'], 'accepted')


if __name__ == '__main__':
    unittest.main()
