"""Durable single-attempt boundary for fictional, local team execution.

No model, transport, credentials, timers or tool calls live here. The trusted
composition binds an agent before exposing a facade. That binding and digest
matching are not authentication or a Python sandbox.
"""
from dataclasses import dataclass
import json

from .bootstrap import TeamWorkflow, Denied, bounded_text, canonical, digest, identifier


VERSION = "offline-team-execution/1"


@dataclass(frozen=True)
class ExecutionClaim:
    """Inert input bytes for one synthetic dispatch, not a permission token."""

    body: str
    digest: str

    def to_dict(self):
        # Return a copy: mutating an adapter's view never rewrites the commitment.
        return json.loads(self.body)


class ExecutionLedger:
    """Borrow one TeamWorkflow connection; its owner remains responsible for close.

    This version deliberately integrates with the rebuilt-r1 trusted local API.
    Schema and private-helper changes require a new compatibility review. It adds
    no external authority to a team start, and must not wrap a live provider.
    """

    def __init__(self, workflow):
        if type(workflow) is not TeamWorkflow:
            raise Denied("Expected exact trusted team workflow")
        self._w = workflow
        if workflow._meta("version") != "rebuilt-r1":
            raise Denied("Unsupported team workflow version")
        with workflow._transaction():
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS execution_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                version TEXT NOT NULL, context TEXT NOT NULL)""")
            previous = workflow.db.execute("SELECT * FROM execution_meta").fetchone()
            if previous:
                if previous["version"] != VERSION or previous["context"] != workflow.context:
                    raise Denied("Execution ledger belongs to another version or context")
            else:
                workflow.db.execute("INSERT INTO execution_meta VALUES(1,?,?)",
                                    (VERSION, workflow.context))
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS execution_runs(
                id TEXT PRIMARY KEY,
                task_id TEXT UNIQUE NOT NULL REFERENCES tasks(id),
                actor TEXT NOT NULL,
                artifact_id TEXT UNIQUE NOT NULL,
                request_id TEXT NOT NULL,
                start_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN
                    ('prepared','uncertain','result_recorded','published')),
                claim TEXT, claim_digest TEXT,
                result TEXT, result_digest TEXT,
                artifact_digest TEXT)""")

    def facade(self, agent_id):
        self._w.facade(agent_id)  # Same trusted binding check as the team API.
        return ExecutionFacade(self, agent_id)

    def _run(self, actor, run_id):
        row = self._w.db.execute("SELECT * FROM execution_runs WHERE id=?",
                                 (identifier(run_id),)).fetchone()
        if not row or row["actor"] != actor:
            raise Denied("Unknown execution for this bound agent")
        return row

    def _current(self, row):
        """Recheck authoritative local state in the caller's transaction."""
        w = self._w
        w._live()
        task = w._task(row["task_id"])
        state = w._row(task.id)
        request = w._request(row["request_id"])
        if (task.assignee != row["actor"] or state["state"] != "running"
                or state["request_id"] != row["request_id"]
                or request["state"] != "started"
                or request["digest"] != row["start_digest"]
                or digest(w._start_review(task)) != row["start_digest"]):
            raise Denied("Execution no longer matches a running approved task")
        return task

    def _status(self, row):
        w = self._w
        return {"run_id": row["id"], "task_id": row["task_id"],
                "state": row["state"], "task_state": w._row(row["task_id"])["state"],
                "lead_state": w._meta("lead"), "artifact_id": row["artifact_id"],
                "claim_digest": row["claim_digest"], "result_digest": row["result_digest"],
                "artifact_digest": row["artifact_digest"],
                "retry_allowed": False, "synthetic_only": True}

    def _prepare(self, actor, task_id, run_id, artifact_id):
        w = self._w
        identifier(run_id)
        identifier(artifact_id)
        task = w._task(task_id)
        if task.assignee != actor:
            raise Denied("Only the bound assignee can prepare execution")
        with w._transaction():
            old = w.db.execute("SELECT * FROM execution_runs WHERE id=?", (run_id,)).fetchone()
            if old:
                if (old["actor"], old["task_id"], old["artifact_id"]) != (actor, task_id, artifact_id):
                    raise Denied("Execution ID cannot change meaning")
                return self._status(old)
            if w.db.execute("SELECT 1 FROM execution_runs WHERE task_id=? OR artifact_id=?",
                            (task_id, artifact_id)).fetchone():
                raise Denied("Task and output are already bound to one execution")
            if w.db.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact_id,)).fetchone():
                raise Denied("Execution output ID must be unused")
            state = w._row(task_id)
            if state["request_id"] is None:
                raise Denied("Task has no approved start")
            request = w._request(state["request_id"])
            row = {"actor": actor, "task_id": task_id, "request_id": request["id"],
                   "start_digest": request["digest"]}
            self._current(row)
            w.db.execute("""INSERT INTO execution_runs
                (id,task_id,actor,artifact_id,request_id,start_digest,state)
                VALUES(?,?,?,?,?,?,'prepared')""",
                (run_id, task_id, actor, artifact_id, request["id"], request["digest"]))
            w._event("execution_prepared", run=run_id, task=task_id, actor=actor)
            return self._status(self._run(actor, run_id))

    def _claim(self, actor, run_id):
        """Commit uncertainty BEFORE returning inputs. Never reissue a claim.

        A crash immediately after commit may mean no computation happened. The
        ledger cannot distinguish that from a lost response; neither permits a
        second dispatch. A retained original result may be reconciled instead.
        """
        w = self._w
        with w._transaction():
            row = self._run(actor, run_id)
            if row["state"] != "prepared":
                raise Denied("Execution already claimed; reconcile, never redispatch")
            task = self._current(row)
            inputs = []
            for item in w._inputs(task):
                artifact = w._artifact(item["artifact_id"])
                inputs.append({**item, "artifact": json.loads(artifact["body"]),
                               "untrusted_content": True})
                if actor != artifact["producer"]:
                    w.db.execute("""UPDATE disclosures SET reads=reads+1
                        WHERE artifact_id=? AND recipient=? AND purpose=?""",
                        (artifact["id"], actor, "task:" + task.id))
            body = {"domain": VERSION, "context": w.context, "run_id": run_id,
                    "agent": w.agents[actor].to_dict(), "task": task.to_dict(),
                    "request_id": row["request_id"], "start_review_digest": row["start_digest"],
                    "artifact_id": row["artifact_id"], "inputs": inputs,
                    "synthetic_only": True, "external_actions_allowed": False,
                    "untrusted_content": True}
            encoded, commitment = canonical(body), digest(body)
            w.db.execute("UPDATE execution_runs SET state='uncertain',claim=?,claim_digest=? WHERE id=?",
                         (encoded, commitment, run_id))
            w._event("execution_claimed", run=run_id, task=task.id, digest=commitment)
        return ExecutionClaim(encoded, commitment)

    def _record_result(self, actor, run_id, claim_digest, content):
        """Record an original result, even after revocation, without publishing it.

        A matching digest authenticates no provider. This is a trusted synthetic
        adapter receipt. No exception, timeout or reported failure resets a run.
        """
        bounded_text(content, 8192)
        w = self._w
        with w._transaction():
            row = self._run(actor, run_id)
            if (type(claim_digest) is not str or not row["claim_digest"]
                    or claim_digest != row["claim_digest"]):
                raise Denied("Result does not match the exact execution claim")
            result = canonical({"domain": VERSION + "/result", "run_id": run_id,
                                "claim_digest": claim_digest, "content": content})
            if row["result"] is not None:
                if row["result"] != result:
                    raise Denied("Execution result is immutable")
                return self._status(row)
            if row["state"] != "uncertain":
                raise Denied("Execution has not been claimed")
            commitment = digest(json.loads(result))
            w.db.execute("UPDATE execution_runs SET state='result_recorded',result=?,result_digest=? WHERE id=?",
                         (result, commitment, run_id))
            w._event("execution_result_recorded", run=run_id, digest=commitment)
            return self._status(self._run(actor, run_id))

    def _publish(self, actor, run_id):
        """Idempotently submit inert text to the existing local review gate.

        Team submission and ledger bookkeeping are separate transactions. A
        crash between them is reconciled ONLY against the exact immutable local
        artifact; it does not call a provider or create another output.
        """
        w = self._w
        with w._transaction():
            row = self._run(actor, run_id)
            if row["state"] == "published":
                return self._status(row)
            if row["state"] != "result_recorded":
                raise Denied("No recorded result to publish")
            content = json.loads(row["result"])["content"]
            existing = w.db.execute("SELECT * FROM artifacts WHERE id=?", (row["artifact_id"],)).fetchone()
            if not existing:
                self._current(row)
            # For an existing output, the team API compares the entire immutable
            # body below. Do not overwrite, accept, re-disclose or revive it.
        submitted = w.facade(actor).submit(row["task_id"], row["artifact_id"], content)
        with w._transaction():
            current = self._run(actor, run_id)
            if current["state"] != "published":
                w.db.execute("UPDATE execution_runs SET state='published',artifact_digest=? WHERE id=?",
                             (submitted["digest"], run_id))
                w._event("execution_artifact_recorded", run=run_id, artifact=row["artifact_id"],
                         digest=submitted["digest"])
            return self._status(self._run(actor, run_id))


class ExecutionFacade:
    """A trusted composition's bound local API, not an owner-approval API."""

    def __init__(self, ledger, agent_id):
        self._ledger, self._agent = ledger, agent_id

    def prepare(self, task_id, run_id, artifact_id):
        return self._ledger._prepare(self._agent, task_id, run_id, artifact_id)

    def claim(self, run_id):
        return self._ledger._claim(self._agent, run_id)

    def record_result(self, run_id, claim_digest, content):
        return self._ledger._record_result(self._agent, run_id, claim_digest, content)

    def publish(self, run_id):
        return self._ledger._publish(self._agent, run_id)

    def status(self, run_id):
        with self._ledger._w._transaction():
            return self._ledger._status(self._ledger._run(self._agent, run_id))
