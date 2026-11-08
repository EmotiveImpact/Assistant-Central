# Relationship-based assistant communication

## Product goal and current boundary

Different people's assistants should communicate across providers because their
owners deliberately connect them and approve scoped authority. Friends, teams and
partners are relationship contexts, not automatic grants to private data. Meeting
coordination is an example, not the whole product. Product name, open-versus-closed
distribution and whole-project licensing remain undecided.

This checkpoint is offline and fictional. It demonstrates reusable permission,
identity-binding and delivery foundations plus two application paths. It does not
connect real Claude, dot, Hermes or other provider accounts, enroll real people,
create persistent credentials or expose a public service.

## Layers

1. **Identity references:** immutable local IDs plus provider/display labels.
   Labels are descriptive only. Existing owner verification keys and approved
   transport-key possession proofs establish fixture identity binding, not a real
   person's identity. The two task peers determine roots and receivers.
2. **Connections and authority:** bilateral pairing remains scoped to the exact
   task context. A broader conversation member receives no task permission.
   Pairing is not disclosure consent. Every outbound message needs a separate
   exact owner-signed envelope approval. A real relationship directory and more
   durable relationship grants are not implemented yet.
3. **Conversation and task context:** generic_protocol.py defines frozen
   IdentityReference, Conversation and Task objects. Context hashes include the
   conversation, identity references, requester, responder, capability and
   operation. Changing any dimension requires a new context and approvals.
4. **Capability boundary:** generic_capabilities.py is a static closed schema
   allowlist. It neither registers remote tools nor performs effects. Unknown
   capabilities/fields fail closed. Text can contain hostile instructions but is
   stored and displayed as untrusted data, never interpreted as authority.
5. **Application projection:** generic_session.py validates one request and one
   exact linked reverse-route result, persists transitions, and reconstructs from
   history. It does not fetch URLs or run agents/tools. The original scheduler is
   the v1 application adapter with availability/proposal/accept messages.
6. **Transport and delivery:** private_message_adapter.py dispatches explicit v1
   scheduling or v2 task data to the same pinned A4A private-message primitives.
   Existing owner proofs, identity binding, encrypted outbox, distinct recipient
   receipt stores and reconciliation stay in the path. Receipt and processing
   are separate, and uncertainty is never translated into a safe resend claim.
7. **Owner interaction:** the shared console and closed service API now support
   generic tasks through separate disposable owner signer children and a public-
   only executor. Exact task review/approval/submit/delivery boundaries are reused.
   The default browser mode targets v1; explicit `--workspace` uses separate
   generic owner assets. Live provider-host integration and actual human
   authentication remain unimplemented.

## Untrusted adapter proposal boundary

`AgentProposalBoundary` is constructed by the trusted host for exactly one task
and one of its two actors. Its sole adapter method is `dispatch` with a closed
JSON grammar: propose, proposal_status, inbox. No command may supply an actor,
owner, arbitrary task, grant, signature or owner/executor method. Scope and route
validation use the existing exact v2 protocol; result proposals require the exact
processed request digest and requested item limit. Text never becomes instruction.

Proposal rows and caller-ID aliases are atomically stored separately from owner
requests. Fingerprints deduplicate by actor/context/exact envelope; mismatched ID
reuse fails. Replays can read historical status after the task becomes terminal,
but cannot create a successor. The trusted owner list shows at most 20 distinct
proposals per bound actor. Separate owner import atomically links to an existing
exact review (including historical refusals) or creates one unsigned review using
the existing current-permission checks. Pairing, sign, resolve, submit, dispatch,
receipt check and processing remain outside the adapter grammar.

The inbox projects only already committed task transitions addressed to the bound
actor. It exposes neither sender outbox nor unprocessed recipient receipts, other
actors' inbound messages, unrelated tasks, signatures nor owner review state.
Previously disclosed processed history is retained after cancellation/revocation;
those controls fence future work, not erase past knowledge. Status returns only
proposal ID, envelope digest, original review state and delivery state, with no
reconciliation or execution side effect. Capacity is bounded without deleting
refusal/history records; exact retries survive a full store.

