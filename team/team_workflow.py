"""New offline team orchestration fixture. No network, tools, or human authentication.

Owner methods are trusted harness controls, never assistant tools. AgentFacade is
a deliberately bound API, not a sandbox. Artifact text is always inert data.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import re
import sqlite3
import time


class Denied(ValueError):
    pass


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise Denied("Invalid identifier")
    return value


def bounded_text(value, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise Denied("Invalid bounded text")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise Denied("Invalid Unicode") from exc
    return value


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied("Expected finite JSON") from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def id_tuple(value, maximum=20):
    if type(value) not in (tuple, list) or len(value) > maximum:
        raise Denied("Invalid identifier list")
    result = tuple(identifier(x) for x in value)
    if len(set(result)) != len(result):
        raise Denied("Duplicate identifier")
    return result


KINDS = ("research", "copy", "slides", "website", "pr-draft")
TERMINAL = ("completed", "refused", "revoked", "stopped")


@dataclass(frozen=True)
class AgentRef:
    id: str
    owner: str
    provider: str
    specialty: str

    def __post_init__(self):
        identifier(self.id)
        identifier(self.owner)
        bounded_text(self.provider, 64)
        bounded_text(self.specialty, 128)

    def to_dict(self):
        return dict(id=self.id, owner=self.owner, provider=self.provider, specialty=self.specialty)


@dataclass(frozen=True)
class TaskSpec:
    id: str
    assignee: str
    objective: str
    output_kind: str
    dependencies: tuple = ()
    resources: tuple = ()

    def __post_init__(self):
        identifier(self.id)
        identifier(self.assignee)
        bounded_text(self.objective, 512)
        if type(self.output_kind) is not str or self.output_kind not in KINDS:
            raise Denied("Unsupported inert output kind")
        object.__setattr__(self, "dependencies", id_tuple(self.dependencies))
        object.__setattr__(self, "resources", id_tuple(self.resources, 8))
        if self.id in self.dependencies:
            raise Denied("Task cannot depend on itself")

    def to_dict(self):
        return dict(id=self.id, assignee=self.assignee, objective=self.objective,
                    output_kind=self.output_kind, dependencies=list(self.dependencies),
                    resources=list(self.resources))


@dataclass(frozen=True)
class TeamPlan:
    id: str
    lead: str
    agents: tuple
    tasks: tuple

    def __post_init__(self):
        identifier(self.id)
        identifier(self.lead)
        if type(self.agents) not in (tuple, list) or type(self.tasks) not in (tuple, list):
            raise Denied("Expected immutable plan sequences")
        object.__setattr__(self, "agents", tuple(self.agents))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if not 2 <= len(self.agents) <= 20 or any(type(a) is not AgentRef for a in self.agents):
            raise Denied("Need 2–20 exact agent references")
        if not 1 <= len(self.tasks) <= 20 or any(type(t) is not TaskSpec for t in self.tasks):
            raise Denied("Need 1–20 exact task specifications")
        agents = {a.id: a for a in self.agents}
        tasks = {t.id: t for t in self.tasks}
        if len(agents) != len(self.agents) or len(tasks) != len(self.tasks):
            raise Denied("Duplicate plan identifiers")
        if self.lead not in agents or len({a.owner for a in self.agents}) > 10:
            raise Denied("Invalid nominated lead or owner count")
        for task in self.tasks:
            if task.assignee not in agents or not set(task.dependencies) <= tasks.keys():
                raise Denied("Unknown assignee or dependency")
        seen, visiting = set(), set()

        def visit(task_id):
            if task_id in visiting:
                raise Denied("Dependency cycle")
            if task_id not in seen:
                visiting.add(task_id)
                for dependency in tasks[task_id].dependencies:
                    visit(dependency)
                visiting.remove(task_id)
                seen.add(task_id)
        for task_id in tasks:
            visit(task_id)

    def to_dict(self):
        return dict(id=self.id, lead=self.lead, agents=[a.to_dict() for a in self.agents],
                    tasks=[t.to_dict() for t in self.tasks])

    @property
    def context(self):
        return digest({"domain": "offline-team-plan/rebuilt-r1", "plan": self.to_dict()})


class TeamWorkflow:
    """Trusted local owner service. Persisted labels do not authenticate humans."""
    def __init__(self, database, plan, *, clock=time.time):
        if type(plan) is not TeamPlan:
            raise Denied("Expected exact immutable team plan")
        self.plan = plan
        self.context = plan.context
        self.agents = {a.id: a for a in plan.agents}
        self.tasks = {t.id: t for t in plan.tasks}
        self.clock = clock
        self.db = sqlite3.connect(database, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, state TEXT NOT NULL,
            request_id TEXT, artifact_id TEXT, source_scope TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, task_id TEXT UNIQUE NOT NULL,
            review TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, expires REAL);
        CREATE TABLE IF NOT EXISTS aliases(actor TEXT NOT NULL, id TEXT NOT NULL,
            request_id TEXT NOT NULL, task_id TEXT NOT NULL, PRIMARY KEY(actor,id));
        CREATE TABLE IF NOT EXISTS scopes(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
            body TEXT NOT NULL, expires REAL NOT NULL, max_uses INTEGER NOT NULL,
            uses INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS locks(resource TEXT PRIMARY KEY, task_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
            producer TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS disclosures(artifact_id TEXT NOT NULL, recipient TEXT NOT NULL,
            purpose TEXT NOT NULL, review_digest TEXT NOT NULL, state TEXT NOT NULL,
            reads INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(artifact_id,recipient,purpose));
        CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL, data TEXT NOT NULL);
        """)
        try:
            with self._transaction():
                old = self.db.execute("SELECT value FROM meta WHERE key='context'").fetchone()
                if old:
                    if (old[0] != self.context or self._meta("plan") != canonical(plan.to_dict())
                            or self._meta("version") != "rebuilt-r1"):
                        raise Denied("Database belongs to another immutable plan")
                else:
                    self.db.executemany("INSERT INTO meta VALUES(?,?)", [
                        ("context", self.context), ("plan", canonical(plan.to_dict())),
                        ("lead", "pending"), ("version", "rebuilt-r1")])
                    self.db.executemany("INSERT INTO tasks(id,state) VALUES(?,'planned')",
                                        [(t.id,) for t in plan.tasks])
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()

    def _meta(self, key):
        return self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0]

    def _check(self, expected_context):
        if type(expected_context) is not str or expected_context != self.context:
            raise Denied("Exact team context required")

    def _owner(self, owner):
        identifier(owner)
        if owner not in {a.owner for a in self.plan.agents}:
            raise Denied("Unknown owner")

    def _task(self, task_id):
        identifier(task_id)
        if task_id not in self.tasks:
            raise Denied("Unknown task")
        return self.tasks[task_id]

    def _task_owner(self, task_id):
        return self.agents[self._task(task_id).assignee].owner

    def _row(self, task_id):
        self._task(task_id)
        return self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

    def _request(self, request_id):
        identifier(request_id)
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise Denied("Unknown start request")
        return row

    def _artifact(self, artifact_id):
        identifier(artifact_id)
        row = self.db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise Denied("Unknown artifact")
        return row

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise Denied("Invalid clock")
        return now

    def _expiry(self, expires):
        now = self._now()
        if type(expires) not in (int, float) or not math.isfinite(expires) or not now < expires <= now + 3600:
            raise Denied("Permission must expire within one hour")

    def _event(self, event, **data):
        if self.db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= 10000:
            raise Denied("Audit capacity reached")
        self.db.execute("INSERT INTO audit(event,data) VALUES(?,?)", (event, canonical(data)))

    def accept_lead(self, owner, *, expected_context):
        self._check(expected_context)
        if owner != self.agents[self.plan.lead].owner:
            raise Denied("Only nominated lead's owner can accept")
        with self._transaction():
            state = self._meta("lead")
            if state == "withdrawn":
                raise Denied("Lead participation is terminally withdrawn")
            if state == "pending":
                self.db.execute("UPDATE meta SET value='accepted' WHERE key='lead'")
                self._event("lead_accepted", owner=owner, lead=self.plan.lead)
        return self.snapshot()

    def withdraw_lead(self, owner, *, expected_context):
        self._check(expected_context)
        if owner != self.agents[self.plan.lead].owner:
            raise Denied("Only nominated lead's owner can withdraw")
        with self._transaction():
            if self._meta("lead") != "withdrawn":
                self.db.execute("UPDATE meta SET value='withdrawn' WHERE key='lead'")
                self.db.execute("UPDATE disclosures SET state='revoked' WHERE recipient=? AND purpose='lead-review'", (self.plan.lead,))
                for task_id in self.tasks:
                    if self._row(task_id)["state"] not in TERMINAL:
                        self._stop(task_id, "stopped", "lead_withdrawn")
                self._event("lead_withdrawn", owner=owner)

    def facade(self, agent_id):
        identifier(agent_id)
        if agent_id not in self.agents:
            raise Denied("Unknown bound agent")
        return AgentFacade(self, agent_id)

    def _live(self):
        if self._meta("lead") != "accepted":
            raise Denied("Nominated lead has not accepted or has withdrawn")

    def _access(self, artifact, actor, purpose):
        if artifact["producer"] == actor:
            return True
        row = self.db.execute("SELECT state FROM disclosures WHERE artifact_id=? AND recipient=? AND purpose=?",
                              (artifact["id"], actor, purpose)).fetchone()
        return bool(row and row[0] == "granted")

    def _inputs(self, task):
        inputs = []
        for dependency in task.dependencies:
            source = self._row(dependency)
            if source["state"] != "completed" or not source["artifact_id"]:
                raise Denied("Dependency has not completed lead review")
            artifact = self._artifact(source["artifact_id"])
            if artifact["state"] != "accepted" or not self._access(artifact, task.assignee, "task:" + task.id):
                raise Denied("Exact dependency artifact has not been disclosed to this agent/task")
            inputs.append({"task": dependency, "artifact_id": artifact["id"], "digest": artifact["digest"]})
        return inputs

    def _start_review(self, task):
        return {"domain": "offline-team-start/rebuilt-r1", "context": self.context,
                "owner": self._task_owner(task.id), "task": task.to_dict(), "inputs": self._inputs(task)}

    def _request_status(self, row):
        return {"request_id": row["id"], "task_id": row["task_id"], "state": row["state"],
                "review_digest": row["digest"], "review": json.loads(row["review"]), "expires": row["expires"]}

    def _propose_start(self, actor, task_id, proposal_id):
        identifier(proposal_id)
        task = self._task(task_id)
        if task.assignee != actor:
            raise Denied("Agent cannot propose another agent's work")
        with self._transaction():
            alias = self.db.execute("SELECT * FROM aliases WHERE actor=? AND id=?", (actor, proposal_id)).fetchone()
            if alias:
                if alias["task_id"] != task_id:
                    raise Denied("Proposal ID was already used for another task")
                return self._request_status(self._request(alias["request_id"]))
            if self.db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] >= 256:
                raise Denied("Proposal alias capacity reached")
            existing = self.db.execute("SELECT * FROM requests WHERE task_id=?", (task_id,)).fetchone()
            if existing:
                request_id = existing["id"]
            else:
                self._live()
                if self._row(task_id)["state"] != "planned":
                    raise Denied("Task cannot create a new start request")
                review = self._start_review(task)
                request_id = "start-" + digest({"context": self.context, "task": task_id})[:48]
                self.db.execute("INSERT INTO requests VALUES(?,?,?,?,?,NULL)",
                                (request_id, task_id, canonical(review), digest(review), "pending"))
                self.db.execute("UPDATE tasks SET state='awaiting_approval',request_id=? WHERE id=?", (request_id, task_id))
                self._event("start_proposed", actor=actor, task=task_id, request=request_id)
            self.db.execute("INSERT INTO aliases VALUES(?,?,?,?)", (actor, proposal_id, request_id, task_id))
            return self._request_status(self._request(request_id))

    def decide_start(self, owner, request_id, review_digest, decision, *, expected_context, expires=None):
        self._check(expected_context)
        if decision not in ("approve", "refuse"):
            raise Denied("Unsupported owner decision")
        with self._transaction():
            request = self._request(request_id)
            task_id = request["task_id"]
            if owner != self._task_owner(task_id) or review_digest != request["digest"]:
                raise Denied("Wrong owner or stale exact review")
            if request["state"] != "pending":
                raise Denied("Start request already decided")
            self._live()
            if digest(self._start_review(self._task(task_id))) != review_digest:
                raise Denied("Start review inputs changed")
            if decision == "approve":
                self._expiry(expires)
                self.db.execute("UPDATE requests SET state='approved',expires=? WHERE id=?", (expires, request_id))
                self.db.execute("UPDATE tasks SET state='approved' WHERE id=?", (task_id,))
            else:
                self._stop(task_id, "refused", "owner_refused")
            self._event("start_" + decision, owner=owner, task=task_id, review=review_digest)

    def grant_scope(self, owner, scope_id, task_ids, *, max_uses, expires, expected_context):
        self._check(expected_context)
        self._owner(owner)
        identifier(scope_id)
        task_ids = id_tuple(task_ids)
        if not task_ids or any(self._task_owner(t) != owner for t in task_ids):
            raise Denied("Scope must name only this owner's exact tasks")
        if type(max_uses) is not int or not 1 <= max_uses <= len(task_ids):
            raise Denied("Invalid scoped use limit")
        self._expiry(expires)
        body = {"domain": "offline-team-work-scope/rebuilt-r1", "context": self.context, "owner": owner,
                "tasks": [self._task(t).to_dict() for t in task_ids], "max_uses": max_uses, "expires": expires}
        with self._transaction():
            self._live()
            old = self.db.execute("SELECT * FROM scopes WHERE id=?", (scope_id,)).fetchone()
            if old:
                if old["body"] != canonical(body):
                    raise Denied("Scope ID cannot change meaning")
                return self.scope_status(owner, scope_id, expected_context=expected_context)
            if any(self._row(t)["state"] in TERMINAL for t in task_ids):
                raise Denied("Cannot grant authority over terminal work")
            if self.db.execute("SELECT COUNT(*) FROM scopes").fetchone()[0] >= 64:
                raise Denied("Scope capacity reached")
            self.db.execute("INSERT INTO scopes(id,owner,body,expires,max_uses,state) VALUES(?,?,?,?,?,'active')",
                            (scope_id, owner, canonical(body), expires, max_uses))
            self._event("scope_granted", owner=owner, scope=scope_id, tasks=list(task_ids))
            return self.scope_status(owner, scope_id, expected_context=expected_context)

    def scope_status(self, owner, scope_id, *, expected_context):
        self._check(expected_context)
        row = self.db.execute("SELECT * FROM scopes WHERE id=?", (identifier(scope_id),)).fetchone()
        if not row or row["owner"] != owner:
            raise Denied("Unknown owner scope")
        return {"scope_id": scope_id, "state": row["state"], "uses": row["uses"],
                "max_uses": row["max_uses"], "expires": row["expires"], "scope": json.loads(row["body"])}

    def revoke_scope(self, owner, scope_id, *, expected_context):
        self._check(expected_context)
        with self._transaction():
            self.scope_status(owner, scope_id, expected_context=expected_context)
            if self.db.execute("SELECT state FROM scopes WHERE id=?", (scope_id,)).fetchone()[0] == "revoked":
                return
            self.db.execute("UPDATE scopes SET state='revoked' WHERE id=?", (scope_id,))
            rows = self.db.execute("SELECT id,state FROM tasks WHERE source_scope=?", (scope_id,)).fetchall()
            for row in rows:
                if row["state"] not in TERMINAL:
                    self._stop(row["id"], "revoked", "scope_revoked")
            self._event("scope_revoked", owner=owner, scope=scope_id)

    def _start(self, actor, request_id, scope_id=None):
        with self._transaction():
            request = self._request(request_id)
            task = self._task(request["task_id"])
            if task.assignee != actor:
                raise Denied("Wrong bound assignee")
            row = self._row(task.id)
            if request["state"] == "started":
                return {"task_id": task.id, "state": row["state"], "already_started": True}
            self._live()
            if request["state"] not in ("pending", "approved"):
                raise Denied("Refused or revoked requests cannot start")
            if digest(self._start_review(task)) != request["digest"]:
                raise Denied("Start inputs changed")
            for resource in task.resources:
                if self.db.execute("SELECT 1 FROM locks WHERE resource=?", (resource,)).fetchone():
                    raise Denied("Required local resource is in use")
            if scope_id is None:
                if request["state"] != "approved" or request["expires"] <= self._now():
                    raise Denied("Current exact manual approval required")
            else:
                identifier(scope_id)
                scope = self.db.execute("SELECT * FROM scopes WHERE id=?", (scope_id,)).fetchone()
                if (not scope or scope["owner"] != self._task_owner(task.id) or scope["state"] != "active"
                        or scope["expires"] <= self._now() or scope["uses"] >= scope["max_uses"]):
                    raise Denied("Scoped permission is unavailable")
                scoped_tasks = json.loads(scope["body"])["tasks"]
                if task.to_dict() not in scoped_tasks:
                    raise Denied("Task is outside exact scope")
                self.db.execute("UPDATE scopes SET uses=uses+1 WHERE id=?", (scope_id,))
            self.db.executemany("INSERT INTO locks VALUES(?,?)", [(r, task.id) for r in task.resources])
            self.db.execute("UPDATE requests SET state='started' WHERE id=?", (request_id,))
            self.db.execute("UPDATE tasks SET state='running',source_scope=? WHERE id=?", (scope_id, task.id))
            self._event("task_started", actor=actor, task=task.id, request=request_id, scope=scope_id)
            return {"task_id": task.id, "state": "running", "already_started": False}

    def _stop(self, task_id, state, reason):
        self.db.execute("UPDATE tasks SET state=?,reason=? WHERE id=?", (state, reason, task_id))
        self.db.execute("UPDATE requests SET state=? WHERE task_id=?", ("refused" if state == "refused" else "revoked", task_id))
        self.db.execute("DELETE FROM locks WHERE task_id=?", (task_id,))
        self.db.execute("UPDATE disclosures SET state='revoked' WHERE purpose=?", ("task:" + task_id,))
        self.db.execute("UPDATE disclosures SET state='revoked' WHERE artifact_id IN (SELECT id FROM artifacts WHERE task_id=?)", (task_id,))
        for task in self.plan.tasks:
            if task_id in task.dependencies and self._row(task.id)["state"] not in TERMINAL:
                self._stop(task.id, "stopped", "dependency_unavailable")

    def revoke_task(self, owner, task_id, *, expected_context):
        self._check(expected_context)
        if owner != self._task_owner(task_id):
            raise Denied("Only assignee owner can revoke this task")
        with self._transaction():
            if self._row(task_id)["state"] in ("refused", "revoked", "stopped"):
                return
            self._stop(task_id, "revoked", "owner_revoked")
            self._event("task_revoked", owner=owner, task=task_id)

    def _submit(self, actor, task_id, artifact_id, content):
        identifier(artifact_id)
        bounded_text(content, 8192)
        task = self._task(task_id)
        if task.assignee != actor:
            raise Denied("Only the bound assignee can submit")
        request_id = self._row(task_id)["request_id"]
        if request_id is None:
            raise Denied("Task has no start authorization")
        start_review_digest = self._request(request_id)["digest"]
        body = {"domain": "offline-team-artifact/rebuilt-r1", "context": self.context,
                "task": task_id, "producer": actor, "kind": task.output_kind, "content": content,
                "start_review_digest": start_review_digest}
        with self._transaction():
            old = self.db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if old:
                if old["body"] != canonical(body):
                    raise Denied("Artifact ID is immutable")
                return {"artifact_id": artifact_id, "digest": old["digest"], "state": old["state"]}
            self._live()
            if self._row(task_id)["state"] not in ("running", "changes_requested"):
                raise Denied("Task is not accepting a new output")
            self._inputs(task)
            if self.db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] >= 64:
                raise Denied("Artifact capacity reached")
            artifact_digest = digest(body)
            self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,'candidate')", (artifact_id, task_id, actor, canonical(body), artifact_digest))
            self.db.execute("UPDATE tasks SET state='awaiting_review',artifact_id=? WHERE id=?", (artifact_id, task_id))
            self._event("artifact_submitted", actor=actor, task=task_id, artifact=artifact_id, digest=artifact_digest)
            return {"artifact_id": artifact_id, "digest": artifact_digest, "state": "candidate"}

    def _disclosure_review(self, owner, artifact_id, recipient, purpose_task):
        artifact = self._artifact(artifact_id)
        if owner != self.agents[artifact["producer"]].owner or recipient not in self.agents:
            raise Denied("Wrong content owner or unknown recipient")
        if self._row(artifact["task_id"])["state"] in ("revoked", "refused", "stopped"):
            raise Denied("Artifact source has stopped")
        if purpose_task is None:
            if recipient != self.plan.lead:
                raise Denied("Review disclosure must target nominated lead")
            if self._row(artifact["task_id"])["artifact_id"] != artifact_id or artifact["state"] != "candidate":
                raise Denied("Only current candidate can be disclosed for review")
            purpose = "lead-review"
        else:
            target = self._task(purpose_task)
            if target.assignee != recipient or artifact["task_id"] not in target.dependencies:
                raise Denied("Disclosure is outside exact dependency route")
            if (artifact["state"] != "accepted" or self._row(artifact["task_id"])["state"] != "completed"
                    or self._row(purpose_task)["state"] in TERMINAL):
                raise Denied("Only accepted output can enter a live dependent task")
            purpose = "task:" + purpose_task
        review = {"domain": "offline-team-disclosure/rebuilt-r1", "context": self.context,
                  "owner": owner, "artifact_id": artifact_id, "artifact_digest": artifact["digest"],
                  "artifact": json.loads(artifact["body"]), "recipient": self.agents[recipient].to_dict(),
                  "purpose": purpose}
        return review

    def disclosure_review(self, owner, artifact_id, recipient, purpose_task=None, *, expected_context):
        self._check(expected_context)
        with self._transaction():
            self._live()
            review = self._disclosure_review(owner, artifact_id, recipient, purpose_task)
            return {"review": review, "review_digest": digest(review)}

    def approve_disclosure(self, owner, artifact_id, recipient, review_digest, purpose_task=None, *, expected_context):
        self._check(expected_context)
        with self._transaction():
            self._live()
            review = self._disclosure_review(owner, artifact_id, recipient, purpose_task)
            if digest(review) != review_digest:
                raise Denied("Disclosure does not match exact reviewed content and recipient")
            key = (artifact_id, recipient, review["purpose"])
            old = self.db.execute("SELECT * FROM disclosures WHERE artifact_id=? AND recipient=? AND purpose=?", key).fetchone()
            if old:
                if old["state"] == "revoked":
                    raise Denied("Revoked disclosure cannot be renewed in this plan")
                return
            self.db.execute("INSERT INTO disclosures(artifact_id,recipient,purpose,review_digest,state) VALUES(?,?,?,?,'granted')", (*key, review_digest))
            self._event("disclosure_approved", owner=owner, artifact=artifact_id, recipient=recipient, purpose=review["purpose"])

    def revoke_disclosure(self, owner, artifact_id, recipient, purpose_task=None, *, expected_context):
        self._check(expected_context)
        with self._transaction():
            artifact = self._artifact(artifact_id)
            if owner != self.agents[artifact["producer"]].owner:
                raise Denied("Only producer owner can withdraw disclosure")
            purpose = "lead-review" if purpose_task is None else "task:" + identifier(purpose_task)
            key = (artifact_id, identifier(recipient), purpose)
            row = self.db.execute("SELECT * FROM disclosures WHERE artifact_id=? AND recipient=? AND purpose=?", key).fetchone()
            if not row:
                raise Denied("Unknown exact disclosure")
            if row["state"] == "revoked":
                return
            self.db.execute("UPDATE disclosures SET state='revoked' WHERE artifact_id=? AND recipient=? AND purpose=?", key)
            if purpose_task is not None and self._row(purpose_task)["state"] not in TERMINAL:
                self._stop(purpose_task, "stopped", "input_disclosure_revoked")
            self._event("disclosure_revoked", owner=owner, artifact=artifact_id, recipient=recipient, purpose=purpose, prior_reads=row["reads"])

    def _read_artifact(self, actor, artifact_id, purpose_task=None):
        purpose = "lead-review" if purpose_task is None else "task:" + identifier(purpose_task)
        with self._transaction():
            artifact = self._artifact(artifact_id)
            if not self._access(artifact, actor, purpose):
                raise Denied("Exact artifact disclosure is not granted")
            if actor != artifact["producer"]:
                self.db.execute("UPDATE disclosures SET reads=reads+1 WHERE artifact_id=? AND recipient=? AND purpose=?", (artifact_id, actor, purpose))
            return {"artifact_id": artifact_id, "digest": artifact["digest"], "state": artifact["state"],
                    "artifact": json.loads(artifact["body"]), "untrusted_content": True}

    def _review_output(self, actor, task_id, artifact_id, decision):
        if actor != self.plan.lead or decision not in ("accept", "changes"):
            raise Denied("Only nominated lead can make a closed review decision")
        with self._transaction():
            self._live()
            row = self._row(task_id)
            artifact = self._artifact(artifact_id)
            if row["state"] != "awaiting_review" or row["artifact_id"] != artifact_id or artifact["task_id"] != task_id:
                raise Denied("Review target is not the current candidate")
            if not self._access(artifact, actor, "lead-review"):
                raise Denied("Lead has no content disclosure permission")
            self._inputs(self._task(task_id))
            state = "completed" if decision == "accept" else "changes_requested"
            self.db.execute("UPDATE tasks SET state=? WHERE id=?", (state, task_id))
            self.db.execute("UPDATE artifacts SET state=? WHERE id=?", ("accepted" if decision == "accept" else "rejected", artifact_id))
            if decision == "accept":
                self.db.execute("DELETE FROM locks WHERE task_id=?", (task_id,))
            self._event("output_" + decision, lead=actor, task=task_id, artifact=artifact_id)

    def snapshot(self):
        """Trusted operator's metadata-only status, not an assistant discovery tool."""
        return {"context": self.context, "lead": self._meta("lead"),
                "tasks": [dict(r) for r in self.db.execute("SELECT * FROM tasks ORDER BY id")],
                "locks": [dict(r) for r in self.db.execute("SELECT * FROM locks ORDER BY resource")]}


class AgentFacade:
    """Already-bound trusted composition. Does not authenticate arbitrary Python callers."""
    def __init__(self, workflow, agent_id):
        self._workflow, self._agent = workflow, agent_id

    def tasks(self):
        w = self._workflow
        return [{"task": t.to_dict(), "state": w._row(t.id)["state"]}
                for t in w.plan.tasks if t.assignee == self._agent]

    def propose_start(self, task_id, proposal_id):
        return self._workflow._propose_start(self._agent, task_id, proposal_id)

    def start(self, request_id, scope_id=None):
        return self._workflow._start(self._agent, request_id, scope_id)

    def submit(self, task_id, artifact_id, content):
        return self._workflow._submit(self._agent, task_id, artifact_id, content)

    def read_artifact(self, artifact_id, purpose_task=None):
        return self._workflow._read_artifact(self._agent, artifact_id, purpose_task)

    def review_output(self, task_id, artifact_id, decision):
        return self._workflow._review_output(self._agent, task_id, artifact_id, decision)
