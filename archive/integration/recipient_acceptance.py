"""Synthetic release and recipient decisions. No authentication or transport.

Owner controls are trusted construction, never agent tools. All state shares the
team transaction to make local revocation ordering explicit. This is deliberately
not a claim of distributed authority or isolation from the local operator.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json

from .bootstrap import TeamWorkflow, Denied, canonical, digest
from .team_proposals import BoundArtifactProposal, OutcomeUnknown, current_mapping
from execution.lineage import collect_lineage, affected_inputs

VERSION = "offline-recipient-acceptance/1"


@dataclass(frozen=True)
class SyntheticDelivery:
    body: str
    digest: str

    def to_dict(self):
        return json.loads(self.body)


class AcceptanceBoundary:
    """Trusted harness service; distribute only separately bound controls."""

    def __init__(self, workflow):
        if type(workflow) is not TeamWorkflow:
            raise Denied("Expected exact trusted team workflow")
        self._w = workflow
        with workflow._transaction():
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS acceptance_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL,
                context TEXT NOT NULL)""")
            old = workflow.db.execute("SELECT * FROM acceptance_meta").fetchone()
            if old and (old["version"] != VERSION or old["context"] != workflow.context):
                raise Denied("Acceptance boundary version or context mismatch")
            if not old:
                workflow.db.execute("INSERT INTO acceptance_meta VALUES(1,?,?)", (VERSION, workflow.context))
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS acceptance_offers(
                id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL, target_task TEXT NOT NULL,
                body TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','released')),
                delivery TEXT, delivery_digest TEXT, expires REAL,
                UNIQUE(artifact_id,target_task))""")
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS acceptance_sources(
                offer_id TEXT NOT NULL REFERENCES acceptance_offers(id), owner TEXT NOT NULL,
                review TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected','revoked')),
                expires REAL, PRIMARY KEY(offer_id,owner))""")
            workflow.db.execute("""CREATE TABLE IF NOT EXISTS acceptance_inbox(
                offer_id TEXT PRIMARY KEY REFERENCES acceptance_offers(id),
                delivery_digest TEXT NOT NULL, review_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','accepted','rejected')),
                decision_digest TEXT)""")

    @contextmanager
    def _mutation(self):
        try:
            with self._w._transaction():
                yield
        except Denied:
            raise
        except Exception:
            raise OutcomeUnknown("Local acceptance outcome unavailable; inspect the exact offer ID. Do not retry release.") from None

    def source_control(self, owner, *, expected_context):
        self._w._check(expected_context)
        self._w._owner(owner)
        return SourceControl(self, owner)

    def recipient_control(self, owner, agent_id, *, expected_context):
        self._w._check(expected_context)
        self._w._owner(owner)
        if agent_id not in self._w.agents or self._w.agents[agent_id].owner != owner:
            raise Denied("Recipient control must bind the exact agent's owner")
        return RecipientControl(self, owner, agent_id)

    def _offer(self, offer_id):
        if type(offer_id) is not str:
            raise Denied("Expected exact offer ID")
        row = self._w.db.execute("SELECT * FROM acceptance_offers WHERE id=?", (offer_id,)).fetchone()
        if not row:
            raise Denied("Unknown acceptance offer")
        body = json.loads(row["body"])
        if (canonical(body) != row["body"] or digest(body) != row["digest"]
                or row["id"] != row["digest"] or body["domain"] != VERSION
                or body["mapping"]["team_context"] != self._w.context):
            raise Denied("Retained offer integrity mismatch")
        return row, body

    def _current(self, row, body):
        mapping, text = current_mapping(self._w, row["artifact_id"], row["target_task"], self._w.context)
        lineage = collect_lineage(self._w, {"inputs": [{"artifact_id": row["artifact_id"],
                                                        "digest": mapping["artifact_digest"]}]})
        if (mapping != body["mapping"] or text != body["text"] or lineage != body["lineage"]
                or self._source_permissions(lineage) != body["source_permissions"]):
            raise Denied("Exact artifact, source permissions or immutable context changed")

    def _source_permissions(self, lineage):
        """Commit and verify each historical edge, including completed tasks."""
        w, result = self._w, []
        for node in lineage["artifacts"]:
            for parent in node["parents"]:
                artifact = w._artifact(parent["artifact_id"])
                edge = {"artifact_id": parent["artifact_id"], "recipient": node["producer"],
                        "purpose": "task:" + node["task_id"]}
                if artifact["producer"] == node["producer"]:
                    result.append({**edge, "authority": "same-producer-local-input"})
                    continue
                grant = w.db.execute("SELECT * FROM disclosures WHERE artifact_id=? AND recipient=? AND purpose=?",
                                     (edge["artifact_id"], edge["recipient"], edge["purpose"])).fetchone()
                review = {"domain": "offline-team-disclosure/rebuilt-r1", "context": w.context,
                          "owner": w.agents[artifact["producer"]].owner, "artifact_id": artifact["id"],
                          "artifact_digest": artifact["digest"], "artifact": json.loads(artifact["body"]),
                          "recipient": w.agents[node["producer"]].to_dict(), "purpose": edge["purpose"]}
                if not grant or grant["state"] != "granted" or grant["review_digest"] != digest(review):
                    raise Denied("Historical source permission no longer matches its exact review")
                result.append({**edge, "review_digest": grant["review_digest"]})
        return result

    def register(self, bound):
        """Import one unsigned stage; legacy protocol state is not release authority."""
        if type(bound) is not BoundArtifactProposal or bound._workflow is not self._w:
            raise Denied("Expected a proposal bound to this exact workflow")
        bound._open()
        with self._mutation():
            old = self._w.db.execute("SELECT id FROM acceptance_offers WHERE artifact_id=? AND target_task=?",
                                     (bound._artifact_id, bound._recipient_task_id)).fetchone()
            if old:
                row, body = self._offer(old["id"])
                if body["proposal_id"] != bound.proposal_id or body["mapping_digest"] != bound.mapping_digest:
                    raise Denied("Offer route cannot be replaced")
                return self._status(row)
            # Same lock order as staging: team, then proposal store. Only capture
            # a pending exact stage. Thereafter this lane owns its own decisions.
            db = bound._store._db
            db.execute("BEGIN IMMEDIATE")
            try:
                staged = bound._store._get(bound.proposal_id)
                if (staged["state"] != "pending" or staged["text"] != bound._text
                        or staged["content_digest"] != bound.content_digest
                        or any(staged[key] is not None for key in ("operation_id", "command_digest",
                               "message_id", "message_digest", "packet_digest"))):
                    raise Denied("Only an exact unsigned pending proposal can enter this lane")
                mapping, text = bound._current_mapping()
                if canonical(mapping) != bound._mapping or text != bound._text:
                    raise Denied("Staged proposal changed")
                lineage = collect_lineage(self._w, {"inputs": [{"artifact_id": bound._artifact_id,
                                                               "digest": mapping["artifact_digest"]}]})
            finally:
                db.execute("ROLLBACK")  # read-only snapshot, no cross-store commit
            body = {"domain": VERSION, "mapping": mapping, "mapping_digest": bound.mapping_digest,
                    "proposal_id": bound.proposal_id, "content_digest": bound.content_digest,
                    "text": text, "lineage": lineage, "source_permissions": self._source_permissions(lineage)}
            offer_id = digest(body)
            self._w.db.execute("INSERT INTO acceptance_offers VALUES(?,?,?,?,?,'pending',NULL,NULL,NULL)",
                               (offer_id, bound._artifact_id, bound._recipient_task_id, canonical(body), offer_id))
            for owner in sorted({node["owner"] for node in lineage["artifacts"]}):
                review = self._source_review(body, owner)
                self._w.db.execute("INSERT INTO acceptance_sources VALUES(?,?,?,?,'pending',NULL)",
                                   (offer_id, owner, canonical(review), digest(review)))
            self._w._event("acceptance_offer_registered", offer=offer_id)
            return self._status(self._offer(offer_id)[0])

    def _source_review(self, body, owner):
        mapping, lineage = body["mapping"], body["lineage"]
        offer_id = digest(body)
        return {"domain": VERSION + "/source-review", "offer_id": offer_id, "owner": owner,
                "recipient": mapping["recipient_agent"], "purpose_task": mapping["recipient_task"]["id"],
                "team_context": self._w.context, "lineage_digest": digest(lineage),
                "owned_sources": [node for node in lineage["artifacts"] if node["owner"] == owner],
                "affected_artifacts": affected_inputs(lineage, owner),
                "foreign_derived_text_shown": False, "synthetic_only": True,
                "scope": "One local release of this exact artifact for recipient review and acceptance; no work or onward disclosure"}

    def _source(self, owner, offer_id):
        row, body = self._offer(offer_id)
        source = self._w.db.execute("SELECT * FROM acceptance_sources WHERE offer_id=? AND owner=?",
                                    (offer_id, owner)).fetchone()
        if not source:
            raise Denied("This owner has no source authority in the offer")
        if (canonical(self._source_review(body, owner)) != source["review"]
                or digest(self._source_review(body, owner)) != source["digest"]):
            raise Denied("Source review integrity mismatch")
        return row, body, source

    def _recipient(self, owner, agent, offer_id):
        row, body = self._offer(offer_id)
        if body["mapping"]["recipient_agent"] != self._w.agents[agent].to_dict() or self._w.agents[agent].owner != owner:
            raise Denied("Offer belongs to a different recipient")
        return row, body

    def _permissions(self, row, body):
        self._current(row, body)
        sources = self._w.db.execute("SELECT * FROM acceptance_sources WHERE offer_id=? ORDER BY owner", (row["id"],)).fetchall()
        required = sorted({node["owner"] for node in body["lineage"]["artifacts"]})
        if [s["owner"] for s in sources] != required:
            raise Denied("Source owner set changed")
        for source in sources:
            self._source(source["owner"], row["id"])
            if source["state"] != "approved" or source["expires"] <= self._w._now():
                raise Denied("Every source owner must grant current exact release permission")
        return min(s["expires"] for s in sources)

    def _status(self, row):
        try:
            self._permissions(row, self._offer(row["id"])[1])
            source_authority = "available"
        except Denied:
            source_authority = "unavailable"
        inbox = self._w.db.execute("SELECT * FROM acceptance_inbox WHERE offer_id=?", (row["id"],)).fetchone()
        return {"offer_id": row["id"], "release_state": row["state"],
                "recipient_state": inbox["state"] if inbox else "not_received",
                "outcome": inbox["state"] if inbox else ("uncertain" if row["state"] == "released" else "not_released"),
                "delivery_digest": row["delivery_digest"],
                "decision_digest": inbox["decision_digest"] if inbox else None,
                "recipient_review_digest": inbox["review_digest"] if inbox else None,
                "expires": row["expires"], "retry_release_allowed": False,
                "current_source_authority": source_authority,
                "synthetic_only": True, "authenticated_consent": False, "authorises_work": False, "authorises_onward_disclosure": False}

    def _delivery(self, row, body, expires):
        m = body["mapping"]
        return {"domain": VERSION + "/delivery", "offer_id": row["id"], "context": self._w.context,
                "proposal_id": body["proposal_id"], "mapping_digest": body["mapping_digest"],
                "recipient": m["recipient_agent"], "task_id": row["target_task"],
                "artifact_id": row["artifact_id"], "artifact_digest": m["artifact_digest"],
                "text": body["text"], "expires": expires, "synthetic_only": True,
                "external_actions_allowed": False, "untrusted_content": True}

    def _review(self, row, body):
        delivery = self._delivery(row, body, row["expires"])
        if canonical(delivery) != row["delivery"] or digest(delivery) != row["delivery_digest"]:
            raise Denied("Original delivery integrity mismatch")
        return {"domain": VERSION + "/recipient-review", "delivery": delivery,
                "delivery_digest": row["delivery_digest"],
                "decision_scope": "Accept this exact inert artifact into the local inbox, or reject it; no execution or onward disclosure",
                "authenticated_consent": False}