This is a local JSON authority boundary, not OS process isolation. The fixture
executor's actor-selecting wrapper and owner proposal list/import commands belong
only to the trusted harness. A production host must authenticate and bind a
provider before routing only nested adapter commands, and isolate untrusted code
from trusted pipes, signing children, object references and storage. No actual
provider MCP compatibility, provider inference or wake/roundtrip is claimed.
See PROVIDER_READINESS.md for acceptance gates beyond this offline proof.

## Generic v2 envelope

The exact fields are version, type, conversation, task, operation, reply_to,
capability, context, sender, recipient and payload. Type is request or result.
A result references the digest of the exact processed request and uses the
reverse requester/responder route. Version 1 remains closed and unchanged;
there is no automatic schema or stored-state migration.

Payloads are detached canonical JSON snapshots, bounded to 8 KiB at ingress.
Python JSON-compatible tuples normalize to lists before wire-schema validation;
this is not a second wire interpretation. The initial capability is
public-resource-shortlist-v1, with a bounded query/max_items request and bounded
items result. HTTPS-shaped references are inert strings, not validated public
sources or navigation permission. Adding a capability requires reviewed schemas,
projection rules and permission tests, not a remote declaration alone.

## Reuse and compatibility details

The generic session inherits atomic storage/submit/cancel/view methods, not the
scheduling projection. A temporary session.meeting = task compatibility alias
exposes only task id/participants to existing consumers. The existing signed
cancellation target field is still named meeting and contains the exact task ID;
its cryptographic scope is unchanged. A later owner-control version should name
scope explicitly rather than silently changing this existing signed grammar.

The unchanged upstream modules and licensed test vectors are tracked in
UPSTREAM.json. Our generic layer is new application code. We do not execute the
full A4A client, MCP server or public relay, and the offline proof does not
establish wire compatibility with arbitrary live provider installations.

## Proven and not proven

The synthetic non-meeting request/result traverses exact signed owner approval,
encryption, authenticated fixture peers, durable queueing, signed receipt and
inert task processing. Tests cover missing consent, wrong scope/recipient,
third-member exclusion, result linkage/limits, cancellation, revocation, uncertain
receipt recovery and record reopen without duplicate processing. Existing
scheduling regressions continue to pass.

Not proven: real-person identity, persistent key custody/recovery, provider-host
compatibility, real agent execution, a general relationship directory, real-browser acceptance of the generic
owner workflow, live transport, distributed revocation, production scale
or browser acceptance. No externally received agent instruction is treated as
permission to act for the owner.

## Restricted host protocol layer (v14)

`RestrictedHostSession` accepts one bounded JSON message and emits a bounded
JSON-RPC response or no response for a notification. Trusted construction binds
an immutable task, actor and restricted proposal callback. The parser owns only
initialization, tool discovery, closed arguments, serialized request-ID tracking
and output validation. Owner signers and executor routing are absent from its
imports and tool schemas. Protocol notifications never execute tools. Duplicate
RPC IDs are rejected; durable proposal IDs continue to identify the original
proposal across fresh RPC sessions. Callback errors are sanitized and never
retried. Uncertain delivery remains uncertain.

Official MCP 2025-06-18 messages informed this deliberately restricted local
profile; omitted optional fields and transport mean no full conformance or actual
host support is claimed. It adds protocol-level offline proof, not a network
service, native tool loading, wake, caller authentication or OS isolation. See
HOST_PROTOCOL.md for the contract and official references.

## Trusted two-task workspace (v15)

`task_fixtures.py` is a closed startup catalog: the original garden task and a
second astronomy task with Bob requesting Alice. All names/provider labels are
fictional references, not a persistent identity shared between tasks. Each
`OwnerUIService` starts separate owner signer children and executor, generates
fresh independent keys, and owns a temporary directory containing its sender and
receiver stores. No shared ledger or mutable executor task selection is used.
Signers and executor independently reconstruct the exact selected catalog task
from `--task-fixture`; no uploaded task JSON or live switching is accepted.
`GenericOwnerWorkflow` matches the entire immutable Task before selecting guide
payloads, not just its ID. The legacy garden fixture remains byte-compatible.

