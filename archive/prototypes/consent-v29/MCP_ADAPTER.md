# Offline SDK-backed proposal adapter

This is an offline protocol interoperability proof, not a native-host installation,
production transport, authentication service, relay, wake integration or security
certification. No host configuration, account, credentials, network listener or live endpoint
is created. Async runtimes may use internal local wakeup descriptors. The fictional names in the tests are not authenticated
owners. ClientInfo (including name/title/provider labels) is never identity proof.

## Supported protocol, exactly

`mcp_proposal_adapter.create_proposal_server(task, actor, dispatch)` constructs a
single-use SDK-backed adapter. Await its `run(read_stream, write_stream)` with the
public MCP SDK's `SessionMessage` memory-stream interface. This is a trusted
composition API, not a public task/actor selector. It opens no transport.

The reviewed optional dependency is **Python MCP SDK 1.29.0**. Its actual legacy
negotiation supports **2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25**. A supported
requested version is returned; an unknown version receives the SDK's 2025-11-25
fallback. The client must accept that version or disconnect. **2026-07-28 is not
implemented.** An unknown-version negotiation test is not modern-protocol support.

The SDK handles initialization, tool discovery/calls, ping and cancellation. The
adapter requires initialize followed by notifications/initialized before tools.
Bounded optional client metadata, titles, nonempty capabilities and request _meta
are accepted as protocol data. Advertising roots, sampling, elicitation or
experimental features adds no application permission, handler or external call.
There are no server-initiated requests. Only tools are advertised by the server;
there are no resources, prompts, subscriptions, dynamic tools or task execution.

Standards basis: the legacy lifecycle, tools and cancellation sections at
https://modelcontextprotocol.io/specification/2025-06-18 and the installed SDK's
public `Server`, `ClientSession`, message models and supported-version list.
No compatibility with a particular host/build/OS is inferred from these tests.

## Immutable application authority

Trusted composition must supply one exact existing Task, one of its participants,
and that actor/task's **AgentProposalBoundary.dispatch** callback, or an equally
restricted existing owner-workspace closure. Never supply a broad executor router,
owner interface, workspace manager or signer. Caller authentication, selecting the
correct binding and protecting Python object references remain integration duties.
Only streams are peer-facing. An untrusted Python caller in the same process is
not isolated by this design.

The three tools are exactly:
- propose: a durable proposal_id plus the exact closed task envelope.
- proposal_status: a durable proposal_id, returning the redacted historical state.
- inbox: no application arguments; only processed messages for the bound actor.

Schemas are freshly scoped to the actor's immutable request/result direction,
task, context, capability and peer. All application arguments remain closed.
Metadata is never merged into those arguments. No signing, review, approval,
submission, delivery, receipt processing, pairing, workspace or key tool exists.
Payloads and HTTPS-shaped references remain untrusted inert data, never fetched.

Two public composition methods on RestrictedHostSession reuse its existing
`_call` and `_validate_output` implementation. The original restricted wire profile
is unchanged. This small facade avoids copying application authorization logic
into the SDK adapter. It bounds input/output, serializes synchronous calls and
converts failures to fixed tool errors. The SDK's redundant JSON-Schema validator
is disabled because its error messages can echo input values, and because JSON
Schema integer semantics differ from the existing lexical integer restriction.
The authoritative validator still rejects 2.0 where an integer spelling is needed.

## Errors, replay and cancellation

RPC request IDs and durable proposal IDs are different. The adapter rejects reused
RPC IDs without executing a second callback. Exact durable proposal retries and
aliases use the existing persistent boundary's history; declined/withdrawn work
cannot acquire new authority by changing the proposal ID. Cross-actor/task IDs,
wrong result linkage, unprocessed requests and over-limit results remain denied.
Receipt alone does not disclose an inbox message.

A callback is never retried automatically. SDK cancellation, lost responses,
disconnection, internal failure or a malformed callback result do not prove that a
proposal was not stored. Inspect durable proposal_status with a fresh RPC ID in a
separately composed session. Existing stopped_uncertain delivery remains uncertain;
it is never converted to resend permission.

Synchronous callbacks preserve thread-affine storage and the existing serialized
application boundary. They run on the event-loop thread and **cannot be preempted
by a cancellation or deadline**. Cancellation may be processed only after a
callback commits. No prompt cancellation or callback CPU/time bound is claimed.
Do not use this as a production untrusted-callback executor.

