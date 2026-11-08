# v29: bounded raw JSON and optional LF bridge

Final fresh extraction: 948 Python tests, 273 DOM-model checks, 153 local source
hashes and 13 upstream hashes passed. All 26 preserved v3-v28 archive hashes match.

- Adds a strict 16 KiB raw JSON admission layer before SDK message construction,
  including UTF-8, duplicate members, nonfinite numbers, depth, nodes and IDs.
- Adds an optional LF bridge for caller-owned asynchronous byte endpoints, with
  bounded serialized output, finite record admission and fixed error reports.
- Keeps the three scoped tools, trusted binding and owner authority unchanged.
- Adds 10 implementation and 16 independent review tests, including an actual SDK
  client using independent byte encoding and fragmented in-memory streams.
- Documents clean-EOF response loss, postcommit cancellation/output uncertainty,
  no replay, and remaining authentication, lifecycle, deadline and logging duties.

No concrete host/transport is opened, installed or selected. These tests do not
establish universal conformance, native acceptance, delivery or OS isolation.

# v28: offline SDK-backed legacy MCP adapter

Final fresh extraction: 922 Python tests, 273 DOM-model checks, 149 local source
hashes and 13 upstream hashes passed. Optional MCP SDK 1.29.0 is verified alongside
the existing pinned dependencies.

- Adds a transport-neutral, single-use SDK Server with exactly the three existing
  scoped proposal/status/processed-inbox tools and no owner authority exposure.
- Reuses application validation through two small trusted facade methods; ordinary
  bounded protocol metadata/capabilities cannot alter actor/task binding or grant tools.
- Exercises actual SDK negotiation for four legacy versions through 2025-11-25,
  including fallback without claiming 2026 support or native host acceptance.
- Adds 40 implementation, independent-review and verifier cases covering scope,
  metadata, types, output redaction, duplicates, cancellation/loss and session bounds.
- Fixes identified SDK malformed-input/unknown-tool diagnostic echo paths. Normal
  SDK DEBUG metadata and INFO request-ID logging remain explicit embedding concerns.
- Keeps the SDK optional for base applications but mandatory for complete checkpoint
  verification. No package or host installation was performed during this work.

This adapter consumes already-parsed streams. Raw framing/parser bounds, native
launching, caller authentication, live transport, wake, OS isolation and preemptible
callback deadlines are not established by this checkpoint.

# v27: independent Python/Node scripted clients

Final fresh extraction: 882 Python tests, 273 DOM-model checks, 145 local source
hashes and 13 upstream hashes passed. Linux, Python 3.12.14 and Node 24.22.1 were
used; other platform/runtime acceptance is not implied.

- Adds an explicitly selected fixed Node client in either actor role while
  keeping the two-Python default independent of Node discovery.
- Independently exercises bounded byte framing, fatal UTF-8 decode, version/ID
  negotiation and exact Unicode/newline envelopes through unchanged server tools.
- Preserves separate owner decisions, receipt-only empty inboxes, declined/stopped
  history and uncertain outcomes without replay or client replacement.
- Uses deterministic .cjs interpretation under enclosing JavaScript module projects.
  Runtime choices remain closed, environments empty and inherited descriptors explicit.
- Includes JavaScript in source freezes and Node prerequisites in full verification.
- Adds 49 tests. A separate 201-test review reused existing authorization/transport
  cases, found no new confirmed routed gap and made no production patch.
- Rechecked all 24 preserved v3-v26 archives against their original SHA-256 values.

This is offline language-neutral wire evidence, not real-provider interoperability,
human-consent evidence, persistent identity or OS isolation. Live host, identities,
key custody and transport decisions still require explicit selection and consent.

# v26: runnable offline two-client handoff

Final fresh extraction: 833 Python tests, 273 DOM-model checks, 142 local source
hashes and 13 upstream hashes passed.

- Adds two distinct fixed scripted client processes using only the existing
  restricted proposal/status/processed-inbox tools, with immutable task routes.
- Keeps owner creation, binding, pairing, review, approval, delivery and processing
  in the separate trusted terminal. Python-only default behavior remains intact.
- Adds explicit synthetic simulation and a reproducible transcript showing that
  delivery receipts do not make messages visible before recipient processing.
- Bounds explicit-step pipe waits/framing, correlates diagnostic reports, rejects
  malformed/trailing data and preserves uncertain outcomes without replay.
- Adds 19 tests. Independent cleanup review fixes descriptor allocation leaks and
  error short-circuits so later cleanup stages still run and uncertainty persists.

This is offline scripted-client evidence, not real agents, native providers,
human-consent evidence or an OS sandbox. Pipe deadlines do not preempt trusted
callbacks, lock waits, process spawning or whole owner actions.

# v25: optional fictional continuity possession proofs

