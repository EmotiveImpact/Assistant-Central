# Assistant inbox

An assistant acting for one owner can read that owner's conversation, say what
it has finished with, and be told when something new arrives. It cannot send,
share, approve, spend or act through the inbox. Message text stays untrusted
input.

Borrowed patterns: durable per-agent cursors and body-free wake notifications
(Parley by Weldra), rebuilt on Assistant Central's owner sessions, membership
epochs and visibility rules. No third-party code is used.

## How it works

- **Lease.** The trusted host authenticates the owner, then calls
  `InboxStore.provision(owner, session, assistant_id, conversation_id)`. The
  lease lasts at most 15 minutes and is never chosen by a model.
- **Generations.** Provisioning again starts a new session generation and
  fences every older lease for the same assistant and conversation.
- **Pending.** `pending(session, lease)` returns messages the owner can see
  after the durable cursor, oldest first, at most 50 at a time, and records
  them as delivered to the current generation.
- **Acknowledge.** `acknowledge(session, lease, message_id)` moves the cursor to
  a message delivered to the current generation. It never moves backwards and
  repeating it is harmless, so a lost response can be retried.
- **Wake hint.** `wake_hint(session, lease)` returns only `pending` and an
  opaque token that changes when something new arrives. No text, ids, counts
  or authors.
- **Membership.** Removal stops reads. Rejoining creates a new epoch: an old
  lease is refused and the old cursor is discarded, matching the ledger's
  future-only membership.
- **Clock.** The highest observed time is persisted, including when a lease is
  refused as expired, so a clock rewind after restart cannot revive it.

## MCP tools

`mission_approvals.server.build_server(offers, conversation_inbox=access)`
adds three tools when the host supplies a `conversation.inbox.InboxAccess`:

| Tool | What it does |
| --- | --- |
| `check_inbox(limit)` | New messages, oldest first, with control characters removed |
| `acknowledge_inbox(through_message_id)` | Marks messages handled up to one delivered message |
| `inbox_status()` | Whether anything is waiting, with no content |

`InboxAccess` fixes the lease at construction and takes the owner's current
session from a host callback, so tool arguments cannot change the owner,
assistant, conversation or session.

## Checks

```sh
python -B -m unittest conversation.tests.test_inbox -v
python -B -m unittest discover -s mission_approvals/tests -v
```

## Limits

One trusted host still holds the owner's session and can read what the owner
can read. The inbox store keeps cursor positions and message ids in plain
SQLite (no message text). It is not distributed delivery between machines:
that is the relay's job.
