# Human-approved agent network: local foundations

The product goal is a relationship-based communication network for different
people's assistants across providers. Connections should follow human pairing,
scoped permissions and explicit authority, not automatically expose private data
because two people are friends. Meeting coordination is one example, not the
intended product boundary.

The runtime is an offline fictional-user prototype. It now supports an explicit
generic conversation/task protocol as well as the original scheduling adapter.
A second, non-meeting resource-shortlist workflow uses the same signed-owner,
encryption and durable receipt machinery. Generic tasks use the separated owner signer/executor console and API. The latest
workspace manages two catalog tasks plus up to eight owner-composed fictional
tasks, each with independent scope and bound proposal/inbox protocol sessions.
The legacy browser mode remains meeting-specific; the explicit `--workspace` mode
adds a separate generic owner interface. This is not yet a complete interoperable
assistant network.

Python 3.11+; the original `demo.py` uses only the standard library. Crypto/process
fixtures and full tests require the pinned dependencies below. No API keys,
accounts, live relay or calendar connection are required. Product naming and
open-versus-closed distribution remain undecided.

## Bounded plain-text question and reply (v21)

The owner task composer now offers two inert capabilities:

- **Public-resource shortlist:** the existing fictional question and bounded
  list of resource references.
- **Bounded plain-text exchange:** a fictional prompt and one nonempty text reply
  within an owner-selected limit of 1–512 Unicode code points.

This is a bounded question/reply task, not an open chat session or permission to
execute instructions in a message. Choose the capability before previewing the
task. The full spec, capability and reply limit become part of the immutable task
context. Changing the capability or content requires a fresh preview/confirmation.

The response form and received-message view adapt to the chosen capability.
Plain text remains inert and is not normalized or truncated. The same explicit
binding, pairing, review, signing, submission, delivery and receipt-processing
steps apply. Reading a prompt cannot authorize a response or any tool action.
Identical declined/withdrawn review history is preserved, and new content cannot
revive a cancelled or completed task.

The new allowlisted `bounded-text-exchange-v1` request has exactly `prompt` and
`max_reply_chars`; its result has exactly `text`, and its fixed operation is
`exchange-text`. Request-relative validation is shared across processing and
response authoring. The signer also checks composition-bound result linkage and
limits before signing. This does not add any agent method or expand transport
bounds. The old six-field shortlist spec and existing catalog hashes are unchanged.

A deterministic fault campaign also hardened stored-history checks before this
checkpoint was released: response composition and agent inbox reads now reject
inconsistent live task metadata/history rather than exposing partial content.
New proposal aliases require a coherent projection. These are local corruption
defenses, not cryptographic storage authentication or a demonstrated remote exploit.

Start with [QUICKSTART.md](QUICKSTART.md). See [TEXT_EXCHANGE.md](TEXT_EXCHANGE.md)
for the precise schema/limits and `verification-v21.json` for final test evidence.
Final fresh-archive verification passed 640 Python tests and 137 DOM-model checks
on 112 source-hashed files. DOM-model checks are not browser acceptance.
All execution remains offline and fictional. Browser, actual provider, real
identity, persistent inbox and production acceptance are still unverified.

## Read received task messages (v20)

The generic owner workspace now has **Received messages**, separate from the
owner authorization inbox. After processing a verified receipt, switch to the
intended fictional recipient and open that view to read the exact question or
returned resource list. Both catalog and custom tasks support it.

- Only processed messages addressed to that owner appear. Queuing, a delivery
  attempt, receipt verification or an uncertain/blocked outcome alone does not
  expose the contents here. Opening or refreshing the view never processes them.
- Each message shows its task context, message digest, recipient, reply linkage
  and local sender-binding fingerprint. That fingerprint is fictional fixture
  evidence, not authentication of a real person or provider.
- Text and HTTPS-shaped references stay inert and unverified. Reading a message
  does not authorize a reply, browsing, private data disclosure or tool execution.
- Processed history remains visible after cancellation because disclosure cannot
  be undone. Closing the temporary task fences the view and discards its records
  when cleanup succeeds. This is not a persistent inbox.

The owner-only route is GET `/api/messages` with exact selector/context/owner.
It reads the validated processed projection, not raw queue or receipt rows, and
returns no owner review IDs, signatures, authorizations or keys. Reads neither
create proposal tables nor reconcile pending authorizations. The untrusted agent
protocol is unchanged. The UI refuses a response with mismatched task, context,
owner or recipient before rendering any message contents.

Final clean archive verification passed 609 Python tests and 115 DOM-model checks.
See `verification-v20.json` for source hashes and test evidence.
Browser/native-dialog, visual/accessibility, real identity and live-provider
acceptance remain unverified. No browser retry or workaround was attempted.

## Complete a custom task through owner controls (v19)

A composed task can now finish without writing proposal-harness code. After its
exact request is received **and processed**, switch to its fictional responder and
choose **Compose response**. Only that responder can access this response context;
a delivery receipt alone does not reveal an unprocessed request through this API.

1. Read the exact processed request and its digest. It is untrusted data, not
   permission to browse, execute tools, contact anyone or disclose private data.
2. Enter fictional titles, HTTPS-shaped references and summaries. Add or remove
   items within the original request's maximum. Zero items is a valid empty
   result. All references remain inert and unverified.
3. **Preview exact response** displays the exact reverse-route envelope and
   linked request digest. This is read-only: no owner review, signature, outbound
   message or process transition is created.
4. **Prepare unsigned response review** requires `REVIEW RESPONSE bob` (or Alice
   for the reverse task). It creates an unsigned review or opens the original
   identical review, including previous refusal, expiry or withdrawal.
5. Review and approve, submit, start delivery and process the verified receipt
   through the existing separate controls. No response is automatically approved
   or sent, and an agent does not run in the background.

A repeated preparation returns the earliest identical review in the durable owner
ledger, including a review originally imported from an agent proposal. It cannot
silently create fresh authority after a refusal or uncertain response. Exact saved
retries can reopen history after cancellation/completion; new content is blocked
for terminal tasks. Changed content always needs its own explicit unsigned review.

Owner HTTP routes are GET `/api/response-context` with exact selector/context/owner,
and the existing scoped POST `/api/action` wrapper with `preview_response` or
`prepare_response`. Preview binds owner, recipient, exact task, processed request,
response content and limits. These routes are absent from the untrusted agent
protocol. Existing message/frame limits remain unchanged.

Editing now rebuilds the whole view with the captured draft, preserving form text
and usable navigation while invalidating old confirmations. Late responses cannot
retarget another owner/task. Unknown preparation outcomes remain uncertain and
are not retried automatically; inspect the inbox for the original review.