Final fresh extraction: 814 Python tests, 273 DOM-model checks across 15 suites,
137 local source hashes and 13 upstream hashes passed.

- Adds explicitly opted-in, disposable continuity enrollment and exact association
  with independently keyed existing task owners, using two informational domains.
- Keeps all task pairing, grants, transport and restricted agent methods unchanged.
  Possession evidence is not real identity, provider authentication or authority.
- Adds trusted HTTP, console and modeled frontend controls with frozen reviews,
  full digest confirmations, bounded historical state and no automatic signing retry.
- Fences new proofs after expiry, retirement, close or relationship stop. Retirement
  does not cancel tasks, revoke task grants or stop messages.
- Adds 58 Python and 99 DOM-model checks, including independent boundary reviews.
  Fixes malformed terminal commit retaining a preview and frontend time-window
  checks that were narrower than the backend's accepted bounded intervals.

# v24: trusted console parity and recovery regressions

Final fresh extraction: 756 Python tests, 174 DOM-model checks, 128 local
source hashes and 13 upstream hashes passed.

- Adds discoverable terminal commands for pure custom task and relationship
  previews, separately typed commits, dynamic explicit task selection and
  processed received-message reads.
- Frozen previews and selected routes cannot silently change. Strict bounded
  JSON rejects duplicate keys/nonfinite values; message content remains inert.
- Communication uncertainty retains read-only inspection until explicit cleanup,
  without retrying owner actions or resetting history.
- Preserves existing catalog simulation and exact backend consent controls.
- Adds four cross-layer recovery cases combining receipts, stops, withdrawals,
  approved successors and lost IPC replies after actual enqueue commit.

# v23: bounded trusted-fixture process communication

Final fresh-extraction verification: 725 Python tests, 174 DOM-model checks,
125 frozen local source hashes and 13 upstream hashes passed.

- Replaces initial-byte-only waiting with a shared absolute deadline covering
  request writes and complete response reads, plus strict bounded UTF-8/JSON.
- Drains stderr in bounded discarded chunks, handles backpressure and partial
  frames, and kills/reaps only the owned fixture child on failure or close.
- Preserves uncertain outcomes, no automatic retries, existing script allowlist,
  public methods and frame limits.
- Adds 20 implementation/independent IPC checks plus two controlled-child
  workspace/startup integration cases. This is verified Linux fixture behavior,
  not real-host, OS isolation, descendant containment or universal preemption.

# v22: explicit relationship task groups and offline verification

- Adds reviewed temporary grouping of exact task contexts, explicit attachment
  and a one-way local stop fence across group members.
- Keeps task-local keys and permissions independent; old adapter callbacks and
  owner mutation paths recheck the fence. History and safe evidence/reduction
  controls remain accessible. No global contact block or remote revocation.
- Adds a local checkpoint verifier with strict source/upstream hashes, exact
  dependency/runtime checks and an explicit full-suite mode. No installation,
  browser/provider acceptance or unauthenticated provenance claims.
- Independent verifier review closed directory-symlink discovery and path-alias
  gaps before release.
- Shortens the current README and preserves its full older narrative in
  CHECKPOINT_HISTORY.md. Final fresh-extraction verification passed 703 Python tests and 174 DOM-model
  checks; 121 frozen source hashes and 13 upstream hashes matched. Evidence is
  in verification-v22.json.

# Development checkpoint v21: November 8, 2026

## Second generic capability: bounded plain-text exchange

- Add one inert prompt/reply capability with closed schemas and an immutable
  reply-character limit, preserving the original shortlist spec and catalog hashes.
- Centralize request-relative result bounds and enforce composition-bound reply
  linkage/limits at proposal, owner review, signer and processing boundaries.
- Add a task capability selector, bounded text response field and received-text
  rendering, retaining exact previews, separate approvals and inert payloads.
- Advertise the matching task-bound restricted-host payload schema without adding
  agent methods, actual host/provider support or broader permissions.
- Preserve all HTTP, startup, envelope and owner IPC bounds; test maximum escaped
  Unicode through real local child processes and in-process HTTP handlers.
- Add a short local QUICKSTART and precise TEXT_EXCHANGE schema guide.
- Fix two locally reproduced consistency gaps: response composition with damaged
  stored context, and agent inbox reads of invalid/partial transition history.
  Centralize context checks, validate all inbox history and gate new aliases.
- Run a deterministic 1,920-operation campaign plus separate history/fault
  scenarios; retain initial failures and final focused/aggregate evidence.
- Final evidence and independent review are in verification-v21.json. No browser,
  external service, account/credential setup, publication or live communication.

# Development checkpoint v20: November 8, 2026

## Read-only received-message owner view

- Add recipient-filtered processed message reads for catalog and custom generic
  tasks, separate from owner authorization cards.