`OwnerWorkspace` is trusted local composition, not a network/agent API. Creation
requires an exact catalog selector and context and does not bind identities,
pair, approve, submit or deliver. Every routed read/action also supplies both
selector and expected context. Creating a slot occupies it for the workspace
lifetime, including failed startup and closed slots. A stale callback cannot
reach a replacement incarnation. Metadata listing is owner-only. Context hashes
are scope checks, not human authentication or authorization tokens.

The adapter factory constructs the existing RestrictedHostSession with an exact
service/task/actor-bound callback. Only its handle(bytes) function is intended
for an untrusted wire; no workspace object, service, process pipe or Python
object access is safe to expose. The three-command adapter grammar is unchanged.
Owner-only proposal discovery/import remains explicit and creates unsigned review
only. Previously required binding, approval, submission, dispatch, processing and
withdrawal confirmations remain separate. The workspace provides no automatic
mutation retry. Storage reopen retains existing live fixture keys; it does not
restart processes or recover identity after key loss.

Task closure fences routing before cleanup, leaves an occupied tombstone, and
does not close the other task. Workspace closure attempts every task even if one
cleanup raises. Incomplete cleanup is reported as uncertain, never as a successful
recovery/discard claim. Startup failure is conservatively marked cleanup-uncertain
because the constructor cannot prove its outcome to the workspace.

`workspace_console.py` adds a trusted interactive owner console and an explicit
interleaved simulated demo. It captures selector/context for each action and does
not change HTTP/browser code. There is no browser acceptance, real provider host,
persistent identity, live transport, background agent execution or OS isolation.

Isolation here is authority/storage/process separation, not independent latency or
fault scheduling: the workspace serializes routed operations with one lock, so a
slow child can delay another task's call. Closing a task fences adapter callbacks;
an already constructed protocol session may still answer protocol-only discovery
or ping for its original scope. It cannot access a newly created incarnation or
invoke the closed child. Only the trusted caller can close that protocol session.

V15 implementation verification: 486 Python tests passed in 69.767 seconds,
including the 22 workspace/independent-review cases; those 22 cases also passed
separately in 11.484 seconds with frozen-v14 golden assertions. Existing DOM-model
checks passed 19/19. Interleaved workspace and single astronomy console demos
completed both exact messages. Logs are under `verification/v15-*`; this is
console/protocol/model evidence, not actual-browser or live-host acceptance.

## Generic owner interface (v17)

`local_owner_app.py --workspace` selects `WorkspaceHandler` and separate
`workspace_ui` assets. Legacy mode and assets remain the default. The subclass
inherits Host/Origin, JSON content type/header, body limit, duplicate-key and
nonfinite-value checks, response headers, static allowlist and bounded handler
concurrency; it overrides only API routing and static root. Query parsing now
preserves then rejects empty fields, including empty duplicate parameters.
Both HTTP modes also reject exponent-overflow floats before service dispatch,
not only the nonstandard literal NaN/Infinity tokens.

`WorkspaceUIService` has no selected-task state. Its exact action wrapper is
`{selector, context, request}`. Only explicit `create` starts a temporary service;
metadata discovery is read-only. Scoped reads require selector, context and owner
(and request ID for review/delivery). `import_proposal` returns the same request
result wrapper used by the existing owner controls. Task closure maps to
`task_closed`, avoiding legacy whole-server shutdown. No agent-facing grammar,
capability scope, keys or persisted protocol records change.

The frontend snapshots selector, context, owner, view generation and hash. Buttons
capture that rendered snapshot; approvals additionally capture request ID and
review digest. Navigation cancels the dialog synchronously, stale closures fail
closed, and delayed reads/mutations cannot overwrite or navigate a newer view.
Rapid clicks are suppressed while a mutation is pending. Task/recipient/review
text is included in consequential confirmation dialogs. Binding confirmation
uses the binding's actual owner even when another owner is being viewed.
Text and URLs use textContent only. No remote resource, anchor, HTML rendering or
payload interpretation is added. Proposal discovery/import is explicit and
preserves original review history; no simulated or live agent runs automatically.

Uncertain startup/closure is inspected via read-only metadata, with affected
mutation controls blocked. A closed slot has no recreate control. Delivery status
continues to distinguish queued, attempted/uncertain, received, processed and
blocked outcomes. Existing receipt checking is explicit and never sends/processes.
These frontend constraints supplement existing exact-context server checks;
navigation, digests and the fixed JSON header are not human authentication.