The adapter prevalidates typed requests/notifications before SDK forwarding, drops
unknown notifications, and handles unknown tool names before SDK cache lookup.
This prevents SDK validation warnings from echoing rejected caller data. Outgoing
SDK errors are replaced with fixed text. Application exceptions and invalid output
projections are likewise redacted. Transport exceptions can still reach the
trusted embedding caller; it must not expose raw exception diagnostics to a peer.
The SDK uses Python logging. Normal DEBUG logs can include protocol data such
as initialized-notification _meta, and INFO cancellation paths may include client
RPC IDs. Fixed wire errors are not universal diagnostic redaction. A production
embedding must select safe logging policy. This adapter does not
mutate process-global logging configuration or capture arbitrary callback output.

## Extra local limits versus standard behavior

These are deliberate profile limits, not general MCP requirements:
- One initialize and one session per adapter instance; no reset/reopen/reconnect.
- RPC IDs are safe-range integers or valid-Unicode strings of at most 256 UTF-8
  bytes, including empty strings and ordinary punctuation. Application proposal
  and task identifier rules are unchanged.
  Invalid IDs terminate silently because the SDK's error model cannot represent
  the JSON-RPC null error ID. No invented ID or callback execution is used.
- At most 1,024 retained request IDs and 2,048 total incoming messages per session.
  Exceeding either terminates ingestion. Pending SDK handlers can exist up to this
  finite request budget; there is no global session, rate or wall-time limit.
- Decoded input is bounded to 16 KiB of JSON re-encoding, depth 32 and 2,048 nodes;
  output to 32 KiB. Ordinary encoding can create bounded transient copies.
- tools/list returns three tools, with no pagination; non-null cursors are rejected.
  tools/call accepts only name, arguments and optional protocol _meta. It does not
  support task-augmented calls. Missing arguments mean empty arguments per SDK;
  explicit null/non-object arguments are rejected before SDK coercion.
- Unknown methods return a fixed protocol error. Operational notifications never
  call tools. Only well-formed initialized/cancelled notifications are forwarded.
- Transport-side metadata objects are stripped rather than treated as identity.

The input streams contain **already parsed** SDK message objects. These bounds do
not protect allocation during raw JSON parsing, detect duplicate JSON members
already discarded by a parser, or provide LF framing. The separate optional MCP_RAW_CODEC.md frontend now supplies bounded raw JSON
admission, duplicate/nonfinite rejection and LF framing for caller-owned async
byte streams. Concrete transport setup, authentication, deadlines, output
backpressure and safe diagnostics remain embedding responsibilities. The old restricted LF stream is not this SDK
transport and cannot be connected by changing a protocol constant. No launchable
stdio entry point is claimed here.

The adapter owns and closes only its internal memory endpoints. Trusted embedding
owns external endpoint lifetime. Abrupt external closure may terminate with an
exception; it never causes replay. No transport-layer delivery acknowledgement,
OS sandbox, process isolation, throughput guarantee or native conformance follows.

## Dependencies and verification

Normal existing fixture/runtime modules do not import MCP. Base requirements stay
unchanged. `requirements-mcp-offline.txt` adds the optional exact MCP SDK pin to the
existing fixture pins. No installation was performed. These are direct dependency
pins, not a hash-locked transitive dependency distribution or provenance attestation.

Tests import the SDK without skip guards: missing/incompatible SDK fails
verification rather than reporting a partial pass. The checkpoint dependency
probe explicitly imports MCP client/server APIs and verifies its pinned version;
a missing or mismatched SDK marks preflight incomplete and the Python suite not-run.
Full checkpoint verification
must include these SDK tests and the existing Python and DOM-model suites.
Run the focused suite using the already available approved dependencies:

    python -m unittest discover -s tests -p 'test_mcp_proposal_adapter.py' -v

The independent SDK client runs the existing proposal/owner-process boundary
suite through memory streams, including each request/result tool, processed-inbox
fences, exact scope, owner injection, decline/history and durability. Spec-shaped
raw SDK messages additionally exercise legacy negotiation/fallback, nonempty
capabilities/metadata, lifecycle, duplicate RPC IDs, malformed/oversize arguments,
fixed errors and response-loss/cancellation without replay. Separate independent
review cases live in tests/test_mcp_adapter_review.py. These are fictional offline
fixtures, not human consent or a native provider acceptance test.

Live-host, owner-authentication, custody, transport/data-destination, native-tools,
private-roundtrip and wake gates in PROVIDER_READINESS.md remain open.

The raw bridge does not change the decoded adapter lifecycle: clean input EOF
may cancel queued handlers/egress before replies are sent. A prior admitted request
can therefore have an unknown outcome even on ordinary EOF. Keep the input open
while awaiting replies; do not infer rollback or automatically replay on any loss.