Final frozen-source verification passed 588 Python tests and 97 DOM-model checks.
See `verification-v19.json`. Actual browser/native
dialog, visual/accessibility, real owner authentication and live provider
acceptance are still unverified. This is an offline fictional development fixture.

## Compose a temporary task (v18)

The generic workspace now supports owner-created fictional task questions, not
only the garden and astronomy fixtures. Run `python local_owner_app.py --workspace`
and choose **Compose temporary task**. This remains an offline development fixture;
do not enter real personal or private data.

1. Enter a short lowercase task identifier, choose Alice→Bob or Bob→Alice, and
   enter a fictional public-resource question with a maximum of one to five items.
   Only the existing `public-resource-shortlist-v1` capability is supported.
2. **Preview exact task** validates and displays the full immutable composition,
   task context and review token. Previewing starts no process, allocates no slot,
   creates no keys and grants no authority.
3. **Create this reviewed task** requires `CREATE TASK`. It starts only that
   task's isolated temporary service. The reviewed query and item bound are part
   of its context, so later edits cannot silently alter the task.
4. Explicitly approve each fictional binding. Pairing reviews, exact request
   approval, submission, delivery and receipt processing remain separate steps.
5. After the request is processed, the guide waits for an explicitly staged and
   owner-reviewed responder proposal. It does not invent an answer, browse URLs,
   connect a provider or execute a tool. The current response path uses the
   trusted local harness and existing staged-proposal import interface.

At most eight custom slots can be allocated in one launcher run, alongside the
two catalog tasks. Duplicate task IDs/selectors, closed slots and uncertain
startup slots cannot be reused. Creation failures remain explicitly uncertain;
inspect the task catalog rather than repeating an action after a lost response.
Editing the form creates a fresh review and never reuses the earlier confirmation.
All payloads, links and identifiers remain inert text.

The JSON composition API is owner-only, not exposed to the restricted agent
protocol. POST `/api/task-preview` accepts exactly `{"spec": {...}}`. POST
`/api/action` creates only with exact fields `action: "compose_task"`, `spec`,
`review_digest` and `confirmation: "CREATE TASK"`. The spec contains only
`selector`, `task_id`, `conversation_id`, `requester`, `query` and `max_items`.
The existing `{selector, context, request}` wrapper is unchanged for subsequent
owner actions. Legacy meeting mode and catalog scope hashes are preserved.

Final source verification passed 566 Python tests and 72 DOM-model checks
(19 legacy, 29 workspace, six prior review, 15 composer, three composer review).
See `verification-v18.json` for evidence. Browser rendering, native
dialogs, accessibility, provider interoperability and real owner authentication
remain unverified. No browser retry or denial workaround was attempted.

## Generic local owner interface (v17)

Final clean verification: 537 Python tests, 29 workspace DOM-model checks, six
supplemental model checks and 19 legacy model checks passed. Actual browser and
visual acceptance remain unverified; see `verification-v17.json`.

Run `python local_owner_app.py --workspace` and open the printed loopback URL in
an authorized environment with a working browser. The default command without
`--workspace` still opens the legacy meeting fixture. No real-browser acceptance
has been completed here: this checkpoint has HTTP/handler and DOM-model evidence,
not verified rendering, native dialogs, accessibility, screenshots or mobile layout.

The generic interface starts with a task catalog. Opening garden or astronomy is
navigation only. **Create selected temporary task** explicitly starts only that
service; neither task is created automatically. One trusted fixture operator can
view either fictional owner, which is not authentication. The same owner label
across tasks does not imply shared keys, accounts or grants.

Within a created task:

1. Review and type the exact binding phrase separately for each owner.
2. Use **Prepare next review** for the next fictional guide decision. It prepares
   a review only. Approval, submission, delivery attempt and processing remain
   separate choices. Exact task/context, owner, recipient and review are displayed.
3. Use **Staged proposals** to discover proposals already staged by the trusted
   local harness. Import opens original history or creates an unsigned review.
   The interface does not start a real agent or generate proposals automatically.
4. Review cancellation, revocation, replacement, pairing recovery or unused
   authorization withdrawal through the existing exact owner controls.
5. **Close only this task** requires `DISCARD FIXTURE`; it does not stop the other
   task or whole launcher. Closed and uncertain slots cannot be reused this run.

Every task read/action carries a captured selector and exact expected context.
Navigation invalidates pending confirmations; stale responses cannot retarget a
new view. No mutation is retried automatically. An unknown delivery outcome is
not a failure or proof of nondelivery. Cleanup faults block the affected task;
stop the launcher and inspect its temporary state if cleanup remains uncertain.
Payloads and resource URLs are inert text, not links or permission to navigate.
Stopping the launcher discards its temporary keys/data when cleanup succeeds.
Never expose this local server externally or enter real personal/private data.

Verification commands: `python -m unittest discover -s tests -v`,
`node tests/owner_ui_dom_check.js`, `node tests/workspace_ui_dom_check.js`,
`node --check workspace_ui/app.js`. See [UI_VERIFICATION.md](UI_VERIFICATION.md).

## Bounded local stream proof (v16)

`restricted_host_stream.serve(reader, writer, session)` adds bounded LF framing
around an already trusted, task/actor-bound protocol session. Tests exercise real
anonymous pipes, fragmented requests and a lost response after proposal staging.
Owner actions stay outside the stream and are explicit in the fictional harness.
There is no production launcher, selected native host, automatic wake or full
MCP conformance claim. See [HOST_PROTOCOL.md](HOST_PROTOCOL.md) for exact limits,
EOF/failure behavior and the official framing source.

## Offline two-task workspace (v15)

Run `python workspace_console.py` for the trusted local console, or
`python workspace_console.py --simulate` for explicitly simulated, interleaved
owner approvals in both garden and astronomy tasks. No network service starts.
Each task uses independent disposable keys, processes and temporary databases.
Quitting discards them; this is not a persistent inbox or real-person identity.

Interactive commands below use Alice as an example; follow the owner named in
the selected review.

- `list` shows the closed catalog and exact context digests.
- `create garden` / `create astronomy` starts only that fictional fixture.
- `select garden` changes navigation only; every following action captures and
  displays that task's exact context.
- `state alice` shows binding reviews or that task's owner inbox.
- `action {"action":"bind","owner":"alice","binding_digest":"<displayed digest>","confirmation":"BIND alice"}` approves only the displayed binding.
  Repeat separately for Bob, then use `next` to prepare the next unsigned review.
- `review alice <request-id>` refreshes an exact review. To approve, use
  `action {"action":"approve","owner":"alice","request_id":"<id>","review_digest":"<digest>","confirmation":"APPROVE alice"}`.
