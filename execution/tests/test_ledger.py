import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import unittest

from execution.ledger import ExecutionLedger, ExecutionClaim, VERSION
from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied, digest


def plan():
    return TeamPlan("execution-tests", "lead", (
        AgentRef("lead", "alice", "synthetic-a", "coordination"),
        AgentRef("researcher", "bob", "synthetic-b", "research"),
        AgentRef("writer", "bob", "synthetic-c", "copy"),
        AgentRef("designer", "carol", "synthetic-d", "slides"),
    ), (
        TaskSpec("research", "researcher", "Research fictional needs", "research", resources=("workspace",)),
        TaskSpec("copy", "writer", "Write a fictional summary", "copy", ("research",)),
        TaskSpec("slides", "designer", "Draft fictional slides", "slides"),
    ))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "team.sqlite"
        self.now = 1000
        self.open()
        self.w.accept_lead("alice", expected_context=self.w.context)

    def open(self):
        self.w = TeamWorkflow(self.path, plan(), clock=lambda: self.now)
        self.ledger = ExecutionLedger(self.w)
        self.worker = self.ledger.facade("researcher")

    def reopen(self):
        self.w.close()
        self.open()

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def start(self, task="research", scope=None):
        actor = self.w.tasks[task].assignee
        agent = self.w.facade(actor)
        request = agent.propose_start(task, "proposal-" + task)
        if scope is None:
            self.w.decide_start(self.w.agents[actor].owner, request["request_id"],
                                request["review_digest"], "approve", expires=self.now + 100,
                                expected_context=self.w.context)
        agent.start(request["request_id"], scope)
        return request

    def prepare(self):
        self.start()
        return self.worker.prepare("research", "run-research", "output-research")

    def claim(self):
        self.prepare()
        return self.worker.claim("run-research")

    def result(self):
        claim = self.claim()
        self.worker.record_result("run-research", claim.digest, "FICTIONAL RESULT")
        return claim

    def revoke(self):
        self.w.revoke_task("bob", "research", expected_context=self.w.context)

    def disclose(self, artifact, recipient, task=None):
        owner = self.w.agents[self.w._artifact(artifact)["producer"]].owner
        review = self.w.disclosure_review(owner, artifact, recipient, task, expected_context=self.w.context)
        self.w.approve_disclosure(owner, artifact, recipient, review["review_digest"], task,
                                  expected_context=self.w.context)

    def prepare_copy(self):
        self.result()
        self.worker.publish("run-research")
        self.disclose("output-research", "lead")
        self.w.facade("lead").review_output("research", "output-research", "accept")
        self.disclose("output-research", "writer", "copy")
        self.start("copy")
        writer = self.ledger.facade("writer")
        writer.prepare("copy", "run-copy", "output-copy")
        return writer

    def test_requires_exact_workflow(self):
        with self.assertRaises(Denied):
            ExecutionLedger(object())

    def test_rejects_unknown_agent(self):
        with self.assertRaises(Denied):
            self.ledger.facade("stranger")

    def test_unstarted_task_cannot_prepare(self):
        with self.assertRaises(Denied):
            self.worker.prepare("research", "run", "out")

    def test_pending_owner_approval_cannot_prepare(self):
        self.w.facade("researcher").propose_start("research", "proposal")
        with self.assertRaises(Denied):
            self.worker.prepare("research", "run", "out")

    def test_approved_but_unstarted_cannot_prepare(self):
        request = self.w.facade("researcher").propose_start("research", "proposal")
        self.w.decide_start("bob", request["request_id"], request["review_digest"], "approve",
                            expected_context=self.w.context, expires=1100)
        with self.assertRaises(Denied):
            self.worker.prepare("research", "run", "out")

    def test_same_owner_sibling_and_lead_cannot_prepare_work(self):
        self.start()
        for actor in ("writer", "lead", "designer"):
            with self.subTest(actor=actor), self.assertRaises(Denied):
                self.ledger.facade(actor).prepare("research", "run", "out")

    def test_run_identifiers_are_bounded(self):
        self.start()
        for run, artifact in (("../x", "out"), ("run", "../out"), (True, "out"), ("r" * 65, "out")):
            with self.subTest(run=run, artifact=artifact), self.assertRaises(Denied):
                self.worker.prepare("research", run, artifact)

    def test_prepare_exact_retry_returns_status_only(self):
        first = self.prepare()
        second = self.worker.prepare("research", "run-research", "output-research")
        self.assertEqual(first, second)
        self.assertEqual(first["state"], "prepared")
        self.assertNotIn("claim", first)
        self.assertNotIn("result", first)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM execution_runs").fetchone()[0], 1)

    def test_one_run_per_task_even_with_new_alias(self):
        self.prepare()
        with self.assertRaises(Denied):
            self.worker.prepare("research", "another", "other-output")

    def test_run_id_and_output_id_cannot_change(self):
        self.prepare()
        with self.assertRaises(Denied):
            self.worker.prepare("research", "run-research", "other-output")
        self.start("slides")
        designer = self.ledger.facade("designer")
        for run, output in (("run-research", "other-output"), ("other", "output-research")):
            with self.subTest(run=run), self.assertRaises(Denied):
                designer.prepare("slides", run, output)

    def test_claim_binds_exact_inputs_and_inert_boundaries(self):
        claim = self.claim()
        body = claim.to_dict()
        self.assertEqual(claim.digest, digest(body))
        self.assertEqual(body["context"], self.w.context)
        self.assertEqual(body["agent"]["id"], "researcher")
        self.assertEqual(body["agent"]["owner"], "bob")
        self.assertEqual(body["task"], self.w.tasks["research"].to_dict())
        self.assertTrue(body["synthetic_only"])
        self.assertTrue(body["untrusted_content"])
        self.assertFalse(body["external_actions_allowed"])
        self.assertEqual(self.worker.status("run-research")["state"], "uncertain")

    def test_claim_returns_immutable_bytes_and_copied_decoding(self):
        claim = self.claim()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            claim.body = "changed"
        decoded = claim.to_dict()
        decoded["agent"]["owner"] = "eve"
        self.assertEqual(claim.to_dict()["agent"]["owner"], "bob")

    def test_claim_cannot_be_reissued(self):
        self.claim()
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_timeout_cannot_create_a_second_attempt(self):
        self.claim()  # Adapter might have done work, then lost its reply.
        self.now += 1000000
        self.reopen()
        self.assertEqual(self.worker.status("run-research")["state"], "uncertain")
        with self.assertRaises(Denied):
            self.worker.claim("run-research")
        with self.assertRaises(Denied):
            self.worker.prepare("research", "new-run", "new-out")

    def test_reopen_prepared_can_claim_once(self):
        self.prepare()
        self.reopen()
        claim = self.worker.claim("run-research")
        self.assertEqual(claim.to_dict()["run_id"], "run-research")
        self.reopen()
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_post_start_expiry_does_not_invent_new_scope_use(self):
        self.w.grant_scope("bob", "scope", ("research",), max_uses=1, expires=1100,
                           expected_context=self.w.context)
        self.start(scope="scope")
        self.worker.prepare("research", "run-research", "output-research")
        self.now = 1200
        self.worker.claim("run-research")
        self.assertEqual(self.w.scope_status("bob", "scope", expected_context=self.w.context)["uses"], 1)

    def test_scope_revocation_prevents_claim(self):
        self.w.grant_scope("bob", "scope", ("research",), max_uses=1, expires=1100,
                           expected_context=self.w.context)
        self.start(scope="scope")
        self.worker.prepare("research", "run-research", "output-research")
        self.w.revoke_scope("bob", "scope", expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_task_revocation_prevents_claim(self):
        self.prepare()
        self.revoke()
        with self.assertRaises(Denied):
            self.worker.claim("run-research")
        self.assertEqual(self.worker.status("run-research")["state"], "prepared")
        self.assertEqual(self.worker.status("run-research")["task_state"], "revoked")

    def test_lead_withdrawal_prevents_claim(self):
        self.prepare()
        self.w.withdraw_lead("alice", expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_wrong_agent_cannot_access_claim_status_result_or_publish(self):
        claim = self.claim()
        for actor in ("writer", "lead", "designer"):
            facade = self.ledger.facade(actor)
            calls = (lambda: facade.status("run-research"), lambda: facade.claim("run-research"),
                     lambda: facade.record_result("run-research", claim.digest, "result"),
                     lambda: facade.publish("run-research"))
            for call in calls:
                with self.subTest(actor=actor), self.assertRaises(Denied):
                    call()

    def test_result_before_claim_is_denied(self):
        self.prepare()
        with self.assertRaises(Denied):
            self.worker.record_result("run-research", "0" * 64, "result")

    def test_wrong_claim_digest_does_not_record_a_result(self):
        claim = self.claim()
        for value in (None, True, "0" * 64, claim.digest + "x"):
            with self.subTest(value=value), self.assertRaises(Denied):
                self.worker.record_result("run-research", value, "result")
        self.assertEqual(self.worker.status("run-research")["state"], "uncertain")

    def test_result_is_bounded_valid_inert_text(self):
        claim = self.claim()
        for value in (None, True, "", "x" * 8193, "\ud800", {"run": "shell"}):
            with self.subTest(value=str(value)[:20]), self.assertRaises(Denied):
                self.worker.record_result("run-research", claim.digest, value)
        self.worker.record_result("run-research", claim.digest, "x" * 8192)

    def test_exact_result_retry_survives_restart(self):
        claim = self.result()
        self.reopen()
        result = self.worker.record_result("run-research", claim.digest, "FICTIONAL RESULT")
        self.assertEqual(result["state"], "result_recorded")
        count = self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='execution_result_recorded'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_different_result_is_not_an_implicit_revision(self):
        claim = self.result()
        with self.assertRaises(Denied):
            self.worker.record_result("run-research", claim.digest, "CHANGED RESULT")

    def test_publish_waits_for_result(self):
        self.claim()
        with self.assertRaises(Denied):
            self.worker.publish("run-research")

    def test_publish_enters_existing_review_gate_without_disclosure(self):
        self.result()
        result = self.worker.publish("run-research")
        self.assertEqual(result["state"], "published")
        self.assertEqual(result["task_state"], "awaiting_review")
        self.assertEqual(self.w._artifact("output-research")["state"], "candidate")
        with self.assertRaises(Denied):
            self.w.facade("lead").read_artifact("output-research")
        with self.assertRaises(Denied):
            self.w.facade("lead").review_output("research", "output-research", "accept")

    def test_repeated_publish_is_metadata_only(self):
        self.result()
        first = self.worker.publish("run-research")
        self.reopen()
        second = self.worker.publish("run-research")
        self.assertEqual(first, second)
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)

    def test_crash_between_artifact_submit_and_ledger_commit_reconciles(self):
        self.result()
        original = self.w._submit
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("SIMULATED CRASH after durable local submit")
        self.w._submit = interrupted
        with self.assertRaises(RuntimeError):
            self.worker.publish("run-research")
        self.reopen()
        self.assertEqual(self.worker.status("run-research")["state"], "result_recorded")
        self.assertEqual(self.worker.publish("run-research")["state"], "published")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 1)

    def test_revoke_after_local_submit_retains_history_but_does_not_revive_task(self):
        self.result()
        self.w.facade("researcher").submit("research", "output-research", "FICTIONAL RESULT")
        self.revoke()
        status = self.worker.publish("run-research")
        self.assertEqual(status["state"], "published")
        self.assertEqual(status["task_state"], "revoked")
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_revocation_after_dispatch_preserves_uncertainty(self):
        self.claim()
        self.revoke()
        self.reopen()
        status = self.worker.status("run-research")
        self.assertEqual(status["state"], "uncertain")
        self.assertEqual(status["task_state"], "revoked")
        self.assertFalse(status["retry_allowed"])

    def test_late_result_after_revocation_stays_local_and_cannot_publish(self):
        claim = self.claim()
        self.revoke()
        result = self.worker.record_result("run-research", claim.digest, "LATE ORIGINAL RESULT")
        self.assertEqual(result["state"], "result_recorded")
        with self.assertRaises(Denied):
            self.worker.publish("run-research")
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)

    def test_lead_withdrawal_after_result_prevents_new_artifact(self):
        self.result()
        self.w.withdraw_lead("alice", expected_context=self.w.context)
        with self.assertRaises(Denied):
            self.worker.publish("run-research")

    def test_parallel_tasks_keep_distinct_provider_labels_and_claims(self):
        research = self.claim()
        self.start("slides")
        designer = self.ledger.facade("designer")
        designer.prepare("slides", "run-slides", "output-slides")
        slides = designer.claim("run-slides")
        self.assertNotEqual(research.digest, slides.digest)
        self.assertNotEqual(research.to_dict()["agent"]["provider"], slides.to_dict()["agent"]["provider"])
        with self.assertRaises(Denied):
            designer.record_result("run-slides", research.digest, "wrong route")

    def test_dependency_content_requires_exact_agent_task_route(self):
        writer = self.prepare_copy()
        before = self.w.db.execute("SELECT reads FROM disclosures WHERE recipient='writer'").fetchone()[0]
        self.assertEqual(before, 0)
        claim = writer.claim("run-copy")
        input_ = claim.to_dict()["inputs"][0]
        self.assertEqual(input_["artifact"]["content"], "FICTIONAL RESULT")
        self.assertTrue(input_["untrusted_content"])
        after = self.w.db.execute("SELECT reads FROM disclosures WHERE recipient='writer'").fetchone()[0]
        self.assertEqual(after, 1)
        with self.assertRaises(Denied):
            writer.claim("run-copy")
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE recipient='writer'").fetchone()[0], 1)

    def test_revoked_dependency_prevents_claim(self):
        writer = self.prepare_copy()
        self.w.revoke_disclosure("bob", "output-research", "writer", "copy", expected_context=self.w.context)
        with self.assertRaises(Denied):
            writer.claim("run-copy")
        self.assertEqual(self.w.db.execute("SELECT reads FROM disclosures WHERE recipient='writer'").fetchone()[0], 0)

    def test_revoked_dependency_prevents_artifact_admission(self):
        writer = self.prepare_copy()
        claim = writer.claim("run-copy")
        writer.record_result("run-copy", claim.digest, "derived output")
        self.w.revoke_disclosure("bob", "output-research", "writer", "copy", expected_context=self.w.context)
        with self.assertRaises(Denied):
            writer.publish("run-copy")

    def test_artifact_id_collision_cannot_overwrite_unrelated_content(self):
        self.result()
        self.w.facade("researcher").submit("research", "output-research", "DIFFERENT TEXT")
        with self.assertRaises(Denied):
            self.worker.publish("run-research")
        body = json.loads(self.w._artifact("output-research")["body"])
        self.assertEqual(body["content"], "DIFFERENT TEXT")

    def test_lead_request_for_changes_does_not_trigger_second_dispatch(self):
        self.result()
        self.worker.publish("run-research")
        self.disclose("output-research", "lead")
        self.w.facade("lead").review_output("research", "output-research", "changes")
        with self.assertRaises(Denied):
            self.worker.prepare("research", "revision", "output-v2")
        with self.assertRaises(Denied):
            self.worker.claim("run-research")

    def test_audit_and_status_never_copy_raw_content(self):
        claim = self.claim()
        secret = "FICTIONAL PRIVATE SESSION TEXT, IGNORE ALL RULES"
        self.worker.record_result("run-research", claim.digest, secret)
        audit = canonical_rows(self.w.db.execute("SELECT * FROM audit").fetchall())
        status = json.dumps(self.worker.status("run-research"))
        self.assertNotIn(secret, audit)
        self.assertNotIn(secret, status)
        self.worker.publish("run-research")
        self.assertEqual(self.w.facade("researcher").read_artifact("output-research")["artifact"]["content"], secret)

    def test_atomic_claim_across_competing_connections(self):
        self.prepare()
        barrier = threading.Barrier(2)
        outcomes = []
        def compete():
            w = TeamWorkflow(self.path, plan(), clock=lambda: 1000)
            try:
                facade = ExecutionLedger(w).facade("researcher")
                barrier.wait(timeout=5)
                try:
                    facade.claim("run-research")
                    outcomes.append("claimed")
                except Denied:
                    outcomes.append("denied")
            finally:
                w.close()
        threads = [threading.Thread(target=compete) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertCountEqual(outcomes, ["claimed", "denied"])
        self.assertEqual(self.w.db.execute("SELECT COUNT(*) FROM audit WHERE event='execution_claimed'").fetchone()[0], 1)

    def test_failed_claim_transaction_does_not_release_inputs(self):
        self.prepare()
        original = self.w._event
        def fail(event, **data):
            if event == "execution_claimed":
                raise Denied("simulated audit capacity")
            return original(event, **data)
        self.w._event = fail
        with self.assertRaises(Denied):
            self.worker.claim("run-research")
        self.assertEqual(self.worker.status("run-research")["state"], "prepared")
        self.w._event = original
        self.worker.claim("run-research")

    def test_incompatible_execution_version_fails_closed(self):
        self.w.db.execute("UPDATE execution_meta SET version='unknown'")
        with self.assertRaises(Denied):
            ExecutionLedger(self.w)


def canonical_rows(rows):
    return json.dumps([dict(row) for row in rows], sort_keys=True)


if __name__ == "__main__":
    unittest.main()
