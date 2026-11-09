"""Conservative artifact ancestry from retained exact team start commitments.

This is dependency provenance, not semantic data tracing or authentication. Every
recorded input contributes authority even if a model claims it did not use it.
"""
import json

from .bootstrap import Denied, bounded_text, canonical, digest, identifier


VERSION = "offline-artifact-lineage/1"


def _object(encoded):
    try:
        value = json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied("Invalid retained lineage record") from exc
    if type(value) is not dict:
        raise Denied("Expected retained lineage object")
    return value


def collect_lineage(workflow, claim):
    """Return canonical ancestry while the caller holds the team write lock.

    Read only. No task starts, new disclosure grants, counters or provider calls.
    Source tasks, selected outputs and every historical dependency disclosure
    must still be available. A stopped source cannot hide behind a completed
    downstream task, which the team's normal stop propagation leaves historical.
    """
    w = workflow
    if not w.db.in_transaction:
        raise Denied("Lineage review requires the team's active transaction")
    nodes, visiting = {}, set()

    def visit(artifact_id, expected_digest):
        identifier(artifact_id)
        if artifact_id in visiting:
            raise Denied("Cyclic artifact ancestry")
        if artifact_id in nodes:
            if nodes[artifact_id]["digest"] != expected_digest:
                raise Denied("Conflicting artifact ancestry")
            return nodes[artifact_id]
        if len(nodes) + len(visiting) >= len(w.tasks):
            raise Denied("Artifact ancestry exceeds the immutable plan")
        artifact = w._artifact(artifact_id)
        task = w._task(artifact["task_id"])
        state = w._row(task.id)
        body = _object(artifact["body"])
        if (artifact["digest"] != expected_digest or digest(body) != expected_digest
                or artifact["state"] != "accepted" or state["state"] != "completed"
                or state["artifact_id"] != artifact_id or not state["request_id"]
                or artifact["producer"] != task.assignee):
            raise Denied("Lineage source is not its exact current accepted artifact")
        request = w._request(state["request_id"])
        review = _object(request["review"])
        inputs = review.get("inputs")
        if type(inputs) is not list or len(inputs) != len(task.dependencies):
            raise Denied("Lineage inputs do not match the approved dependency plan")
        if (request["task_id"] != task.id or request["state"] != "started"
                or request["digest"] != digest(review)
                or review != {"domain": "offline-team-start/rebuilt-r1", "context": w.context,
                              "owner": w._task_owner(task.id), "task": task.to_dict(), "inputs": inputs}
                or canonical(body) != artifact["body"]
                or body != {"domain": "offline-team-artifact/rebuilt-r1", "context": w.context,
                            "task": task.id, "producer": task.assignee, "kind": task.output_kind,
                            "content": body.get("content"), "start_review_digest": request["digest"]}):
            raise Denied("Artifact lineage does not match its exact retained start review")
        bounded_text(body["content"], 8192)
        visiting.add(artifact_id)
        parents = []
        for dependency, item in zip(task.dependencies, inputs):
            if (type(item) is not dict or set(item) != {"task", "artifact_id", "digest"}
                    or item["task"] != dependency):
                raise Denied("Lineage dependency selectors changed")
            identifier(item["artifact_id"])
            source = w._artifact(item["artifact_id"])
            if source["task_id"] != dependency or not w._access(source, task.assignee, "task:" + task.id):
                raise Denied("An upstream artifact disclosure is unavailable")
            parent = visit(item["artifact_id"], item["digest"])
            parents.append({"artifact_id": parent["artifact_id"], "digest": parent["digest"]})
        visiting.remove(artifact_id)
        node = {"artifact_id": artifact_id, "digest": artifact["digest"],
                "task_id": task.id, "producer": task.assignee, "owner": w._task_owner(task.id),
                "content": body["content"], "parents": parents}
        nodes[artifact_id] = node
        return node

    roots = []
    for item in claim["inputs"]:
        node = visit(item["artifact_id"], item["digest"])
        roots.append({"artifact_id": node["artifact_id"], "digest": node["digest"]})
    return {"domain": VERSION, "roots": roots, "artifacts": [nodes[key] for key in sorted(nodes)]}


def affected_inputs(lineage, owner):
    """Bind an owner's source contributions to exact outgoing artifact hashes.

    Content of another owner's derived artifact is deliberately not returned.
    """
    nodes = {node["artifact_id"]: node for node in lineage["artifacts"]}

    memo = {}

    def sources(artifact_id):
        if artifact_id in memo:
            return memo[artifact_id]
        node = nodes[artifact_id]
        result = {artifact_id} if node["owner"] == owner else set()
        for parent in node["parents"]:
            result.update(sources(parent["artifact_id"]))
        memo[artifact_id] = result
        return result

    result = []
    for root in lineage["roots"]:
        contribution = sources(root["artifact_id"])
        if contribution:
            result.append({**root, "owner_source_ids": sorted(contribution)})
    return result
