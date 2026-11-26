"""Rehearse an upstream owner's veto across a completed derived artifact."""
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
    path = Path(directory) / "lineage-demo.sqlite"
    if path.exists():
        raise Denied("Use fresh state; never replay an earlier disclosure")
    plan = TeamPlan("inherited-disclosure-demo", "lead", (
        AgentRef("lead", "alice", "fixture-a", "coordination"),
        AgentRef("researcher", "bob", "fixture-b", "research"),
        AgentRef("writer", "carol", "fixture-c", "copy"),
        AgentRef("designer", "dana", "fixture-d", "slides"),
    ), (
        TaskSpec("research", "researcher", "Research a fictional garden", "research"),
        TaskSpec("copy", "writer", "Write a garden invitation", "copy", ("research",)),
        TaskSpec("slides", "designer", "Outline fictional garden slides", "slides", ("copy",)),
    ))
    w = TeamWorkflow(path, plan, clock=lambda: 1000)
    try:
        def start(task):
            actor = w.tasks[task].assignee
            request = w.facade(actor).propose_start(task, "start-" + task)
            w.decide_start(w.agents[actor].owner, request["request_id"], request["review_digest"],
                           "approve", expected_context=w.context, expires=1100)
            w.facade(actor).start(request["request_id"])

        def disclose(owner, artifact, recipient, task=None):
            review = w.disclosure_review(owner, artifact, recipient, task, expected_context=w.context)
            w.approve_disclosure(owner, artifact, recipient, review["review_digest"], task, expected_context=w.context)

        def finish(task, content):
            start(task)
            actor, artifact = w.tasks[task].assignee, task + "-out"
            w.facade(actor).submit(task, artifact, content)
            disclose(w.agents[actor].owner, artifact, "lead")
            w.facade("lead").review_output(task, artifact, "accept")

        w.accept_lead("alice", expected_context=w.context)
        finish("research", "FICTIONAL BOB SOURCE: The garden needs volunteers.")
        disclose("bob", "research-out", "writer", "copy")
        finish("copy", "FICTIONAL CAROL COPY: Join the garden volunteer introduction.")
        disclose("carol", "copy-out", "designer", "slides")
        start("slides")
        ledger = ExecutionLedger(w)
        ledger.facade("designer").prepare("slides", "run-slides", "slides-out")
        gate = ProviderGate(ledger)
        designer = gate.facade("designer")
        designer.propose("run-slides", ProviderRoute("fixture-d", "fictional-account", "fixture-model",
                                                      "Synthetic rehearsal; no provider terms or promises"))
        for owner in ("carol", "dana"):
            review = gate.owner_review(owner, "run-slides", expected_context=w.context)
            gate.decide(owner, "run-slides", review["review_digest"], "approve", expected_context=w.context, expires=1100)
        try:
            designer.release("run-slides")
            raise AssertionError("The original source owner must retain a veto")
        except Denied:
            original_owner_still_required = True
        bob = gate.owner_review("bob", "run-slides", expected_context=w.context)
        assert "FICTIONAL BOB SOURCE" in json.dumps(bob)
        assert "FICTIONAL CAROL COPY" not in json.dumps(bob)
        gate.decide("bob", "run-slides", bob["review_digest"], "approve", expected_context=w.context, expires=1100)
        # Withdraw the original input route AFTER the derived copy completed.
        w.revoke_disclosure("bob", "research-out", "writer", "copy", expected_context=w.context)
        assert w._row("copy")["state"] == "completed"
        assert w._row("slides")["state"] == "running"
        try:
            designer.release("run-slides")
            raise AssertionError("A completed intermediary must not hide source withdrawal")
        except Denied:
            historical_withdrawal_blocks_release = True
        return {"simulation": True, "human_approval_claimed": False, "external_calls": 0,
                "original_owner_still_required": original_owner_still_required,
                "source_owner_cannot_read_derived_text": True,
                "historical_withdrawal_blocks_release": historical_withdrawal_blocks_release,
                "final_status": designer.status("run-slides")}
    finally:
        w.close()


if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    with tempfile.TemporaryDirectory(prefix="synthetic-lineage-") as directory:
        print(json.dumps(simulate(directory), indent=2))
