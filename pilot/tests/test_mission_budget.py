"""Competing mission runs, durable uncertainty and exact provider projection."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from pilot.mission import direct_offer, direct_task_text, evidence, fixture_request, mission_context, task_text
from pilot.crypto import digest
import hashlib
from pilot.provider import ProviderBudget, ProviderDenied, ProviderOutcomeUnknown, ResponsesAdapter
from pilot.tests.test_provider import FixtureAuth, FixtureTransport, response


class MissionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'runs.db'
        self.auth = FixtureAuth()
        self.transport = FixtureTransport()
        self.limit = 276
        self.commitment = 'a' * 64
        self.text = task_text('Original fictional brief', self.limit, self.commitment)
        self.context = mission_context(self.commitment, self.limit)

    def connect(self):
        return sqlite3.connect(self.path, isolation_level=None)

    def adapter(self, db, **options):
        def authorise(token, binding):
            return {'task_text': self.text, 'context': binding['context'], 'recipient': 'assistant', 'synthetic_only': True, 'projection':'mission-brief-only/1'}
        return ResponsesAdapter(db, authorise, self.auth.authenticate, legacy_storage_fixture=True,
                                transport=self.transport, clock=lambda: 1000, budget=ProviderBudget(max_requests=3),
                                **options)

    def prepare(self, adapter, run):
        binding = {'provider': 'openai', 'model': 'synthetic-research-v1', 'context': self.context,
                   'payload_digest': 'b' * 64, 'item_id': run, 'max_output_tokens': 128}
        return adapter.prepare('owner-session', run, binding)

    def approve(self, adapter, run):
        result = self.prepare(adapter, run)
        review = adapter.review('owner-session', run)['review']
        self.assertEqual(review['request']['input'], 'Original fictional brief')
        self.assertEqual(review['mission_quote']['reserve_microusd'], 276)
        adapter.approve('owner-session', run, result['review_digest'], expires=1100)

    def test_utf8_measurement_and_exact_digest_are_independent_of_owner_judgement(self):
        content = 'é'
        expected = hashlib.sha256(content.encode()).hexdigest()
        agreed = {'executor': 'a' * 64, 'goal': 'Review', 'deliverable': 'Text',
                  'cap_microusd': 276, 'criteria': [{'kind': 'sha256', 'value': expected},
                                                     {'kind': 'max_utf8_bytes', 'value': 1}]}
        offer = direct_offer('b' * 64, 'one', 1500, agreed)
        commitment = digest(offer)
        context = mission_context(commitment, 276)
        artifact = {'text': content, 'context': context, 'parent_id': 'c' * 64}
        report = evidence(agreed, artifact['parent_id'], 1, commitment, digest(artifact), artifact)
        self.assertEqual(report['findings'][0]['status'], 'passed')
        self.assertEqual(report['findings'][1]['observed'], 2)
        self.assertFalse(report['all_checks_passed'])
        changed = {**offer, 'terms': {**agreed, 'cap_microusd': 277}}
        with self.assertRaises(ValueError):
            fixture_request({'input': direct_task_text('Brief', changed)}, context)

    def test_two_connections_cannot_reserve_the_same_remaining_budget(self):
        with closing(self.connect()) as db:
            adapter = self.adapter(db)
            for run in ('one', 'two'):
                self.approve(adapter, run)
        barrier = threading.Barrier(2)
        def worker(run):
            with closing(self.connect()) as conn:
                worker_adapter = self.adapter(conn)
                barrier.wait(5)
                try:
                    return worker_adapter.dispatch('owner-session', run)['mission_usage']['actual_microusd']
                except ProviderDenied:
                    return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(worker, ['one', 'two']), [44, 'denied'])
        self.assertEqual(len(self.transport.calls), 1)
        self.assertNotIn(self.commitment, self.transport.calls[0].decode())
        self.assertEqual(json.loads(self.transport.calls[0])['input'], 'Original fictional brief')

    def test_timeout_and_bad_usage_hold_funds_after_restart_and_cancel(self):
        for label, callback in [('timeout', lambda _: (_ for _ in ()).throw(TimeoutError())),
                                ('malformed', lambda _: (200, json.dumps({**response(), 'usage': {'output_tokens': True}}).encode()))]:
            with self.subTest(label=label):
                self.path = Path(self.temp.name) / (label + '.db')
                self.transport = FixtureTransport(callback)
                with closing(self.connect()) as db:
                    adapter = self.adapter(db)
                    self.approve(adapter, 'one')
                    with self.assertRaises(ProviderOutcomeUnknown):
                        adapter.dispatch('owner-session', 'one')
                with closing(self.connect()) as db:
                    adapter = self.adapter(db)
                    receipt = adapter.cancel('owner-session', 'one')['mission_usage']
                    self.assertIsNone(receipt['actual_microusd'])
                    self.assertEqual(receipt['held_microusd'], 276)
                    self.approve(adapter, 'two')
                    with self.assertRaises(ProviderDenied):
                        adapter.dispatch('owner-session', 'two')
                self.assertEqual(len(self.transport.calls), 1)

    def test_cap_substitution_and_live_flag_refused_before_review(self):
        with closing(self.connect()) as db:
            adapter = self.adapter(db, allow_live=True)
            with self.assertRaises(ProviderDenied):
                self.prepare(adapter, 'one')
            self.text = task_text('Original fictional brief', 277, self.commitment)
            with self.assertRaises(ProviderDenied):
                self.prepare(self.adapter(db), 'two')
            self.text = 'plain text'
            with self.assertRaises(ProviderDenied):
                self.prepare(self.adapter(db), 'three')
        self.assertFalse(self.transport.calls)
