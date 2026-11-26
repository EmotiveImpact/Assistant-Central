# Restricted local host protocol profile (v16 stream layer)

This is an offline protocol and anonymous-pipe stream proof, not an installed native tool, a live
provider roundtrip, automatic wake, authentication or OS sandbox. It does not
claim full MCP conformance. No host configuration, account, port, credential,
relay, calendar or network operation is implemented.

## Standards consulted

The official **MCP 2025-06-18** specification was read on November 7, 2026:

- Base JSON-RPC messages and unique session request IDs:
  https://modelcontextprotocol.io/specification/2025-06-18/basic
- Initialization, version negotiation, initialized notification:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- Tools discovery, calls and text/error results:
  https://modelcontextprotocol.io/specification/2025-06-18/server/tools

These sources ground the message shapes and lifecycle, not native compatibility.
No MCP SDK was installed. This deliberately narrower local profile has bounded local stream framing, but no
production transport launcher or conformance certification. Later live integration
must select an actual host/version and verify supported transport and optional
fields before making compatibility claims.

## Trusted composition and authority

Trusted code constructs `RestrictedHostSession(task, actor, dispatch)` once, with
an immutable existing `Task`, one exact participant and that actor/task's
`AgentProposalBoundary.dispatch` callback. Only `handle(bytes)` belongs on the
untrusted wire. Never pass the executor's broad command router as this callback,
and never expose Python object references, owner signers, storage or trusted
executor pipes to untrusted code. Constructor inputs cannot be supplied or
rebound by protocol messages. A future authenticated host is responsible for
selecting these inputs, authenticating the caller, isolating processes and
providing transport/resource limits. The fixture tests' actor-selecting closures
are trusted test composition, not a public routing API.

The layer imports no owner service and dispatches only three closed commands:

- `propose`: exact `proposal_id` and v2 `envelope`; local proposal storage only.
- `proposal_status`: exact `proposal_id`; redacted current proposal/delivery state.
- `inbox`: no arguments; already processed task messages addressed to this actor.

Envelope and payload schemas are closed. Discovery derives a fresh schema for
this session only: its exact task, conversation, operation, capability, context,
sender and recipient are constants, and only the bound actor's request or result
direction is advertised. No other task or identity display/provider labels are
listed. Shared schema templates are never mutated. Runtime checks additionally enforce the
bound task, sender, route, context, request/result linkage and requested item
limit. JSON numeric values must use integer spelling for integer fields (for
example `2`, not `2.0`); JSON Schema's mathematical integer/const semantics cannot
express that lexical restriction. Envelope sender/recipient/task fields describe the existing immutable
scope; they are assertions to verify, never routing selectors. No owner import,
list, pair, sign, resolve, submit, dispatch, process, bootstrap or rebind command
is exposed. Payloads and HTTPS-shaped references remain inert untrusted text.

## Wire contract and deliberate restrictions

`handle` accepts one complete UTF-8 JSON message as bytes and returns one JSON
response as bytes or `None` for notifications. The separate v16 `restricted_host_stream.serve(reader, writer, session)` adds
bounded newline framing before invoking `handle`. There is no HTTP implementation,
socket listener or production process launcher.
Do not connect this function directly to a live host and claim native support.

Initialize with JSON-RPC `2.0`, a fresh ID, method `initialize` and exactly
`protocolVersion`, empty `capabilities`, and `clientInfo` containing only bounded
`name` and `version`. The response advertises version `2025-06-18` and only
`tools: {}`. If another version was requested, this supported version is returned;
a client that cannot use it must disconnect. Then send the ID-less
`notifications/initialized` with no params or empty params. Discovery and tool
calls before this handshake fail. Re-initialization is rejected. `ping` with no
params or empty params is supported. Trusted `close()` permanently closes the
session; wire messages cannot reopen it.

