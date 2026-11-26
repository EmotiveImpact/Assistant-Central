import dataclasses
import json
from pathlib import Path
import tempfile
import unittest

from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied, canonical, digest
from execution.ledger import ExecutionLedger
from execution.provider_gate import ProviderGate, ProviderRoute, VERSION
from execution.lineage import collect_lineage


def plan():
    return TeamPlan("lineage-tests", "lead", (
        AgentRef("lead", "alice", "fixture-a", "coordination"),
        AgentRef("researcher", "bob", "fixture-b", "research"),
        AgentRef("writer", "carol", "fixture-c", "copy"),
        AgentRef("designer", "dana", "fixture-d", "slides"),
        AgentRef("editor", "erin", "fixture-e", "copy"),
    ), (
        TaskSpec("research", "researcher", "BOB SOURCE OBJECTIVE", "research"),
        TaskSpec("copy", "writer", "CAROL SOURCE OBJECTIVE", "copy", ("research",)),
        TaskSpec("slides", "designer", "DANA SOURCE OBJECTIVE", "slides", ("research",)),
        TaskSpec("final", "editor", "ERIN FINAL OBJECTIVE", "copy", ("copy", "slides")),
    ))


ROUTE = ProviderRoute("fixture-e", "fictional-account", "fixture-model", "Synthetic local-only data policy")


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lineage.sqlite"
        self.now = 1000
        self.open()
        self.w.accept_lead("alice", expected_context=self.w.context)
        self.finish("research", "BOB ORIGINAL SOURCE")
        self.disclose("research-out", "writer", "copy")
        self.disclose("research-out", "designer", "slides")
        self.finish("copy", "CAROL DERIVED TEXT")
        self.finish("slides", "DANA DERIVED TEXT")
        self.disclose("copy-out", "editor", "final")
        self.disclose("slides-out", "editor", "final")
        self.start("final")
        self.ledger.facade("editor").prepare("final", "run-final", "final-out")

    def open(self):
        self.w = TeamWorkflow(self.path, plan(), clock=lambda: self.now)
        self.ledger = ExecutionLedger(self.w)
        self.gate = ProviderGate(self.ledger)
        self.worker = self.gate.facade("editor")

    def reopen(self):
        self.w.close()
        self.open()

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def start(self, task):
        actor = self.w.tasks[task].assignee
        request = self.w.facade(actor).propose_start(task, "start-" + task)
        self.w.decide_start(self.w.agents[actor].owner, request["request_id"], request["review_digest"],
                            "approve", expected_context=self.w.context, expires=1100)
        self.w.facade(actor).start(request["request_id"])

    def disclose(self, artifact, recipient, task=None):
        owner = self.w.agents[self.w._artifact(artifact)["producer"]].owner
        review = self.w.disclosure_review(owner, artifact, recipient, task, expected_context=self.w.context)
        self.w.approve_disclosure(owner, artifact, recipient, review["review_digest"], task,
                                  expected_context=self.w.context)

    def finish(self, task, content):
        self.start(task)
        self.w.facade(self.w.tasks[task].assignee).submit(task, task + "-out", content)
        self.disclose(task + "-out", "lead")
        self.w.facade("lead").review_output(task, task + "-out", "accept")

    def propose(self):
        return self.worker.propose("run-final", ROUTE)

    def review(self, owner):
        return self.gate.owner_review(owner, "run-final", expected_context=self.w.context)

    def approve(self, owner):
        self.gate.decide(owner, "run-final", self.review(owner)["review_digest"], "approve",
                         expected_context=self.w.context, expires=1100)

    def granted(self):
        self.propose()
        for owner in ("bob", "carol", "dana", "erin"):
            self.approve(owner)

    def stored(self):
        return json.loads(self.w.db.execute("SELECT body FROM provider_requests WHERE run_id='run-final'").fetchone()[0])

    def assert_no_release(self):
        with self.assertRaises(Denied):
            self.worker.release("run-final")
        self.assertEqual(self.worker.status("run-final")["state"], "pending")
        self.assertEqual(self.worker.status("run-final")["execution"]["state"], "prepared")

    def test_ancestor_owner_is_required_through_both_derived_paths(self):
        result = self.propose()
        self.assertEqual([d["owner"] for d in result["decisions"]], ["bob", "carol", "dana", "erin"])
        for owner in ("carol", "dana", "erin"):
            self.approve(owner)
        self.assert_no_release()
        self.approve("bob")
        self.worker.release("run-final")

    def test_diamond_ancestry_is_deduplicated_and_exact(self):
        self.propose()
        lineage = self.stored()["lineage"]
        nodes = {node["artifact_id"]: node for node in lineage["artifacts"]}
        self.assertEqual(set(nodes), {"research-out", "copy-out", "slides-out"})
        self.assertEqual([root["artifact_id"] for root in lineage["roots"]], ["copy-out", "slides-out"])
        self.assertEqual(nodes["copy-out"]["parents"], nodes["slides-out"]["parents"])
        self.assertEqual(nodes["research-out"]["parents"], [])
        self.assertEqual(nodes["research-out"]["digest"], self.w._artifact("research-out")["digest"])
        self.assertEqual(self.review("bob")["review"]["lineage_digest"], digest(lineage))

    def test_upstream_owner_sees_own_original_not_foreign_derived_text(self):
        self.propose()
        review = self.review("bob")["review"]
        encoded = json.dumps(review)
        self.assertIn("BOB ORIGINAL SOURCE", encoded)
        for other in ("CAROL DERIVED TEXT", "DANA DERIVED TEXT", "ERIN FINAL OBJECTIVE",
                      "CAROL SOURCE OBJECTIVE", "DANA SOURCE OBJECTIVE"):
            self.assertNotIn(other, encoded)
        self.assertEqual(review["owned_data"], {"inputs": []})
        self.assertFalse(review["upstream_source_data_is_extra_payload"])
        self.assertFalse(review["other_owners_derived_text_is_shown"])
        self.assertEqual(review["affected_payload_inputs"], [
            {"artifact_id": "copy-out", "digest": self.w._artifact("copy-out")["digest"], "owner_source_ids": ["research-out"]},
            {"artifact_id": "slides-out", "digest": self.w._artifact("slides-out")["digest"], "owner_source_ids": ["research-out"]},
        ])

    def test_each_other_owner_preview_remains_scoped(self):
        self.propose()
        for owner, own, forbidden in (("carol", "CAROL DERIVED TEXT", ("BOB ORIGINAL SOURCE", "DANA DERIVED TEXT", "ERIN FINAL OBJECTIVE")),
                                      ("dana", "DANA DERIVED TEXT", ("BOB ORIGINAL SOURCE", "CAROL DERIVED TEXT", "ERIN FINAL OBJECTIVE")),
                                      ("erin", "ERIN FINAL OBJECTIVE", ("BOB ORIGINAL SOURCE", "CAROL DERIVED TEXT", "DANA DERIVED TEXT"))):
            text = json.dumps(self.review(owner))
            self.assertIn(own, text)
            for value in forbidden:
                self.assertNotIn(value, text)
        with self.assertRaises(Denied):
            self.review("alice")

    def test_upstream_content_is_not_added_to_provider_payload(self):
        self.granted()
        release = self.worker.release("run-final").to_dict()
        self.assertEqual(release["payload"]["inputs"], [
            {"artifact_id": "copy-out", "content": "CAROL DERIVED TEXT"},
            {"artifact_id": "slides-out", "content": "DANA DERIVED TEXT"}])
        self.assertNotIn("BOB ORIGINAL SOURCE", json.dumps(release))
        self.assertNotIn("lineage", release)

    def test_completed_descendant_cannot_hide_revoked_source_task(self):
        self.granted()
        self.w.revoke_task("bob", "research", expected_context=self.w.context)
        self.assertEqual(self.w._row("copy")["state"], "completed")
        self.assertEqual(self.w._row("slides")["state"], "completed")
        self.assertEqual(self.w._row("final")["state"], "running")
        self.assert_no_release()

    def test_withdrawn_historical_input_edge_blocks_new_onward_release(self):
        self.granted()
        self.w.revoke_disclosure("bob", "research-out", "writer", "copy", expected_context=self.w.context)
        self.assertEqual(self.w._row("copy")["state"], "completed")
        self.assertEqual(self.w._row("final")["state"], "running")
        self.assert_no_release()

    def test_invalid_ancestry_blocks_proposal_and_does_not_create_decisions(self):
        self.w.revoke_disclosure("bob", "research-out", "designer", "slides", expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.propose()
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM provider_requests").fetchone()[0], 0)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM provider_decisions").fetchone()[0], 0)

    def test_upstream_approval_cannot_be_spoofed_by_other_owner_digest(self):
        self.propose()
        with self.assertRaises(Denied):
            self.gate.decide("bob", "run-final", self.review("carol")["review_digest"], "approve",
                             expected_context=self.w.context, expires=1100)
        self.assertEqual(self.review("bob")["state"], "pending")

    def test_upstream_refusal_remains_terminal_after_reopen(self):
        self.propose()
        self.gate.decide("bob", "run-final", self.review("bob")["review_digest"], "refuse", expected_context=self.w.context)
        self.reopen()
        self.propose()
        for owner in ("carol", "dana", "erin"):
            self.approve(owner)
        with self.assertRaises(Denied):
            self.approve("bob")
        self.assert_no_release()

    def test_upstream_provider_revocation_and_expiry_are_enforced(self):
        self.granted()
        self.gate.revoke("bob", "run-final", expected_context=self.w.context)
        self.assert_no_release()
        self.now = 1100
        self.assert_no_release()
        self.assertEqual(self.review("bob")["state"], "revoked")

    def test_previewing_ancestry_does_not_increment_historical_reads(self):
        before = [dict(row) for row in self.w.db.execute("SELECT * FROM disclosures ORDER BY artifact_id,recipient,purpose")]
        self.granted()
        after = [dict(row) for row in self.w.db.execute("SELECT * FROM disclosures ORDER BY artifact_id,recipient,purpose")]
        self.assertEqual(before, after)
        self.worker.release("run-final")
        self.assertEqual([row[0] for row in self.w.db.execute("SELECT reads FROM disclosures WHERE artifact_id='research-out' AND purpose!='lead-review'")], [0, 0])
        self.assertEqual([row[0] for row in self.w.db.execute("SELECT reads FROM disclosures WHERE purpose='task:final'")], [1, 1])

    def test_missing_upstream_artifact_is_rejected(self):
        self.granted()
        self.w.db.execute("DELETE FROM artifacts WHERE id='research-out'")
        self.assert_no_release()

    def test_changed_source_body_without_matching_digest_is_rejected(self):
        self.granted()
        body = json.loads(self.w._artifact("research-out")["body"])
        body["content"] = "Changed text"
        self.w.db.execute("UPDATE artifacts SET body=? WHERE id='research-out'", (canonical(body),))
        self.assert_no_release()

    def test_corrupt_retained_start_review_is_rejected(self):
        self.granted()
        self.w.db.execute("UPDATE requests SET review='[]' WHERE task_id='copy'")
        self.assert_no_release()

    def test_removed_ancestry_cannot_reuse_original_output_commitment(self):
        self.granted()
        request = self.w._request(self.w._row("copy")["request_id"])
        body = json.loads(request["review"])
        body["inputs"] = []
        self.w.db.execute("UPDATE requests SET review=?,digest=? WHERE id=?", (canonical(body), digest(body), request["id"]))
        self.assert_no_release()

    def test_crossed_ancestry_selector_is_rejected(self):
        self.granted()
        request = self.w._request(self.w._row("copy")["request_id"])
        body = json.loads(request["review"])
        body["inputs"][0]["task"] = "slides"
        self.w.db.execute("UPDATE requests SET review=? WHERE id=?", (canonical(body), request["id"]))
        self.assert_no_release()

    def test_malformed_retained_json_is_denied(self):
        self.granted()
        self.w.db.execute("UPDATE artifacts SET body='{' WHERE id='research-out'")
        self.assert_no_release()

    def test_ancestry_digest_is_part_of_exact_provider_request(self):
        self.propose()
        body = self.stored()
        original_digest = self.worker.status("run-final")["request_digest"]
        body["lineage"]["artifacts"][0]["parents"] = []
        self.assertNotEqual(digest(body), original_digest)

    def test_released_run_remains_uncertain_after_ancestor_withdrawal(self):
        self.granted()
        release = self.worker.release("run-final")
        self.w.revoke_task("bob", "research", expected_context=self.w.context)
        self.reopen()
        with self.assertRaises(Denied):
            self.worker.release("run-final")
        self.assertEqual(self.worker.status("run-final")["execution"]["state"], "uncertain")
        self.worker.record_result("run-final", release.digest, "Retained original result")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts WHERE id='final-out'").fetchone()[0], 0)

    def test_metadata_and_audit_do_not_export_ancestral_content(self):
        self.granted()
        release = self.worker.release("run-final")
        self.worker.record_result("run-final", release.digest, "RESULT TEXT")
        text = json.dumps(self.worker.status("run-final")) + json.dumps([dict(row) for row in self.w.db.execute("SELECT * FROM audit")])
        for forbidden in ("BOB ORIGINAL SOURCE", "CAROL DERIVED TEXT", "DANA DERIVED TEXT", "ERIN FINAL OBJECTIVE", "RESULT TEXT"):
            self.assertNotIn(forbidden, text)

    def test_v1_database_is_rejected_without_upgrading_decisions(self):
        self.granted()
        self.w.db.execute("UPDATE provider_meta SET version='offline-provider-disclosure/1'")
        before = [dict(row) for row in self.w.db.execute("SELECT * FROM provider_decisions")]
        with self.assertRaises(Denied):
            ProviderGate(self.ledger)
        self.assertEqual([dict(row) for row in self.w.db.execute("SELECT * FROM provider_decisions")], before)
        self.assertEqual(self.w.db.execute("SELECT version FROM provider_meta").fetchone()[0], "offline-provider-disclosure/1")
        self.assertEqual(VERSION, "offline-provider-disclosure/2")

    def test_lineage_requires_existing_team_transaction(self):
        with self.assertRaises(Denied):
            collect_lineage(self.w, {})

    def test_maximum_dense_plan_same_owner_needs_one_exact_approval(self):
        dense = TeamPlan("dense-lineage", "lead", (
            AgentRef("lead", "alice", "fixture-a", "coordination"),
            AgentRef("worker", "bob", "fixture-b", "research"),
        ), tuple(TaskSpec("task-" + str(i), "worker", "Objective " + str(i), "research",
                          tuple("task-" + str(j) for j in range(i))) for i in range(20)))
        w = TeamWorkflow(Path(self.tmp.name) / "dense.sqlite", dense, clock=lambda: 1000)
        try:
            w.accept_lead("alice", expected_context=w.context)
            worker = w.facade("worker")
            for i in range(20):
                task, artifact = "task-" + str(i), "artifact-" + str(i)
                request = worker.propose_start(task, "start-" + str(i))
                w.decide_start("bob", request["request_id"], request["review_digest"], "approve", expected_context=w.context, expires=1100)
                worker.start(request["request_id"])
                if i < 19:
                    worker.submit(task, artifact, "Source " + str(i))
                    review = w.disclosure_review("bob", artifact, "lead", expected_context=w.context)
                    w.approve_disclosure("bob", artifact, "lead", review["review_digest"], expected_context=w.context)
                    w.facade("lead").review_output(task, artifact, "accept")
            ledger = ExecutionLedger(w)
            ledger.facade("worker").prepare("task-19", "dense-run", "dense-output")
            gate = ProviderGate(ledger)
            facade = gate.facade("worker")
            request = facade.propose("dense-run", dataclasses.replace(ROUTE, provider="fixture-b"))
            self.assertEqual([row["owner"] for row in request["decisions"]], ["bob"])
            review = gate.owner_review("bob", "dense-run", expected_context=w.context)
            self.assertEqual(len(review["review"]["affected_payload_inputs"]), 19)
            self.assertEqual(len(review["review"]["owned_data"]["inputs"]), 19)
            gate.decide("bob", "dense-run", review["review_digest"], "approve", expected_context=w.context, expires=1100)
            self.assertEqual(len(facade.release("dense-run").to_dict()["payload"]["inputs"]), 19)
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
