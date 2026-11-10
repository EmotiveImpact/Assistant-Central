"""Fictional owner-authenticated source statements, never real consent fixtures."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.crypto import b64, fingerprint
from pilot.provider import ENDPOINT
from pilot.source_grants import (DOMAIN, MAX_BYTES, GrantDenied, GrantOutcomeUnknown,
    SourceGrantLedger, commitment, disclosure_plan, review_statement, sign_statement,
    statement, verify_statement)


class SourceGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.auths, self.sessions, self.publics, self.fps = {}, {}, {}, {}
        for name in ('alice', 'bob', 'executor', 'recipient'):
            auth = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            self.addCleanup(auth.close)
            auth.bootstrap(name, name + '-assistant', 'Fictional source password ' + name)
            self.auths[name] = auth
            self.sessions[name] = auth.login('Fictional source password ' + name)
            self.publics[name] = auth.public_identity()
            self.fps[name] = fingerprint(self.publics[name])
        self.db = sqlite3.connect(self.root / 'ledger.sqlite', isolation_level=None, check_same_thread=False)
        self.addCleanup(self.db.close)
        self.ledger = self.new_ledger(self.db)
        self.session = self.sessions['executor']
        self.payload = {'text': 'Fictional garden times: Alice Monday, Bob Tuesday.'}
        self.fragments = sorted([
            {'owner': self.fps['alice'], 'source_id': 'calendar-a', 'value': {'day': 'Monday'}},
            {'owner': self.fps['bob'], 'source_id': 'calendar-b', 'value': {'day': 'Tuesday'}}],
            key=lambda item: (item['owner'], item['source_id']))
        self.plan = {'operation_id': 'fictional-disclosure-1', 'context': commitment({'task': 'garden'}),
            'executor': self.fps['executor'], 'recipient': self.fps['recipient'],
            'purpose': 'Compare fictional garden availability', 'destination': None,
            'payload_digest': commitment(self.payload), 'sources': [
                {'owner': item['owner'], 'source_id': item['source_id'], 'revision': 1,
                 'scope': ['day'], 'data_digest': commitment(item['value'])} for item in self.fragments]}
        self.grants = {self.fps[name]: self.signed(name) for name in ('alice', 'bob')}

    def new_ledger(self, db, **kwargs):
        return SourceGrantLedger(db, self.auths['executor'], list(self.publics.values()), clock=lambda: self.now, **kwargs)

    def body(self, name, *, plan=None, revision=1, issued_at=1000, expires_at=1500):
        plan = copy.deepcopy(self.plan if plan is None else plan)
        return {'domain': DOMAIN, 'kind': 'grant', 'issuer': self.fps[name],
                'operation_id': plan['operation_id'], 'revision': revision,
                'issued_at': issued_at, 'expires_at': expires_at, 'plan': plan}

    def signed(self, name, **kwargs):
        body = self.body(name, **kwargs)
        return sign_statement(self.auths[name], self.sessions[name], body, review_statement(body)['review_digest'])

    def withdrawal(self, name, operation=None, issued_at=1000):
        body = {'domain': DOMAIN, 'kind': 'withdrawal', 'issuer': self.fps[name],
                'operation_id': operation or self.plan['operation_id'], 'issued_at': issued_at}
        return sign_statement(self.auths[name], self.sessions[name], body, review_statement(body)['review_digest'])

    def observe(self):
        for grant in self.grants.values():
            self.ledger.observe(self.session, grant)

    def consume(self, **kwargs):
        values = {'plan': self.plan, 'payload': self.payload, 'fragments': self.fragments, 'signed_grants': self.grants}
        values.update(kwargs)
        return self.ledger.consume(self.session, **values)

    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM source_grant_claims').fetchone()[0]

    def test_exact_two_owner_consumption_is_only_a_local_source_gate(self):
        self.observe()
        result = self.consume()
        self.assertTrue(result['consumed'])
        self.assertEqual(result['plan_digest'], commitment(self.plan))
        for field in ('retry_allowed', 'execution_approved', 'recipient_accepted', 'remote_revocation_known'):
            self.assertIs(result[field], False)
        self.assertEqual(self.count(), 1)

    def test_signature_verification_alone_grants_neither_observation_nor_use(self):
        grant = self.grants[self.fps['alice']]
        self.assertEqual(verify_statement(grant, self.publics['alice']), grant['statement'])
        with self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 0)

    def test_every_declared_owner_must_supply_current_signature(self):
        self.observe()
        for grants in ({}, {self.fps['alice']: self.grants[self.fps['alice']]},
                       {**self.grants, self.fps['recipient']: self.grants[self.fps['alice']]}):
            with self.subTest(grants=list(grants)), self.assertRaises(GrantDenied): self.consume(signed_grants=grants)
        self.assertEqual(self.count(), 0)

    def test_wrong_signing_key_and_signer_identity_fail(self):
        original = self.grants[self.fps['alice']]
        for name in ('bob', 'recipient'):
            with self.assertRaises(GrantDenied): verify_statement(original, self.publics[name])
        forged = copy.deepcopy(original)
        encoded = json.dumps(forged['statement'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        forged['signature'] = b64(self.auths['bob'].sign(self.sessions['bob'], DOMAIN.encode() + b'\n' + encoded))
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, forged)

    def test_sign_requires_exact_own_identity_review_and_current_session(self):
        body = self.body('alice')
        review = review_statement(body)['review_digest']
        for auth, session, digest in ((self.auths['bob'], self.sessions['bob'], review),
            (self.auths['alice'], self.sessions['bob'], review), (self.auths['alice'], self.sessions['alice'], '0' * 64)):
            with self.assertRaises(GrantDenied): sign_statement(auth, session, body, digest)
        self.auths['alice'].logout(self.sessions['alice'])
        with self.assertRaises(GrantDenied): sign_statement(self.auths['alice'], self.sessions['alice'], body, review)

    def test_no_none_stale_cross_owner_or_revoked_executor_session(self):
        self.observe()
        for session in (None, '', self.sessions['alice'], 'a' * 43):
            with self.assertRaises(GrantDenied): self.ledger.consume(session, self.plan, self.payload, self.fragments, self.grants)
            with self.assertRaises(GrantDenied): self.ledger.observe(session, self.withdrawal('alice'))
            with self.assertRaises(GrantDenied): self.ledger.cancel(session, self.plan['operation_id'])
        self.auths['executor'].revoke_all(self.session)
        with self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 0)

    def test_tampering_any_signed_field_is_detected(self):
        original = self.grants[self.fps['alice']]
        changes = [('revision', 2), ('expires_at', 1400), ('operation_id', 'other')]
        for field, value in changes:
            forged = copy.deepcopy(original); forged['statement'][field] = value
            with self.subTest(field=field), self.assertRaises(GrantDenied): verify_statement(forged, self.publics['alice'])
        forged = copy.deepcopy(original); forged['signature'] = forged['signature'][:-1] + '!'
        with self.assertRaises(GrantDenied): verify_statement(forged, self.publics['alice'])

    def test_domain_separation_refuses_other_owner_or_packet_signatures(self):
        grant = copy.deepcopy(self.grants[self.fps['alice']])
        encoded = json.dumps(grant['statement'], sort_keys=True, separators=(',', ':')).encode()
        grant['signature'] = b64(self.auths['alice'].sign(self.sessions['alice'], encoded))
        with self.assertRaises(GrantDenied): verify_statement(grant, self.publics['alice'])
        grant['statement']['domain'] = 'assistant-central-pilot-packet/1'
        with self.assertRaises(GrantDenied): verify_statement(grant, self.publics['alice'])

    def test_plan_context_recipient_purpose_source_revision_and_scope_are_exact(self):
        self.observe()
        plans = []
        for field, value in [('context', 'a' * 64), ('recipient', self.fps['alice']), ('purpose', 'Another purpose'),
                             ('executor', self.fps['bob']), ('operation_id', 'another-operation')]:
            plan = copy.deepcopy(self.plan); plan[field] = value; plans.append(plan)
        for field, value in [('revision', 2), ('scope', ['extra']), ('source_id', 'other-source')]:
            plan = copy.deepcopy(self.plan); plan['sources'][0][field] = value; plans.append(plan)
        for plan in plans:
            with self.subTest(plan=plan), self.assertRaises(GrantDenied): self.consume(plan=plan)
        self.assertEqual(self.count(), 0)

    def test_payload_and_each_source_fragment_must_match_exact_commitment(self):
        self.observe()
        with self.assertRaises(GrantDenied): self.consume(payload={**self.payload, 'extra': 'hidden'})
        fragments = copy.deepcopy(self.fragments); fragments[0]['value']['day'] = 'Wednesday'
        with self.assertRaises(GrantDenied): self.consume(fragments=fragments)
        with self.assertRaises(GrantDenied): self.consume(fragments=self.fragments[::-1])
        with self.assertRaises(GrantDenied): self.consume(fragments=self.fragments[:1])
        self.assertEqual(self.count(), 0)

    def test_provider_destination_model_and_budget_are_exact_not_activation(self):
        self.plan['recipient'] = self.fps['executor']
        self.plan['destination'] = {'provider': 'openai', 'endpoint': ENDPOINT,
                                    'model': 'synthetic-research-v1', 'max_output_tokens': 128}
        self.grants = {self.fps[name]: self.signed(name) for name in ('alice', 'bob')}
        self.observe()
        for field, value in [('provider', 'other'), ('endpoint', ENDPOINT + '/'),
                             ('model', 'different-model'), ('max_output_tokens', 256)]:
            plan = copy.deepcopy(self.plan); plan['destination'][field] = value
            with self.subTest(field=field), self.assertRaises(GrantDenied): self.consume(plan=plan)
        plan = copy.deepcopy(self.plan); plan['destination'] = None
        with self.assertRaises(GrantDenied): self.consume(plan=plan)
        self.assertFalse(self.consume()['execution_approved'])

    def test_expiry_and_future_timestamps_reject_without_claim(self):
        future = self.signed('alice', plan={**self.plan, 'operation_id': 'future-operation'}, issued_at=1001, expires_at=1500)
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, future)
        self.observe(); self.now = 1500
        with self.assertRaises(GrantDenied): self.consume()
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.grants[self.fps['alice']])
        self.assertEqual(self.count(), 0)

    def test_expiry_crossing_final_commit_rolls_back(self):
        self.observe()
        original = self.ledger._status
        def late(operation):
            result = original(operation); self.now = 1500; return result
        with patch.object(self.ledger, '_status', late), self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 0)

    def test_consumption_replay_survives_duplicate_observation_restart_and_new_revision(self):
        self.observe(); self.consume()
        self.observe()  # Receipt/import idempotence is deliberately not reusable authority.
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()
        for name in ('alice', 'bob'):
            self.grants[self.fps[name]] = self.signed(name, revision=2)
        self.observe()
        with self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 1)

    def test_observed_new_revision_fences_old_even_when_signature_is_valid(self):
        self.observe()
        newer = self.signed('alice', revision=2)
        self.ledger.observe(self.session, newer)
        with self.assertRaises(GrantDenied): self.consume()
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.grants[self.fps['alice']])
        self.grants[self.fps['alice']] = newer
        self.assertTrue(self.consume()['consumed'])

    def test_revision_equivocation_commits_permanent_fence_before_reporting_denial(self):
        self.observe()
        other_plan = copy.deepcopy(self.plan); other_plan['purpose'] = 'Conflicting purpose'
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', plan=other_plan))
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', revision=2))

    def test_withdrawal_before_grant_survives_restart_and_cannot_be_resurrected(self):
        self.ledger.observe(self.session, self.withdrawal('alice'))
        self.ledger = self.new_ledger(self.db)
        for revision in (1, 2, 99):
            with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', revision=revision))
        with self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.ledger.status(self.session, self.plan['operation_id'])['observed_withdrawals'], [self.fps['alice']])

    def test_delayed_withdrawal_never_expires_and_unknown_source_cannot_veto_others(self):
        self.observe(); self.now = 1400
        self.ledger.observe(self.session, self.withdrawal('alice', issued_at=1))
        with self.assertRaises(GrantDenied): self.consume()
        # Recipient owns no source in this plan; their source veto cannot impersonate Alice.
        self.ledger.observe(self.session, self.withdrawal('recipient'))
        self.assertIn(self.fps['alice'], self.ledger.status(self.session, self.plan['operation_id'])['observed_withdrawals'])

    def test_unobserved_remote_withdrawal_is_not_falsely_claimed_known(self):
        self.observe()
        withdrawal = self.withdrawal('alice')  # Not delivered/observed by this ledger.
        result = self.consume()
        self.assertFalse(result['remote_revocation_known'])
        self.ledger.observe(self.session, withdrawal)
        status = self.ledger.status(self.session, self.plan['operation_id'])
        self.assertTrue(status['consumed'])
        self.assertEqual(status['observed_withdrawals'], [self.fps['alice']])
        self.assertFalse(status['recipient_accepted'])

    def test_executor_cancellation_is_separate_terminal_local_veto(self):
        self.ledger.cancel(self.session, self.plan['operation_id'])
        self.ledger.cancel(self.session, self.plan['operation_id'])
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.observe()
        with self.assertRaises(GrantDenied): self.consume()
        status = self.ledger.status(self.session, self.plan['operation_id'])
        self.assertTrue(status['cancelled']); self.assertEqual(status['observed_withdrawals'], [])

    def test_pin_revocation_fences_source_recipient_and_executor_without_replacement(self):
        self.observe()
        for name in ('alice', 'recipient', 'executor'):
            with self.subTest(name=name):
                self.ledger.revoke_pin(self.session, self.fps[name])
                with self.assertRaises(GrantDenied): self.consume()
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()

    def test_changed_pin_configuration_or_capacity_reopen_fails_closed(self):
        with self.assertRaises(GrantDenied): self.new_ledger(self.db, max_records=999)
        pins = list(self.publics.values())[:-1]
        with self.assertRaises(GrantDenied): SourceGrantLedger(self.db, self.auths['executor'], pins, clock=lambda: self.now)
        with self.assertRaises(GrantDenied): SourceGrantLedger(sqlite3.connect(':memory:'), self.auths['executor'], [self.publics['alice']], clock=lambda: self.now)

    def test_same_signing_key_under_different_identity_labels_is_not_another_owner(self):
        alias = {**self.publics['alice'], 'owner_id': 'alias', 'agent_id': 'alias-agent'}
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        with self.assertRaises(GrantDenied): SourceGrantLedger(db, self.auths['executor'], [*self.publics.values(), alias])

    def test_unknown_fields_duplicate_sources_scopes_and_wrong_types_fail_closed(self):
        mutations = []
        plan = copy.deepcopy(self.plan); plan['unknown'] = True; mutations.append(plan)
        plan = copy.deepcopy(self.plan); plan['sources'].append(plan['sources'][0]); mutations.append(plan)
        for scope in ([], ['day', 'day'], ['*'], ['z', 'a'], [None]):
            plan = copy.deepcopy(self.plan); plan['sources'][0]['scope'] = scope; mutations.append(plan)
        for revision in (True, 0, -1, 1.0, '1'):
            plan = copy.deepcopy(self.plan); plan['sources'][0]['revision'] = revision; mutations.append(plan)
        for plan in mutations:
            with self.subTest(plan=plan), self.assertRaises(GrantDenied): disclosure_plan(plan)
        for field, value in [('expires_at', True), ('revision', 1.0), ('issued_at', 0), ('expires_at', 1601)]:
            body = self.body('alice'); body[field] = value
            with self.subTest(field=field), self.assertRaises(GrantDenied): statement(body)
        body = self.body('alice'); body['extra'] = 'ignored?'
        with self.assertRaises(GrantDenied): statement(body)

    def test_byte_nesting_nonfinite_and_unicode_bounds(self):
        for payload in ('x' * (MAX_BYTES + 1), '\ud800', float('nan'), float('inf'), 2**64, (1, 2)):
            with self.subTest(payload=type(payload)), self.assertRaises(GrantDenied): commitment(payload)
        nested = []
        for _ in range(10): nested = [nested]
        with self.assertRaises(GrantDenied): commitment(nested)
        plan = copy.deepcopy(self.plan); plan['purpose'] = 'é' * 600
        with self.assertRaises(GrantDenied): disclosure_plan(plan)
        plan = copy.deepcopy(self.plan); plan['sources'] *= 9
        with self.assertRaises(GrantDenied): disclosure_plan(plan)

    def test_detached_snapshots_do_not_mutate_review_or_signed_statements(self):
        body = self.body('alice')
        reviewed = review_statement(body)
        signed = sign_statement(self.auths['alice'], self.sessions['alice'], body, reviewed['review_digest'])
        body['plan']['purpose'] = 'mutated after signing'
        self.assertNotEqual(signed['statement']['plan']['purpose'], body['plan']['purpose'])
        self.assertEqual(signed['statement'], reviewed['review']['statement'])

    def test_no_source_text_prompt_scope_or_signed_payload_persists(self):
        self.observe(); self.consume()
        dump = '\n'.join(self.db.iterdump())
        for private in (self.plan['purpose'], self.payload['text'], 'calendar-a', 'calendar-b', 'Monday', 'Tuesday', 'signature', 'synthetic-research-v1'):
            self.assertNotIn(private, dump)

    def test_clock_rollback_is_rejected_across_reopen(self):
        self.observe(); self.now = 1100
        self.ledger.status(self.session, self.plan['operation_id'])
        self.now = 1050
        with self.assertRaises(GrantDenied): self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()

    def test_nested_transaction_is_never_silently_committed(self):
        self.observe(); self.db.execute('BEGIN IMMEDIATE')
        try:
            with self.assertRaises(GrantDenied): self.consume()
            self.assertTrue(self.db.in_transaction)
        finally: self.db.rollback()
        self.assertEqual(self.count(), 0)

    def test_database_failure_rolls_back_without_echoing_private_errors(self):
        self.observe()
        self.db.execute("CREATE TRIGGER deny_claim BEFORE INSERT ON source_grant_claims BEGIN SELECT RAISE(ABORT,'private fixture message'); END")
        with self.assertRaises(GrantOutcomeUnknown) as caught: self.consume()
        self.assertNotIn('private fixture', str(caught.exception))
        self.assertEqual(self.count(), 0)

    def test_lost_commit_ack_remains_consumed_and_never_retries(self):
        self.observe()
        original = self.ledger._transaction
        @contextmanager
        def lost(*args, **kwargs):
            with original(*args, **kwargs) as now: yield now
            raise GrantOutcomeUnknown('Synthetic lost commit acknowledgement')
        with patch.object(self.ledger, '_transaction', lost), self.assertRaises(GrantOutcomeUnknown): self.consume()
        self.assertTrue(self.ledger.status(self.session, self.plan['operation_id'])['consumed'])
        with self.assertRaises(GrantDenied): self.consume()

    def test_competing_connections_can_consume_only_once(self):
        self.observe()
        db2 = sqlite3.connect(self.root / 'ledger.sqlite', isolation_level=None, check_same_thread=False)
        self.addCleanup(db2.close)
        ledger2 = self.new_ledger(db2)
        outcomes = []
        def consume(ledger):
            try: outcomes.append(ledger.consume(self.session, self.plan, self.payload, self.fragments, self.grants)['consumed'])
            except GrantDenied: outcomes.append(False)
        threads = [threading.Thread(target=consume, args=(ledger,)) for ledger in (self.ledger, ledger2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10); self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(outcomes), [False, True]); self.assertEqual(self.count(), 1)

    def test_observation_limit_does_not_evict_old_replay_or_withdrawal_history(self):
        db = sqlite3.connect(':memory:', isolation_level=None); self.addCleanup(db.close)
        ledger = self.new_ledger(db, max_records=2)
        for grant in self.grants.values(): ledger.observe(self.session, grant)
        plan = {**self.plan, 'operation_id': 'another-operation'}
        with self.assertRaises(GrantDenied): ledger.observe(self.session, self.signed('alice', plan=plan))
        ledger.observe(self.session, self.withdrawal('alice'))
        with self.assertRaises(GrantDenied): ledger.consume(self.session, self.plan, self.payload, self.fragments, self.grants)

    def test_withdrawal_capacity_failure_permanently_fences_all_consumption(self):
        db = sqlite3.connect(':memory:', isolation_level=None); self.addCleanup(db.close)
        ledger = self.new_ledger(db, max_records=2)
        for grant in self.grants.values(): ledger.observe(self.session, grant)
        for operation in ('unused-1', 'unused-2'):
            ledger.observe(self.session, self.withdrawal('bob', operation=operation))
        result = ledger.observe(self.session, self.withdrawal('alice'))
        self.assertEqual(result['state'], 'ledger-fenced')
        ledger = self.new_ledger(db, max_records=2)
        self.assertTrue(ledger.status(self.session, self.plan['operation_id'])['ledger_fenced'])
        with self.assertRaises(GrantDenied): ledger.consume(self.session, self.plan, self.payload, self.fragments, self.grants)

    def test_cancellation_capacity_failure_also_fences_instead_of_forgetting_veto(self):
        db = sqlite3.connect(':memory:', isolation_level=None); self.addCleanup(db.close)
        ledger = self.new_ledger(db, max_records=2)
        for grant in self.grants.values(): ledger.observe(self.session, grant)
        for operation in ('unused-1', 'unused-2'): ledger.cancel(self.session, operation)
        result = ledger.cancel(self.session, self.plan['operation_id'])
        self.assertTrue(result['ledger_fenced'])
        with self.assertRaises(GrantDenied): ledger.consume(self.session, self.plan, self.payload, self.fragments, self.grants)

    def test_foreign_executor_grant_cannot_be_imported(self):
        plan = {**self.plan, 'executor': self.fps['bob']}
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', plan=plan))

    def test_unknown_recipient_is_not_enrolled_by_a_signed_grant(self):
        plan = {**self.plan, 'recipient': 'a' * 64}
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', plan=plan))

    def test_wrong_operation_withdrawal_does_not_cancel_another_operation(self):
        self.observe()
        self.ledger.observe(self.session, self.withdrawal('alice', operation='other-operation'))
        self.assertTrue(self.consume()['consumed'])

    def test_recipient_source_veto_is_not_executor_cancellation(self):
        self.observe()
        self.ledger.observe(self.session, self.withdrawal('recipient'))
        self.assertTrue(self.consume()['consumed'])
        self.assertFalse(self.ledger.status(self.session, self.plan['operation_id'])['cancelled'])

    def test_future_withdrawal_and_unknown_fields_never_erase_current_observation(self):
        self.observe()
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.withdrawal('alice', issued_at=1001))
        signed = self.withdrawal('alice'); signed['statement']['expires_at'] = 1100
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, signed)
        self.assertTrue(self.consume()['consumed'])

    def test_withdrawal_after_consumption_retains_history_without_claiming_recall(self):
        self.observe(); self.consume()
        self.ledger.observe(self.session, self.withdrawal('bob'))
        result = self.ledger.cancel(self.session, self.plan['operation_id'])
        self.assertTrue(result['consumed']); self.assertTrue(result['cancelled'])
        self.assertEqual(result['observed_withdrawals'], [self.fps['bob']])
        self.assertFalse(result['remote_revocation_known'])

    def test_future_higher_revision_fences_old_without_early_use(self):
        self.observe()
        future = self.signed('alice', revision=2, issued_at=1100, expires_at=1400)
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, future)
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()
        self.grants[self.fps['alice']] = future
        with self.assertRaises(GrantDenied): self.consume()
        self.now = 1100
        self.assertTrue(self.consume()['consumed'])

    def test_ineligible_same_revision_equivocation_still_fences_the_operation(self):
        self.observe()
        other_plan = {**self.plan, 'executor': self.fps['bob']}
        with self.assertRaises(GrantDenied): self.ledger.observe(self.session, self.signed('alice', plan=other_plan))
        self.ledger = self.new_ledger(self.db)
        with self.assertRaises(GrantDenied): self.consume()

    def test_auth_session_expiring_at_commit_never_consumes(self):
        self.observe()
        original = self.ledger._status
        def expire(operation):
            result = original(operation); self.now = 5000; return result
        with patch.object(self.ledger, '_status', expire), self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 0)

    def test_local_cancel_after_other_connection_claim_preserves_both_facts(self):
        self.observe()
        db2 = sqlite3.connect(self.root / 'ledger.sqlite', isolation_level=None)
        self.addCleanup(db2.close)
        ledger2 = self.new_ledger(db2)
        self.consume()
        cancelled = ledger2.cancel(self.session, self.plan['operation_id'])
        self.assertTrue(cancelled['cancelled']); self.assertTrue(cancelled['consumed'])
        with self.assertRaises(GrantDenied): self.consume()

    def test_withdrawal_observed_on_other_connection_fences_pending_consume(self):
        self.observe()
        db2 = sqlite3.connect(self.root / 'ledger.sqlite', isolation_level=None)
        self.addCleanup(db2.close)
        ledger2 = self.new_ledger(db2)
        ledger2.observe(self.session, self.withdrawal('alice'))
        with self.assertRaises(GrantDenied): self.consume()
        self.assertEqual(self.count(), 0)


if __name__ == '__main__':
    unittest.main()