Verification is in-process handler/service integration and a separate JS DOM
model, plus legacy regressions. No real browser was launched or bypass attempted.
Rendering, native dialog behavior, accessibility and visual acceptance remain
unverified. No live provider connection, enrollment, persistent identity or
production readiness is established.


## Trusted owner task composition (v18)

`task_composer.py` is a pure, closed parser and preview generator. It admits only
fictional Alice/Bob directions and the existing public-resource-shortlist
capability. Task selector, task/conversation IDs, requester, inert question and
item count are the entire spec; arbitrary peers, tools, provider endpoints and
capability registration remain unsupported. The query is nonempty bounded text,
not executable instructions or a permission grant.

An optional `composition_digest` on `Task` commits the complete validated spec
into its exact task context. It is absent from legacy serialization when unset,
so the garden/astronomy hashes are unchanged. The commitment is a scope binding,
not authentication, owner approval or a claim of external protocol compatibility.
Every custom signer/executor reconstructs and validates the same immutable spec
at startup. The signer, owner workflow and agent proposal boundary reject changed
request payloads even when the caller keeps the old context string.

The preview endpoint has the same bounded HTTP parser and same-origin controls
as owner actions, but does not allocate state or keys. Creation revalidates the
exact spec and its preview digest, then requires the typed owner confirmation.
There is no mutable server-side "last preview" pointer. A workspace lock covers
capacity, duplicates and allocation; at most eight custom slots can be allocated.
Creation or cleanup uncertainty tombstones the slot. Caller-owned spec objects
and returned catalog rows do not mutate the captured scope.

Each custom task still gets separate temporary signer/executor processes and
stores. The custom guide prepares bilateral pairing and the exact composed
request only. Once that request is processed, it returns an explicit awaiting
state until a responder proposal is separately staged, imported, approved,
submitted, delivered and processed. No synthetic response is automatically made
for a composed question. The restricted actor-bound protocol gains no new tool.

The UI freezes the full preview snapshot before confirmation, captures view
scope/generation, and invalidates old confirmations on navigation/edit. A lost
creation response fences that button; catalog inspection is read-only. Payloads
and URLs remain textContent. Final/status/awaiting messages stay visible instead
of being erased by navigation. These are model-tested controls, not a proof of
browser native-dialog behavior or human authentication.

Startup specs are bounded to 8KiB serialized JSON. Custom task public review
responses may be up to 64KiB because a review includes repeated escaped message
text; legacy responses and every incoming command remain bounded at 16KiB.
This is a narrow trusted-process transport accommodation, not an expansion of
agent commands, envelope limits, data permissions or a general streaming channel.


## Explicit owner-authored responses (v19)

`OwnerResponses` adds trusted-local context, preview and preparation methods to
`GenericOwnerWorkflow`. It requires a composed task and its exact responder. The
processed durable projection must contain the original composition-bound request;
received-only ciphertext is insufficient. Context is a detached snapshot of that
exact request and its digest. Catalog tasks and other owners cannot use this path.

Preview validates the closed result schema, requested item count and existing
canonical 8KiB envelope bound, then constructs the exact reverse-route reply. Its
preview digest covers the context, owner, recipient, processed incoming request and
result envelope. Preview is read-only and does not stage an agent proposal or owner
request. Request text and resource references remain untrusted, inert data.

Preparation checks exact preview digest and typed owner phrase, then atomically
looks for the earliest identical canonical envelope for that owner/context in the
existing owner request ledger. It deliberately includes every lifecycle state,
including declined, deferred, expired, withdrawn and imported proposals. An exact
saved retry can return original history after a task becomes terminal, but cannot
allocate a new request or renew permission. New content requires a nonterminal
processed request and the existing draft checks before inserting an unsigned row.
The separate explicit approval/signing, submission, dispatch and processing
boundaries are unchanged. No capability or agent command is added.