- Show exact task/message/reply digests and fictional sender binding; keep all
  payloads, resource references and provider labels inert and unverified.
- Hide queued, dispatched, received-only, uncertain and blocked messages. Reads
  do not process receipts, reconcile owner requests or create proposal records.
- Preserve processed history after cancellation while fencing closed/uncertain
  services. Validate complete history and custom composition before display.
- Add exact GET routing and a scoped owner UI with read-only refresh/back,
  delayed-response cancellation and fail-closed returned-scope validation.
- Independent review added history corruption, no-write, maximum-frame, agent
  boundary and interrupted UI checks; no remaining substantive defect found.
- No browser, actual provider, account, credential, publication or external send.
  Final aggregate evidence is in verification-v20.json.

# Development checkpoint v19: November 8, 2026

## Explicit responder authoring through owner controls

- Add processed-request-only response context for a custom task's exact responder.
- Add pure response preview and typed preparation of an unsigned owner review.
  Keep all approval, submission, delivery and receipt-processing choices separate.
- Reuse earliest identical durable history across all states and agent imports,
  preserving declined/withdrawn reviews and safe exact retry after terminal state.
- Enforce original item limits, exact reverse route/reply linkage, payload/frame
  bounds, immutable scope and terminal-state refusal for new content.
- Add bounded inert response fields, add/remove controls, exact preview, captured
  confirmation, and interrupted/delayed/repeated-flow model checks.
- Fix post-edit navigation: rebuild the whole view while retaining entered text,
  rather than leave sidebar controls with an invalidated generation.
- Preserve legacy catalog flows, untrusted agent grammar and IPC limits. No live
  provider, browser retry, publication, account, credential or external message.
- See verification-v19.json for aggregate and independent review evidence.

# Development checkpoint v18: November 8, 2026

## Explicit owner task composer

- Add a pure bounded composition preview and exact typed task creation, with
  fictional Alice/Bob directions and the existing public-resource capability.
- Bind the complete composition, including request payload bounds, into the
  task context without changing existing catalog hashes.
- Isolate up to eight custom task services, with duplicate/capacity checks and
  non-reusable closed or uncertain slots.
- Keep binding, pairing, approval, submission, sending and processing separate.
  Wait for a reviewed responder proposal instead of fabricating a response.
- Add a generic UI form, immutable review, edit/Back/navigation protection,
  duplicate-click suppression and uncertain-creation inspection. Keep waiting
  status visible and all payloads inert.
- Preserve legacy meeting UI and existing actor-bound proposal grammar.
- Independent review found a Unicode serialization/startup bound mismatch;
  maximum-input lifecycle checks also exposed a public review-response frame
  bound. Both were addressed before the checkpoint was finalized.
- See verification-v18.json for final full-suite and independent-review evidence.
  No actual-browser acceptance, account/credential setup, external communication,
  live provider, publication or persistent identity is established.

# Development checkpoint v17: November 8, 2026

## Separate generic task owner interface

- Add explicit `--workspace` launcher mode and separate local assets. Legacy
  meeting mode remains the default.
- Reuse HTTP security defenses through scoped dispatch hooks; reject blank query
  fields including hidden empty duplicates.
- Expose explicit per-task creation, temporary identity binding, owner reviews,
  delivery controls, staged proposal import/history and task-only closure.
- Capture task/context/owner/review for actions, invalidate stale confirmations,
  suppress delayed view results and duplicate clicks, and keep payloads inert.
- Add 21 handler/service tests and 29 separate workspace DOM-model checks. Retain
  all 19 legacy DOM-model checks. The final clean archive passed all 537 Python tests.
  The earlier 528-test implementation run is retained separately.
- Independent review adds 9 Python cases and 6 DOM-model checks; reject numeric
  exponent overflow before either HTTP mode dispatches to its service.
- Real-browser rendering, dialog, accessibility and visual acceptance remain
  unverified. No live-provider, persistent-account or public-service integration.

# Development checkpoint v16: November 7, 2026

## Bounded local host stream

Added a reusable LF-framed byte-stream layer over one already-bound restricted
protocol session. Actual anonymous-pipe tests cover fragments, multiple records,
notifications, malformed input, partial EOF, exact limits, output loss after
durable proposal staging and independent task scopes. Short byte writes are
completed without replaying callbacks; write/flush failure remains uncertain.
Owner steps stay outside the stream. No transport launcher or host is configured.

The implementation pass completed 501 Python tests and 19 DOM-model checks.
Independent review added six cases; the combined 21 stream cases passed with no
blocking defect. The checkpoint's clean full result is recorded separately in
verification-v16.json. Limits include no deadlines, blocked-I/O cancellation,
general DoS isolation, actual native-host acceptance or authentication. Existing
workspace, protocol and owner authorization semantics remain unchanged.

---

# Development checkpoint v15: November 7, 2026

