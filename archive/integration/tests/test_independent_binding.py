"""Adversarial synthetic-only review. No peer transport or privileged owner facade."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from integration.bootstrap import AssistantFacade, Denied, TeamWorkflow
from integration.team_proposals import BoundArtifactProposal, OutcomeUnknown
from team_workflow import AgentRef, TaskSpec, TeamPlan


class IndependentBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'team.sqlite'
        self.plan = TeamPlan('independent', 'lead', (
            AgentRef('lead', 'owner', 'fixture', 'review'),
            AgentRef('source', 'owner', 'fixture', 'research'),
            AgentRef('target', 'owner', 'fixture', 'copy')),
            (TaskSpec('source-task', 'source', 'Synthetic research', 'research'),
             TaskSpec('target-task', 'target', 'Synthetic copy', 'copy', ('source-task',)),
             TaskSpec('other-task', 'target', 'Different purpose', 'copy', ('source-task',))))
        self.w = TeamWorkflow(self.path, self.plan, clock=lambda: 1000)
        self.addCleanup(self.w.close)
        self.w.accept_lead('owner', expected_context=self.w.context)
        self.text = 'INERT synthetic review payload'
        source = self.w.facade('source')
        request = source.propose_start('source-task', 'alias-original')
        self.w.decide_start('owner', request['request_id'], request['review_digest'], 'approve',
                            expires=1100, expected_context=self.w.context)
        source.start(request['request_id'])
        source.submit('source-task', 'artifact-one', self.text)
        self.share('lead')
        self.w.facade('lead').review_output('source-task', 'artifact-one', 'accept')

    def share(self, recipient='target', task=None):
        review = self.w.disclosure_review('owner', 'artifact-one', recipient, task,
                                           expected_context=self.w.context)
        self.w.approve_disclosure('owner', 'artifact-one', recipient, review['review_digest'], task,
                                  expected_context=self.w.context)

    def bind(self, task='target-task', database=':memory:'):
        result = BoundArtifactProposal(self.w, 'artifact-one', task,
                                        expected_context=self.w.context, database=database)
        self.addCleanup(result.close)
        return result

    def ready(self, database=':memory:'):
        self.share(task='target-task')
        return self.bind(database=database)

    def test_same_owner_does_not_imply_disclosure(self):
        with self.assertRaises(Denied):
            self.bind()

    def test_disclosure_is_exact_purpose_not_recipient_only(self):
        self.share(task='other-task')
        with self.assertRaises(Denied):
            self.bind()

    def test_bound_facade_exact_type_and_no_content_in_result(self):
        bound = self.ready()
        self.assertIs(type(bound.facade), AssistantFacade)
        value = bound.facade.propose({'text': self.text})
        self.assertEqual(value['state'], 'pending')
        self.assertNotIn(self.text, json.dumps(value))
        self.assertEqual(bound.facade.processed_inbox({})['items'], [])
        self.assertEqual(bound.facade.propose({'text': self.text}), value)

    def test_malformed_and_crossed_selectors_are_denied(self):
        bound = self.ready()
        for argument in (None, [], {}, {'text': self.text, 'recipient': 'target'},
                         {'text': 'altered'}, {'text': '\ud800'}, {'text': 1}):
            with self.subTest(argument=repr(argument)), self.assertRaises(Denied):
                bound.facade.propose(argument)
        for argument in (None, {}, {'proposal_id': '0' * 64},
                         {'proposal_id': bound.proposal_id, 'text': self.text}):
            with self.subTest(argument=repr(argument)), self.assertRaises(Denied):
                bound.facade.status(argument)

    def test_revoked_after_construction_denies_stage_but_preserves_status(self):
        bound = self.ready()
        original = bound.facade.propose({'text': self.text})
        self.w.revoke_disclosure('owner', 'artifact-one', 'target', 'target-task',
                                 expected_context=self.w.context)
        with self.assertRaises(Denied):
            bound.facade.propose({'text': self.text})
        self.assertEqual(bound.facade.status({'proposal_id': bound.proposal_id}), original)
        with self.assertRaises(Denied):
            self.bind()

    def test_stale_review_digest_denies_stage(self):
        bound = self.ready()
        self.w.db.execute("UPDATE disclosures SET review_digest=? WHERE purpose='task:target-task'", ('0' * 64,))
        with self.assertRaises(Denied):
            bound.facade.propose({'text': self.text})

    def test_another_purpose_cannot_rebind_existing_database(self):
        path = Path(self.temp.name) / 'proposal.sqlite'
        self.ready(database=path)
        self.share(task='other-task')
        with self.assertRaises(Exception) as caught:
            self.bind('other-task', database=path)
        self.assertIn('immutable', str(caught.exception))

    def test_declined_record_survives_new_binding_and_alias(self):
        path = Path(self.temp.name) / 'proposal.sqlite'
        bound = self.ready(database=path)
        bound.facade.propose({'text': self.text})
        # Synthetic preexisting decline fixture; no owner-review object constructed.
        record = bound._store._get(bound.proposal_id)
        record['state'] = 'declined'
        record['evidence_basis'] = 'local owner declined exact meaning'
        with bound._store._db:
            bound._store._save(record)
        bound.close()
        alias = self.w.facade('source').propose_start('source-task', 'alias-different')
        self.assertEqual(alias['request_id'], self.w._row('source-task')['request_id'])
        self.assertEqual(self.w._row('source-task')['state'], 'completed')
        reopened = self.bind(database=path)
        self.assertEqual(reopened.proposal_id, bound.proposal_id)
        self.assertEqual(reopened.facade.propose({'text': self.text})['state'], 'declined')

    def test_committed_lower_failure_is_redacted_and_inspectable(self):
        bound = self.ready()
        original = bound._plain_propose
        def committed_then_failed(argument):
            original(argument)
            raise RuntimeError('SECRET synthetic internal detail')
        with patch.object(bound, '_plain_propose', committed_then_failed):
            with self.assertRaises(OutcomeUnknown) as caught:
                bound.facade.propose({'text': self.text})
        self.assertNotIn('SECRET', str(caught.exception))
        self.assertEqual(bound.facade.status({'proposal_id': bound.proposal_id})['state'], 'pending')

    def test_outer_transaction_exit_failure_is_uncertain_and_redacted(self):
        bound = self.ready()
        transaction = self.w._transaction
        @contextmanager
        def fail_exit():
            with transaction():
                yield
                raise sqlite3.OperationalError('SECRET synthetic commit failure')
        with patch.object(self.w, '_transaction', fail_exit):
            with self.assertRaises(OutcomeUnknown) as caught:
                bound.facade.propose({'text': self.text})
        self.assertNotIn('SECRET', str(caught.exception))
        self.assertEqual(bound.facade.status({'proposal_id': bound.proposal_id})['state'], 'pending')

    def test_revocation_cannot_commit_during_local_stage(self):
        bound = self.ready()
        ready, started, finished = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def revoke():
            other = TeamWorkflow(self.path, self.plan, clock=lambda: 1000)
            try:
                ready.set()
                started.wait(6)
                other.revoke_disclosure('owner', 'artifact-one', 'target', 'target-task',
                                       expected_context=other.context)
            except BaseException as exc:
                errors.append(exc)
            finally:
                other.close()
                finished.set()
        # Construct the second connection before the mapped team lock is taken.
        original = bound._plain_propose
        def stage(argument):
            self.assertFalse(finished.is_set())
            result = original(argument)
            self.assertFalse(finished.wait(0.1))
            return result
        thread = threading.Thread(target=revoke)
        thread.start()
        self.assertTrue(ready.wait(6))
        # Release the competing revoke only after the normal BEGIN IMMEDIATE.
        mapping = bound._current_mapping
        def current():
            result = mapping()
            started.set()
            return result
        with patch.object(bound, '_current_mapping', current), patch.object(bound, '_plain_propose', stage):
            bound.facade.propose({'text': self.text})
        thread.join(6)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(finished.is_set())
        with self.assertRaises(Denied):
            bound.facade.propose({'text': self.text})

    def test_nonempty_publication_is_not_disclosed(self):
        bound = self.ready()
        with bound._store._db:
            bound._store._db.execute('INSERT INTO publication VALUES(1,?)',
                (json.dumps({'items': [{'text': 'SECRET synthetic inbound'}]}),))
        with self.assertRaises(Denied) as caught:
            bound.facade.processed_inbox({})
        self.assertNotIn('SECRET', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
