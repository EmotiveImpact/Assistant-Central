"""Five synthetic artifacts. Explicit scripted choices are not human approvals."""
import json
from pathlib import Path
import tempfile
from team_workflow import AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied


def plan():
    return TeamPlan("fictional-community-launch", "lead", (
        AgentRef("lead", "alice", "provider-a-fixture", "Coordination and review"),
        AgentRef("researcher", "bob", "provider-b-fixture", "Public research"),
        AgentRef("writer", "carol", "provider-c-fixture", "Copy editing"),
        AgentRef("designer", "dana", "provider-d-fixture", "Slide design"),
        AgentRef("web-builder", "alice", "provider-a-fixture", "Website drafts"),
        AgentRef("developer", "bob", "provider-e-fixture", "Code and PR drafts"),
    ), (
        TaskSpec("research", "researcher", "Summarize fictional public community needs", "research"),
        TaskSpec("copy", "writer", "Write launch copy from accepted research", "copy", ("research",)),
        TaskSpec("slides", "designer", "Outline slides from accepted research", "slides", ("research",)),
        TaskSpec("website", "web-builder", "Draft a website from accepted copy and slides", "website", ("copy", "slides"), ("draft-workspace",)),
        TaskSpec("pr", "developer", "Prepare a PR draft describing the accepted website", "pr-draft", ("website",), ("draft-workspace",)),
    ))


def disclose(w, artifact, recipient, task=None):
    owner = w.agents[w._artifact(artifact)["producer"]].owner
    review = w.disclosure_review(owner, artifact, recipient, task, expected_context=w.context)
    w.approve_disclosure(owner, artifact, recipient, review["review_digest"], task, expected_context=w.context)


def simulate(directory):
    """No network or tools. Writes only fictional local state and JSON artifacts."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "fictional-team.sqlite"
    if database.exists():
        raise Denied("Demo requires a new output directory; existing state is not replayed")
    w = TeamWorkflow(database, plan(), clock=lambda: 1000)
    try:
        w.accept_lead("alice", expected_context=w.context)
        # Bob separately grants only his two exact tasks, not any disclosure.
        w.grant_scope("bob", "bob-exact-work", ("research", "pr"), max_uses=2,
                      expires=1500, expected_context=w.context)
        texts = {
            "research": "SYNTHETIC RESEARCH: A fictional garden needs a clear volunteer introduction.",
            "copy": "SYNTHETIC COPY: Grow together. Join the fictional Saturday garden introduction.",
            "slides": "SYNTHETIC SLIDE OUTLINE: 1. Welcome. 2. Volunteer roles. 3. Next steps.",
            "website": "SYNTHETIC WEBSITE DRAFT: Hero, volunteer section, schedule, and a nonfunctional interest form.",
            "pr": "SYNTHETIC PR DRAFT: Add the reviewed garden website draft. No repository or pull request was created.",
        }
        outputs = []
        for task_id in ("research", "copy", "slides", "website", "pr"):
            spec = w.tasks[task_id]
            for dependency in spec.dependencies:
                disclose(w, dependency + "-v1", spec.assignee, task_id)
            agent = w.facade(spec.assignee)
            request = agent.propose_start(task_id, "proposal-" + task_id)
            owner = w.agents[spec.assignee].owner
            if owner == "bob":
                agent.start(request["request_id"], "bob-exact-work")
            else:
                w.decide_start(owner, request["request_id"], request["review_digest"], "approve",
                               expires=1500, expected_context=w.context)
                agent.start(request["request_id"])
            artifact_id = task_id + "-v1"
            agent.submit(task_id, artifact_id, texts[task_id])
            disclose(w, artifact_id, "lead")
            w.facade("lead").read_artifact(artifact_id)
            w.facade("lead").review_output(task_id, artifact_id, "accept")
            output = agent.read_artifact(artifact_id)
            outputs.append(output)
            (directory / (artifact_id + ".json")).write_text(json.dumps(output, indent=2) + "\n")
        result = {"simulation": True, "human_approval_claimed": False, "external_calls": 0,
                  "new_rebuild": True, "artifact_count": len(outputs), "snapshot": w.snapshot(),
                  "bob_scope": w.scope_status("bob", "bob-exact-work", expected_context=w.context)}
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        w.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="team-rebuilt-fictional-") as directory:
        print(json.dumps(simulate(directory), indent=2))