## Trusted two-task owner workspace

- Added a closed garden/astronomy startup catalog, reverse-direction second task,
  exact full-task guide matching and `--task-fixture` selection.
- Composed independent signer/executor/storage services behind context-qualified
  trusted workspace routing, occupied-slot tombstones and cleanup uncertainty.
- Added exact service/task/actor-bound restricted sessions without expanding the
  untrusted adapter grammar; retained all separate owner authorization steps.
- Added a local interactive/simulated console and cross-task isolation tests.
- No HTTP/browser changes, live accounts/services, persistent credentials,
  external communications, publication or native host acceptance.

Final implementation verification passed 486 Python tests, including 22
workspace cases (eight independently added review cases), and 19 DOM-model
checks. Both console demonstrations and compile checks passed. A transient
pre-freeze wording-assertion failure is retained separately from the final
passing log. Global routing is serialized; process/store separation is not an
OS sandbox or independent task-latency guarantee. Closed-task callbacks are
fenced, while immutable protocol discovery may remain available.

---

# Development checkpoint v14: November 7, 2026

## Restricted local host protocol profile

Added a trusted task/actor-bound JSON-RPC parser and tools facade over the v13
proposal boundary. Official MCP 2025-06-18 lifecycle, base and tools specifications
informed the local message contract. Exact handshake, closed arguments/schemas,
notification non-execution, bounded unique RPC IDs, serialized processing,
sanitized errors, output validation and no automatic retries preserve the owner
boundary. Protocol IDs are separate from durable proposal idempotency.

Two fictional sessions exercise the existing explicit independent owner workflow.
Additional tests cover reconnect after refusal/withdrawal, hostile protocol input,
concurrent request-ID replay, output leaks and stopped-uncertain delivery without
resend. This is restricted offline protocol proof only, not full MCP conformance,
a native host integration, wake, authentication or OS sandbox. No live host,
account, relay, provider call, installation or publication was added. Frozen v13
and prior artifacts remain unchanged. See HOST_PROTOCOL.md for source references
and exact restrictions. Final implementation verification passed 464 Python
tests (including 27 protocol implementation cases and nine independent review
cases), 19/19 DOM-model checks and Python compilation. Logs are stored in
verification/v14-implementation-*.log. No browser acceptance is claimed.

---

# Development checkpoint v13: November 7, 2026

## Bound agent proposal and processed-inbox interface

Added a closed task-and-actor-bound JSON facade for untrusted proposals, redacted
status and already processed inbound messages. Durable caller IDs and exact
fingerprint aliases reject payload mismatch and preserve original decision history
across retries, new aliases and storage reopen. Agents receive no signing,
pairing, owner resolve/submit, dispatch/process, keys or arbitrary actor/context
surface. Payloads remain inert and schema-bounded.

Trusted-only discovery and import connect proposals to the existing unsigned owner
review. Import never grants missing pairing or follows owner-created successor
reviews automatically. Existing exact owner reviews, including refusal, are reused.
Receipt alone never exposes inbox data; previously processed history remains
visible after cancellation/revocation because prior disclosure cannot be recalled.

Added end-to-end tests with two fictional adapters plus separate owner steps, and
deterministic storage/expiry/capacity tests. A clean archive extraction passed
all 428 Python tests and 19/19 DOM-model checks, including 21 implementation cases
and seven independent race/fault tests. Review found no blocking issue in this
offline boundary. Fixture executor routing is explicitly
trusted-harness-only; this is not OS isolation or a live MCP/provider integration.
No scheduling features, accounts, live credentials, network calls, publication or
external communications were added. Frozen v12 and prior artifacts are unchanged.
See PROVIDER_READINESS.md for the next host/identity/relay gates.

---

# Development checkpoint v12: November 7, 2026

## Generic owner-controlled process workflow

Added explicit generic/meeting fixture selection to existing signer, executor and
console. GenericOwnerWorkflow reuses the shared request/authorization ledger,
withdrawal/replacement and delivery controls, with a task-specific review/guide
adapter. Signer and executor independently enforce exact task context, peers and
payload. Generic mode requires the closed owner-workflow command surface.

Added generic OwnerUIService API support without changing the browser launcher or
HTML. The console guide is explicitly the fixed synthetic non-meeting example;
normal mode requires local choices and --simulate labels synthetic approvals.
No real provider or human identity is claimed.

400 Python tests and 19 DOM-model checks pass. Fifteen new generic process/API/
console cases cover independent validation, bypasses, refusal/deferral, uncertainty,
reopen and withdrawal. Independent review found a malformed binding-frame liveness
bug; explicit dict validation and nonfatal malformed-then-valid regression fix it.
No remaining concrete issue reported. No browser QA attempted.

V3-v11 archives are unchanged. No accounts, live services, persistent real keys,
external communications, publication or deployment. Reopening stores uses the same
live disposable key processes, not identity recovery.