`tools/list` returns all three schemas with no pagination. `tools/call` requires
exactly `name` and `arguments`. Optional metadata, client capabilities, titles,
cursors and extensions accepted by broader MCP implementations are deliberately
not supported here. There are no resources, prompts, sampling, roots, progress,
subscriptions, cancellation handler, server-initiated calls or dynamic tool list.
Batches, client responses, extra fields and null/fractional/boolean IDs fail.
Unknown notifications are silently ignored, as are invalid operational
notifications. In particular `tools/call` without an ID never invokes a callback
or mutates anything. Malformed JSON or malformed message envelopes receive a
bounded parse/invalid-request error; recognizable notifications receive no reply.

Input is capped at 16 KiB, depth 32 and 2,048 JSON nodes; output at 32 KiB. Duplicate
object keys, nonfinite numbers and malformed Unicode are rejected. Proposal
commands and envelopes retain the v13 12 KiB/8 KiB bounds. IDs are safe-range
integers or 1–64 ASCII alphanumeric/underscore/hyphen characters. At most 1,024
unique request IDs are retained per session, including requests that fail after
ID validation. A later new ID closes an exhausted session. No ID eviction or
mutation replay cache is used. Calls are serialized. Memory bounds do not imply
CPU scheduling guarantees, a timeout for a stuck trusted callback, or protection
from clients repeatedly opening sessions; those are transport/host concerns.

RPC IDs and durable `proposal_id` are distinct. Every request needs a fresh RPC
ID; duplicate RPC IDs fail without invoking the callback. To inspect/retry a
proposal, use a fresh RPC ID with the same durable proposal ID and exact envelope,
or use `proposal_status`. Reconnect creates a new RPC session but does not renew
or reset owner history. Existing boundary idempotency and aliases preserve the
original declined/withdrawn/superseded review. The adapter never retries a
callback, even after a failure or response problem. An internal error means the
outcome may be unknown, not that mutation did not happen.

Errors use bounded fixed text and never echo callback exceptions, SQL, paths,
owner review cards or recipient details. Invalid methods/parameters use protocol
errors; a boundary denial uses a tool result with `isError: true`. Outputs are
validated against closed status/inbox projections, including task/recipient and
envelope digest. Only processed history can appear in inbox; receipt alone is
insufficient. `stopped_uncertain` remains visible as uncertainty, not a resend
permission. The callback still owns the processed-history proof: schema checks
cannot make an arbitrary or compromised callback trustworthy.

## Offline evidence

`tests/test_restricted_host_protocol.py` runs the existing v13 fictional adapter
process tests through two independently constructed wire sessions, plus lifecycle,
notification, malformed JSON, authority injection, bounded-ID, concurrent replay,
exception redaction, output-validation and reconnect cases. Alice and Bob's
proposal calls do not advance owner authorization. Independent explicit fixture
owner actions pair, import, approve, submit, deliver and process each request and
result. Reconnect after decline/withdrawal and cancellation during an uncertain
attempt preserve history and do not cause a resend. These are synthetic fixture
owners and disposable keys, not humans approving a real exchange.

See PROVIDER_READINESS.md for native tools, private roundtrip, wake and operational
acceptance gates. Frozen v13 artifacts are unchanged.

Final implementation verification: 464 Python tests passed in 72.217 seconds;
19/19 DOM-model checks passed; the protocol and both test modules compiled.
This includes nine independent review cases. Logs are in
`verification/v14-implementation-python.log`, `verification/v14-implementation-dom.log`
and `verification/v14-implementation-compile.log`. The empty compile log reflects
a successful no-output compilation. No actual browser or host acceptance ran.

## v15 trusted workspace composition

`OwnerWorkspace.adapter(selector, expected_context, actor)` constructs this same
restricted session around one independently started catalog task. Its callback
captures the exact child service and actor and checks liveness/context on every
call. No workspace create/list/select/close or owner action was added to the wire
grammar. Different task sessions never share keys, storage or owner authority.
The factory is trusted local composition only, not authenticated caller routing,
transport, native integration or OS isolation. A closed slot is never reused.
Closing the child task fences tool callbacks, not protocol-only ping/discovery on
an existing session. Workspace serialization provides no independent task latency
guarantee or callback cancellation; those remain host/transport concerns.