class SourceControl:
    """Fictional owner control. Never add these methods to the model tool list."""

    def __init__(self, boundary, owner):
        self._b, self._owner = boundary, owner

    def review(self, offer_id):
        with self._b._w._transaction():
            _, _, source = self._b._source(self._owner, offer_id)
            state = source["state"]
            if state == "approved" and source["expires"] <= self._b._w._now():
                state = "expired"
            return {"review": json.loads(source["review"]), "review_digest": source["digest"],
                    "state": state, "expires": source["expires"]}

    def decide(self, offer_id, review_digest, decision, *, expires=None):
        b = self._b
        if decision not in ("approve", "reject"):
            raise Denied("Expected source approve or reject")
        with b._mutation():
            row, body, source = b._source(self._owner, offer_id)
            if source["digest"] != review_digest or source["state"] != "pending" or row["state"] != "pending":
                raise Denied("Source decision is stale or already terminal")
            if decision == "approve":
                b._w._expiry(expires)
                b._current(row, body)
            elif expires is not None:
                raise Denied("Rejection cannot grant an expiry")
            b._w.db.execute("UPDATE acceptance_sources SET state=?,expires=? WHERE offer_id=? AND owner=?",
                            ("approved" if decision == "approve" else "rejected", expires, offer_id, self._owner))
            b._w._event("acceptance_source_decided", offer=offer_id, owner=self._owner, decision=decision)
            return b._status(row)

    def revoke(self, offer_id):
        b = self._b
        with b._mutation():
            row, _, source = b._source(self._owner, offer_id)
            if source["state"] not in ("revoked", "rejected"):
                b._w.db.execute("UPDATE acceptance_sources SET state='revoked' WHERE offer_id=? AND owner=?", (offer_id, self._owner))
                b._w._event("acceptance_source_revoked", offer=offer_id, owner=self._owner)
            return b._status(row)

    def release(self, offer_id):
        b = self._b
        with b._mutation():
            row, body, _ = b._source(self._owner, offer_id)
            if self._owner != body["mapping"]["source_agent"]["owner"]:
                raise Denied("Only the outgoing artifact's owner may release it")
            if row["state"] != "pending":
                raise Denied("Release already claimed; inspect history, never reissue")
            expires = b._permissions(row, body)
            delivery = b._delivery(row, body, expires)
            b._w.db.execute("UPDATE acceptance_offers SET state='released',delivery=?,delivery_digest=?,expires=? WHERE id=?",
                            (canonical(delivery), digest(delivery), expires, offer_id))
            b._w._event("acceptance_release_claimed", offer=offer_id, digest=digest(delivery))
        # Unknown is durable before any payload leaves this call.
        return SyntheticDelivery(canonical(delivery), digest(delivery))

    def status(self, offer_id):
        with self._b._w._transaction():
            row, _, _ = self._b._source(self._owner, offer_id)
            return self._b._status(row)