---

# Development checkpoint v11: November 7, 2026

## Restore the broad network boundary

Added immutable provider-neutral identity references, conversations and tasks;
closed explicit v2 envelopes; an allowlisted capability boundary; exact request/
result linkage; and a durable non-meeting task projection. No mandatory meeting
or candidate fields exist in v2. Scheduling remains an explicit v1 adapter.

The generic private-message adapter reuses unchanged pinned A4A event/crypto
primitives. Existing owner-signed decisions, identity bindings, bilateral scoped
pairing, durable encrypted delivery, receipts and reconciliation protect the new
path. A synthetic resource-shortlist request/result completes with two verified
receipts and two inert transitions, without live provider/tool calls.

385 Python tests and 19 DOM-model checks pass, including 24 new generic cases.
Independent review found no blocking authority or binding defect. Strengthened
third-member test starts with a valid three-member-conversation envelope before
changing only the recipient. Fresh imports of affected modules also pass.

This proves an offline non-meeting protocol path, not provider compatibility,
real-person enrollment or actual resource discovery. Generic owner UI is not yet
integrated; existing browser acceptance stays blocked. Compatibility aliases and
legacy cancellation target spelling remain explicit. V3-v10 archives preserved;
all vendored source hashes unchanged. No live services/accounts/publication.

---

# Development checkpoint v10: November 7, 2026

## Exact owner-signed withdrawal of unused authority

Added a domain-separated withdrawal proof, a permanent local execution tombstone,
and a separate explicit fresh unsigned successor. An already-signed expired/stale
request no longer has to trap the guide. The original decision and signature are
retained. Both SignedOwnerGateway.apply and encrypted enqueue check the fence
inside their existing transactions before replay or execution.

Withdrawal refuses all original execution evidence: owner ledger, encrypted
outbox, local approval, receipt or transition, including queued/blocked messages
with zero attempts. It cannot undo dispatch or recall information. Fresh owner
signature and review digest bind the exact original scope. Exact retry after lost
response, storage reopen or proof expiry returns the recorded result.

Integrated separate signer, closed executor commands, explicitly typed UI/console
withdrawal and independent fresh-review action. No real identities, persistent
credentials, relay connections, external communications or publication.

## Verification and product scope

361 Python tests and 19 DOM-model checks, with 22 new core/process/adapter cases
and three UI-model cases. Independent review and final extraction evidence are
recorded in verification-v10.json. Real-browser acceptance remains blocked.

The broader goal is cross-provider, relationship-based assistant communication.
Scheduling remains an example and the current legacy runtime is still coupled to
it. This consent safety slice does not substitute for generic conversation/task
architecture or demonstrate live provider interoperability. V3-v9 are unchanged.

---

# Development checkpoint v9: November 7, 2026

## Separate owner reviews for pairing recovery

Blocked unsigned sends expose only their missing/expired directional pairings.
An explicit action prepares or opens one separate pairing review, deriving the
peer and context from the exact send. Each owner must approve and submit their
own grant. No active grant is extended; no send review is replaced, approved,
enqueued or dispatched as a side effect.

Added durable source-token/direction-to-pairing links, source revision changes,
read-only navigation in both directions, closed process/UI commands and an
explicit console path. Exact retries return the same historical request. Existing
unresolved/refused directional reviews are surfaced, including history behind a
newer submitted grant. Replacement ancestry retains source navigation.

Original unsigned sends still require explicit replacement and fresh approval
after pairing is restored. Authorized/submitted/uncertain sends, superseded
sources, cancellation, expired identities and competing deliveries fail closed.

## Verification and remaining limits

**339 Python tests** and **16 DOM-model checks** pass, including 30 new core,
process and UI-adapter cases and two DOM cases. Independent review reproduced a
history-dedup gap; it was fixed and the deferred/declined regressions verified.
Synthetic evidence shows zero deliveries through both separate pairing grants.

Browser/visual QA remains blocked. No live identities, services, credentials,
external communications, publication or deployment. Temporary single-operator
fixture only. V3-v8 archives unchanged. The broader network remains unfinished.

---

# Development checkpoint v8: November 7, 2026

## Explicit unsigned review replacement

Fixed a reproduced owner-workflow dead end after a review's five-minute expiry.
Owners may explicitly request a fresh unsigned review. The old request is retained
as superseded with append-only lineage. Message, recipient, meeting and pairing
scope stay exact; nonce/time/current contact versions are refreshed. A new owner
signature and separate execution/delivery steps remain required.

The operation is atomic and idempotent for the original review token. Ancestors
cannot be resolved again. Declined, authorized, submitted, committed or uncertain
operations are not replaced. Cancellation, expired identities/pairings, current
scheduler state and delivery reservations continue to block. Storage reopen and
additive schema setup preserve earlier requests.