The owner UI exposes response composition only for the custom responder after the
request's processed state. Context/preview reads do not grant authority. Captured
preview content and request linkage survive input mutation only as immutable
snapshots. Editing does a full view rebuild so both navigation and generation
fences stay correct. Lost preparation responses disable repeated preparation in
that view and point to inbox inspection; no mutation is automatically retried.
Existing generic message, owner IPC and HTTP limits are not enlarged.


## Received-message owner view (v20)

`GenericOwnerWorkflow.received_messages` validates the exact stored session context
and replays the complete generic task projection before returning any content.
Custom tasks additionally compare the processed request to the immutable composed
spec. The projection validates scope, ordering, request/result linkage and bounds;
if later history is corrupt, earlier content is not partially returned.

Only a processed request/result whose recipient equals the selected enrolled
owner enters the response. The current protocol permits one request and one
linked result, so this is inherently bounded. Queues, raw encrypted inboxes,
receipts and uncertain/blocked delivery states are not content sources. The read
does not reconcile authorizations, add transitions, stage proposals or create
AgentProposalBoundary tables. It returns exact detached envelopes, digests and
the current immutable registry's sender-binding fingerprint, not signatures,
owner authorization/request IDs, keys or outgoing/other-owner messages.

Cancellation preserves already processed history; it cannot undo prior disclosure.
Workspace and service closure/uncertainty fences apply before reads. Reopen only
replays existing stores with retained live fixture keys; no persistent identity
or lost-key recovery is implied. Both generic catalog and custom tasks support
this trusted-owner read; the legacy meeting mode and agent grammar do not change.

GET `/api/messages` uses the existing same-origin bounded handler and exact
selector/context/owner routing. The UI distinguishes received messages from
owner approval requests. It renders only inert text, checks returned scope and
recipient before displaying contents, and fences late responses by view generation
and hash. Refresh/back do not mutate state. A binding fingerprint is described as
fictional local evidence, never human/provider authentication or future authority.


## Second generic capability: bounded text (v21)

`bounded-text-exchange-v1` adds a closed inert request (`prompt`, `max_reply_chars`)
and result (`text`) with fixed `exchange-text` operation. The custom text spec is
an exact seven-field alternative to the original six-field shortlist spec; unknown
or mixed fields are rejected. The original form omits capability and retains its
existing serialized commitment and preview hashes. No automatic migration occurs.

`validate_result_against_request` shares request-relative result bounds between
task projection and response preview, rather than assuming every result contains
resource items. The composition validator now also verifies result scope, exact
reply digest and original bound, so the separate owner signer rejects over-bound
or incorrectly linked composed replies even before session processing. Fixed task
context, owner proof and route still apply; an inert text field cannot choose a
capability, operation, peer or tool.

The restricted local host advertises the proper payload shape for its bound task
without expanding its three-method grammar. The UI preserves old default shortlist
wire shape, captures capability-specific previews, and rebuilds edited forms with
new generation fences. Plain-text reply fields count Unicode code points and do
not normalize/truncate content. Received text remains plaintext and carries the
same exact scope/digest/fictional-binding warning as the existing message view.
No transport limit is increased and no actual provider or browser acceptance is
inferred from local process, handler or DOM-model tests.


### Stored-history consistency hardening before v21 release

Every `GenericPersistentSession._restore` checks its immutable in-memory task and
stored session-context row before replay. Already-open consumers reject a missing
or changed row. Response context/preview/preparation therefore cannot bypass the
check; a normal terminal exact-history retry retains its existing semantics.

The agent inbox now consumes the complete validated projection, including
composition-bound request/result checks, before selecting recipient messages.
It no longer truncates raw transition rows and returns an earlier message while
later linkage or duplicates are corrupt. New proposal aliases also require a
coherent projection; terminal historical aliases remain metadata, not authority.
The owner received-message view uses the same centralized scope check and validates
both composed request and result. Outputs and agent method grammar are unchanged.

These guards address reproducible trusted-local corruption and consistency faults.
They do not authenticate database bytes or defend a compromised host. The existing
constructor may initialize a missing session row on reopen, validating remaining
history against the trusted task before committing. Changed existing context is
rejected. Some exact historical receipt/status retries can return their previously
recorded metadata without new writes, approval, disclosure or sending.

## Temporary relationship task groups (v22)

