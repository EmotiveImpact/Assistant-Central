"""Synthetic original-result reconciliation, then an owner-controlled handoff."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution.ledger import ExecutionLedger
from team.run_checks import offline_guard
from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied


def simulate(directory):
    path = Path(directory) / "execution-demo.sqlite"
    if path.exists():
        raise Denied("Use a fresh directory; the demo never replays existing work")
    plan = TeamPlan("synthetic-execution-demo", "lead", (
        AgentRef("lead", "alice", "local-fixture-a", "coordination"),
        AgentRef("researcher", "bob", "local-fixture-b", "research"),
        AgentRef("writer", "carol", "local-fixture-c", "copy"),
    ), (
        TaskSpec("research", "researcher", "Research a fictional garden", "research"),
        TaskSpec("copy", "writer", "Write copy using the accepted research", "copy", ("research",)),
    ))
    w = TeamWorkflow(path, plan, clock=lambda: 1000)
    try:
        w.accept_lead("alice", expected_context=w.context)
        request = w.facade("researcher").propose_start("research", "request-research")
        w.decide_start("bob", request["request_id"], request["review_digest"], "approve",
                       expected_context=w.context, expires=1500)
        w.facade("researcher").start(request["request_id"])
        researcher = ExecutionLedger(w).facade("researcher")
        researcher.prepare("research", "run-research", "research-output")
        claim = researcher.claim("run-research")
        # A local fixture computes inert output. No model or provider is invoked.
        original_result = "SYNTHETIC RESEARCH: The fictional garden needs volunteers."
        # Simulate a lost receipt by closing before recording that original result.
    finally:
        w.close()
    w = TeamWorkflow(path, plan, clock=lambda: 1000)
    try:
        ledger = ExecutionLedger(w)
        researcher = ledger.facade("researcher")
        after_restart = researcher.status("run-research")
        try:
            researcher.claim("run-research")
            raise AssertionError("A second dispatch must never be allowed")
        except Denied:
            duplicate_dispatch_blocked = True
        researcher.record_result("run-research", claim.digest, original_result)
        researcher.publish("run-research")
        review = w.disclosure_review("bob", "research-output", "lead", expected_context=w.context)
        w.approve_disclosure("bob", "research-output", "lead", review["review_digest"], expected_context=w.context)
        w.facade("lead").review_output("research", "research-output", "accept")
        review = w.disclosure_review("bob", "research-output", "writer", "copy", expected_context=w.context)
        w.approve_disclosure("bob", "research-output", "writer", review["review_digest"], "copy",
                             expected_context=w.context)
        request = w.facade("writer").propose_start("copy", "request-copy")
        w.decide_start("carol", request["request_id"], request["review_digest"], "approve",
                       expected_context=w.context, expires=1500)
        w.facade("writer").start(request["request_id"])
        writer = ledger.facade("writer")
        writer.prepare("copy", "run-copy", "copy-output")
        copy_claim = writer.claim("run-copy")
        assert copy_claim.to_dict()["inputs"][0]["artifact"]["content"] == original_result
        writer.record_result("run-copy", copy_claim.digest,
                             "SYNTHETIC COPY: Join the fictional garden's volunteer introduction.")
        published = writer.publish("run-copy")
        # Deliberately leave Carol's new output awaiting her separate disclosure.
        try:
            w.facade("lead").read_artifact("copy-output")
            raise AssertionError("No implicit lead disclosure")
        except Denied:
            unapproved_disclosure_blocked = True
        return {"simulation": True, "human_approval_claimed": False, "external_calls": 0,
                "restart_state": after_restart["state"],
                "duplicate_dispatch_blocked": duplicate_dispatch_blocked,
                "unapproved_disclosure_blocked": unapproved_disclosure_blocked,
                "copy_status": published, "snapshot": w.snapshot()}
    finally:
        w.close()


if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    with tempfile.TemporaryDirectory(prefix="synthetic-execution-") as directory:
        print(json.dumps(simulate(directory), indent=2))
