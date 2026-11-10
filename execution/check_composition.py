"""Compose local execution and protocol staging. No provider or peer transport."""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution.bootstrap import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied
from execution.ledger import ExecutionLedger
from integration.team_proposals import BoundArtifactProposal
from integration.recipient_acceptance import AcceptanceBoundary
from team.run_checks import offline_guard

TEXT = "SYNTHETIC ONLY: A fictional garden needs a volunteer introduction."


def check():
    plan = TeamPlan("execution-proposal-composition", "lead", (
        AgentRef("lead", "alice", "fixture-a", "review"),
        AgentRef("researcher", "bob", "fixture-b", "research"),
        AgentRef("writer", "carol", "fixture-c", "copy"),
    ), (
        TaskSpec("research", "researcher", "Research fictional garden needs", "research"),
        TaskSpec("copy", "writer", "Write copy from accepted research", "copy", ("research",)),
    ))
    with tempfile.TemporaryDirectory(prefix="execution-proposal-composition-") as directory:
        w = TeamWorkflow(Path(directory) / "team.sqlite", plan, clock=lambda: 1000)
        bound = None
        try:
            w.accept_lead("alice", expected_context=w.context)
            request = w.facade("researcher").propose_start("research", "request")
            w.decide_start("bob", request["request_id"], request["review_digest"], "approve",
                           expected_context=w.context, expires=1100)
            w.facade("researcher").start(request["request_id"])
            worker = ExecutionLedger(w).facade("researcher")
            worker.prepare("research", "run", "research-output")
            claim = worker.claim("run")
            worker.record_result("run", claim.digest, TEXT)
            worker.publish("run")
            review = w.disclosure_review("bob", "research-output", "lead", expected_context=w.context)
            w.approve_disclosure("bob", "research-output", "lead", review["review_digest"],
                                 expected_context=w.context)
            w.facade("lead").review_output("research", "research-output", "accept")
            review = w.disclosure_review("bob", "research-output", "writer", "copy", expected_context=w.context)
            w.approve_disclosure("bob", "research-output", "writer", review["review_digest"], "copy",
                                 expected_context=w.context)
            bound = BoundArtifactProposal(w, "research-output", "copy", expected_context=w.context)
            proposal = bound.facade.propose({"text": TEXT})
            if proposal["state"] != "pending" or w._row("copy")["state"] != "planned":
                raise AssertionError("Unsigned staging cannot approve or start downstream work")
            boundary = AcceptanceBoundary(w)
            offer_id = boundary.register(bound)["offer_id"]
            source = boundary.source_control("bob", expected_context=w.context)
            recipient = boundary.recipient_control("carol", "writer", expected_context=w.context)
            source.decide(offer_id, source.review(offer_id)["review_digest"], "approve", expires=1100)
            delivery = source.release(offer_id)
            recipient.receive(delivery)
            accepted = recipient.decide(offer_id, recipient.review(offer_id)["review_digest"], "accept")
            if accepted["recipient_state"] != "accepted" or w._row("copy")["state"] != "planned":
                raise AssertionError("Recipient acceptance must not start downstream work")
            w.revoke_disclosure("bob", "research-output", "writer", "copy", expected_context=w.context)
            try:
                bound.facade.propose({"text": TEXT})
            except Denied:
                pass
            else:
                raise AssertionError("Revocation must block new staging")
            historical = bound.facade.status({"proposal_id": bound.proposal_id})
            if historical["state"] != "pending":
                raise AssertionError("Local staged history must not imply delivery or execution")
            return {"simulation": True, "external_calls": 0,
                    "execution_state": worker.status("run")["state"],
                    "proposal_state": historical["state"],
                    "recipient_acceptance": recipient.status(offer_id),
                    "downstream_state": w._row("copy")["state"],
                    "revoked_route_restage_blocked": True}
        finally:
            if bound is not None:
                bound.close()
            w.close()


if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    print(json.dumps(check(), indent=2))