- `action {"action":"submit","owner":"alice","request_id":"<id>"}` separately submits that authorization.
- `delivery alice <request-id>` inspects status. Sending requires
  `action {"action":"attempt","owner":"alice","request_id":"<id>","confirmation":"SEND alice"}`;
  processing a verified receipt requires a separate `process` action with owner
  and request_id. A receipt check uses `check`; it does not resend.
- `action` also accepts the existing exact closed owner actions for decline,
  defer, cancel, revoke, review replacement and unused-authorization withdrawal.
  No arbitrary executor command or task JSON is accepted.
- `proposals alice` lists staged agent proposals for that exact task/actor.
  `import alice <proposal-id>` opens the exact owner review. Any new review is
  unsigned; existing review history is preserved. It cannot pair, approve,
  submit or deliver. Required pairings must already be approved.
- `close` asks to discard only the selected task. A closed/failed slot cannot be
  recreated before a new workspace. `quit` closes all created fixtures.

The existing single-task console also accepts
`python owner_console.py --workflow generic --task-fixture astronomy --simulate`.
`--scenario` retains its existing fault-simulation meaning. HTTP/browser UI is
unchanged and does not expose this workspace.

## Legacy scheduling fixture

```sh
python demo.py                         # manually approve every simulated human step
python demo.py --simulate              # explicitly labeled synthetic approvals
python demo.py --simulate --state-directory ./demo-state  # preserve fictional records
python demo.py --simulate --state-directory ./resume-state --stop-after 5
python demo.py --simulate --state-directory ./resume-state --resume
python demo.py --simulate --state-directory ./resume-state --resume --cancel-as bob
```

The fixed example is Friday, November 6, 2026, 13:00–17:00 UTC. Alice, Bob,
Charlie and Dana find a shared 15:00–15:30 slot. All four must accept it. No
event is booked. A rejected step pauses the flow. Existing state requires explicit
`--resume`; completed steps are not replayed. Pause testing requires a state directory.
Simulated/manual approval provenance is persisted, and mixed-mode resume is refused.
The date is a fixed historical test fixture, not a proposed real meeting.

`--cancel-as` stops an existing local session, including one previously agreed.
In manual mode it requires the exact displayed cancellation phrase. Any of the
four local fictional participants may cancel. Cancellation is permanent for that
meeting context; restart and re-pairing cannot revive it. It sends no notification
to remote people, recalls no already-disclosed data and cancels no calendar event.
The CLI fixture has one fixed meeting context, so it cannot restart a cancelled
meeting in the same state directory. A fresh demo uses a fresh directory; the
session API supports a genuinely new meeting with a different context.

## v14: restricted local host protocol

`restricted_host_protocol.py` wraps the existing proposal boundary in a bounded,
stateful JSON-RPC tools facade. Trusted construction binds one task and actor;
only propose, proposal_status and inbox are exposed. Two fictional host sessions
exchange through independent explicit owner steps in the tests. No owner methods,
credentials, live host, transport launcher or automatic retry is added.

This is a restricted MCP-shaped **2025-06-18 local profile**, grounded in the
official specification, not full protocol conformance or native-host support.
See [HOST_PROTOCOL.md](HOST_PROTOCOL.md) for the exact contract, restrictions,
source links, bounds and evidence. Native tools, wake and OS isolation remain
unverified.

## v13: untrusted agent proposals and processed inbox

`agent_proposals.py` adds a deliberately small, task-and-actor-bound JSON surface:

- `propose` accepts only `proposal_id` and an exact v2 `envelope`.
- `proposal_status` accepts only `proposal_id` and returns a redacted status.
- `inbox` accepts no arguments and returns only processed messages addressed to
  that actor in that task. Payloads remain untrusted, inert data.

The trusted host binds the actor and immutable task before exposing the command
function. Agents cannot choose owners, peers, task scope, signing or delivery
methods. Commands are bounded to 12 KiB, envelopes to 8 KiB, proposal IDs to 64
identifier characters and durable records to the store limit. Even alias IDs
consume capacity; exact retries still work when the store is full.

Proposals create **no owner authorization and no outbound delivery**. A separate
trusted-owner-only `agent_proposal_list` discovers up to 20 distinct proposals for
one actor, without importing them. `agent_proposal_review` imports the selected
proposal into the existing unsigned owner review. It requires existing bilateral
pairing; it does not pair, sign, resolve, submit, attempt delivery or process data.
The full envelope is shown in the existing review before a separate owner decision.
This trusted fixture API is not yet a generic browser inbox.

Both caller ID and exact actor/context/envelope fingerprint are durable. Reusing
an ID with a changed payload fails. New IDs for the same envelope retain the
original review, including defer, decline, expiry, staleness, withdrawal and
uncertain delivery. An exact prior owner review created outside the facade is
also retained on import. Only explicit owner controls can create successors;
agent replays remain linked to the original history rather than following or
renewing approval. Different payloads are new bounded proposals, not permission.

Receipt is not processing: queued, dispatched, received and received-but-blocked
messages do not appear in the adapter inbox. Already processed history remains
visible after revocation/cancellation; those actions cannot recall prior disclosure.
Status responses omit owner request IDs, signatures, review tokens and bindings.
They do not retry, reconcile or execute anything.

`tests/test_agent_proposals.py` demonstrates two fictional adapters, separate
owner signer children, trusted owner steps and encrypted delivery through the
existing executor. `tests/test_agent_proposal_storage.py` exercises deterministic
expiry, capacity, isolation and retained history. Run both with:

```sh
python -m unittest discover -s tests -p 'test_agent_proposal*.py' -v
```

**Checkpoint verification:** a clean archive extraction passed all 428 Python
tests and 19/19 DOM-model checks, including 21 implementation cases and seven
independent race/fault cases for this boundary. See `fresh-extraction-tests-v13.txt`,
`fresh-dom-tests-v13.txt` and `REVIEW_V13.md`. The earlier 421-test implementation
run is retained in `test-results-v13-implementation.txt`. These are offline
regressions, not a security audit or real-provider/browser acceptance test.

**Boundary limits:** the executor's outer `fixture_agent_call(actor, command)` is
trusted test-harness routing, not an agent-accessible endpoint. Only the nested
command is untrusted adapter input. The class and pre-bound callable are not a
Python or OS sandbox: arbitrary code sharing interpreter/filesystem privileges
could bypass them. Do not give adapters the trusted executor pipe, object graph
or files. No real provider MCP server, authenticated provider host, live relay,
actual model execution or unattended agent wake is implemented. See
[PROVIDER_READINESS.md](PROVIDER_READINESS.md) for future acceptance gates.