## v16 bounded local stream composition

The official MCP 2025-06-18 transports source was read on November 7, 2026:
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
Its stdio section specifies UTF-8 individual JSON-RPC messages delimited by
newlines, with no embedded newlines, and protocol messages only on stdout.
Optional diagnostics belong on stderr. The reusable stream function implements
these framing rules; real anonymous pipes exercise it locally. This is not a
claim that the entire restricted profile is MCP-conformant or installed in a host.

Trusted code supplies one existing `RestrictedHostSession` and blocking binary
reader/writer objects. Session creation, task/actor selection, workspace creation,
identity binding, pairing, proposal import, approval, submission and delivery
remain separate trusted owner operations. The stream accepts none of them.
One invocation exclusively owns its session; callers must not concurrently use
that session elsewhere. It closes the session on all exit paths but does not
close caller-owned file descriptors. No new launcher or owner control channel
is provided. Do not expose workspace references or trusted executor pipes.

- LF is the only record delimiter. JSON string escapes such as `\n` remain data;
  raw LF always ends an independent record. Producers must JSON-escape payload
  newlines; recovery cannot infer their intended boundaries. Multiline JSON is
  never assembled. CRLF is accepted
  through JSON trailing whitespace (CR counts toward the input bound).
- At most 16 KiB payload bytes are retained for the pending frame, with at most
  one additional bounded read of 4 KiB. Parsing/encoding/writing also make bounded
  transient copies; this is not an exact total heap allocation limit. Reads shrink to remaining capacity plus
  one sentinel byte. A complete frame of exactly 16 KiB is allowed. Output uses
  the existing 32 KiB message bound plus a single LF delimiter.
- Read fragments are accumulated without decoding until a complete frame exists.
  Complete malformed UTF-8/JSON, duplicate keys and empty records receive existing
  bounded JSON-RPC errors. Subsequent complete records can continue. Notifications
  receive no response and tool notifications never dispatch.
- Oversize frames terminate immediately without draining or attempting to parse
  or dispatch them; remaining bytes are not processed. EOF with a partial frame
  discards it without dispatch, even if its bytes form valid JSON. Neither path
  emits a transport diagnostic onto the protocol stream. Earlier complete records
  may already have executed and are not undone.
- Successful short writes are completed from the remaining response bytes, not by
  repeating the request or callback. Write failure, invalid/no write progress, or
  flush failure terminates the stream without retries and reports
  `StreamEnd('output_failed', outcome_unknown=True)` to the trusted caller. This
  includes failures after a proposal was committed or after a response might
  already have reached the peer. Flush success itself proves no peer receipt.
- Clean EOF, partial EOF, oversize and read failures return fixed local reason
  codes. These reports do not certify delivery of earlier replies or imply that
  any earlier proposal failed. `outcome_unknown=False` likewise does not certify
  absence of earlier mutations or acknowledgement of earlier responses. There is
  no automatic reconnect or mutation retry.
  Reconnect must be composed independently; use durable `proposal_status` and
  fresh RPC IDs to inspect history, never assume disconnection rolls back work.
- The stream emits no stdout/stderr diagnostics and no raw exception or payload
  text. Callback code is trusted and must itself avoid protocol-output pollution;
  this helper does not capture process-global stdout or sandbox Python code.

`read1(n)` is preferred for buffered pipes; otherwise `read(n)` must be a blocking
binary read returning at most n bytes. Nonblocking streams are unsupported. The
helper does not provide deadlines, cancellation of blocked reads/writes/callbacks,
a total byte/time budget, a rate limit, or a global session cap. The protocol's
1,024-request ID bound remains, but unlimited notifications or malformed records
can still consume time. This is bounded framing memory, not general DoS isolation.
A future actual host must supply lifecycle/resource policy and authentication.