Added explicit workflow executor, UI adapter, browser-model and console paths.
The browser dialog requires `REVIEW <owner>` and distinguishes preparing a review
from granting approval. Unknown fields/wrong owners/stale tokens are rejected.
The fixture-only request preparation command supports a bounded TTL for process
expiry tests; the browser service does not expose that parameter.

## Verification and scope

**309 Python tests** and **14 DOM-model checks** pass. Thirty new Python cases
cover expiry, contact changes, terminal states, original ledger collisions,
concurrent replacement/decline, exact retries after successor state changes,
rollback, limits, storage reopen, schema compatibility and process/UI boundaries.
Two DOM cases cover typed replacement and ancestor navigation. Independent core
review and adversarial race probes found no blocking issue; generic control-card
wording was corrected. Synthetic log shows replacement creates no delivery.

Browser/visual QA remains blocked, unchanged from v7. This checkpoint does not
restore expired pairing or identity; the explicit pairing-restoration UX is a
separate open gap. No live account, external service/message, real credential,
relay, calendar, public site, repository push or deployment was used. V3-v7
archives are unchanged. The broader product remains unfinished.

---

# Development checkpoint v7: November 7, 2026

## Local browser interface, with a verification gap

- Added a local-only HTML/CSS/JavaScript owner workspace with desktop/mobile
  style rules over the v6
  workflow. Binding and request approvals require explicit typed choices. Owner
  selection is fictional role selection, not real-user authentication.
- Added read-only state/review/delivery GET routes and closed action POST routes.
  Existing separate owner signer/executor processes retain their boundaries.
  Preparing a request, approving, submitting, attempting delivery, checking an
  existing receipt and processing it remain distinct actions.
- Added exact Host/Origin checks, strict bounded JSON/headers, static allowlisting,
  local-only content policy, no-store responses and a bounded handler pool.
  No remote resources, cookies, passwords or session credentials are created.
- Added deferred-review resume, stale response/owner navigation protection,
  double-action suppression and explicit uncertainty for lost/truncated responses.
- Added robust all-resource cleanup, fallback child termination and explicit
  cleanup-incomplete status. Closing only a tab keeps the launcher alive;
  explicit discard or launcher shutdown removes temporary records and keys.

## Verification

**279 Python tests passed**, including 21 new adapter/real-loopback HTTP/security
cases. A real HTTP end-to-end fixture completes 12 receipts/12 transitions and
cleanup. **12 DOM-model checks passed**, including navigation, confirmation back,
defer/resume, stale responses, duplicate clicks and mutation uncertainty. Python
compile and JavaScript syntax checks passed. Review-found cleanup and response-
parsing gaps were fixed with regression tests.

**Real-browser and visual verification did not pass:** installed Chromium could
not start because its required local IPC socket was denied by this environment.
No browser interaction, pixel layout, native dialog, mobile viewport or actual
accessibility review occurred. The optional browser_ui_check.py is provided for
an authorized capable environment; it has not passed here. See UI_VERIFICATION.md
for the exact passed/blocked split. Do not describe v7 as browser-tested or ready
for production. The next meaningful task is verifying this existing UI.

The trusted-local-host/fictional-data boundary remains unchanged. No live account,
external service/message, relay, calendar, persistent credential/access, public
site, repository push or deployment was created. V3-v6 archives are untouched.
Real identity and persistent key custody still need a separately authorized design.

---

# Development checkpoint v6: November 7, 2026

## Implemented after v5

- Added a public-only durable owner-request inbox and readable exact review cards.
  Approve, decline and defer have explicit, distinct meanings. A monotonic request
  revision and current-state fingerprint prevent resolving stale reviews.
- Kept owner signing in separate existing fixture processes. Persisted signed
  authorization before execution; same-nonce ledger reconciliation repairs the
  crash gap after execution commits and before request status updates.
- Added dedicated workflow executor mode that refuses raw enqueue/control/send
  bypasses. Owner-scoped request access, closed commands and bounded compact lists
  preserve the existing fixture interface limits.
- Added an interactive guided console with explicit submit, send, receipt-check
  and processing steps. Back/list/defer grant nothing; deferral requires explicit
  resume, and declined requests are not silently recreated.
- Displayed uncertain dispatch outcomes distinctly from received/processed data.
  Missing/unavailable acknowledgement checks do not create retries. Cancellation
  leaves existing uncertain receipt checks reachable while the console remains
  open, and disables attempts when current consent no longer permits them.
- Fixed review-found guided recovery, deferral and cancellation-receipt visibility
  gaps, and kept an invalid early processing choice from terminating the console.
- Factored unsigned delivery-draft validation from signature verification. Draft
  validation creates no authority and cannot enter the encrypted outbox unsigned.

