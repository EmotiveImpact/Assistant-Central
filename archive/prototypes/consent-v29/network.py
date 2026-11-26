"""Local consent-gated agent protocol. No network, credentials, or LLM execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import threading
from typing import Callable


class Denied(ValueError):
    """A fail-closed protocol or consent error."""


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def snapshot_envelope(value):
    """Strict closed schema at local ingress; malformed data never gains authority."""
    # V1 remains the explicit scheduling adapter. V2 is a separate closed
    # conversation/task grammar; neither shape is silently translated.
    if type(value) is dict and type(value.get('version')) is int and value['version']==2:
        from generic_protocol import snapshot_task_envelope
        return snapshot_task_envelope(value)
    try:
        body = canonical(value)
        if len(body.encode()) > 8192:
            raise Denied("Message too large")
        message = json.loads(body)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied("Message must be bounded JSON") from exc
    if type(message) is not dict or set(message) != {"version", "type", "meeting", "context", "sender", "recipient", "payload"}:
        raise Denied("Unknown or missing envelope fields")
    if type(message["version"]) is not int or message["version"] != 1:
        raise Denied("Unsupported protocol version")
    if any(type(message[k]) is not str or not re.fullmatch(r"[a-z0-9_-]{1,64}", message[k]) for k in ("sender", "recipient", "meeting")):
        raise Denied("Invalid identity or meeting ID")
    if type(message["context"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", message["context"]):
        raise Denied("Invalid context digest")
    kind, payload = message["type"], message["payload"]
    if type(kind) is not str or kind not in ("availability", "proposal", "accept") or type(payload) is not dict:
        raise Denied("Unsupported message type or payload")
    if kind == "availability":
        if set(payload) != {"candidate_indices"} or type(payload["candidate_indices"]) is not list:
            raise Denied("Only candidate indices are permitted")
        indices = payload["candidate_indices"]
        if len(indices) > 16 or any(type(i) is not int or not 0 <= i < 16 for i in indices) or indices != sorted(set(indices)):
            raise Denied("Invalid candidate indices")
    elif set(payload) != {"candidate_index"} or type(payload["candidate_index"]) is not int or not 0 <= payload["candidate_index"] < 16:
        raise Denied("Invalid candidate index")
    return message


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z", value):
        raise Denied("Timestamps must be UTC, with minute precision")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Denied("Invalid timestamp") from exc


@dataclass(frozen=True, order=True)
class Slot:
    start: str
    end: str

    def __post_init__(self):
        if timestamp(self.start) >= timestamp(self.end):
            raise Denied("Empty or reversed interval")

    def to_dict(self):
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class Meeting:
    id: str
    coordinator: str
    participants: tuple[str, ...]
    candidates: tuple[Slot, ...]

    def __post_init__(self):
        object.__setattr__(self, "participants", tuple(self.participants))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if any(type(p) is not str or not re.fullmatch(r"[a-z0-9_-]{1,64}", p) for p in self.participants):
            raise Denied("Invalid participant ID")
        if any(type(s) is not Slot for s in self.candidates):
            raise Denied("Candidates must be immutable slots")
        if not re.fullmatch(r"[a-z0-9_-]{1,64}", self.id):
            raise Denied("Invalid meeting ID")
        if len(set(self.participants)) != len(self.participants) or not 2 <= len(self.participants) <= 10:
            raise Denied("Need 2–10 distinct participants")
        if self.coordinator not in self.participants:
            raise Denied("Coordinator must participate")
        if not 1 <= len(self.candidates) <= 16 or len(set(self.candidates)) != len(self.candidates):
            raise Denied("Need 1–16 distinct candidate slots")


def context_digest(meeting: Meeting) -> str:
    from generic_protocol import Task, task_context_digest
    if type(meeting) is Task:
        return task_context_digest(meeting)
    if type(meeting) is not Meeting:
        raise Denied('Expected an explicit scheduling or task context')
    return digest({"id": meeting.id, "coordinator": meeting.coordinator,
                   "participants": list(meeting.participants),
                   "candidates": [s.to_dict() for s in meeting.candidates]})


class ConsentGate:
    """Trusted local boundary. Never expose approve() as an agent/remote tool.

    Approval identifiers are local consent records, NOT identity credentials.
    The OS user running the CLI represents the human in this simulation.
    """

    def __init__(self, owner: str, clock: Callable[[], float]):
        self.owner, self.clock = owner, clock
        self._grants = {}
        self._lock = threading.Lock()

    def approve(self, reviewed_envelope: dict, ttl_seconds: int = 300) -> str:
        if reviewed_envelope.get("sender") != self.owner:
            raise Denied("Only the sender can approve disclosure")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 600:
            raise Denied("Approval lifetime must be 1–600 seconds")
        approval_id = secrets.token_hex(16)
        with self._lock:
            self._grants[approval_id] = [digest(reviewed_envelope), self.clock() + ttl_seconds, False]
        return approval_id

    def revoke(self, approval_id: str):
        with self._lock:
            self._grants.pop(approval_id, None)

    def consume(self, envelope: dict, approval_id: str):
        with self._lock:
            grant = self._grants.get(approval_id)
            if not grant or grant[2] or self.clock() >= grant[1] or digest(envelope) != grant[0]:
                raise Denied("Missing, expired, revoked, used or mismatched approval")
            grant[2] = True


class Agent:
    def __init__(self, identity: str, free: tuple[Slot, ...], clock: Callable[[], float]):
        self.identity = identity
        self.__free = tuple(free)
        self.human = ConsentGate(identity, clock)

    def preview_availability(self, meeting: Meeting) -> dict:
        if self.identity not in meeting.participants:
            raise Denied("Agent is not a meeting participant")
        # Only candidate indices leave this boundary, never calendar entries/reasons.
        available = [i for i, slot in enumerate(meeting.candidates)
                     if any(f.start <= slot.start and slot.end <= f.end for f in self.__free)]
        return {"version": 1, "type": "availability", "meeting": meeting.id,
                "context": context_digest(meeting),
                "sender": self.identity, "recipient": meeting.coordinator,
                "payload": {"candidate_indices": available}}


class Broker:
    """In-process transport simulator, not an internet authentication boundary.

    Real deployment requires independently authenticated owners and peers,
    authenticated transport and a durable transactional replay/consent store.
    """

    def __init__(self, agents: tuple[Agent, ...], meeting: Meeting):
        self._agents = {a.identity: a for a in agents}
        if len(self._agents) != len(agents) or set(self._agents) != set(meeting.participants):
            raise Denied("Peer registry must exactly match participants")
        self.meeting = meeting
        self._received = {}
        self._acceptances = set()
        self._proposal = None
        self._offered = set()
        self.cancellation = None
        self.audit = []
        self._lock = threading.Lock()

    def _validate(self, envelope: dict):
        self._require_active()
        if type(envelope) is not dict or set(envelope) != {"version", "type", "meeting", "context", "sender", "recipient", "payload"}:
            raise Denied("Unknown or missing envelope fields")
        if type(envelope["version"]) is not int or envelope["version"] != 1:
            raise Denied("Unsupported protocol version")
        if envelope["meeting"] != self.meeting.id or envelope["context"] != context_digest(self.meeting):
            raise Denied("Wrong meeting scope")
        if type(envelope["sender"]) is not str or type(envelope["recipient"]) is not str:
            raise Denied("Peer IDs must be strings")
        if envelope["sender"] not in self._agents or envelope["recipient"] not in self._agents:
            raise Denied("Unregistered sender or wrong recipient")
        if envelope["type"] != "proposal" and envelope["recipient"] != self.meeting.coordinator:
            raise Denied("Replies may only go to the coordinator")
        p = envelope["payload"]
        if type(p) is not dict:
            raise Denied("Payload must be an object")
        if envelope["type"] == "availability":
            if set(p) != {"candidate_indices"} or type(p["candidate_indices"]) is not list:
                raise Denied("Only candidate indices may be disclosed")
            indices = p["candidate_indices"]
            if any(type(i) is not int or not 0 <= i < len(self.meeting.candidates) for i in indices):
                raise Denied("Invalid candidate index")
            if indices != sorted(set(indices)):
                raise Denied("Indices must be unique and sorted")
            if envelope["sender"] in self._received or self._proposal is not None:
                raise Denied("Availability is already submitted or proposal is fixed")
        elif envelope["type"] in ("accept", "proposal"):
            if set(p) != {"candidate_index"} or type(p["candidate_index"]) is not int:
                raise Denied("Acceptance must identify exactly one candidate")
            if self._proposal is None or p["candidate_index"] != self._proposal:
                raise Denied("Acceptance does not match current proposal")
            if envelope["type"] == "proposal":
                if envelope["sender"] != self.meeting.coordinator or envelope["recipient"] in self._offered:
                    raise Denied("Only coordinator may send a proposal once to each participant")
            elif envelope["sender"] not in self._offered:
                raise Denied("Participant has not received an approved proposal")
            elif envelope["sender"] in self._acceptances:
                raise Denied("Participant already accepted")
        else:
            raise Denied("Unsupported message type; instructions are not executable")

    def deliver(self, agent: Agent, envelope: dict, approval_id: str):
        # Snapshot the proposed message before validation/consumption to prevent
        # mutation between consent checking and processing.
        try:
            snapshot = json.loads(canonical(envelope))
        except (TypeError, ValueError) as exc:
            raise Denied("Envelope must be JSON") from exc
        with self._lock:
            self._validate(snapshot)
            if self._agents.get(snapshot["sender"]) is not agent:
                raise Denied("Transport sender does not match claimed identity")
            agent.human.consume(snapshot, approval_id)
            self._apply_validated(snapshot)

    def _apply_validated(self, snapshot):
        """Trusted projection only; caller must validate and commit consent first."""
        if snapshot["type"] == "availability":
            self._received[snapshot["sender"]] = set(snapshot["payload"]["candidate_indices"])
        elif snapshot["type"] == "proposal":
            self._offered.add(snapshot["recipient"])
        else:
            self._acceptances.add(snapshot["sender"])
        # Metadata only, no availability payload or free-text content in log.
        self.audit.append({"event": "delivered", "type": snapshot["type"],
                           "sender": snapshot["sender"], "recipient": snapshot["recipient"],
                           "meeting": self.meeting.id})

    def propose(self, coordinator: Agent) -> Slot | None:
        with self._lock:
            self._require_active()
            if self._agents.get(self.meeting.coordinator) is not coordinator:
                raise Denied("Only coordinator can calculate the intersection")
            if len(self._received) != len(self.meeting.participants):
                raise Denied("Waiting for all participants' approved disclosures")
            common = set.intersection(*self._received.values())
            if not common:
                return None
            self._proposal = min(common)
            return self.meeting.candidates[self._proposal]

    def preview_acceptance(self, agent: Agent) -> dict:
        self._require_active()
        if self._agents.get(agent.identity) is not agent or self._proposal is None or agent.identity not in self._offered:
            raise Denied("No proposal for this participant")
        return {"version": 1, "type": "accept", "meeting": self.meeting.id,
                "context": context_digest(self.meeting),
                "sender": agent.identity, "recipient": self.meeting.coordinator,
                "payload": {"candidate_index": self._proposal}}

    def preview_proposal(self, coordinator: Agent, recipient: str) -> dict:
        self._require_active()
        if self._agents.get(self.meeting.coordinator) is not coordinator or self._proposal is None or recipient not in self._agents:
            raise Denied("No authorized proposal")
        return {"version": 1, "type": "proposal", "meeting": self.meeting.id,
                "context": context_digest(self.meeting),
                "sender": coordinator.identity, "recipient": recipient,
                "payload": {"candidate_index": self._proposal}}

    @property
    def agreed(self) -> bool:
        return self.cancellation is None and self._proposal is not None and self._acceptances == set(self.meeting.participants)

    def _require_active(self):
        if self.cancellation is not None:
            raise Denied("Meeting cancelled; no new scheduling actions are allowed")