`tests/test_restricted_host_stream.py` exercises fragmented real anonymous pipes,
coalesced messages, notifications, malformed records, exact limits, oversize and
partial EOF, short writes, write/flush failures and an actual broken output pipe.
Two independently scoped workspace streams use only explicit synthetic harness
owner steps, reject scope/authority injection and preserve the closed-workspace
callback fence. Lost replies after staging, fresh RPC IDs, repeated proposal IDs
and declined review aliases preserve owner history without automatic mutation
retries. No native host, automatic wake, real-account authentication or OS sandbox
acceptance was performed. Frozen v15 artifacts remain unchanged.

v16 implementation verification (before independent review additions): **501
Python tests passed in 70.960 seconds**, including 15 stream cases; **19/19
DOM-model checks** passed; the new module and test compiled. Logs:
`verification/v16-implementation-python.log`,
`verification/v16-stream-tests.log`,
`verification/v16-implementation-dom.log`, and
`verification/v16-implementation-compile.log`.
These counts do not imply browser, native host or full MCP acceptance.


## v26 runnable scripted clients

OFFLINE_PEER_DEMO.md adds two fixed stdlib-only client children with immutable
actor/task sessions. Their stdout carries this restricted protocol; separate
anonymous descriptors carry responses and bounded diagnostic reports. Trusted
supervisor control messages are not native provider-protocol evidence. Owner
commands remain in the existing separate terminal console, not on either stream.

The new narrow supervisor supplies explicit-step nonblocking pipe waits, fixed
frame budgets, correlated diagnostic reports and bounded child cleanup without
changing this module or the signer/executor launcher allowlist. It never polls,
reconnects or retries a callback. Limits exclude process spawning, trusted callback
execution, lock acquisition and whole owner actions. Distinct same-user processes
prove neither an OS sandbox nor installed-host or provider compatibility.


## v27 independent mixed-language client

An explicit mixed-demo option selects one fixed Node 18+ CommonJS client and leaves
the other in Python. Node 24.22.1/Linux is the tested runtime; no other Node/OS
acceptance is claimed. Independent byte framing, fatal UTF-8 decode, protocol
version negotiation and response-ID checks exercise the same restricted server.
Both actor assignments complete exact synthetic request/result roundtrips. The
CommonJS suffix prevents an enclosing JavaScript module project from changing
script interpretation. No server tools or owner authority are added.

Runtime resolution and the two-script choice belong only to trusted composition.
Child environments remain empty, descriptors explicit, and unknown outcomes never
trigger replacement/replay. This is offline language compatibility, not installed
host or provider interoperability. See OFFLINE_MIXED_PEERS.md.


## v28 separate SDK-backed legacy adapter

The original strict 2025-06-18 wire profile above remains unchanged. A new
transport-neutral `mcp_proposal_adapter.create_proposal_server(task, actor, dispatch)`
uses reviewed SDK 1.29.0 negotiation and decoded SessionMessage streams. It accepts
bounded ordinary protocol metadata while reusing the same application validator
through two small trusted facade methods. There is no actor/task selector on wire.

Supported legacy versions are 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25.
Unknown-version fallback is 2025-11-25, not 2026 support. SDK tests establish this
restricted decoded-stream profile, not universal conformance or native acceptance.
No real stdio/HTTP launcher, authentication or peer transport is provided. Raw
framing/parser bounds, safe SDK logging and non-preemptible callback policy remain
embedding responsibilities. See MCP_ADAPTER.md and its independent review.


## v29 bounded raw frontend for the SDK adapter

The optional mcp_raw_codec.py validates UTF-8 bytes, duplicate members, IDs, depth,
nodes and record size before SDK construction. mcp_lf_bridge.py connects only
caller-provided asynchronous byte streams to a pre-bound SDK adapter. It does not
open stdio, a listener or another transport, and adds no tool or owner permission.

Records are limited to 16 KiB before parsing and output to 32 KiB, excluding LF.
Malformed records consume a finite admission budget; raw errors can carry null IDs.
The original strict protocol is unchanged. Clean EOF can discard queued responses
in the SDK layer, so prior admitted requests retain unknown outcomes without replay.
No native acceptance, flush guarantee or hard callback deadline is implied.
See MCP_RAW_CODEC.md and MCP_RAW_INDEPENDENT_REVIEW.md for exact contracts.