RelationshipWorkspace adds trusted-local organization of explicit selector/context
pairs, not shared cryptographic identity. Pure create/attach/stop previews commit
only after exact review and typed confirmation. Registry/group revisions bind
preview membership; task labels do not infer a relationship. Each task retains
its own keys, pairings, approvals and delivery evidence.

A stop atomically records a monotonic context fence under OwnerWorkspace's lock.
Owner mutations and old adapter callbacks check that fence; overlapping groups
cannot remove it. History/evidence reads, explicit receipt/reconciliation checks,
authority-reducing controls and close remain available. No signed cancellation,
receipt, global contact block or remote revocation is fabricated. The stop is
serialized and cannot preempt an already-entered action.

Groups and fences last only for this launcher. A private integrity seal detects
accidental in-process corruption, not arbitrary same-process tampering. The
restricted agent grammar and task envelopes are unchanged. See
RELATIONSHIP_WORKSPACE.md for the complete API, allowlist and limits.

## Trusted fixture IPC deadlines (v23)

The existing three-script trusted local launcher now uses nonblocking binary
pipes and one absolute deadline across a request's complete write and response
read/decoding. Partial frames and stderr flooding no longer defeat that
communication deadline. Bounds, process allowlist and public API are unchanged.
Malformed/failed/late replies kill and reap the owned child with bounded cleanup;
no command is retried or declared uncommitted.

This is Linux fixture IPC, not the restricted agent stream transport, an OS
sandbox, process-tree containment or real-host integration. Process creation and
caller serialization are outside the communication deadline. Cleanup has its
own bound, and a full owner action may use multiple pipe exchanges. Relationship
stops remain lock-serialized rather than preemptive. Controlled-child integration
checks show a partial response times out, releases the workspace lock, preserves
uncertainty and allows the group fence to commit afterward.

## Trusted console parity (v24)

The existing owner console now exposes exact custom task and relationship
previews, separately confirmed commits, dynamic explicit selection and processed
message reads. Selected routes are detached immutable selector/context snapshots;
listing, group changes and task creation do not retarget them. JSON commands are
bounded and reject duplicate keys/nonfinite values; received text is only printed.

Uncertain communication clears pending previews and latches read-only inspection
until explicit close/quit rather than silently discarding all tasks. The backend
remains the authority for each route. No CLI command is added to the restricted
agent grammar, and this single-operator terminal is not owner authentication.

Additional cross-layer regressions combine lost receipts, storage reopen,
relationship stops, withdrawn aliases and explicitly approved successors. A real
executor enqueue followed by injected lost IPC response preserves one queued
record, no dispatch/replay, child termination and unaffected second-task progress.
No new routed consent/disclosure gap was confirmed in that focused review; it
is not a security certification or a production acceptance claim.

## Informational fictional continuity (v25)

Explicit opt-in adds a bounded disposable registry and a fourth fixed trusted
fixture script for an independent continuity signer. Enrollment is separately
confirmed; construction and preview create no signing key/process. Each exact
association needs both the existing task owner's signature and the continuity
signer's signature over the same closed body using separate informational domains.
Task roots, transport, grants, bindings and restricted-agent grammar are unchanged.

The workspace pins incarnation, selector/context, actor and existing public roots;
a private preview MAC prevents stateless review rewriting. A two-minute review
window is checked before and after signing. An uncertain slot is occupied before
the first IPC write and cannot trigger automatic signing retry. Lifetime limits
are four identities and twenty associations, including tombstones. New proofs are
fenced by retirement, close, task-group stop and stale review generations.

Historical signature verification alone does not establish current recognition,
current possession, a real human/provider identity or authority. Recognition lasts
at most 24 hours, with earlier local fences. Retirement removes continuity
recognition only; task cancellation and grant revocation remain separate controls.
The opt-in trusted HTTP, console and modeled frontend routes preserve frozen
reviews and single-attempt commits. No agent-facing continuity method, persistent
key custody, rotation, migration, real owner enrollment or recovery is added.
See CONTINUITY_PROOFS.md and CONTINUITY_OWNER_GUIDE.md.


## Two scripted client processes (v26)

