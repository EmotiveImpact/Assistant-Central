# Temporary relationship task groups: owner workspace

This is trusted-local, fictional, in-memory organization of exact task contexts.
It is not person authentication, shared cryptographic identity, an authority
grant, a remote block, task cancellation, nondelivery evidence, or distributed
revocation. No external account, network service or agent wire grammar was added. The
existing owner workspace has a group interface, checked with DOM models only;
actual browser acceptance remains unverified.

## Closed owner API

- `GET /api/relationships`: detached array of group records.
- `POST /api/relationship-preview`: one of these exact bodies:
  - `{operation: "create", spec: {group_id, label, members}}`
  - `{operation: "attach", group_id, member}`
  - `{operation: "stop", group_id}`
- `POST /api/action`: `{action, review, confirmation}`. Action is
  `relationship_create`, `relationship_attach`, or `relationship_stop`. Review
  is the entire exact returned preview, including its digest. Confirmation is
  respectively `CREATE GROUP`, `ATTACH TASK`, or `STOP GROUP`.

Actual JSON examples are in `verification/v22-relationship-api-examples.json`.
Each member is exactly `{selector, context}`. Membership is never inferred from
names, labels, participants, or matching request text. Group IDs are immutable
`group-` slugs (maximum 54 characters); labels are inert, 1–80 characters.
There are at most 8 lifetime groups, each with at most 10 explicit contexts.
No rename, detach, delete, resume, or ID recycling API exists. Known catalog
contexts may be grouped before creation; custom contexts must already exist
through separately reviewed composition. Grouping allocates no signer, keys,
bindings, pairings, approvals, messages, receipts, or services.

Create review binds the registry revision. Attach review binds the exact group
ID, revision, existing membership, and added member. Stop review binds the group
ID, revision, and entire membership. Changed membership invalidates old reviews.
Stop commits retain their exact original review so only exact retries succeed,
even after unrelated groups change. A post-stop preview returns that same review.
Previews never allocate IDs, consume capacity, or create/modify services.

`list_tasks` and owner `state` add `local_work_stopped` and `relationship_groups`
(full detached matching group records), leaving original `phase` unchanged.
A group record has `group_id`, `label`, `revision`, `members`, `stopped`, and
`stop_review` (null until stopped). Revision increases on attach and stop.
Overlapping groups are allowed. Stop permanently fences every exact member
context, even through another still-active group. An active group's membership
cannot be expanded if it contains a fenced member. A different group or display
label cannot remove the fence. Unlinked contexts remain operational.

## Stop fence and preserved history

The fence is committed under the same workspace RLock used by every routed
service operation, before any later linked-service entry. Previously captured
adapter dispatch closures recheck it. Unknown future action names default to
blocked after stop. No task creation, binding, new adapter, proposal, proposal
import, response preview/preparation, review/pairing preparation, approval,
submission, delivery attempt, processing, storage reopen, or cancellation/revoke
review can proceed for fenced contexts. Group and context tombstones survive
successful/uncertain cleanup for the workspace lifetime; no restart/recovery
persistence is claimed.

The explicit post-stop owner action allowlist is:
- `check`: queries and verifies receipts, never retransmits or processes.
- `recover`: reconciles already-committed execution status, never submits.
- `decline`, `defer`: resolve existing pending reviews without authority.
- `withdraw_unused`: may sign an authority-reducing withdrawal of an existing
  unused authorization, never signs a new grant, sends, or makes a replacement.
- `close`/discard: always available, including after integrity failures, subject
  to exact task context and the existing discard confirmation.

These retain their original closed schemas, exact review requirements, state
checks, and signer verification. Existing adapters permit only `proposal_status`
and `inbox` after stop, in addition to their unchanged protocol lifecycle calls;
`propose` is denied even when it would otherwise be an idempotent replay.
History reads (`state`, `review`, `delivery`, received messages, proposals, and
read-only response context) remain available while the task service is open.
Close still discards its temporary service data as before; group tombstones
remain. The fence is never implemented by fabricating task/proposal/receipt
state. Delivery views preserve their original evidence state and attempt count,
but explicitly return `local_work_stopped: true`, `can_start_attempt: false`,
and `can_process: false`. Review cards retain underlying historical data;
clients must consult the task-local fence to suppress effectful controls.

An operation already holding the lock may finish before stop obtains it. This
is serialization, not preemption or recall. A child request can delay stop. The v23 fixture IPC bounds each complete
write/read exchange, but process creation, serialization, a whole multi-command
owner action and waiting for the workspace lock are not one shared deadline.
No stop preemption, interruption or hard process-isolation guarantee is
established. See FIXTURE_IPC.md for exact communication/cleanup limits.

Private in-memory state has an integrity seal and exact task resolution checks
so accidental mutation fails closed at routing. This is not tamper resistance
against code with arbitrary access to the Python process. Preview and result
objects are detached. Private direct service references are trusted harness
internals, not published owner/agent routes.

## Verification

Within your prepared virtual environment, run `python verify_checkpoint.py --full`
after checking the final checkpoint manifest. This installs nothing and reports
missing runtimes or dependencies instead of treating unrun tests as passing.

Focused tests: `tests/test_relationship_workspace.py`. Logs are
`verification/v22-integrated-relationship-tests.txt` and the final logs listed in
`verification-v22.json`.
Coverage includes pure reviews, stale/exact retries, closed schemas/capacities,
overlap, two capabilities, no new grouping authority, old adapter closures,
mutation routes, monotonic cleanup, receipt uncertainty/history, authority
reduction, and deterministic send/stop lock serialization. HTTP checks use the
in-process handler only, without sockets. No browser/native-dialog verification,
real-browser acceptance, real provider interoperability, or publication is claimed.


The frontend freezes requested operation, group revision, membership and known
task contexts before requesting a preview. Mismatched previews are refused before
showing a review or commit control. The server independently revalidates the exact
review. Group metadata is schema/scope-checked before rendering. Stopped tasks
retain ordinary navigation to received messages and staged-proposal history;
proposal import stays blocked. No review or mutation retries automatically.