class RecipientControl:
    """Exact recipient's fictional owner controls, separate from source and lead."""

    def __init__(self, boundary, owner, agent):
        self._b, self._owner, self._agent = boundary, owner, agent

    def receive(self, delivery):
        b = self._b
        if type(delivery) is not SyntheticDelivery or type(delivery.body) is not str or len(delivery.body) > 16384:
            raise Denied("Expected bounded original synthetic delivery")
        try:
            value = delivery.to_dict()
            if canonical(value) != delivery.body or digest(value) != delivery.digest:
                raise ValueError()
            offer_id = value["offer_id"]
        except (ValueError, TypeError, KeyError, RecursionError):
            raise Denied("Malformed synthetic delivery") from None
        with b._mutation():
            row, body = b._recipient(self._owner, self._agent, offer_id)
            if row["state"] != "released" or delivery.body != row["delivery"] or delivery.digest != row["delivery_digest"]:
                raise Denied("Delivery is not the original exact release")
            if b._w.db.execute("SELECT 1 FROM acceptance_inbox WHERE offer_id=?", (offer_id,)).fetchone():
                return b._status(row)  # history only, even after withdrawal
            b._permissions(row, body)
            review = b._review(row, body)
            b._w.db.execute("INSERT INTO acceptance_inbox VALUES(?,?,?,'pending',NULL)",
                            (offer_id, delivery.digest, digest(review)))
            # Conservative exposure counter: local receipt may expose content,
            # irrespective of whether this fictional owner later accepts it.
            b._w.db.execute("UPDATE disclosures SET reads=reads+1 WHERE artifact_id=? AND recipient=? AND purpose=?",
                            (row["artifact_id"], self._agent, "task:" + row["target_task"]))
            b._w._event("acceptance_received", offer=offer_id, recipient=self._agent)
            return b._status(row)

    def review(self, offer_id):
        b = self._b
        with b._w._transaction():
            row, body = b._recipient(self._owner, self._agent, offer_id)
            inbox = b._w.db.execute("SELECT * FROM acceptance_inbox WHERE offer_id=?", (offer_id,)).fetchone()
            if not inbox or inbox["state"] != "pending":
                raise Denied("Only a pending received artifact can be reviewed")
            b._permissions(row, body)
            review = b._review(row, body)
            if digest(review) != inbox["review_digest"]:
                raise Denied("Recipient review integrity mismatch")
            return {"review": review, "review_digest": inbox["review_digest"]}

    def status(self, offer_id):
        with self._b._w._transaction():
            row, _ = self._b._recipient(self._owner, self._agent, offer_id)
            return self._b._status(row)

    def decide(self, offer_id, review_digest, decision):
        b = self._b
        if decision not in ("accept", "reject"):
            raise Denied("Expected recipient accept or reject")
        with b._mutation():
            row, body = b._recipient(self._owner, self._agent, offer_id)
            inbox = b._w.db.execute("SELECT * FROM acceptance_inbox WHERE offer_id=?", (offer_id,)).fetchone()
            if not inbox or inbox["review_digest"] != review_digest or digest(b._review(row, body)) != review_digest:
                raise Denied("Exact received recipient review required")
            decision_digest = digest({"domain": VERSION + "/decision", "owner": self._owner,
                                      "agent": self._agent, "review_digest": review_digest, "decision": decision})
            if inbox["state"] != "pending":
                if inbox["decision_digest"] == decision_digest:
                    return b._status(row)  # exact duplicate is metadata, not renewal
                raise Denied("Recipient decision is terminal")
            if decision == "accept":
                b._permissions(row, body)
            # Rejection can still close an expired/withdrawn received proposal.
            b._w.db.execute("UPDATE acceptance_inbox SET state=?,decision_digest=? WHERE offer_id=?",
                            ("accepted" if decision == "accept" else "rejected", decision_digest, offer_id))
            b._w._event("acceptance_recipient_decided", offer=offer_id, recipient=self._agent,
                        decision=decision, digest=decision_digest)
            return b._status(row)