## v12: generic tasks through separated owner processes

```sh
python owner_console.py --workflow generic                 # explicit local choices
python owner_console.py --workflow generic --simulate      # labeled fixture choices
python owner_console.py --workflow generic --simulate --scenario lost-receipt
```

The non-meeting task now uses the same separated owner-signing and public-only
execution architecture as the original example. Two disposable signer children
hold their own owner keys; the executor receives public owner roots. Both signer
and executor independently validate the immutable task context, task peers,
capability payload and exact original message. A fixed workflow selector chooses
meeting or generic; there is no permissive fallback or provider discovery.

Generic review shows the exact recipient, task, capability, request/result type,
inert payload, reply linkage and digest. Binding, pairing, approval, submission,
delivery attempt, receipt checking and processing remain distinct choices. The
shared deferral, refusal, withdrawal, replacement and delivery-uncertainty rules
still apply. Generic mode refuses all legacy raw control/enqueue/delivery bypasses.
No owner decision is inferred when normal interactive mode is quit or cancelled.

`OwnerUIService('generic')` supports the same closed, typed action API and is tested
at that service boundary. The browser launcher and HTML are still the original
meeting workspace; generic browser support and real-browser acceptance are not
claimed. The generic console guide intentionally demonstrates only its exact
synthetic task, rather than pretending arbitrary provider tasks are integrated.

**Verification:** 400 Python tests and 19 DOM-model checks pass. Fifteen new cases
cover separated generic exchange, independent signer scope/payload checks,
wrong-owner/bypass rejection, defer/decline, uncertain receipt and storage reopen,
withdrawal, non-simulated quit and five console scenarios. A reviewer found a
malformed binding frame could terminate the generic signer; explicit type checks
and a malformed-frame-then-valid-binding regression fix it. No remaining blocking
finding was reported. See `test-results-v12.txt` and `generic-owner-*-v12.txt`.

Normal/defer/lost-receipt simulations complete with two verified receipts and two
transitions. Decline stops before disclosure; an unknown delivery outcome remains
uncertain without automatic retry. Storage reopen retains live disposable
signer/transport processes, not lost-key recovery. No real provider, account,
identity, network service, browsing or tool execution is involved. V3-v11 remain
preserved.

## Earlier v11: a generic conversation/task boundary, not a meeting-only network

```sh
python generic_demo.py --simulate
```

Two fictional provider-labeled assistants exchange an explicitly simulated
request and result for a public-resource shortlist. The payload uses inert
synthetic references; no website is visited, provider contacted or tool executed.
The demo passes through existing signed owner decisions, pinned identity bindings,
A4A cryptographic primitives, durable encrypted outbox, separate receiver stores,
verified receipts and processed task transitions. It finishes with two receipts,
two transitions and a completed task. Pairing alone sends nothing.

The new v2 envelope contains conversation, task, operation, capability, context,
sender, recipient, payload and exact request-digest reply linkage. It has no
meeting or candidate fields. Immutable task context binds every scope dimension.
Only its two designated peers can participate; a third conversation member gains
no task authority. Provider/display labels are references, not authentication.

Capabilities are static allowlisted data schemas, not execution grants. The first
non-meeting capability accepts only a bounded shortlist query and bounded inert
results. Unknown fields, tool instructions as fields and unknown capabilities fail
closed. Free text remains untrusted data. Every disclosed request/result still
requires an exact owner signature and bilateral task-scoped pairing. A result
must reverse the route, match the exact processed request and respect its size
limit. The v1 scheduling adapter remains supported without automatic migration.

**Verification:** 385 Python tests and 19 DOM-model checks pass. Twenty-four new
core/encrypted integration cases prove the non-meeting path, scope rejection,
consent, receipt uncertainty, revocation/cancellation and retained-record reopen.
Independent review found no blocking authority/binding defect; its third-member
regression was strengthened. All 13 copied upstream files still match their
pinned hashes. See `generic-task-output.txt`, `test-results-v11.txt` and
`ARCHITECTURE.md`.

**Limits:** provider labels do not prove live cross-provider interoperability.
At v11, V2 used direct simulated owner fixtures. V12 adds separated local
signer/executor workflow; real-human authentication and generic browser support
remain unimplemented. HTTPS-shaped result references are inert text,
not validated public sources. Some reused storage/control interfaces retain a
clearly documented legacy scope alias. Relationship directories, real provider
adapters, durable identity custody and generic owner UI remain future work.
Browser acceptance remains blocked. V3-v10 archives stay unchanged.

## Earlier v10: withdraw a provably unused authorization

An owner can now explicitly withdraw an authorization that was signed but never
executed, including one that expired or became stale while awaiting submission.
Choose **Withdraw unused authorization** and type `WITHDRAW <owner>`. Unlike
message approval, this specifically labeled action signs and applies the local
withdrawal in one step. It does not approve a replacement or dispatch anything.

The separate signer binds a fresh, domain-separated withdrawal to the exact owner,
context, original request, decision/message fingerprint and current review token.
The executor atomically rejects withdrawal if any execution ledger, outbox,
approval, receipt or processed transition exists for that authorization. Even a
queued message with zero attempts is excluded. This is not recall of a send.

A durable additive tombstone keeps the original signed evidence and fences both
raw control execution and encrypted enqueue. The old signature stays blocked in
this local execution store across record reopen and clock rollback. Exact retries
recover the same recorded result after expiry or a lost response. Withdrawn
requests no longer trap the guide.

Preparing a **fresh unsigned review** is a separate typed choice. It preserves the
exact action/message while obtaining a new nonce and checking current permissions.
It still needs a new approval and separate submission/delivery. The original
remains withdrawn rather than being relabeled as an unsigned superseded draft.
The fresh successor has its own durable, idempotent history. Explicitly choosing
Prepare next review in the guide can also create an unsigned draft after a
withdrawal; neither route revives the old authorization.

Verification: **361 Python tests** and **19 DOM-model checks**, including 22 new
core/process/adapter withdrawal cases and three UI-model cases. Evidence includes
transaction rollback, submit-versus-withdraw races, copied-token replay, wrong
scope/signature, old database setup, lost commit response and separate successors.
See `test-results-v10.txt`, `owner-ui-dom-v10-output.txt` and
`unused-withdrawal-output.txt`. Browser/visual verification remains blocked.

Withdrawal is local consent bookkeeping, not distributed revocation or provider
interoperability. Temporary fixture shutdown still discards its keys and records;
there is no real-person authentication or automatic identity recovery. V3-v9
archives are preserved.

