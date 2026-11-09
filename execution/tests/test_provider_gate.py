import dataclasses
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied, digest
from execution.ledger import ExecutionLedger
from execution.provider_gate import ProviderGate, ProviderRoute, ProviderRelease


def plan():
    return TeamPlan("provider-tests", "lead", (
        AgentRef("lead", "alice", "synthetic-a", "coordination"),
        AgentRef("researcher", "bob", "synthetic-b", "research"),
        AgentRef("expert", "dana", "synthetic-d", "research"),
        AgentRef("writer", "carol", "synthetic-c", "copy"),
        AgentRef("sibling", "carol", "synthetic-c", "copy"),
    ), (
        TaskSpec("research", "researcher", "Research fictional plants", "research"),
        TaskSpec("analysis", "expert", "Analyze fictional weather", "research"),
        TaskSpec("copy", "writer", "CAROL TASK TEXT", "copy", ("research", "analysis")),
    ))


ROUTE = ProviderRoute("synthetic-c", "fictional-account", "fixture-model", "Local fixture only; no retention promise")


class ProviderGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "team.sqlite"
        self.now = 1000
        self.open()
        self.w.accept_lead("alice", expected_context=self.w.context)

    def open(self):
        self.w = TeamWorkflow(self.path, plan(), clock=lambda: self.now)
        self.ledger = ExecutionLedger(self.w)
        self.gate = ProviderGate(self.ledger)
        self.writer = self.gate.facade("writer")

    def reopen(self):
        self.w.close()
        self.open()

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def start(self, task, scope=None):
        actor = self.w.tasks[task].assignee
        facade = self.w.facade(actor)
        request = facade.propose_start(task, "start-" + task)
        if scope is None:
            self.w.decide_start(self.w.agents[actor].owner, request["request_id"],
                                request["review_digest"], "approve", expires=self.now + 100,
                                expected_context=self.w.context)
        facade.start(request["request_id"], scope)

    def disclose(self, owner, artifact, recipient, task=None):
        review = self.w.disclosure_review(owner, artifact, recipient, task, expected_context=self.w.context)
        self.w.approve_disclosure(owner, artifact, recipient, review["review_digest"], task,
                                  expected_context=self.w.context)

    def prepare(self, scope=None):
        for task, owner, actor, text in (("research", "bob", "researcher", "BOB DATA"),
                                          ("analysis", "dana", "expert", "DANA DATA")):
            self.start(task)
            artifact = task + "-out"
            self.w.facade(actor).submit(task, artifact, text)
            self.disclose(owner, artifact, "lead")
            self.w.facade("lead").review_output(task, artifact, "accept")
            self.disclose(owner, artifact, "writer", "copy")
        self.start("copy", scope)
        self.ledger.facade("writer").prepare("copy", "run-copy", "copy-out")
        return self.writer.propose("run-copy", ROUTE)

    def approve(self, owner, expires=1100):
        review = self.gate.owner_review(owner, "run-copy", expected_context=self.w.context)
        return self.gate.decide(owner, "run-copy", review["review_digest"], "approve",
                               expected_context=self.w.context, expires=expires)

    def approve_all(self):
        for owner in ("bob", "carol", "dana"):
            self.approve(owner)

    def granted(self):
        self.prepare()
        self.approve_all()

    def assert_no_release(self):
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.assertEqual(self.writer.status("run-copy")["state"], "pending")
        self.assertEqual(self.ledger.facade("writer").status("run-copy")["state"], "prepared")

    def test_exact_types_context_and_agent_required(self):
        with self.assertRaises(Denied):
            ProviderGate(object())
        with self.assertRaises(Denied):
            self.gate.facade("unknown")
        self.prepare()
        with self.assertRaises(Denied):
            self.writer.propose("run-copy", ROUTE.to_dict())
        with self.assertRaises(Denied):
            self.gate.owner_review("carol", "run-copy", expected_context="other-context")

    def test_route_is_immutable_bounded_and_copied(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ROUTE.account_ref = "changed"
        for changes in ({"provider": ""}, {"account_ref": "../account"}, {"model_ref": "m" * 129},
                        {"data_policy": "\ud800"}, {"provider": True}):
            with self.subTest(changes=changes), self.assertRaises(Denied):
                dataclasses.replace(ROUTE, **changes)
        copied = ROUTE.to_dict()
        copied["account_ref"] = "other"
        self.assertEqual(ROUTE.account_ref, "fictional-account")

    def test_requires_a_prepared_started_execution(self):
        with self.assertRaises(Denied):
            self.writer.propose("run-copy", ROUTE)
        self.start("research")
        self.ledger.facade("researcher").prepare("research", "run-research", "out")
        with self.assertRaises(Denied):
            self.gate.facade("researcher").propose("run-research", ROUTE)

    def test_only_task_owner_needed_without_inputs(self):
        self.start("research")
        self.ledger.facade("researcher").prepare("research", "run-research", "out")
        facade = self.gate.facade("researcher")
        request = facade.propose("run-research", dataclasses.replace(ROUTE, provider="synthetic-b"))
        self.assertEqual([d["owner"] for d in request["decisions"]], ["bob"])
        review = self.gate.owner_review("bob", "run-research", expected_context=self.w.context)
        self.gate.decide("bob", "run-research", review["review_digest"], "approve",
                         expected_context=self.w.context, expires=1100)
        self.assertEqual(facade.release("run-research").to_dict()["payload"]["inputs"], [])

    def test_team_start_and_disclosures_do_not_authorize_provider(self):
        result = self.prepare()
        self.assertEqual([d["owner"] for d in result["decisions"]], ["bob", "carol", "dana"])
        self.assert_no_release()

    def test_task_owner_cannot_approve_input_owners_data(self):
        self.prepare()
        self.approve("carol")
        self.assert_no_release()
        self.approve("bob")
        self.assert_no_release()
        self.approve("dana")
        self.writer.release("run-copy")

    def test_owner_previews_do_not_expose_other_owners_data(self):
        self.prepare()
        for owner, own, forbidden in (("bob", "BOB DATA", ("DANA DATA", "CAROL TASK TEXT")),
                                      ("dana", "DANA DATA", ("BOB DATA", "CAROL TASK TEXT")),
                                      ("carol", "CAROL TASK TEXT", ("BOB DATA", "DANA DATA"))):
            review = self.gate.owner_review(owner, "run-copy", expected_context=self.w.context)
            text = json.dumps(review)
            self.assertIn(own, text)
            for content in forbidden:
                self.assertNotIn(content, text)
            self.assertEqual(review["review_digest"], digest(review["review"]))
            self.assertFalse(review["review"]["live_provider_permission"])
            self.assertEqual(review["review"]["common_metadata"]["recipient"], ROUTE.to_dict())
        with self.assertRaises(Denied):
            self.gate.owner_review("alice", "run-copy", expected_context=self.w.context)

    def test_cross_owner_review_digest_cannot_approve(self):
        self.prepare()
        review = self.gate.owner_review("bob", "run-copy", expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.gate.decide("carol", "run-copy", review["review_digest"], "approve",
                             expected_context=self.w.context, expires=1100)
        with self.assertRaises(Denied):
            self.gate.decide("alice", "run-copy", review["review_digest"], "approve",
                             expected_context=self.w.context, expires=1100)

    def test_same_owner_sibling_and_lead_have_no_facade_access(self):
        self.granted()
        for actor in ("sibling", "lead", "researcher", "expert"):
            facade = self.gate.facade(actor)
            for call in (lambda: facade.status("run-copy"), lambda: facade.release("run-copy"),
                         lambda: facade.propose("run-copy", ROUTE),
                         lambda: facade.record_result("run-copy", "x", "result")):
                with self.subTest(actor=actor), self.assertRaises(Denied):
                    call()
        self.writer.release("run-copy")

    def test_route_policy_account_and_model_changes_cannot_replace_request(self):
        first = self.prepare()
        for field, value in (("provider", "other"), ("account_ref", "other-account"),
                             ("model_ref", "other-model"), ("data_policy", "different terms")):
            with self.subTest(field=field), self.assertRaises(Denied):
                self.writer.propose("run-copy", dataclasses.replace(ROUTE, **{field: value}))
        self.assertEqual(first, self.writer.propose("run-copy", ROUTE))

    def test_exact_proposal_retry_is_metadata_only_even_after_release(self):
        self.granted()
        self.writer.release("run-copy")
        self.reopen()
        status = self.writer.propose("run-copy", ROUTE)
        self.assertEqual(status["state"], "released")
        self.assertFalse(status["retry_allowed"])
        for text in ("BOB DATA", "DANA DATA", "CAROL TASK TEXT", ROUTE.data_policy):
            self.assertNotIn(text, json.dumps(status))

    def test_approval_cannot_be_renewed_or_extended(self):
        self.prepare()
        self.approve("carol")
        with self.assertRaises(Denied):
            self.approve("carol", expires=1200)
        self.now = 1100
        with self.assertRaises(Denied):
            self.approve("carol", expires=1200)
        self.assert_no_release()

    def test_expiry_limits_are_finite_and_one_hour(self):
        self.prepare()
        for expires in (None, True, float("inf"), float("nan"), 1000, 4601):
            with self.subTest(expires=expires), self.assertRaises(Denied):
                self.approve("carol", expires)
        self.approve("carol", 4600)

    def test_any_expired_approval_blocks_release_at_exact_boundary(self):
        self.granted()
        self.now = 1100
        self.assert_no_release()
        self.assertEqual({d["state"] for d in self.writer.status("run-copy")["decisions"]}, {"expired"})
        self.assertEqual(self.gate.owner_review("bob", "run-copy", expected_context=self.w.context)["state"], "expired")

    def test_invalid_clock_blocks_release(self):
        self.granted()
        self.now = float("nan")
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.now = 1000
        self.writer.release("run-copy")

    def test_refusal_is_terminal_and_cannot_be_aliased(self):
        self.prepare()
        review = self.gate.owner_review("bob", "run-copy", expected_context=self.w.context)
        self.gate.decide("bob", "run-copy", review["review_digest"], "refuse", expected_context=self.w.context)
        self.approve("carol")
        self.approve("dana")
        self.assert_no_release()
        self.writer.propose("run-copy", ROUTE)
        with self.assertRaises(Denied):
            self.approve("bob")
        with self.assertRaises(Denied):
            self.ledger.facade("writer").prepare("copy", "new-run", "new-out")

    def test_revocation_before_approval_and_after_approval_is_terminal(self):
        self.prepare()
        self.gate.revoke("bob", "run-copy", expected_context=self.w.context)
        self.approve("carol")
        self.gate.revoke("carol", "run-copy", expected_context=self.w.context)
        self.approve("dana")
        self.assert_no_release()
        for owner in ("bob", "carol"):
            with self.assertRaises(Denied):
                self.approve(owner)

    def test_only_participating_owner_can_revoke(self):
        self.granted()
        with self.assertRaises(Denied):
            self.gate.revoke("alice", "run-copy", expected_context=self.w.context)
        self.writer.release("run-copy")

    def test_release_commits_both_fences_and_exact_payload_once(self):
        self.granted()
        release = self.writer.release("run-copy")
        self.assertIs(type(release), ProviderRelease)
        body = release.to_dict()
        self.assertEqual(release.digest, digest(body))
        self.assertEqual(body["payload"]["recipient"], ROUTE.to_dict())
        self.assertEqual(body["payload"]["task_text"], "CAROL TASK TEXT")
        self.assertEqual(body["payload"]["inputs"], [
            {"artifact_id": "research-out", "content": "BOB DATA"},
            {"artifact_id": "analysis-out", "content": "DANA DATA"}])
        self.assertTrue(body["payload"]["synthetic_only"])
        self.assertFalse(body["payload"]["external_actions_allowed"])
        self.assertEqual(body["payload"]["tool_permissions"], [])
        self.assertEqual(body["payload"]["spend_limit"], 0)
        self.assertEqual(self.writer.status("run-copy")["execution"]["state"], "uncertain")
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        with self.assertRaises(Denied):
            self.ledger.facade("writer").claim("run-copy")

    def test_release_is_immutable_and_decoded_views_are_copies(self):
        self.granted()
        release = self.writer.release("run-copy")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            release.body = "changed"
        body = release.to_dict()
        body["payload"]["inputs"].clear()
        self.assertEqual(len(release.to_dict()["payload"]["inputs"]), 2)

    def test_previews_do_not_count_as_agent_reads_release_counts_once(self):
        self.granted()
        def counts():
            return [r[0] for r in self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:copy'")]
        self.assertEqual(counts(), [0, 0])
        self.writer.release("run-copy")
        self.assertEqual(counts(), [1, 1])
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.assertEqual(counts(), [1, 1])

    def test_restart_prepared_release_and_lost_receipt_never_redispatch(self):
        self.granted()
        self.reopen()
        release = self.writer.release("run-copy")
        self.reopen()
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.writer.record_result("run-copy", release.digest, "ORIGINAL SYNTHETIC RESULT")
        self.reopen()
        status = self.writer.record_result("run-copy", release.digest, "ORIGINAL SYNTHETIC RESULT")
        self.assertEqual(status["state"], "result_recorded")
        with self.assertRaises(Denied):
            self.writer.record_result("run-copy", release.digest, "CHANGED RESULT")

    def test_result_must_match_original_release(self):
        self.granted()
        with self.assertRaises(Denied):
            self.writer.record_result("run-copy", "0" * 64, "result")
        release = self.writer.release("run-copy")
        for wrong in (None, True, "0" * 64, release.to_dict()["claim_digest"]):
            with self.subTest(wrong=wrong), self.assertRaises(Denied):
                self.writer.record_result("run-copy", wrong, "result")

    def test_revocation_after_release_preserves_uncertainty_and_original_receipt(self):
        self.granted()
        release = self.writer.release("run-copy")
        status = self.gate.revoke("bob", "run-copy", expected_context=self.w.context)
        self.assertEqual(status["state"], "released")
        self.assertEqual(status["execution"]["state"], "uncertain")
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.writer.record_result("run-copy", release.digest, "LATE RESULT")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts WHERE id='copy-out'").fetchone()[0], 0)

    def test_source_disclosure_withdrawal_blocks_release(self):
        self.granted()
        self.w.revoke_disclosure("bob", "research-out", "writer", "copy", expected_context=self.w.context)
        self.assert_no_release()

    def test_task_revocation_blocks_release(self):
        self.granted()
        self.w.revoke_task("carol", "copy", expected_context=self.w.context)
        self.assert_no_release()

    def test_source_task_revocation_blocks_release(self):
        self.granted()
        self.w.revoke_task("dana", "analysis", expected_context=self.w.context)
        self.assert_no_release()

    def test_lead_withdrawal_blocks_release(self):
        self.granted()
        self.w.withdraw_lead("alice", expected_context=self.w.context)
        self.assert_no_release()

    def test_scope_revocation_blocks_release(self):
        self.w.grant_scope("carol", "scope", ("copy",), max_uses=1, expires=1100, expected_context=self.w.context)
        self.prepare(scope="scope")
        self.approve_all()
        self.w.revoke_scope("carol", "scope", expected_context=self.w.context)
        self.assert_no_release()

    def test_local_ledger_claim_cannot_be_repackaged_as_provider_release(self):
        self.granted()
        self.ledger.facade("writer").claim("run-copy")
        with self.assertRaises(Denied):
            self.writer.release("run-copy")
        self.assertEqual(self.writer.status("run-copy")["state"], "pending")

    def test_failure_after_claim_rolls_back_both_fences_and_read_counters(self):
        self.granted()
        original = self.w._event
        def fail(event, **data):
            if event == "provider_payload_released_locally":
                raise RuntimeError("simulated failed transaction")
            return original(event, **data)
        with patch.object(self.w, "_event", fail), self.assertRaises(RuntimeError):
            self.writer.release("run-copy")
        self.assertEqual(self.writer.status("run-copy")["state"], "pending")
        self.assertEqual(self.writer.status("run-copy")["execution"]["state"], "prepared")
        self.assertEqual([r[0] for r in self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:copy'")], [0, 0])
        self.writer.release("run-copy")

    def test_status_and_audit_contain_no_raw_inputs_routes_or_results(self):
        self.granted()
        release = self.writer.release("run-copy")
        self.writer.record_result("run-copy", release.digest, "RESULT BODY")
        texts = [json.dumps(self.writer.status("run-copy")),
                 json.dumps([dict(r) for r in self.w.db.execute("SELECT * FROM audit")])]
        for text in texts:
            for content in ("BOB DATA", "DANA DATA", "CAROL TASK TEXT", "RESULT BODY", ROUTE.data_policy):
                self.assertNotIn(content, text)

    def test_output_still_needs_separate_disclosure_and_lead_acceptance(self):
        self.granted()
        release = self.writer.release("run-copy")
        self.writer.record_result("run-copy", release.digest, "COPY RESULT")
        self.ledger.facade("writer").publish("run-copy")
        with self.assertRaises(Denied):
            self.w.facade("lead").review_output("copy", "copy-out", "accept")
        self.disclose("carol", "copy-out", "lead")
        self.w.facade("lead").review_output("copy", "copy-out", "accept")
        self.assertEqual(self.writer.status("run-copy")["execution"]["task_state"], "completed")

    def test_schema_version_mismatch_is_rejected(self):
        self.w.db.execute("UPDATE provider_meta SET version='different'")
        with self.assertRaises(Denied):
            ProviderGate(self.ledger)

    def test_claim_composition_requires_transaction(self):
        self.prepare()
        with self.assertRaises(Denied):
            self.ledger._claim_locked("writer", "run-copy")


if __name__ == "__main__":
    unittest.main()