A trusted terminal launcher creates two fixed stdlib-only children and binds each
restricted session once to an exact actor/task. The optional console handler
receives a detached selected route and cannot rebind clients. The default console
has no handler. Clients receive inert envelopes, narrow step commands and anonymous
protocol pipes, never owner signing material, executor pipes or workspace objects.

A separate narrow supervisor bounds explicit-step pipe waits and framing, checks
reports against the actual last server response, and closes/reaps failed children
without replay. Cleanup attempts continue after individual errors and retain
uncertainty even if a later wait succeeds. Trusted callbacks, lock acquisition,
OS spawn/scheduling and whole actions are outside that pipe deadline. No background
service consumes client output while the owner is idle. Explicit simulation uses
synthetic owner decisions and checks receipt-only inboxes remain empty.

This is a single-operator offline fixture, not isolated hostile execution,
distributed owner infrastructure or native provider interoperability. Existing
restricted tools, task consent and fixture executable allowlist are unchanged.


## Independent mixed-language peer proof (v27)

The separate peer supervisor now has a closed Python/Node script choice. An
explicit mixed option preflights the trusted installed Node runtime before any
client session starts; the default remains Python-only and does not discover
Node. Both languages use immutable actor/task sessions and the same three tools.
Node independently implements bounded byte framing, fatal UTF-8 decode and
version/ID checks. Empty environments prevent ambient NODE_OPTIONS/NODE_PATH from
adding behavior. The .cjs suffix makes interpretation independent of parent
package type. The fixture signer/executor allowlist remains unchanged.

Both mixed assignments preserve exact Unicode envelopes, owner consent, declined
history, stopped-task fences and processed-only inboxes. The simulation explicitly
compares the complete expected envelope. Full verification includes Node-dependent
Python tests and hashes root JavaScript source alongside Python. This adds no
real owner authentication, provider support, persistent access or OS isolation.

A separate focused review reran 201 existing authorization/transport tests and
found no new confirmed routed consent/disclosure defect. Reviewed source files
were unchanged. See verification/v27-authorization-review.md for precise boundaries
and limits; these are regression results, not security certification.


## SDK-backed decoded-stream MCP adapter (v28)

An optional exact SDK dependency supplies legacy lifecycle and protocol models.
The adapter is single-use and receives already-parsed streams rather than selecting
stdio, HTTP, host identity or relay. Trusted composition fixes task/actor/dispatch.
Only three tools are advertised, and metadata/capabilities remain inert. Two small
public facade methods reuse the existing application authorization/output checks;
the original strict wire profile and backend owner decisions are unchanged.

Typed prevalidation and unknown-tool interception prevent identified SDK warning
paths from echoing rejected content. Wire errors and callback/owner-shaped output
are fixed/redacted. Normal SDK DEBUG metadata and INFO request-ID diagnostics are
not universally redacted; embedding must choose a safe logging policy without
assuming this adapter changes global logging or captures arbitrary callback output.

Bounded decoded objects and retained IDs limit each session, not parser allocation,
global rate, wall time or total memory. Callbacks stay synchronous for storage
thread affinity and cannot be preempted. Cancellation/disconnection never replays
work or proves absence of a committed proposal. Source/client tests cover actual
legacy negotiation, metadata, scoped calls, negative authority cases and resource
cleanup. Raw frontends, real identity/custody and native/relay/wake gates remain open.


## Bounded raw SDK frontend (v29)

A strict JSON record codec applies a 16 KiB byte ceiling and lexical nesting scan
before parsing, followed by duplicate-member, Unicode, numeric and tree checks.
It preserves application integer/float/Boolean types through SDK model construction.
The optional LF bridge accepts caller-owned async byte endpoints, limits records,
and serializes bounded whole-frame sends. It never selects or opens a transport.

No new authority enters the SDK adapter: the same three tools and immutable trusted
task/actor binding remain. Raw rejected requests do not consume the adapter ID ledger
but count toward the raw-record budget. There is no automatic replay. EOF, output
failure or cancellation can follow committed work; even clean EOF can lose queued
replies. Fixed local reports preserve conservative uncertainty. Endpoint lifetime,
logging, authentication, hard deadlines and global admission remain embedding duties.
See MCP_RAW_CODEC.md for the contract and independent review for evidence/limits.
