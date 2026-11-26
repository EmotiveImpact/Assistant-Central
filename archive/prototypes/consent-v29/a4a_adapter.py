"""Offline, unsigned subset of A4A task events. No transport or authority.

Tag layouts adapted from sdk-python/a4a/types.py (TaskRequest, TaskStatus,
TaskResult), Agent.prepare_private_message in sdk-python/a4a/agent.py,
and integer grammar from sdk-python/a4a/event.py, upstream
https://github.com/a4a-network/a4a at
6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e.
Copyright (c) 2026 A4A Network. MIT; see vendor/a4a/LICENSE.
Modifications: stdlib-only builders and strict, bounded draft validation;
caller-supplied deterministic timestamps and delivery IDs; no signing, keys,
transport, delegation, agreement creation, or execution. Unknown fields/tags,
signed events and legacy task aliases are deliberately rejected. This subset
is stricter than the upstream readers. Tests compare tag shapes, not live wire
interoperability or cryptographic verification. A draft's agreement reference
is only text: it never proves an agreement or consent exists.
"""
from __future__ import annotations

import copy
import re
from vendor.a4a.sanitize import wrap_untrusted

UPSTREAM_REVISION = "6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e"
UPSTREAM_TYPES_URL = f"https://github.com/a4a-network/a4a/blob/{UPSTREAM_REVISION}/sdk-python/a4a/types.py"
KIND_TASK_REQUEST, KIND_TASK_STATUS, KIND_TASK_RESULT = 31030, 31031, 31032
TASK_STATUSES = ("accepted", "in_progress", "review", "completed", "failed")
MAX_TAG_INT = 10**19 - 1
PUBLIC_GRACE_SECONDS = 30 * 24 * 3600
PUBLIC_DEFAULT_TTL_SECONDS = 90 * 24 * 3600
_UINT = re.compile(r"0|[1-9][0-9]{0,18}")
_HEX = re.compile(r"[0-9a-f]{64}")


class DraftError(ValueError):
    """Unsupported or malformed offline event; never an authorization decision."""


