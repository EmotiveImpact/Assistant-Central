"""Rehearse separate source-owner and task-owner disclosure, entirely offline."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied
from execution.ledger import ExecutionLedger
from execution.provider_gate import ProviderGate, ProviderRoute
from team.run_checks import offline_guard


def simulate(directory):
    path = Path(directory) / "provider-demo.sqlite"
    if path.exists():
        raise Denied("Use a fresh directory; never replay a prior release")
    plan = TeamPlan("provider-disclosure-demo", "lead", (
        AgentRef("lead", "alice", "synthetic-a", "coordination"),
        AgentRef("researcher", "bob", "synthetic-b", "research"),
        AgentRef("writer", "carol", "synthetic-c", "copy"),
    ), (
        TaskSpec("research", "researcher", "Research a fictional garden", "research"),
        TaskSpec("copy", "writer", "Write a fictional garden introduction", "copy", ("research",)),
    ))
    w = TeamWorkflow(path, plan, clock=lambda: 1000)
    try:
        w.accept_lead("alice", expected_context=w.context)
        request = w.facade("researcher").propose_start("research", "start-research")
        w.decide_start("bob", request["request_id"], request["review_digest"], "approve",
                       expected_context=w.context, expires=1100)
        w.facade("researcher").start(request["request_id"])
        w.facade("researcher").submit("research", "research-out", "FICTIONAL RESEARCH: The garden needs volunteers.")
        review = w.disclosure_review("bob", "research-out", "lead", expected_context=w.context)
        w.approve_disclosure("bob", "research-out", "lead", review["review_digest"], expected_context=w.context)
        w.facade("lead").review_output("research", "research-out", "accept")
        review = w.disclosure_review("bob", "research-out", "writer", "copy", expected_context=w.context)
        w.approve_disclosure("bob", "research-out", "writer", review["review_digest"], "copy", expected_context=w.context)
        request = w.facade("writer").propose_start("copy", "start-copy")
        w.decide_start("carol", request["request_id"], request["review_digest"], "approve",
                       expected_context=w.context, expires=1100)
        w.facade("writer").start(request["request_id"])
        ledger = ExecutionLedger(w)
        ledger.facade("writer").prepare("copy", "run-copy", "copy-out")
        gate = ProviderGate(ledger)
        writer = gate.facade("writer")
        route = ProviderRoute("synthetic-c", "fictional-account", "fixture-model",
                              "Offline rehearsal only. No provider terms accepted or retention assurance.")
        writer.propose("run-copy", route)
        # Explicit fictional choices. These calls do not authenticate humans.
        carol = gate.owner_review("carol", "run-copy", expected_context=w.context)
        assert not carol["review"]["owned_data"]["inputs"]
        gate.decide("carol", "run-copy", carol["review_digest"], "approve", expected_context=w.context, expires=1100)
        try:
            writer.release("run-copy")
            raise AssertionError("Task owner cannot grant onward disclosure of Bob's data")
        except Denied:
            task_owner_only_blocked = True
        try:
            gate.owner_review("alice", "run-copy", expected_context=w.context)
            raise AssertionError("Lead has no authority over this provider disclosure")
        except Denied:
            lead_override_blocked = True
        bob = gate.owner_review("bob", "run-copy", expected_context=w.context)
        assert "task_text" not in bob["review"]["owned_data"]
        gate.decide("bob", "run-copy", bob["review_digest"], "approve", expected_context=w.context, expires=1100)
        release = writer.release("run-copy")
        # No provider/adapter is called. Construct one inert fictional receipt.
        original_result = "FICTIONAL COPY: Join the garden's volunteer introduction."
    finally:
        w.close()
    w = TeamWorkflow(path, plan, clock=lambda: 1000)
    try:
        ledger = ExecutionLedger(w)
        gate = ProviderGate(ledger)
        writer = gate.facade("writer")
        after_restart = writer.status("run-copy")
        try:
            writer.release("run-copy")
            raise AssertionError("Lost receipt must never cause a second release")
        except Denied:
            redispatch_blocked = True
        writer.record_result("run-copy", release.digest, original_result)
        ledger.facade("writer").publish("run-copy")
        try:
            w.facade("lead").read_artifact("copy-out")
            raise AssertionError("Provider approval must not grant lead access to the result")
        except Denied:
            output_disclosure_still_required = True
        withdrawn = gate.revoke("bob", "run-copy", expected_context=w.context)
        return {"simulation": True, "human_approval_claimed": False, "external_calls": 0,
                "task_owner_only_blocked": task_owner_only_blocked,
                "lead_override_blocked": lead_override_blocked,
                "owner_reviews_isolated": True, "redispatch_blocked": redispatch_blocked,
                "output_disclosure_still_required": output_disclosure_still_required,
                "restart_execution_state": after_restart["execution"]["state"],
                "withdrawal_recalls_data": False, "final_status": withdrawn}
    finally:
        w.close()


if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    with tempfile.TemporaryDirectory(prefix="synthetic-provider-") as directory:
        print(json.dumps(simulate(directory), indent=2))
