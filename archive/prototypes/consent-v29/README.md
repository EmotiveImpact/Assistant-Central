# Human-approved assistant network: offline prototype

A relationship-based communication network for different people's assistants,
across providers. Scheduling is one possible task, not the product boundary.
Relationships should help people choose whom to work with. They must never become
implicit permission to disclose private information or execute tools.

This checkpoint is an **offline fictional development fixture**, not a connected
assistant network. Alice and Bob are roles controlled by one trusted local
operator. Provider labels do not establish compatibility or authenticate people.
No account, API key, relay, calendar or live-provider connection is used.
Product naming, distribution and the license for newly written code remain open
product decisions; pinned upstream notices are preserved.

## Start here

- [QUICKSTART.md](QUICKSTART.md): run the temporary owner workspace and complete
  a fictional request and response through separate owner controls.
- [CONSOLE_GUIDE.md](CONSOLE_GUIDE.md): use the trusted terminal interface for
  custom tasks, responses, history and relationship controls.
- [OFFLINE_PEER_DEMO.md](OFFLINE_PEER_DEMO.md): two scripted client processes
  using restricted tools while owner decisions remain separate.
- [OFFLINE_MIXED_PEERS.md](OFFLINE_MIXED_PEERS.md): optional Python/Node
  client combinations, independently exercising the same restricted wire profile.
- [PROVIDER_READINESS.md](PROVIDER_READINESS.md): acceptance gates and decisions
  required before any real host or transport integration.
- [ARCHITECTURE.md](ARCHITECTURE.md): scope, permissions, identity fixtures,
  transport, storage and trust boundaries.
- [HOST_PROTOCOL.md](HOST_PROTOCOL.md): the restricted local JSON/stream profile.
- [MCP_ADAPTER.md](MCP_ADAPTER.md): optional SDK-backed legacy MCP adapter,
  tested offline with independent SDK clients and exact authority limits.
- [MCP_RAW_CODEC.md](MCP_RAW_CODEC.md): bounded raw JSON admission and an optional
  LF bridge for caller-supplied asynchronous byte streams.
- [FIXTURE_IPC.md](FIXTURE_IPC.md): trusted local process deadlines and cleanup.
- [RELATIONSHIP_WORKSPACE.md](RELATIONSHIP_WORKSPACE.md): exact task grouping
  and one-way local stop controls, with their scope and limitations.
- [CONTINUITY_OWNER_GUIDE.md](CONTINUITY_OWNER_GUIDE.md): optional informational
  links between independently keyed fictional task identities.
- [UI_VERIFICATION.md](UI_VERIFICATION.md): frontend evidence and unverified areas.
- [CHECKPOINT_HISTORY.md](CHECKPOINT_HISTORY.md) and [CHANGELOG.md](CHANGELOG.md):
  preserved implementation history and older commands/evidence.

Python 3.11+ is the declared minimum. Full fixture verification has run on Linux
with Python 3.12 and the pinned dependencies in `requirements-offline.txt`.
Other operating systems and Python versions have not been acceptance-tested.
Node 18+ is required for full verification and the optional mixed-language demo,
not the Python-only owner app. Node 24.22.1 on Linux is the tested runtime.

## What you can try

Run `python local_owner_app.py --workspace` after following the dependency setup
in the quickstart. Open only the loopback URL printed by your own launcher and
keep the terminal running. Do not expose its port or enter real/private data.

The workspace offers two fixed examples and up to eight custom temporary tasks:

- **Public-resource shortlist:** an exact question and up to five fictional
  resource references. URLs are inert, unverified strings.
- **Bounded plain-text exchange:** an exact prompt and a nonempty response within
  an owner-chosen limit of 1–512 Unicode code points.

The local operator composes custom responses. No AI runs in the background,
retrieves references or interprets received messages as instructions.
See [TEXT_EXCHANGE.md](TEXT_EXCHANGE.md) for the bounded-text schema.

Each task has independent temporary stores, owner signer processes and transport
keys. Creating a task grants nothing. Its transport bindings, both pairing
directions, exact message review/approval, submission, delivery and receipt
processing remain separate explicit steps. The received-message view shows only
already processed content addressed to the chosen fictional role.

The lower-trust agent interface can propose a message, inspect proposal status or
read its processed inbox. It cannot choose another scope or expose owner sign,
submit, pairing, delivery or processing commands. It is a reviewed local protocol
boundary, not an operating-system sandbox or authenticated native provider host.

## Use the trusted terminal interface

`python workspace_console.py` opens the local owner console. It supports exact
custom-task and relationship previews with separate typed confirmations, explicit
task selection, received-message reads and the same backend owner controls.
The guide includes bounded text and shortlist examples. No received text is
interpreted as a command.

After uncertain communication the console retains a read-only inspection session
until you explicitly close tasks or quit. It does not retry a mutation, replace a
route or silently erase history. Reads depending on a terminated child may still
fail. Explicit session shutdown discards temporary data and may retry idempotent
resource cleanup, not owner approvals, submissions or sends.

## Try two scripted client processes

`python offline_peer_demo.py` starts a trusted terminal walkthrough. After you
explicitly create/select the fixed bounded-text task and review both transport
bindings, launch two scripted clients. They discover only proposal, status and
processed-inbox tools; owner pairing, import, review, approval, submission,
delivery and processing remain separate terminal choices.

The explicit `--simulate` mode reproduces fixed synthetic owner choices. It
checks that a delivery receipt alone does not reveal recipient inbox content.
This demonstrates two local client processes, not independent provider services,
real human approval, network interoperability or an OS sandbox. See the demo
guide for commands, bounded pipe waits and uncertain cleanup behavior.

