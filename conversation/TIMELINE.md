# One timeline

`conversation/timeline.py` keeps one owner-side timeline of what happened
across the owner's conversations, in the order it happened. The owner can see
what their assistant saw and did in one place.

## What goes in

The owner's own host components add an entry at the moment something happens.
Each component takes an optional `timeline=` argument:

| Component | Entries |
| --- | --- |
| `InboxAccess` | `message_received` (from you, your assistant or someone else) |
| `OwnerDesk` | `policy_changed`, `guidance_changed`, `message_proposed`, `message_sent_by_assistant`, `message_approved`, `message_declined`, `message_failed` |
| `DraftAccess` | `draft_started`, `draft_revised`, `draft_suggested` |
| `OwnerQuestions` | `question_asked`, `question_answered` (with whether it came from the phone or Central) |
| `record_mission_activity` | `mission_activity`, imported from a `mission_cards` activity log |

## Guarantees

- **No content.** Entries hold references, states and who acted, never message,
  draft or question text. The owner's screen fetches text from the store that
  owns it, with that store's own checks.
- **No duplicates.** Each entry is unique by kind and reference, so a retried
  step or a re-read message is listed once.
- **Tamper-evident.** Entries are hash-chained. A changed, reordered or
  deleted entry makes `read` and `verify` refuse.
- **Private.** Details are sealed to the owner's key, only the owner's session
  can read the timeline, and it never enters the conversation.
- **Never in the way.** A failed timeline write is dropped rather than undoing
  the action it describes. The action's own store remains the record of truth.
