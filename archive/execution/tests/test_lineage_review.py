"""Independent synthetic-only adversarial coverage of inherited disclosure."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied, canonical, digest
from execution.ledger import ExecutionLedger
from execution.provider_gate import ProviderGate, ProviderRoute
from execution.lineage import collect_lineage


def diamond_plan():
    return TeamPlan('lineage-review', 'lead', (
        AgentRef('lead', 'lead-owner', 'fixture', 'coordination'),
        AgentRef('source', 'alice', 'fixture', 'research'),
        AgentRef('left', 'bob', 'fixture', 'research'),
        AgentRef('right', 'alice', 'fixture', 'research'),
        AgentRef('target', 'alice', 'fixture', 'copy'),
    ), (
        TaskSpec('source', 'source', 'SOURCE OBJECTIVE', 'research'),
        TaskSpec('left', 'left', 'LEFT OBJECTIVE', 'research', ('source',)),
        TaskSpec('right', 'right', 'RIGHT OBJECTIVE', 'research', ('source',)),
        TaskSpec('target', 'target', 'TARGET OBJECTIVE', 'copy', ('left', 'right')),
    ))


class InheritedDisclosureIndependentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'lineage.sqlite'
        self.plan = diamond_plan()
        self.build()

    def build(self):
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: 1000)
        self.ledger = ExecutionLedger(self.w)
        self.gate = ProviderGate(self.ledger)
        self.w.accept_lead('lead-owner', expected_context=self.w.context)
        for task in ('source', 'left', 'right', 'target'):
            for dep in self.w.tasks[task].dependencies:
                self.disclose(dep, task, task)
            proposal = self.w.facade(task).propose_start(task, 'start-' + task)
            self.w.decide_start(self.owner(task), proposal['request_id'], proposal['review_digest'],
                                'approve', expires=1100, expected_context=self.w.context)
            self.w.facade(task).start(proposal['request_id'])
            if task != 'target':
                self.w.facade(task).submit(task, task + '-out', task.upper() + ' PRIVATE TEXT')
                self.disclose(task, 'lead', None)
                self.w.facade('lead').review_output(task, task + '-out', 'accept')
        self.ledger.facade('target').prepare('target', 'run', 'final-out')
        self.facade = self.gate.facade('target')
        self.route = ProviderRoute('fixture', 'account', 'model', 'Synthetic local only')
        self.facade.propose('run', self.route)

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def owner(self, task):
        return self.w.agents[task].owner

    def disclose(self, source, actor, task):
        args = (self.owner(source), source + '-out', actor)
        review = self.w.disclosure_review(*args, task, expected_context=self.w.context)
        self.w.approve_disclosure(*args, review['review_digest'], task, expected_context=self.w.context)

    def review(self, owner):
        return self.gate.owner_review(owner, 'run', expected_context=self.w.context)['review']

    def approve(self):
        for owner in [item['owner'] for item in self.facade.status('run')['decisions']]:
            review = self.gate.owner_review(owner, 'run', expected_context=self.w.context)
            self.gate.decide(owner, 'run', review['review_digest'], 'approve',
                             expires=1100, expected_context=self.w.context)

    def denied_release(self):
        with self.assertRaises(Denied):
            self.facade.release('run')
        self.assertEqual(self.facade.status('run')['state'], 'pending')
        self.assertEqual(self.ledger.facade('target').status('run')['state'], 'prepared')

    def test_diamond_shared_ancestor_same_owner_roles_and_private_previews(self):
        self.assertEqual([r['owner'] for r in self.facade.status('run')['decisions']], ['alice', 'bob'])
        alice, bob = self.review('alice'), self.review('bob')
        self.assertEqual([x['artifact_id'] for x in alice['upstream_source_data']], ['source-out'])
        self.assertNotIn('LEFT PRIVATE TEXT', json.dumps(alice))
        self.assertNotIn('SOURCE PRIVATE TEXT', json.dumps(bob))
        self.assertNotIn('RIGHT PRIVATE TEXT', json.dumps(bob))
        self.assertNotIn('TARGET OBJECTIVE', json.dumps(bob))
        self.assertEqual(alice['owned_data']['task_text'], 'TARGET OBJECTIVE')
        self.assertEqual({x['artifact_id']: x['owner_source_ids'] for x in alice['affected_payload_inputs']},
                         {'left-out': ['source-out'], 'right-out': ['right-out', 'source-out']})
        for item in alice['affected_payload_inputs']:
            self.assertEqual(item['digest'], self.w._artifact(item['artifact_id'])['digest'])
        self.approve()
        payload = self.facade.release('run').to_dict()['payload']
        self.assertEqual([x['artifact_id'] for x in payload['inputs']], ['left-out', 'right-out'])
        self.assertNotIn('SOURCE PRIVATE TEXT', json.dumps(payload))

    def test_transitive_only_owner_is_required_without_direct_input_or_task(self):
        self.w.close()
        self.path = Path(self.tmp.name) / 'three-owner.sqlite'
        self.plan = replace(self.plan, agents=tuple(
            replace(agent, owner='carol') if agent.id in ('right', 'target') else agent
            for agent in self.plan.agents))
        self.build()
        self.assertEqual([r['owner'] for r in self.facade.status('run')['decisions']],
                         ['alice', 'bob', 'carol'])
        alice = self.review('alice')
        self.assertEqual(alice['owned_data'], {'inputs': []})
        self.assertEqual([x['artifact_id'] for x in alice['upstream_source_data']], ['source-out'])
        for other in ('LEFT PRIVATE TEXT', 'RIGHT PRIVATE TEXT', 'TARGET OBJECTIVE'):
            self.assertNotIn(other, json.dumps(alice))
        for owner in ('bob', 'carol'):
            review = self.gate.owner_review(owner, 'run', expected_context=self.w.context)
            self.gate.decide(owner, 'run', review['review_digest'], 'approve',
                             expires=1100, expected_context=self.w.context)
        self.denied_release()
        review = self.gate.owner_review('alice', 'run', expected_context=self.w.context)
        self.gate.decide('alice', 'run', review['review_digest'], 'approve',
                         expires=1100, expected_context=self.w.context)
        self.facade.release('run')

    def test_one_withdrawn_diamond_edge_blocks_even_when_other_path_valid(self):
        self.approve()
        self.w.revoke_disclosure('alice', 'source-out', 'left', 'left', expected_context=self.w.context)
        self.assertEqual(self.w._row('left')['state'], 'completed')
        self.assertEqual(self.w._row('target')['state'], 'running')
        self.denied_release()

    def test_same_owner_different_producer_historical_disclosure_is_required(self):
        self.approve()
        self.w.revoke_disclosure('alice', 'source-out', 'right', 'right', expected_context=self.w.context)
        self.denied_release()

    def test_historical_task_revocation_cannot_hide_behind_completed_branches(self):
        self.approve()
        self.w.revoke_task('alice', 'source', expected_context=self.w.context)
        self.assertEqual(self.w._row('left')['state'], 'completed')
        self.assertEqual(self.w._row('target')['state'], 'running')
        self.denied_release()

    def test_historical_artifact_rejected_after_proposal_blocks(self):
        self.approve()
        self.w.db.execute("UPDATE artifacts SET state='rejected' WHERE id='source-out'")
        self.denied_release()

    def test_retained_input_selectors_cannot_drop_ancestry(self):
        self.approve()
        request = self.w._request(self.w._row('left')['request_id'])
        review = json.loads(request['review'])
        review['inputs'] = []
        self.w.db.execute('UPDATE requests SET review=?,digest=? WHERE id=?',
                          (canonical(review), digest(review), request['id']))
        self.denied_release()

    def test_changed_ancestor_body_even_with_rehashed_metadata_blocks(self):
        self.approve()
        artifact = self.w._artifact('source-out')
        body = json.loads(artifact['body'])
        body['content'] = 'CHANGED SOURCE'
        self.w.db.execute('UPDATE artifacts SET body=?,digest=? WHERE id=?',
                          (canonical(body), digest(body), 'source-out'))
        self.denied_release()

    def test_current_ancestor_pointer_cannot_select_a_different_artifact(self):
        self.approve()
        self.w.db.execute("UPDATE tasks SET artifact_id='right-out' WHERE id='source'")
        self.denied_release()

    def test_malformed_retained_record_is_denied(self):
        self.approve()
        self.w.db.execute("UPDATE requests SET review='[]' WHERE task_id='source'")
        self.denied_release()

    def test_weak_v1_schema_version_is_rejected_without_upgrading(self):
        self.w.db.execute("UPDATE provider_meta SET version='offline-provider-disclosure/1'")
        with self.assertRaises(Denied):
            ProviderGate(self.ledger)
        self.assertEqual(self.w.db.execute('SELECT version FROM provider_meta').fetchone()[0],
                         'offline-provider-disclosure/1')

    def test_lineage_requires_transaction_and_does_not_consume_historical_reads(self):
        with self.assertRaises(Denied):
            collect_lineage(self.w, {'inputs': []})
        before = [tuple(r) for r in self.w.db.execute('SELECT * FROM disclosures ORDER BY artifact_id,recipient,purpose')]
        self.approve()
        self.facade.release('run')
        after = [tuple(r) for r in self.w.db.execute('SELECT * FROM disclosures ORDER BY artifact_id,recipient,purpose')]
        self.assertEqual([r for r in before if r[0] == 'source-out'],
                         [r for r in after if r[0] == 'source-out'])

    def test_concurrent_committed_ancestor_revocation_blocks_waiting_release(self):
        self.approve()
        ready, go = threading.Event(), threading.Event()
        attempting, finished = threading.Event(), threading.Event()
        outcomes = []
        def release():
            w = TeamWorkflow(self.path, self.plan, clock=lambda: 1000)
            try:
                ledger = ExecutionLedger(w)
                gate = ProviderGate(ledger)
                ready.set()
                if not go.wait(8):
                    raise RuntimeError('Release test was not signalled')
                attempting.set()
                gate.facade('target').release('run')
                outcomes.append('released')
            except Denied:
                outcomes.append('denied')
            except Exception as exc:
                outcomes.append(repr(exc))
            finally:
                w.close()
                finished.set()
        # The second connection must observe this committed withdrawal, not a
        # stale ancestry snapshot. BEGIN IMMEDIATE is the common release fence.
        thread = threading.Thread(target=release)
        thread.start()
        self.assertTrue(ready.wait(8))
        with self.w._transaction():
            self.w.db.execute("UPDATE disclosures SET state='revoked' WHERE artifact_id='source-out' AND recipient='left' AND purpose='task:left'")
            go.set()
            self.assertTrue(attempting.wait(8))
            self.assertFalse(finished.wait(0.05))
        self.assertTrue(finished.wait(8))
        thread.join(1)
        self.assertEqual(outcomes, ['denied'])
        self.denied_release()


if __name__ == '__main__':
    unittest.main()