To run one independently implemented Node client, explicitly add
`--mixed-node alice` or `--mixed-node bob` to the demo command. Either role can
use Node; the other stays Python. The Python-only default never looks for Node.
Mixed runs check negotiated versions, byte framing and exact Unicode content,
while preserving every separate owner decision. This is language-neutral local
wire evidence, not installed-provider interoperability.

## Group related fictional tasks

A temporary relationship task group links only the exact task contexts the
operator explicitly selects and reviews. Creating or expanding a group starts no
service and grants no identity, pairing or send authority. Each task keeps its
independent keys and approvals.

**Stop further work in this group** requires a fresh review of the complete
membership and `STOP GROUP`. It permanently prevents new work in those contexts
for this launcher run, including callbacks created earlier. Processed history and
receipt evidence remain readable, and explicitly permitted authority-reducing
actions remain available. Other tasks are unaffected.

This is not a contact directory, persistent relationship identity or a global
block on a person/provider. Started actions may finish before the serialized stop
commits; disclosed data cannot be recalled. There is no resume or automatic
reattachment. See the relationship guide for exact allowed operations.

## Optional fictional continuity proofs

Explicitly opt in with `python local_owner_app.py --workspace --continuity` or
`python workspace_console.py --continuity`. Enroll a disposable continuity key,
then separately review and confirm each association with an existing task owner.
Two domain-separated signatures provide historical possession evidence linking
independent task keys to that fictional continuity key.

This is informational only: it grants no pairing, approval, message or account
permission and does not identify a real person or provider. Task keys and consent
remain separate. Association reviews expire after two minutes; certificates are
recognized for at most 24 hours and never renewed automatically. Stopped/closed
tasks or retired identities cannot create new associations. Historical evidence
and uncertain attempts remain inspectable for the disposable launcher run.

Retiring continuity recognition **does not stop task messages or revoke grants**.
Use task/group controls separately. Default launches create no continuity registry
or signer. See [CONTINUITY_PROOFS.md](CONTINUITY_PROOFS.md) for exact semantics.

## Consent, uncertainty and stopping

- An agent proposal or received message is data, never an owner instruction.
- Exact retries preserve original review history, including refusals and
  withdrawals. Changed content requires a new review.
- A timeout or missing receipt is an unknown outcome, not evidence of nondelivery
  or permission to resend. No automatic mutation retries are performed.
- Cancellation and revocation fence future work within their defined local
  scope. They cannot recall already disclosed data or a started dispatch.
- Closing a task discards its temporary records and keys when cleanup succeeds.
  A closed/uncertain slot cannot be reused in the same run. This is not a
  persistent inbox or recovery after key loss.
- Closing the browser tab does not stop the launcher. Use Ctrl+C in its terminal
  when finished, and inspect any reported cleanup uncertainty.

## Optional SDK-backed MCP adapter

The new transport-neutral adapter uses the reviewed Python MCP SDK 1.29.0 and
accepts ordinary bounded client metadata without granting new powers. It exposes
only the existing scoped proposal, status and processed-inbox tools. Caller/task
binding still comes from trusted composition; client labels are not authentication.
Owner signing, approval, sending and processing remain separate.

The SDK negotiates its four supported legacy versions through 2025-11-25. This is
not 2026-era protocol support, a native-host installation or a network listener.
The decoded SDK layer and optional bounded raw JSON/LF bridge are tested with
in-memory streams, including an actual SDK client. The bridge supplies strict
byte/depth/node admission, duplicate-key rejection and serialized bounded frames.
It opens no transport. Clean input EOF may discard queued responses, so prior
admitted outcomes remain uncertain and are never retried. Embedding still owns
authentication, endpoint lifetime, deadlines and logging policy; synchronous
callbacks are not preemptible. Normal SDK logs can contain client metadata/IDs.
See MCP_ADAPTER.md and MCP_RAW_CODEC.md before integrating it. Base owner applications do not need MCP;
complete checkpoint verification additionally needs requirements-mcp-offline.txt.

## Trusted local process failures

The local fixture bounds complete request/response pipe exchanges, including
partial writes and partial replies, and drains diagnostics without retaining
them. A failed or late response closes and reaps that owned child. No retry is
automatic, and timeout still cannot establish that a command did not commit.
These are Linux fixture limits, not an OS sandbox or a guaranteed deadline for
an entire owner action or group stop.

## Latest verified checkpoint

**v29:** 948 Python tests and 273 DOM-model checks passed in a fresh archive
extraction; all 153 frozen source-file hashes matched. Verification includes
normal and failed deliveries, isolation, owner consent, exact retries, bounded
Unicode messages, storage faults and independent regressions.

A deterministic fault campaign additionally exercised 1,920 interleaved probes
across 16 task scopes and 32 history/fault scenarios. These are coverage counts,
not additional unittest cases. Local storage-corruption checks are not a claim
of cryptographic storage authentication or a demonstrated remote-agent exploit.
Run `python verify_checkpoint.py` for a fast offline preflight, or explicitly use
`python verify_checkpoint.py --full` to rerun the local suites. Neither installs
anything. Missing prerequisites or unrun suites are reported honestly.
See `verification-v29.json` and its linked report for exact evidence.

**Not verified:** real-person authentication, real-browser rendering/native
dialogs/accessibility, native provider interoperability, host wake, live transport,
persistent key custody, OS isolation or production security. DOM-model checks
are not browser tests. No browser retry or workaround was attempted.
