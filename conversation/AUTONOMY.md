# Autonomy dial and private guidance

`conversation/autonomy.py` lets an owner decide how much their assistant may
say on its own in one conversation, and leave private notes that only that
assistant reads.

## Modes

| Mode | What the assistant can do |
| --- | --- |
| `review_each` (default) | Every proposed message waits for the owner to approve the exact text. |
| `check_in` | Up to `every` messages in a row go out on their own; the next waits for the owner. Approving it starts a new run. |
| `within_limits` | Messages go out on their own while the caps hold. |

Every standing policy also has hard caps: at most `max_auto` unreviewed
messages in total (no more than 200), at most `max_bytes` per message (no more
than 16 KB), and an expiry of no more than seven days. When a policy expires or
is cleared, the assistant is back to `review_each`.

## What stays out of reach

Only plain new messages can be sent without review. Quoting or summarising
earlier messages, sharing history, disclosing to a provider, running anything
and spending have no automatic path here.

## How readers can tell

A message sent under a standing policy is still signed by the owner, but it
carries the ledger kind `assistant`. A message the owner approved carries the
kind `message`. Every member can see the difference.

## Private guidance

`add_guidance` stores a short note (up to 4 KB, at most 32 per assistant and
conversation), encrypted to the owner's own key. The assistant reads it with a
current lease. It never enters the conversation.

## Assistant tools

When the host passes a `DeskAccess` to `mission_approvals.server.build_server`
as `owner_desk`, the assistant gets three MCP tools:

- `read_owner_guidance`
- `propose_message(request_id, text)`: sends or queues, idempotent by `request_id`
- `message_status(request_id)`

The lease and owner session come from the host. Nothing the model sends can
choose the owner, the assistant identity or the conversation.