## Earlier v9: explicit recovery of missing bilateral pairing

A blocked unsigned send now shows which directional pairing has expired or is
missing. Choose **Review pairing for <owner>** and type `REVIEW PAIR <owner>` to
open a separate unsigned pairing review for that owner. The opposite owner and
meeting are derived from the original send; this action cannot change recipients,
message, duration or context. Each owner must separately approve and submit.
Existing active grants are not extended.

Recovery preparation does not sign, grant pairing, replace the send, enqueue or
send anything. After both necessary grants are applied, return to the original
send and explicitly prepare a new review. Old send signatures remain invalid;
fresh approval, submission and dispatch are still separate steps. The console
also exposes this explicit recovery path.

Existing pending, deferred, declined, stale or authorized directional pairing
reviews are surfaced rather than silently recreated. A refusal remains a refusal.
Only explicit review replacement supersedes old unsigned history. A submitted
grant does not hide older unresolved/refused reviews. Recovery links persist in
one transaction with a source revision change. Exact retries return the same
historical pairing request even after it expires, is declined, submitted or
replaced. Navigation back to the source is read-only.

Only uncommitted unsigned pending/deferred sends can initiate this flow.
Superseded, authorized, submitted and uncertain sends cannot. Meeting cancellation,
transport identity expiry, scheduling changes and competing deliveries still
block. This restores no identity and grants no inferred consent.

Verification: **339 Python tests** and **16 DOM-model checks** pass. Thirty new
Python cases cover separate bilateral approval, prior history, exact retries,
subprocess/UI boundaries, rollback, reopen, limits and concurrent preparation or
cancellation. Two new DOM checks cover the typed direction and source navigation.
Independent review found a history-dedup gap, fixed with deferred/declined
regressions and verified. See `test-results-v9.txt`, `owner-ui-dom-v9-output.txt`
and `pairing-recovery-output.txt`. Browser and visual QA remain blocked. V3-v8
archives are preserved unchanged.

The fixture remains temporary and single-operator, not real-person authentication
or a live network. Expired identities and already-authorized/uncertain operations
are deliberately not restarted by this recovery flow.

## Earlier v8: explicit recovery from an expired unsigned review

A reproduced workflow dead end is fixed: a five-minute unsigned review could
expire and remain the only item returned by the guide forever. An owner can now
choose **Prepare new review** and type the displayed `REVIEW <owner>` phrase.
The console also offers this choice when an eligible draft expires.

This creates an entirely new **unsigned** request, not renewed consent. It keeps
the exact action, participants, meeting, message and pairing duration, while using
a fresh nonce/time window and current contact versions. The old request remains
visible as superseded, linking to its successor. No signature, submission,
delivery or identity binding is created by replacement. A new explicit approval
is still required.

Replacement is allowed only for expired/stale unsigned pending or deferred
requests whose current permissions still allow the same action. Declined,
authorized, submitted, committed and uncertain operations cannot be replaced.
Cancellation, current scheduling state, transport identity expiry, pairing and
competing delivery reservations still fail closed. Old signatures and even a
freshly read ancestor digest cannot revive a superseded request.

The new request, append-only lineage record and ancestor revision commit in one
transaction. Repeating the exact replacement operation returns the same successor,
even if that successor later expires, is declined or is submitted. It never
silently creates another request. Storage reopen preserves this history, and
concurrent replacement/decline has one winner. Existing request records are not
rewritten during the additive schema setup.

**At the v8 checkpoint:** replacement did not restore expired/revoked pairing.
V9 adds the separate explicit pairing-review path above. Replacement itself still
restores neither pairing nor transport identity.

Verification: **309 Python tests** and **14 DOM-model checks** passed, retaining the
previous suite plus 30 core/process/adapter cases and two DOM cases. Logs are in
`test-results-v8.txt`, `owner-ui-dom-v8-output.txt` and
`review-replacement-output.txt`. Browser/visual verification remains blocked as
described below; none of these checks is a browser acceptance test. V3-v7 archives
remain unchanged.

## Earlier v7: local browser interface (browser verification pending)

A loopback-only interface now wraps the tested owner inbox and delivery API. It
provides owner selection, readable request cards, explicit confirmation dialogs,
defer/resume, cancellation/revocation reviews, and separate receipt-check, attempt
and processing controls. It uses no external resources, services or real identities.

**Verification limit:** service/HTTP and DOM-model tests pass, but Chromium could
not launch in this execution environment. Real-browser interaction, native dialogs,
layout, mobile rendering and accessibility have not been verified. See
`UI_VERIFICATION.md`. This is a development UI checkpoint, not a finished product.

After installing the pinned Python dependencies below:

```sh
python local_owner_app.py
```

Open the exact `http://127.0.0.1:<port>` URL printed by that launcher in a browser
on the **same computer**. The default port is selected automatically; an optional
`--port` sets only the loopback port, never a public interface. The local address
is not a shareable website. No account creation or connection is required.

The first screen asks for explicit fictional transport-binding approvals. Owner
switching is role selection by one trusted operator, not authentication. The
server turns each explicit typed UI choice into the exact request-specific
confirmation required by the existing isolated signer. It checks the displayed
review digest before signing and again through the owner workflow. GET requests,
refresh, browser navigation and role selection do not prepare or approve work.
Preparing the next review requires an explicit action.

A request signature, execution submission, delivery attempt, receiver receipt and
local processing remain separate states/actions. Defer returns to the inbox and
requires explicit resume. Decline remains terminal. Missing or malformed mutation
responses warn that the outcome may be uncertain and are never automatically
retried. An existing receipt check never starts a delivery or processes a message.
Cancellation cannot recall an already-started attempt or disclosed information.

Keep the launcher running. Closing a browser tab keeps the fixture alive in the
local process, so the tab can be reopened or refreshed. **Discard fixture** or
stopping the launcher removes temporary state and disposable generated keys.
There is no persistent identity or restart recovery. An incomplete cleanup is
shown explicitly and blocks new actions. Use fictional data only.

The HTTP layer is bound to literal loopback, requires exact Host/Origin values and
closed JSON commands, serves only three static resources, disables caching,
blocks cross-origin framing/resources and limits request bodies/concurrent
handlers. These controls mitigate browser cross-origin access, not hostile local
processes or compromised consoles. No cookies, passwords or session credentials
are created. Never expose this unauthenticated fixture to the LAN or Internet.

Verification: **279 Python tests** plus **12 DOM-model checks** passed. A real
loopback HTTP client completed the 12-message flow and explicit cleanup. Python
compile and JavaScript syntax checks passed. Node is needed only to run the DOM
checks; browser runtime use needs only the Python dependencies and a browser.