## Verification and limits

**258 tests passed**: previous 213 plus 29 core workflow and 16 process/console
cases. Tests cover concurrent resolution, stale snapshots, exact signature/body
matching, terminal decline, defer/review revisions, crash windows, rollback,
wrong-owner access, legacy bypass, IPC bounds, guided manual-input interruptions,
cancellation and uncertainty. Full and lost-ACK synthetic runs reach 12 receipts
and 12 transitions. Decline sends nothing; a still-unconfirmed attempt stops
without automatic retry. Compile checks and fresh-archive extraction are recorded
in verification-v6.json. Separate code review found no remaining blocker within
this offline trusted-console fixture, not an independent security audit.

This is a disposable local console, not real-user authentication or a persistent
multi-user app. Console exit discards temporary state and generated fixture keys;
there is no later console resume or recovered identity. Underlying journal reopen
is tested with unchanged live fixture identities. No real account, external
message, relay, calendar, persistent credential/access, push or deployment was
created. V3/v4/v5 archives remain untouched. Source rollback must not bypass newer
cancellation, consent, identity or receipt state.

Real authentication, protected persistent key custody/rotation, multi-device
operation, graphical owner UI and live transport still remain future work. Real
connections, persistent access and publication require separate authorization.

---

# Development checkpoint v5: November 7, 2026

## Implemented after v4

- Combined signed owner decisions and the pinned A4A cryptographic modules in a
  durable offline outbox/receiver flow. Four disposable owner signer subprocesses
  are separate from the executor that holds fictional transport keys.
- Owner signatures plus transport-key proof of possession bind exact fictional
  recipients, meeting, allowed inbound peers and expiry. Public roots and complete
  bindings are pinned in SQLite. Exact sends bind both transport identities; legacy
  unbound send decisions cannot enter the encrypted outbox.
- Persisted immutable encrypted packets and consumed approvals together. Receiver
  receipts, sender receipt records and scheduling transitions are separate durable
  steps, never an asserted atomic transaction across actors.
- Reconciliation queries signed receipts before retrying uncertain deliveries;
  an unavailable query does not resend. Exact ciphertext/nonce retries deduplicate.
- Added explicit blocked, received-but-blocked and stopped-uncertain states.
  Cancellation and revocation stop later attempts but do not erase disclosure or
  recall an attempt whose dispatch already committed. Late signed receipts remain
  recoverable; uncertain operations keep their semantic-step reservation.
- Rechecked consent and current scheduling state inside dispatch transactions.
  Added fault injection around receipt/transition persistence and concurrent races.
- Added public-only receipt reading. A two-process test destroys all generated
  private keys when preparation exits, then recovers an existing signed receipt
  using public bindings and stored records only. It cannot deliver new messages or
  restore identity, and creates no persistent credential or access.
- Added four integrated process demo scenarios and bounded malformed-ID handling.
  Preserved prior fixtures, upstream source checks, licenses and dependency pins.

## Verification

Python 3.12.14, exact dependencies in `fixture-environment.json`: **213 tests
passed**, up from v4's 151. Added 11 identity-binding tests, 37 encrypted-delivery
cases and 14 integrated process/demo cases. Full-suite and demo logs accompany
this checkpoint. Compile checks and a fresh-extraction test are recorded in the
release verification file. A separate code review exercised faults and IPC
handling; this is not an independent cryptographic or production security audit.

## Boundaries and preserved work

One trusted local console controls all fictional owner roles. The binding proves
fixture-key possession and signed approval, not real-human identity. Separate
receiver databases remain on the same host. Python audit hooks prevent incidental
network/process calls in reviewed worker code, not malicious same-user host access.
Stored fictional bodies and metadata are plaintext. Normal storage reopen retains
live actor keys; the key-free proof recovers existing receipt evidence only.

No live accounts, relay, calendar, external agent, publication or deployment was
used. Generated private keys are not saved. The v3 and v4 ZIPs remain unchanged.
Use isolated fresh directories for older source; do not run old code over newer
state to bypass cancellation, bindings, consumed approvals or receipt evidence.

Real-human enrollment, protected key custody/rotation, remote cancellation notice
and live transport reconciliation remain future work under separate authorization.

---

# Development checkpoint v4: November 7, 2026

## Implemented after v3

- Five unchanged, pinned A4A event/crypto modules now run an offline signed and
  encrypted scheduling round trip. Added strict fixture sender/recipient/context
  binding, malformed-event refusal, and tampering checks.
- Copied source is verified against upstream Git blob IDs and SHA-256 checksums.
  The original MIT notice and the separate NIP-44 vector license are retained.
- Official NIP-44 known-answer vectors pass, alongside nine unchanged upstream
  event checks. This validates those exercised components, not the full SDK or a
  connected service.
