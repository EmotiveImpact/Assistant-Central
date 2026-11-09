"""Owner-scoped provider disclosure rehearsal. No provider is invoked here.

All controls and state are trusted local fiction, not human authentication or a
security boundary against code sharing this interpreter/database. Only synthetic
input may enter this module. A returned release remains inert local test data.
"""
from dataclasses import asdict, dataclass
import json

from .bootstrap import Denied, bounded_text, canonical, digest, identifier
from .ledger import ExecutionLedger


VERSION = "offline-provider-disclosure/1"


@dataclass(frozen=True)
class ProviderRoute:
    """Exact unverified destination labels and policy text, never credentials."""

    provider: str
    account_ref: str
    model_ref: str
    data_policy: str

    def __post_init__(self):
        bounded_text(self.provider, 64)
        identifier(self.account_ref)
        bounded_text(self.model_ref, 128)
        bounded_text(self.data_policy, 1024)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProviderRelease:
    """One exact synthetic payload. This is not authorization for external I/O."""

    body: str
    digest: str

    def to_dict(self):
        return json.loads(self.body)


class ProviderGate:
    """Compose owner-specific disclosure and the execution fence atomically.

    Owner methods MUST remain trusted harness controls, never model tools. Use
    only this bound facade for this lane; the original ledger remains a separate
    local fixture, not a provider API. Labels/digests authenticate nobody.
    """

    def __init__(self, ledger):
        if type(ledger) is not ExecutionLedger:
            raise Denied("Expected exact trusted execution ledger")
        self._ledger, self._w = ledger, ledger._w
        w = self._w
        with w._transaction():
            w.db.execute("""CREATE TABLE IF NOT EXISTS provider_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                version TEXT NOT NULL, context TEXT NOT NULL)""")
            old = w.db.execute("SELECT * FROM provider_meta").fetchone()
            if old:
                if old["version"] != VERSION or old["context"] != w.context:
                    raise Denied("Provider gate belongs to another version or context")
            else:
                w.db.execute("INSERT INTO provider_meta VALUES(1,?,?)", (VERSION, w.context))
            w.db.execute("""CREATE TABLE IF NOT EXISTS provider_requests(
                run_id TEXT PRIMARY KEY REFERENCES execution_runs(id),
                actor TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','released')),
                release_digest TEXT)""")
            w.db.execute("""CREATE TABLE IF NOT EXISTS provider_decisions(
                run_id TEXT NOT NULL REFERENCES provider_requests(run_id),
                owner TEXT NOT NULL, review TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','approved','refused','revoked')),
                expires REAL, PRIMARY KEY(run_id,owner))""")

    def facade(self, agent_id):
        self._ledger.facade(agent_id)
        return ProviderFacade(self, agent_id)

    def _request(self, run_id, actor=None):
        row = self._w.db.execute("SELECT * FROM provider_requests WHERE run_id=?",
                                 (identifier(run_id),)).fetchone()
        if not row or (actor is not None and row["actor"] != actor):
            raise Denied("Unknown provider request for this caller")
        return row

    def _owner_row(self, owner, run_id):
        self._w._owner(owner)
        row = self._w.db.execute("SELECT * FROM provider_decisions WHERE run_id=? AND owner=?",
                                 (identifier(run_id), owner)).fetchone()
        if not row:
            raise Denied("Owner has no data in this exact provider request")
        return row

    def _body_locked(self, actor, run_id, route):
        if type(route) is not ProviderRoute:
            raise Denied("Expected exact immutable provider route")
        w = self._w
        claim = self._ledger._claim_body_locked(actor, self._ledger._run(actor, run_id))
        if route.provider != claim["agent"]["provider"]:
            raise Denied("Provider route must match the exact assigned agent")
        inputs, input_owners = [], []
        for item in claim["inputs"]:
            inputs.append({"artifact_id": item["artifact_id"], "content": item["artifact"]["content"]})
            input_owners.append({"artifact_id": item["artifact_id"], "digest": item["digest"],
                                 "owner": w.agents[item["artifact"]["producer"]].owner})
        payload = {"domain": VERSION + "/payload", "context": w.context, "run_id": run_id,
                   "recipient": route.to_dict(), "task_id": claim["task"]["id"],
                   "output_kind": claim["task"]["output_kind"],
                   "task_text": claim["task"]["objective"], "inputs": inputs,
                   "synthetic_only": True, "external_actions_allowed": False,
                   "untrusted_content": True, "tool_permissions": [], "spend_limit": 0}
        return {"domain": VERSION, "claim_digest": digest(claim), "payload": payload,
                "task_owner": claim["agent"]["owner"], "input_owners": input_owners}

    @staticmethod
    def _review(body, owner):
        payload = body["payload"]
        own_ids = {item["artifact_id"] for item in body["input_owners"] if item["owner"] == owner}
        owned_data = {"inputs": [item for item in payload["inputs"] if item["artifact_id"] in own_ids]}
        if owner == body["task_owner"]:
            owned_data["task_text"] = payload["task_text"]
        # Other owners' text is not part of this owner's preview. Shared metadata
        # and full-payload hashes bind all decisions to one immutable request.
        common = {key: value for key, value in payload.items() if key not in ("task_text", "inputs")}
        return {"domain": VERSION + "/owner-review", "owner": owner,
                "request_digest": digest(body), "payload_digest": digest(payload),
                "common_metadata": common, "owned_data": owned_data,
                "scope": "This owner's listed data, once, for this exact synthetic task and route",
                "human_authentication": False, "live_provider_permission": False}

    def _current_locked(self, request):
        body = json.loads(request["body"])
        route = ProviderRoute(**body["payload"]["recipient"])
        current = self._body_locked(request["actor"], request["run_id"], route)
        if canonical(current) != request["body"] or digest(current) != request["digest"]:
            raise Denied("Provider request no longer matches the exact execution inputs")
        return body

    def _status_locked(self, request):
        w = self._w
        now = w._now()
        decisions = []
        for row in w.db.execute("SELECT * FROM provider_decisions WHERE run_id=? ORDER BY owner",
                                (request["run_id"],)):
            state = row["state"]
            if state == "approved" and row["expires"] <= now:
                state = "expired"
            decisions.append({"owner": row["owner"], "state": state, "expires": row["expires"]})
        return {"run_id": request["run_id"], "request_digest": request["digest"],
                "state": request["state"], "decisions": decisions,
                "release_digest": request["release_digest"],
                "execution": self._ledger._status(self._ledger._run(request["actor"], request["run_id"])),
                "retry_allowed": False, "synthetic_only": True, "external_actions_allowed": False}

    def _propose(self, actor, run_id, route):
        w = self._w
        if type(route) is not ProviderRoute:
            raise Denied("Expected exact immutable provider route")
        with w._transaction():
            self._ledger._run(actor, run_id)
            old = w.db.execute("SELECT * FROM provider_requests WHERE run_id=?", (run_id,)).fetchone()
            if old:
                if json.loads(old["body"])["payload"]["recipient"] != route.to_dict():
                    raise Denied("Provider route is immutable; no aliases or replacement requests")
                return self._status_locked(old)
            body = self._body_locked(actor, run_id, route)
            w.db.execute("INSERT INTO provider_requests VALUES(?,?,?,?,'pending',NULL)",
                         (run_id, actor, canonical(body), digest(body)))
            owners = sorted({body["task_owner"], *(item["owner"] for item in body["input_owners"])})
            for owner in owners:
                review = self._review(body, owner)
                w.db.execute("INSERT INTO provider_decisions VALUES(?,?,?,?,'pending',NULL)",
                             (run_id, owner, canonical(review), digest(review)))
            w._event("provider_disclosure_proposed", run=run_id, digest=digest(body))
            return self._status_locked(self._request(run_id, actor))

    def owner_review(self, owner, run_id, *, expected_context):
        self._w._check(expected_context)
        with self._w._transaction():
            row = self._owner_row(owner, run_id)
            state = row["state"]
            if state == "approved" and row["expires"] <= self._w._now():
                state = "expired"
            return {"review": json.loads(row["review"]), "review_digest": row["digest"],
                    "state": state, "expires": row["expires"]}

    def decide(self, owner, run_id, review_digest, decision, *, expected_context, expires=None):
        w = self._w
        w._check(expected_context)
        if decision not in ("approve", "refuse"):
            raise Denied("Unsupported provider disclosure decision")
        with w._transaction():
            row = self._owner_row(owner, run_id)
            request = self._request(run_id)
            if review_digest != row["digest"] or type(review_digest) is not str:
                raise Denied("Wrong owner or stale provider disclosure review")
            if row["state"] != "pending" or request["state"] != "pending":
                raise Denied("Provider disclosure is already decided; cannot renew or retry")
            if decision == "approve":
                w._expiry(expires)
                self._current_locked(request)
            elif expires is not None:
                raise Denied("A refusal cannot grant an expiry")
            state = "approved" if decision == "approve" else "refused"
            w.db.execute("UPDATE provider_decisions SET state=?,expires=? WHERE run_id=? AND owner=?",
                         (state, expires, run_id, owner))
            w._event("provider_disclosure_decided", run=run_id, owner=owner,
                     decision=state, review_digest=review_digest)
            return self._status_locked(request)

    def revoke(self, owner, run_id, *, expected_context):
        """Withdraw future release, even before approval; never claim recall."""
        w = self._w
        w._check(expected_context)
        with w._transaction():
            row = self._owner_row(owner, run_id)
            if row["state"] not in ("revoked", "refused"):
                w.db.execute("UPDATE provider_decisions SET state='revoked' WHERE run_id=? AND owner=?",
                             (run_id, owner))
                w._event("provider_disclosure_revoked", run=run_id, owner=owner,
                         already_released=self._request(run_id)["state"] == "released")
            return self._status_locked(self._request(run_id))

    def _release(self, actor, run_id):
        w = self._w
        with w._transaction():
            request = self._request(run_id, actor)
            if request["state"] != "pending":
                raise Denied("Payload may already be released; never redispatch")
            body = self._current_locked(request)
            now = w._now()
            for owner in sorted({body["task_owner"], *(item["owner"] for item in body["input_owners"])}):
                row = self._owner_row(owner, run_id)
                if (row["state"] != "approved" or row["expires"] <= now
                        or row["review"] != canonical(self._review(body, owner))
                        or row["digest"] != digest(self._review(body, owner))):
                    raise Denied("Every data owner must approve the current exact provider disclosure")
            claim = self._ledger._claim_locked(actor, run_id)
            if claim.digest != body["claim_digest"]:
                raise Denied("Execution commitment changed before provider release")
            release = {"domain": VERSION + "/release", "request_digest": request["digest"],
                       "claim_digest": claim.digest, "payload": body["payload"]}
            commitment = digest(release)
            w.db.execute("UPDATE provider_requests SET state='released',release_digest=? WHERE run_id=?",
                         (commitment, run_id))
            w._event("provider_payload_released_locally", run=run_id, digest=commitment)
        # Both uncertainty and the disclosure decision commit BEFORE returning.
        return ProviderRelease(canonical(release), commitment)

    def _record_result(self, actor, run_id, release_digest, content):
        with self._w._transaction():
            request = self._request(run_id, actor)
            if (request["state"] != "released" or type(release_digest) is not str
                    or request["release_digest"] != release_digest):
                raise Denied("Result must match the original exact provider release")
            claim_digest = json.loads(request["body"])["claim_digest"]
        # Original receipts may be retained after revocation. This does not call
        # any adapter, admit an artifact, or restore disclosure permission.
        return self._ledger._record_result(actor, run_id, claim_digest, content)


class ProviderFacade:
    """Bound synthetic route. No owner controls, provider callbacks or discovery."""

    def __init__(self, gate, agent_id):
        self._gate, self._agent = gate, agent_id

    def propose(self, run_id, route):
        return self._gate._propose(self._agent, run_id, route)

    def release(self, run_id):
        return self._gate._release(self._agent, run_id)

    def record_result(self, run_id, release_digest, content):
        return self._gate._record_result(self._agent, run_id, release_digest, content)

    def status(self, run_id):
        with self._gate._w._transaction():
            return self._gate._status_locked(self._gate._request(run_id, self._agent))