```sh
python -m unittest discover -s tests -v
node --check owner_ui/app.js
node tests/owner_ui_dom_check.js
```

The included optional `browser_ui_check.py` can close part of the verification gap
in an authorized browser-capable environment. It has not passed here and does not
replace actual visual review. Previous archives remain unchanged.

## Earlier v6: guided owner inbox and uncertainty handling

After installing the pinned dependencies below, run:

```sh
python owner_console.py                           # interactive fictional-owner console
python owner_console.py --simulate                # explicitly synthetic complete flow
python owner_console.py --simulate --scenario decline
python owner_console.py --simulate --scenario defer
python owner_console.py --simulate --scenario lost-receipt
python owner_console.py --simulate --scenario uncertain
```

The guide prepares one owner request at a time. It shows the exact recipient,
message, meeting context, transport binding and expiry before the existing separate
owner signer can approve it. Pair/revoke/cancel cards explain their limits. Local
role selection is **not authentication**; one trusted operator still controls all
fictional people. There is no browser/server, account enrollment or new credential
system.

- **Approve:** records the exact owner-signed decision durably. Submission is a
  separate explicit step. For a message it only enqueues the fixed ciphertext;
  the subsequent send attempt is separate again.
- **Decline:** a terminal tombstone for this request. The guide will not replace
  it or ask again. Direct raw approval/control/send commands are rejected by the
  dedicated workflow executor mode, including previously signed tokens.
- **Defer:** grants nothing and invalidates the old review token. An explicit
  resume is required before review continues. Back and list also grant nothing.
- **Stale/expired:** current contact versions, cancellations, scheduling changes,
  pending operations, request revision and identity registry are rechecked.
  Changed or expired reviews cannot authorize an action or renew themselves.
- **Delivery:** inspecting status never sends, checks a receipt or processes a
  scheduling step. Receipt checks, explicit attempts and processing are distinct
  commands. An uncertain outcome is never displayed as success or failure merely
  because an acknowledgement is absent. The simulated uncertain run stops rather
  than resending or inventing a replacement approval.

The durable request journal separates `pending`/`deferred`, `declined`,
`authorized` and `submitted`. `submitted` means the signed control action was
applied or the exact message was enqueued; it does **not** mean delivered. Approval
and execution do not pretend to be one transaction. If execution commits before
its inbox status update, recovery verifies the existing consumed-decision ledger
using the same nonce and exact decision/message fingerprint. The guide repairs
only that status, without signing, enqueueing again, dispatching or processing.
A declined request cannot become approved through this workflow. Once authorized,
withdrawing authority requires the separately reviewed cancellation/revocation
path, not relabeling it as declined.

The delivery dashboard retains `received` versus `processed`, displays
`dispatched` as uncertain, and preserves `received_blocked` as received with
processing blocked. Post-cancellation existing receipt checks remain reachable
while this console is running. No new attempt is offered when consent, pairing,
identity validity or scheduling state no longer permits it. The dispatch layer
still rechecks everything inside its transaction. Cancellation cannot recall an
already-started attempt or disclosed information.

**Lifetime limitation:** `owner_console.py` uses a temporary directory and live
disposable signer/executor processes. Closing it discards those records and keys.
Defer is useful only while that console remains open; this is not a persistent
multi-user inbox or restartable identity system. The underlying journal survives
storage reopen, as tested with unchanged live fixture identities. Existing public
receipt evidence can also be recovered by the separate v5 key-free fixture, not
by pretending new keys are the same identity. Use only fictional data.

`encrypted_executor_process.py --owner-workflow` exposes only closed owner-scoped
request/delivery commands; legacy raw fixture APIs are disabled in that mode.
Those APIs remain in the separate v5 regression mode and are not a product-facing
security surface. Same-host hostile code and a compromised trusted console remain
outside the demonstrated boundary. The inbox lists only the latest 20 compact
request summaries per owner to keep IPC frames bounded; exact known request IDs
can still be reviewed by the low-level fixture API.

Verification: **258 tests passed**, retaining the previous 213 plus 29 workflow
core cases and 16 process/console cases. Coverage includes approve/decline races,
deferral and stale cards, wrong owners, raw-API bypass attempts, crash gaps,
reopen/reconciliation, malformed IPC, bounded inboxes, back/defer/resume/decline,
invalid early processing, cancellation and uncertain delivery. Full simulated
completion has 12 receiver receipts and 12 scheduling transitions. Decline and
uncertain-with-no-receipt scenarios retain zero receiver receipts/transitions.
`test-results-v6.txt`, `owner-*-output.txt` and `verification-v6.json` hold evidence.
This checkpoint was code-reviewed and tested, not independently security-audited.

## Earlier v5: owner-bound encrypted delivery and reconciliation

V5 joins the earlier separate cryptographic and owner-decision proofs into one
**offline, fictional** delivery flow. After installing the dependencies below:

```sh
python encrypted_demo.py --simulate
python encrypted_demo.py                    # explicit local owner confirmations
python encrypted_demo.py --simulate --scenario lost-receipt
python encrypted_demo.py --simulate --scenario cancel-before-dispatch
python encrypted_demo.py --simulate --scenario cancel-after-receipt
python key_free_recovery_demo.py
```

Four owner signer subprocesses approve public transport-key bindings and exact
outbound messages. A separate execution process holds transport keys but no owner
signing keys. Each binding requires an owner signature and proof of possession of
the transport key, with the exact meeting context, recipient set and expiry.
Every send binds both sender and recipient binding digests. Replacing a pinned
binding, substituting a recipient, or using a legacy unbound send is refused.
These checks establish possession and approval of **fixture keys**, not the
identity of real people. One trusted local console still controls all four roles.

The execution process writes immutable encrypted packets to a sender SQLite
outbox. Each recipient has a separate receiver database and its own transport
key interface. Receipt persistence and local scheduling processing are separate
steps. The databases and actors run on one host, not independent devices.

Delivery states have deliberately different meanings:

- `queued`: exact approval consumed and encrypted packet persisted, not dispatched.
- `dispatched`: an attempt was started; without a receipt its outcome is uncertain.
- `received`: the exact recipient signed a receipt for the exact encrypted packet.
- `processed`: receipt verified and local scheduling transition committed.
- `blocked`: prevented before any dispatch attempt.
- `received_blocked`: receipt is retained, but cancellation, revocation or changed
  scheduling state prevents processing. Disclosure is not erased from history.
- `stopped_uncertain`: earlier dispatch outcome is unresolved and permission is
  no longer valid. No further attempt is allowed; a later receipt can still be
  reconciled. Its scheduling-step reservation is retained to avoid a duplicate.