def _text(value, name, maximum=4096, nonempty=True):
    if type(value) is not str or (nonempty and not value) or len(value) > maximum:
        raise DraftError(f"Invalid {name}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DraftError(f"Invalid Unicode in {name}") from exc
    return value


def _uint(value, name):
    if type(value) is not int or not 0 <= value <= MAX_TAG_INT:
        raise DraftError(f"{name} must be an exact non-negative integer of at most 19 digits")
    return value


def _hex(value, name):
    _text(value, name, 64)
    if not _HEX.fullmatch(value):
        raise DraftError(f"{name} must be 64 lowercase hexadecimal characters")
    return value


def _event(kind, tags, content, created_at):
    event = {"id": "", "pubkey": "", "created_at": created_at,
             "kind": kind, "tags": tags, "content": content, "sig": ""}
    inspect_draft(event)
    return event


def task_request(*, agreement_id: str, task_id: str, description: str,
                 executor: str, deadline: int, delivery_id: str,
                 created_at: int, content: str = "") -> dict:
    """Prepare a local draft, not a send or a task accepted by any peer.

    executor is a public-key-shaped fixture/reference, never a newly created key.
    delivery_id supplies upstream's unique d tag; callers own uniqueness.
    """
    _uint(created_at, "created_at")
    _uint(deadline, "deadline")
    expiration = (max(created_at, deadline) + PUBLIC_GRACE_SECONDS if deadline
                  else created_at + PUBLIC_DEFAULT_TTL_SECONDS)
    tags = [["agreement", agreement_id], ["task_id", task_id],
            ["description", description], ["deadline", str(deadline)],
            ["e", agreement_id], ["d", delivery_id],
            ["expiration", str(expiration)], ["p", executor]]
    return _event(KIND_TASK_REQUEST, tags, content, created_at)


def task_status(*, agreement_id: str, task_id: str, status: str, progress: int,
                delivery_id: str, created_at: int, content: str = "") -> dict:
    _uint(progress, "progress")
    tags = [["task_id", task_id], ["agreement", agreement_id], ["e", agreement_id],
            ["status", status], ["progress", str(progress)], ["d", delivery_id]]
    return _event(KIND_TASK_STATUS, tags, content, created_at)


def task_result(*, agreement_id: str, task_id: str, result_url: str,
                delivery_id: str, created_at: int, content: str = "") -> dict:
    """Record a result reference as untrusted text. Never open or fetch it."""
    tags = [["task_id", task_id], ["agreement", agreement_id], ["e", agreement_id],
            ["result_url", result_url], ["d", delivery_id]]
    return _event(KIND_TASK_RESULT, tags, content, created_at)


def inspect_draft(event: dict) -> dict:
    """Validate a strict offline subset and return a detached untrusted preview.

    Does not accept signed incoming events, authenticate a peer, establish consent,
    deliver messages, or transition local scheduling state. Sanitization is display
    hygiene, not a prompt-injection security boundary. No input text is executed.
    """
    fields = {"id", "pubkey", "created_at", "kind", "tags", "content", "sig"}
    if type(event) is not dict or set(event) != fields:
        raise DraftError("Unknown or missing event fields")
    if any(event[name] != "" for name in ("id", "pubkey", "sig")):
        raise DraftError("Only unsigned, unauthenticated offline drafts are supported")
    _uint(event["created_at"], "created_at")
    kind = event["kind"]
    layouts = {
        KIND_TASK_REQUEST: {"agreement", "task_id", "description", "deadline", "e", "d", "expiration", "p"},
        KIND_TASK_STATUS: {"task_id", "agreement", "e", "status", "progress", "d"},
        KIND_TASK_RESULT: {"task_id", "agreement", "e", "result_url", "d"},
    }
    if type(kind) is not int or kind not in layouts:
        raise DraftError("Unsupported A4A task kind")
    content = _text(event["content"], "content", 16384, nonempty=False)
    raw_tags = event["tags"]
    if type(raw_tags) is not list or len(raw_tags) > 8:
        raise DraftError("Invalid tags")
    tags = {}
    for tag in raw_tags:
        if type(tag) is not list or len(tag) != 2:
            raise DraftError("Each supported tag must contain exactly two strings")
        name, value = tag
        _text(name, "tag name", 32)
        _text(value, "tag value", nonempty=False)
        if name in tags:
            raise DraftError("Duplicate tag")
        tags[name] = value
    if set(tags) != layouts[kind]:
        raise DraftError("Unknown or missing tags")
    _hex(tags["agreement"], "agreement")
    if tags["e"] != tags["agreement"]:
        raise DraftError("Conflicting agreement references")
    for name in ("task_id", "d"):
        _text(tags[name], name, 128)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", tags[name]):
            raise DraftError(f"Invalid {name}")
    for name in ("deadline", "expiration", "progress"):
        if name in tags and not _UINT.fullmatch(tags[name]):
            raise DraftError(f"Non-canonical integer tag: {name}")
    if kind == KIND_TASK_REQUEST:
        _hex(tags["p"], "executor")
        _text(tags["description"], "description")
        deadline = int(tags["deadline"])
        expected = (max(event["created_at"], deadline) + PUBLIC_GRACE_SECONDS if deadline
                    else event["created_at"] + PUBLIC_DEFAULT_TTL_SECONDS)
        if int(tags["expiration"]) != expected:
            raise DraftError("Expiration does not match this draft subset's retention rule")
    elif kind == KIND_TASK_STATUS:
        if tags["status"] not in TASK_STATUSES or not 0 <= int(tags["progress"]) <= 100:
            raise DraftError("Invalid task status or progress")
    # All potentially external free text is framed; no URLs are visited.
    preview_text = "\n".join(f"{k}: {v}" for k, v in tags.items()) + "\n" + content
    return {"offline_only": True, "authenticated": False, "authorization": "none",
            "kind": kind, "task_id": tags["task_id"],
            "event": copy.deepcopy(event), "preview": wrap_untrusted(preview_text)}


def scheduling_draft(envelope: dict, *, meeting, peer_pubkeys: dict,
                     delivery_id: str, created_at: int) -> dict:
    """Convert an app scheduling envelope into an UNSIGNED kind-14 inner draft.

    Shape adapted from Agent.prepare_private_message in sdk-python/a4a/agent.py
    at UPSTREAM_REVISION. A4A requires the inner event to be signed, then sealed
    and gift-wrapped before publication. THIS PLAINTEXT DRAFT MUST NOT BE SENT.
    peer_pubkeys are caller-provided offline references, not authenticated peers.
    No synthetic agreement is created: scheduling is application data in content.
    The local Broker still owns approval, state validation and delivery. This
    function performs structural/scope checks only and does not consume approval.
    """
    import json
    from network import Meeting, context_digest

    if type(meeting) is not Meeting:
        raise DraftError("Expected local Meeting context")
    if type(peer_pubkeys) is not dict or set(peer_pubkeys) != set(meeting.participants):
        raise DraftError("Peer reference map must match meeting participants")
    for value in peer_pubkeys.values():
        _hex(value, "peer public-key reference")
    if len(set(peer_pubkeys.values())) != len(peer_pubkeys):
        raise DraftError("Peer references must be distinct")
    fields = {"version", "type", "meeting", "context", "sender", "recipient", "payload"}
    if type(envelope) is not dict or set(envelope) != fields:
        raise DraftError("Unknown or missing scheduling envelope fields")
    if type(envelope["version"]) is not int or envelope["version"] != 1:
        raise DraftError("Unsupported scheduling version")
    if envelope["meeting"] != meeting.id or envelope["context"] != context_digest(meeting):
        raise DraftError("Wrong scheduling context")
    for name in ("sender", "recipient"):
        if type(envelope[name]) is not str or envelope[name] not in peer_pubkeys:
            raise DraftError("Unknown scheduling peer")
    message_type = envelope["type"]
    if type(message_type) is not str or message_type not in ("availability", "proposal", "accept"):
        raise DraftError("Unsupported scheduling message")
    if message_type == "proposal":
        if envelope["sender"] != meeting.coordinator:
            raise DraftError("Only coordinator may propose")
    elif envelope["recipient"] != meeting.coordinator:
        raise DraftError("Scheduling replies must target coordinator")
    payload = envelope["payload"]
    if type(payload) is not dict:
        raise DraftError("Scheduling payload must be an object")
    if message_type == "availability":
        if set(payload) != {"candidate_indices"} or type(payload["candidate_indices"]) is not list:
            raise DraftError("Only candidate indices may be disclosed")
        indices = payload["candidate_indices"]
    else:
        if set(payload) != {"candidate_index"}:
            raise DraftError("Expected one candidate index")
        indices = [payload["candidate_index"]]
    if any(type(i) is not int or not 0 <= i < len(meeting.candidates) for i in indices):
        raise DraftError("Invalid candidate index")
    if indices != sorted(set(indices)):
        raise DraftError("Candidate indices must be sorted and unique")
    _uint(created_at, "created_at")
    _text(delivery_id, "delivery_id", 128)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", delivery_id):
        raise DraftError("Invalid delivery ID")
    content = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    inner = {"id": "", "pubkey": "", "created_at": created_at, "kind": 14,
             "tags": [["p", peer_pubkeys[envelope["recipient"]]], ["d", delivery_id],
                      ["a4a_conversation", envelope["context"]]],
             "content": content, "sig": ""}
    return {"offline_only": True, "authenticated": False, "encrypted": False,
            "authorization": "none", "publishable": False,
            "required_before_network": ["human disclosure approval", "authenticated peer binding",
                                        "sign inner event", "encrypt seal and gift wrap"],
            "inner_event": inner, "preview": wrap_untrusted(content)}