- Four disposable Ed25519 owner signer processes and one public-key-only execution
  process demonstrate separate owner confirmation and execution interfaces.
- Signed decisions cover pairing, exact messages, revocation and cancellation.
  Context, target, expiry, nonce and contact versions are checked. Decisions and
  local effects commit together; restart/retry cannot duplicate the effect.
- Contact versions prevent a previously signed but unseen message or pairing
  decision from becoming usable after revocation and re-pairing.
- A trusted bootstrap pins owner verification roots in SQLite and refuses silent
  replacement. No private key is stored. No real owner/account enrollment occurs.
- Process fixture protocols have bounded JSON frames and reject unsigned approval,
  signing, key-export and re-bootstrap commands on the execution interface.

## Verification

Python 3.12.14 with exact versions in fixture-environment.json: **151 unittest
cases passed**, including the original 90-case suite, 24 signed-decision tests,
14 cryptographic fixture tests, 11 source/vector test groups and 12 subprocess/demo
tests. Unchanged upstream checks run within adapter tests. compileall passed.
Full signed-demo completion and cancellation, and the guarded crypto round trip,
are captured in the output text files. Generated fixture keys were discarded.

Only the missing coincurve/bech32 dependencies were installed into an isolated
project-external test directory. No global package environment was changed. The
artifact contains source, dependency pins and logs, not installed package binaries.

## What this does not establish

This is a self-reviewed offline development checkpoint. The signed owner demo and
A4A encrypted round trip are separate proofs, not a combined network transport.
One trusted local console plays all fictional human roles. The signer process
proves possession of a fixture key, not the identity of a real person. Python audit
hooks block network/process calls in the reviewed subprocesses, but are not an OS
security sandbox against arbitrary hostile code or same-user process inspection.

No real credentials, calendars, relay, external agents, public repository, deployment
or remote messages were used. No persistent access was created. Published upstream
known-answer test scalars are test data, never real keys. SQLite remains fictional
plaintext storage. Public-key ownership, identity recovery and production custody
still need a separately authorized design and implementation.

## Next bounded slice

Bind stable, independently verified transport identities to owner-approved human
recipients, then combine signed decisions and encrypted delivery in an offline
durable outbox/receiver fixture. Prove retries, cancellation and delivery/processing
reconciliation before proposing any real accounts or relay connections.

## Recovery and preserved work

The v3 ZIP remains untouched. Restore source only into a separate empty directory.
Do not run older code against v4 state: v3 does not enforce signed-decision roots,
contact-version invalidation or the consumed-decision ledger. Never use source
rollback to bypass cancellation or revocation records.

---

# Development checkpoint: November 7, 2026

This continues the existing local agent-network prototype. It is not a new
product/repository, a deployed service, or a live A4A client.

## Implemented in v3

- Persisted terminal cancellation by any registered local participant.
- Cancellation and invalidation of unused approvals share one SQLite transaction.
- New pairing, approval and delivery are denied after cancellation, including
  restart. Committed receipt retries remain read-only and preserve history.
- Send/cancel races resolve according to SQLite transaction order. Information
  sent before cancellation cannot be recalled.
- Readable, deterministic consent review shows participants, sender, recipient,
  exact UTC times and the scheduling data being disclosed before the raw message.
- CLI cancellation requires an existing session and preserves simulated/manual
  provenance. Manual cancellation requires an exact confirmation phrase.

## Verification

Python 3.12.14: 90 unittest cases passed, up from the freshly verified 70-case
baseline. The 20 new cases cover cancellation/recovery, concurrency, transactional
rollback, identity fixtures, context boundaries, review and CLI behavior.
`python -m compileall -q .` also passed. CLI successful, paused/resumed and cancelled
runs are recorded in the accompanying text logs. No external service was contacted
by these runs and all people/calendar windows were fictional.

This was an implementation self-review, not an independent security audit. No
browser UI, provider compatibility, cryptography, live relays or real calendar
integration was exercised. The existing A4A source attribution and offline adapter
remain unchanged.

## Continue from here

1. Exercise the pinned A4A SDK inside an isolated offline fixture, preserving the
   existing consent/session layer and upstream licensing evidence.
2. Design authenticated owner approval independently from the agent process.
3. Add durable external transport reconciliation and separately approved remote
   cancellation notifications before claiming a connected multi-agent network.

Real identity/relay setup, credentials, calendar access and external publication
are not part of this checkpoint. Product naming and project-wide licensing remain
undecided.

## Recovery

The earlier agent-network-prototype-v2.zip remains untouched beside this project.
Extract it into a separate empty directory to inspect or restore the previous
source checkpoint. Do not overwrite retained SQLite state without a backup. New
cancellation records must not be bypassed by running older code against a v3 state
file: v2 does not enforce them. Recovery is for source comparison and isolated
fictional fixtures, not for resuming cancelled state.