Before an uncertain retry, the sender queries the receiver's existing signed
receipt. An unavailable query does not trigger another send. A retry retains the
same delivery ID and ciphertext. The receiver deduplicates exact retries and
rejects nonce reuse with different ciphertext or consent. Sender-side checks of
permission and scheduling state run inside the dispatch transaction. Receipt
recording and subsequent processing each roll back atomically on failure.

**Cancellation boundary:** committing a dispatch attempt starts an in-flight
operation. Cancellation blocks later attempts but cannot recall that operation
or data already disclosed. A cancellation between dispatch commit and receiver
receipt may therefore still produce a receipt; subsequent processing is blocked.
This is not atomic cancellation across a real distributed network.

The lost-receipt demo commits receiver state, drops the acknowledgement, reopens
storage with the same live actor keys, and recovers the receipt without another
attempt. The separate `key_free_recovery_demo.py` goes further only for **existing
receipt evidence**: its preparation process exits, destroying its generated
private keys, then a new process reads public bindings and durable records to
verify and process the existing receipt. It loads no private key and cannot
receive/decrypt new messages, create a new delivery or restore an identity.
No generated private keys are persisted. This is not a key-custody/recovery system.

`test-results-v5.txt` records **213 passing unittest cases** on Python 3.12.14:
the previous 151 plus 11 identity-binding, 37 encrypted-delivery and 14 integrated
process/demo cases. Regression coverage includes forged receipts, recipient/key
substitution, lost acknowledgements, expiry, revoke/re-pair, cancellation races,
rollback at multiple transaction stages, concurrent operations, stale scheduling
steps, malformed IPC identifiers and process-exit receipt recovery. Demo output
files named `encrypted-*-output.txt` and `key-free-recovery-output.txt` record the
bounded proofs. This is a development checkpoint with code review, not an
independent security audit or proof of live interoperability.

## Earlier v4: isolated crypto and owner-decision fixtures

Install the test dependencies in a dedicated environment, then run:

```sh
python -m venv .venv
. .venv/bin/activate                     # Windows: .venv\Scripts\activate
python -m pip install -r requirements-offline.txt
python sdk_fixture_check.py
python signed_demo.py --simulate
python signed_demo.py                    # local operator confirms each owner decision
python signed_demo.py --simulate --cancel-after 5
python -m unittest discover -s tests -v
```

Dependency installation uses the package registry. Fixture subprocesses themselves
deny socket operations and child-process launches with a Python audit hook. That
is a regression guard for reviewed code, not an operating-system sandbox.

V4 introduced two distinct offline proofs, retained as regression fixtures:

1. **Pinned A4A crypto:** unchanged `crypto.py`, `keys.py`, `event.py`, `nip44.py`
   and `giftwrap.py` sign, encrypt, decrypt and verify a fictional scheduling message.
   The receiver additionally checks the enrolled fixture sender, exact recipient,
   conversation, delivery ID and closed scheduling schema. Official NIP-44
   known-answer vectors and nine unchanged upstream event tests also run.
2. **Signed owner decisions:** four disposable signer subprocesses retain separate
   Ed25519 private keys. A fifth process receives public verification keys and only
   accepts signed pairing, send, revoke and cancel decisions. Decisions bind exact
   context/target, message digest, expiry, one-use nonce and contact versions.
   Consent, local receipt, scheduling transition and the consumed-decision record
   commit atomically. A stale unseen approval cannot revive after revoke/re-pair.

The signed demo remains an owner **identity bootstrap fixture**, not authentication
of four real people. One trusted local console controls every fictional role.
The signing pipe must not be handed to an agent. This is process/interface
separation, not protection against arbitrary hostile code with the same OS access,
a compromised console, interpreter or database. No persistent credential or real
account is enrolled. Disposable generated keys are never saved or exported, and
all processes and temporary demo state are removed at the end. Publicly published
known-answer test scalars are retained only in the licensed upstream vector file.

In the v4 demos the proofs remain separate: the signed demo processes messages in
local SQLite; the crypto fixture exercises an in-memory envelope round trip. V5
combines these components only in the offline fixture described above. There is
no connected multi-agent service, live relay, cross-provider handshake, real peer
identity enrollment or live external-delivery reconciliation. SQLite stores only
fictional records, including plaintext bodies and metadata. No calendar is written.

`test-results-v4.txt` records **151 passing unittest cases** on Python 3.12.14,
including adapters running unchanged upstream checks. `sdk-fixture-output.txt`,
`signed-demo-output.txt` and `signed-cancel-output.txt` record the offline proofs.
`fixture-environment.json` records exact tested dependency versions. This is a
self-reviewed development checkpoint, not an independent cryptographic audit or
end-to-end production compatibility/security assessment.

## What works

- Both owners explicitly pair for the exact meeting context, with expiry and
  revocation. Pairing grants no permission to disclose information.
- Exact outbound message consent is separately required, bounded by recipient,
  message body, meeting context and expiry. Single-use approvals prevent replay.
- Before each message, a read-only review names the sender and sole recipient,
  lists the meeting participants, and spells out the exact UTC times. Availability
  review shows every candidate, including unavailable slots; omissions also convey
  information. The exact structured message, message digest and context follow.
- The meeting context binds all participants and exact UTC candidate times, not
  just a reusable meeting name. Immutable slots prevent changing approved meanings.
- Only candidate indices are exchanged. Calendar titles, reasons, projects, chat
  history and file contents are absent from this application protocol.
- Availability goes to the coordinator only. Sharing the resulting proposal with
  each participant also requires the coordinator's approval. Each acceptance is
  independently approved. Candidate availability and a common-slot proposal do
  reveal personal/derived information; this is deliberate, reviewed disclosure.
- Unknown fields, unsupported actions, fake identities, altered bodies, expired
  or revoked grants and out-of-scope recipients are rejected.
- SQLite stores purpose-scoped pairings, exact message approvals and durable
  inbox receipts. A transaction consumes consent and records local receipt
  atomically in the original local-delivery path. V5 consumes approval at durable
  enqueue, records remote-fixture receipt separately, then processes the scheduling
  transition. Retrying an exact approved delivery does not duplicate it, including
  after restarting the store. `received` is not confused with `processed`.
- Scheduling state is reconstructed from a durable transition journal. Consent
  consumption, receipt, transition and processing acknowledgement share one SQLite
  transaction in the original local-only path. V5 has separate enqueue, receiver
  receipt, sender receipt and processing transactions, with explicit reconciliation
  between them. A transaction failure rolls that step back; restart and concurrent
  duplicate delivery produce no extra scheduling transitions. Re-pairing cannot revive unused
  approvals invalidated by revocation. Local record counts and message sizes are bounded.
