"""Read-only, deterministic human review of the closed scheduling protocol.

No free-form agent text or aliases enter this display. This is a local CLI view,
not authenticated owner UI, calendar integration, or an approval-granting method.
"""
from network import Denied, context_digest, digest, snapshot_envelope


def person(identity):
    return f"{identity.title()} [{identity}]"


def render_review(meeting, envelope):
    message = snapshot_envelope(envelope)
    if message["meeting"] != meeting.id or message["context"] != context_digest(meeting):
        raise Denied("Review context does not match this meeting")
    if any(message[key] not in meeting.participants for key in ("sender", "recipient")):
        raise Denied("Review requires registered meeting participants")
    kind = message["type"]
    if kind == "proposal":
        if message["sender"] != meeting.coordinator:
            raise Denied("Only the coordinator can propose a meeting")
    elif message["recipient"] != meeting.coordinator:
        raise Denied("Availability and acceptance go only to the coordinator")
    indices = message["payload"].get("candidate_indices", [message["payload"].get("candidate_index")])
    if any(index >= len(meeting.candidates) for index in indices):
        raise Denied("Review candidate is not in this meeting")
    lines = [
        "REVIEW BEFORE SENDING (fictional local simulation)",
        f"Meeting: {meeting.id}",
        f"From: {person(message['sender'])}",
        f"Only recipient of this message: {person(message['recipient'])}",
        "Meeting participants: " + ", ".join(person(p) for p in meeting.participants),
    ]
    if kind == "availability":
        lines.append("Action: share availability for the candidate times below.")
        lines.append("Omitted candidates mean not available for that whole candidate slot.")
        for index, slot in enumerate(meeting.candidates):
            status = "AVAILABLE" if index in indices else "NOT AVAILABLE"
            lines.append(f"  {slot.start} to {slot.end} (UTC): {status}")
        if not indices:
            lines.append("No candidate slots are available.")
    else:
        slot = meeting.candidates[indices[0]]
        action = "send a proposed time" if kind == "proposal" else "accept the proposed time"
        lines += [f"Action: {action}.", f"Exact time: {slot.start} to {slot.end} (UTC)"]
    lines += [
        "This discloses scheduling information. No titles, reasons, private chats or files are sent.",
        "This does not create a calendar booking or authorize later messages.",
        f"Exact message digest: {digest(message)}",
        f"Meeting context: {message['context']}",
    ]
    return "\n".join(lines)