- Durable participant cancellation atomically stops the local meeting and
  invalidates unused approvals. New pairings, approvals and deliveries for the
  cancelled context fail closed. The original local-only send/cancel operations are
  serialized in SQLite. V5 serializes cancellation against dispatch commitment,
  not against an already in-flight receiver operation; see the boundary above.
  Retrying a committed session receipt is read-only and creates no new disclosure.
- Untrusted contact text can be displayed through A4A's preserved framing helper.
  This does not pair contacts or grant permission. Scheduling messages are closed
  structured data, not instructions passed to an LLM.

## A4A reuse and boundary

Upstream: https://github.com/a4a-network/a4a

Pinned revision: `6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e` (October 31, 2026).
The root LICENSE at that revision grants MIT terms, copyright 2026 A4A Network.
The original license and third-party notice document are preserved under
`vendor/a4a/`. `UPSTREAM.json` binds copied files to SHA-256 checksums and source URLs.

The first reused component is upstream `sdk-python/a4a/sanitize.py`, byte-for-byte
unchanged. `durable.quarantine_preview` invokes it with an unverified-contact
label. The original 11 sanitization checks are also preserved unchanged and run
through a local adapter. Framing is display hygiene, not a security boundary or
proof that prompt injection cannot succeed.

The scheduler, exact-consent enforcement and local SQLite delivery/session modules
are new application-layer code. `a4a_adapter.py` additionally adapts actual upstream
task tag layouts and `Agent.prepare_private_message` into strictly offline drafts.
`scheduling_draft` converts a validated scheduling envelope into the upstream
kind-14 inner-message shape with recipient, delivery and conversation tags. It
explicitly marks the result unauthenticated, unencrypted and unpublishable. No
agreement is fabricated; the scheduler remains responsible for approval and state. We inspected upstream SDK dependency metadata and inbox
implementation, but did not copy, install or execute the full SDK, MCP server or
relay. In v4, five upstream cryptographic/event modules are copied unchanged into
`vendor/a4a_sdk/` and executed only in the offline fixture. Their pinned blobs and
checksums are recorded in `UPSTREAM.json`. The local package wrapper intentionally
does not import the full upstream client or relay. This is **not yet a connected
A4A client**, a full fork, an independently reviewed cryptographic product, or a
replacement for upstream delivery semantics. The original draft adapter
constructs protocol-shaped drafts, not complete signed/encrypted A4A events. No public A4A
relay was contacted. The upstream notice describes additional components that
are not bundled here.

## Security model and limits

This is a testable policy prototype, not production-ready security:

1. One trusted local operator simulates four humans. Python method calls are not
   a separately authenticated owner channel. `owner_*` and `ConsentGate.approve`
   must never become remotely callable agent tools. A compromised host/process
   can bypass these boundaries. Python object identity is only a local fixture.
2. V4 and v5 verify signatures and encryption with disposable fictional keys only.
   No real-human identity enrollment, live E2EE service, cross-provider handshake,
   real contact invitation, Internet transport or persistent key custody is implemented.
3. Stored demo bodies and consent metadata are plaintext synthetic data. Do not
   enter real calendar or private information. There is no production at-rest
   security, retention policy or complete denial-of-service defense. Message size and
   per-table record limits are present, but are not a whole-system resource sandbox.
4. The SQLite transport and scheduling transitions now survive restarts together.
   Tests inject failures during transition insertion and processing updates, and
   verify rollback. This establishes local transactional behavior, not exactly-once
   external effects or safety against a compromised database/host. No external
   calendar effects exist. V5 receiver persistence is deliberately a separate
   transaction, not an effect rolled back by the sender transaction. Reconciliation
   is exercised only against offline stores, not a live remote transport.
5. `PersistentSession.submit` validates a closed scheduling schema and current state
   before atomic delivery. `LocalDelivery` also rejects unknown envelope/payload
   fields, but does not itself enforce meeting-state sequencing or authenticate
   owner arguments. Use the session API for the scheduling application. Owner UI
   methods are local trusted code, never safe to expose directly to remote agents.
6. Cancellation is local only and cannot recall information already disclosed.
   It cannot recall an already committed dispatch attempt either. It is a
   trusted-owner action, not an incoming protocol message. Future remote
   cancellation notification needs its own explicit approval and reconciliation.
   No commitments,
   payments, project/file sharing or calendar writes are available in this build.
7. Candidate times must be UTC minute-precision values. Local timezone display,
   daylight-saving handling, real calendars and race-safe booking remain future work.

## Earlier v3 verification

On November 7, 2026, Python 3.12.14: 90 unittest cases passed, including 11 original A4A checks inside
one adapter test and 18 offline protocol-adapter tests. Coverage includes the
four-person flow, denial, malformed JSON, private-field/injection rejection,
impersonation, mutation, expiry, replay, revocation, bilateral pairing, purpose
boundaries, restart after every transition, concurrent duplicate/competing sends,
transaction rollback at two failure points, CLI pause/resume, repeated resume,
and refusal to relabel simulated approvals as manual approvals. Twenty additional
cases cover cancellation, restart, exact-context isolation, concurrency, rollback,
fake local owners, unchanged receipt retries, record limits, readable review and
CLI cancellation confirmation/provenance. `compileall` also passed.

The simulated CLI completed all four acceptances with 12 audit events; manual
pairing denial sent nothing. `demo-output.txt` captures a fictional successful run,
`test-results.txt` captures the full suite, `resume-output.txt` captures pause,
resume and already-completed resume, and `cancellation-output.txt` captures pause,
cancel, blocked resume and repeated cancellation. No full upstream suite, live relay,
mobile/browser UI, live cryptographic transport or independent penetration test was run.

## Next implementation slice

Real-browser interaction and visual/accessibility review remain blocked until an
authorized browser-capable environment can run the existing checks. The service,
HTTP and DOM-model evidence must not be presented as browser acceptance.

Independent offline resilience work can continue. The next confirmed usability
gap is restoring expired bilateral pairing through separately reviewed owner
choices while leaving declined requests and uncertain deliveries intact. Neither
replacement nor pairing should silently restore data-sharing authority.

Real-human authentication, protected persistent key custody/rotation, recipient-
operated devices, live relay delivery and remote cancellation remain unimplemented.
Real accounts, persistent credentials/access, relay/calendar connections and
publication require separate explicit authorization. Restore older source only
into separate empty folders; never use it to bypass newer cancellation, identity,
consent, lineage or receipt state. V3-v7 ZIPs are preserved unchanged.
