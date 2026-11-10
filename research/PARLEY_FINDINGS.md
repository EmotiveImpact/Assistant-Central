# Two different Parley projects

Inspected 10 November 2026. This is source and documentation research, not a live
service trial or security audit. No account was created, agent connected,
installer run, credential supplied or model request made. Neither project is a
drop-in replacement for Assistant Central's owner-controlled network.

## Recommendation

Use Weldra's documented coordination patterns and ericscalibur's room experience
as design references. Implement them on our existing permission and acceptance
contracts. Do not replace those contracts with a team token, a room URL, a model
instruction or an unversioned acceptance flag.

The most valuable combination is a durable conversation shared by authenticated
owners, private owner-to-assistant guidance, reliable delivery to supported
existing assistant sessions, and an explicit proposal/review/acceptance flow.
Historical disclosure, provider disclosure and permission to perform an action
must remain three different decisions.

## 1. Parley by Weldra

### What the primary documentation establishes

[The quickstart](https://parley.weldra.dev/docs) documents a hosted MCP endpoint,
team tokens and named agents. Its tools discover teammates, send messages and
check an inbox. Repo-scoped Spaces organise messages. Per-agent cursors support
ordered catch-up. A prompt hook checks unread work; optional Claude Live Wake
sends a body-free notification to an already running session. It does not start
an agent or approve tools. Human questions correlate replies through Slack or
Telegram; paid paging escalates overdue blocking work. Path claims are advisory,
not filesystem locks. The event record can be exported as JSON. These are
documented behaviours, not independently exercised guarantees.

[The homepage](https://parley.weldra.dev/) advertises cross-person, cross-machine
coding-agent coordination and labels its animated relay example as simulated.
Its provenance labels and delivery states are useful presentation ideas, not
proof that arbitrary incoming text is safe or authorised to execute.

### Security, source availability and licence

[Security disclosures](https://parley.weldra.dev/security) claim team isolation,
hashed agent tokens, encrypted integration secrets, TLS, managed Postgres and an
append-only activity record. They expressly say there is no SOC 2/ISO 27001
certification or independent penetration test. We did not verify these controls.
An operator's append-only promise is not independent cryptographic tamper evidence.

No public source repository was verified through the official site's links and
targeted GitHub/web searches for Weldra and its exact service domain. This is a
bounded search result, not proof that no repository exists. The public installer
URL was discoverable but the web reader could not retrieve it; it was not run.
[Terms §11](https://parley.weldra.dev/terms) reserve the hub and client tooling's
intellectual property and do not grant an open-source copying licence. No Weldra
code has been imported. Independent implementation of general coordination
patterns is the useful route; a future connector also needs its own service and
data-sharing review.

[Weldra's company page](https://weldra.dev/) distinguishes live Parley from Reeve,
an in-development tool-authorisation gateway. Do not attribute Reeve's advertised
policy checks or just-in-time credentials to Parley.

### What to adapt

- Separate durable delivery from optional host notification. Our notification
  should carry an opaque inbox hint, not private content or permission to act.
- Keep an explicit cursor per receiving identity and session generation. Advance
  it only under a documented durable acknowledgement contract.
- Show lightweight work claims alongside a task and branch. Treat overlap as a
  coordination warning, never permission to write or evidence of an enforced lock.
- Correlate a blocked task with one human question and one reviewed response.
  Expiry, cancellation, duplicate replies and escalation need explicit states.
- Expose a timeline tying proposal, disclosure, receipt, recipient acceptance,
  execution attempt and result together, without confusing these events.

These are proposed Assistant Central designs, not claims about Weldra's internals.

## 2. ericscalibur/Parley

### Exact source and copying decision

Public repository: [ericscalibur/Parley](https://github.com/ericscalibur/Parley).
Inspected revision:
[`f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b`](https://github.com/ericscalibur/Parley/tree/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b).
It contains seven tracked files, including one server and one HTML client, with
no test suite. Its package's test command is a placeholder. This is a small
prototype, regardless of the package's 1.0.0 version string.

[package.json](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/package.json)
declares **ISC**. However, the pinned tree has no licence file or copyright notice,
and GitHub does not identify a repository licence. Do not describe it simply as
unlicensed: there is an explicit metadata declaration. For this research import
we conservatively retained references and original analysis only, pending a clear
licence/notice record before republishing or adapting its implementation. No
Parley source is included in the sixteen-source archive inventory. This is a
technical provenance decision, not a legal opinion.

### Behaviour verified by static source inspection

| Concern | Source behaviour | Useful lesson and boundary |
|---|---|---|
| Different owners in a shared room | [Room state and broadcast](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L18-L89) model two participant seats and an optional judge. Shared state includes the transcript, current draft and acceptance flags. | Clear shared floor and named representatives. These are user-supplied seat names, not authenticated owner identities. |
| Private briefs and files | [Prompt assembly](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L130-L181) includes the acting seat's brief/private files and both seats' shared files. Broadcast omits the brief, keys and private-file bodies. | The UI distinction is valuable. Model instructions asking for secrecy are not a disclosure control. The server and selected model provider receive the private material. |
| Collaboration and negotiation | The same [prompt assembly](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L130-L181) selects cooperative or negotiating objectives, including the possibility of no agreement. | Separate room purpose and conversational stance from permissions. Negotiation mode must not create legal or financial authority. |
| Existing assistant connection | [Provider calls](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L230-L371) use a seat's API key and assemble a fresh model request. | This is model-API orchestration, not a bridge to an owner's existing personal assistant or its private history. Default model names were not tested. |
| Human steering | [Pause and autonomy handlers](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L629-L644), [draft approval](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L684-L703) and [private nudges](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L776-L783) give each participant local controls. Autonomy zero reviews each outbound turn; intermediate values periodically pause. | Adopt private steering and bounded review cadence. Preserve explicit permission gates regardless of an autonomy slider. |
| Shared draft | [Draft extraction and posting](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L467-L514) parse text markers into one mutable draft and detect readiness for review. | A side-by-side proposed artefact is useful. Use validated structured events and immutable revisions rather than treating model text markers as authority. |
| Mutual acceptance | [Ratification](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L763-L774) records one boolean for each participant seat; the judge cannot ratify. | Bilateral review is useful UX. It is not cryptographic owner approval and does not bind a content hash, revision, recipients or action scope. |
| Persistence and reconnect | The [room store](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L18-L52) is in memory; [joining](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L558-L592) takes an available seat by room name. [Disconnect](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L786-L803) frees the seat but retains the room's shared state. | Do not adopt this for persistent multi-owner chat. A later occupant receives earlier shared history; there is no source-owner historical grant or authenticated rejoin contract. |

### Three implementation hazards worth learning from

1. **Private from the other UI is not private from the provider.** The source's
   file-upload comment says private files never leave the server, yet prompt
   assembly and provider dispatch transmit them to the selected API. Our UI must
   explicitly distinguish recipient, operator, runtime and model-provider audiences.
   The public floor can also reveal private source material through model output;
   asking the model not to reveal it does not solve this.
2. **Approval must cover the bytes delivered.** After both boolean approvals,
   [compilation](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L373-L400)
   makes a new model call. Its [completion handler](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L705-L732)
   publishes newly generated final-document text without a second exact-content
   approval. Assistant Central should compile first, then review that immutable
   result, or require fresh approval of every changed result.
3. **Pause must fence in-flight work.** The [turn loop](https://github.com/ericscalibur/Parley/blob/f9f5fb3ce4aa01d50c0efcd99bf4f23e0e51412b/server.js#L420-L465)
   checks running state before awaiting a provider, but does not recheck a session
   generation or pause state before posting its eventual response. This is a
   static-review race concern, not a reproduced exploit. Fence stale results at
   commit, not merely at dispatch. Apply the same rule to replaced seats and
   changed sources, with an explicit uncertain-attempt reconciliation path.

The README also contains older scope wording about collaboration-only operation;
the pinned server implements negotiation and a draft panel. The code, not that
stale scope paragraph, is the basis for the comparison. No runtime reliability,
security or provider compatibility has been established by this inspection.

## 3. Comparison with Assistant Central

Baseline checked: `main` at
[`55b7df104b12f69336055ca9d5ba0d773d8b10a5`](https://github.com/EmotiveImpact/Assistant-Central/tree/55b7df104b12f69336055ca9d5ba0d773d8b10a5).

Our [pilot runtime](../pilot/RUNTIME.md), [work loop](../pilot/WORKFLOW.md),
[encrypted storage](../pilot/STORAGE.md) and
[HTTPS exchange](../pilot/HTTPS_EXCHANGE.md) already provide stronger explicit
owner, pinned-peer, proposal/decision/receipt and reviewed-result boundaries than
the room prototype. These remain tested pilot contracts, not demonstrated live
multi-owner deployment. The [signed source-grant module](../pilot/SOURCE_GRANTS.md)
binds exact declared source and payload commitments, audience and expiry, but is
standalone: its documentation explicitly says it is not yet a runtime permission
or provider-dispatch path. Do not claim that integration is finished.

[Conversation PR #22](https://github.com/EmotiveImpact/Assistant-Central/pull/22)
adds a separately reviewed local trusted-host ledger. At this comparison point
it was not part of the pinned main baseline. Its review evidence is not evidence
of distributed delivery, provider disclosure or native-assistant connection.

What the two Parleys add to our design is a more obvious day-to-day experience:
named assistants in a room, private steering, a shared draft, clear readiness for
review, delivery visibility and blocked-work escalation. What they do not supply
is our complete independent-owner authority model. Preserve the existing gates
while adding these missing interaction and integration layers.

## 4. Prioritised engineering tasks

These are recommendations, not claims that the work is implemented. Coordinate
with the existing conversation, host-bridge and owner-interface work before
opening overlapping implementation changes.

| Priority | Task | Completion evidence |
|---|---|---|
| P0 | Connect durable conversations to the existing owner ledger. Use immutable event IDs, authenticated principals, membership epochs and future-only default joins. Add selected-history grants without turning a whole-room invite into blanket source consent. | Add a third owner, restart, remove/rejoin them, and prove older messages, search snippets, attachments and derived summaries remain unavailable without current grants from every declared source owner. |
| P0 | Bind provider disclosure and outbound conversation publication to exact source commitments. Keep private brief and public floor as distinct objects. Recheck authority atomically with a single dispatch attempt. | Revocation between review and dispatch fails closed; changing provider, model, recipient, purpose or payload invalidates approval. A summary cannot erase upstream ownership. Do not claim semantic tracking of undeclared sources. |
| P0 | Build bilateral proposal review over immutable artefact revisions. Separate each source owner's disclosure permission, recipient acceptance and each owner's permission to act. | Both parties approve the same digest. Mutation or new compilation requires fresh review. Approval to discuss or accept an artefact never authorises a payment, contract, deployment or external message. |
| P0 | Finish a supported existing-session bridge with durable inbox/outbox and correlation. Keep received, fetched, processed and completed separate. | Two independently controlled, explicitly enrolled assistant hosts exchange a reviewed task and result; restart/replay does not duplicate side effects. A fresh API model or synthetic fixture does not count as this acceptance test. |
| P1 | Add private steering, per-owner review cadence, pause and cancellation generations. Keep useful in-flight output quarantined when authority changes. | A delayed result after pause/rejoin/revocation cannot enter the shared floor or execute tools. Resuming requires current authority, not a stale boolean. |
| P1 | Add correlated human asks and bounded escalation. Minimise the alert payload; record intended recipient and exact question. | Duplicate/late replies cannot approve a changed task. Deadlines stop after cancellation. Slack/Telegram or other external delivery occurs only under the owner's approved recipient/data scope. |
| P1 | Add advisory file/work claims and a compact audit view. Store task, owner, repository, branch, path, expiry and generation. | Conflicting claims are visible; stale claims expire. Claims never bypass repository permission or merge review. Audit export exposes delivery and acceptance as separate events, with documented trust and rollback limits. |
| P2 | Add an optional neutral reviewer and negotiation stance as room settings. Use typed, bounded envelopes and turn/token budgets. | Reviewer sees only separately authorised material and cannot accept for an owner. Lack of agreement, budget exhaustion and human intervention are normal terminal states, not reasons for an endless agent loop. |

## Reuse decision

- **Copy now:** no code from either Parley in this research update.
- **Adapt now:** the interaction and coordination methods above, implemented
  independently on our reviewed boundaries.
- **Investigate later:** a Weldra connector only if wanted for a concrete workflow;
  it requires service, disclosure and supported-host verification. Resolve
  ericscalibur's licence notice before copying implementation. No outreach or
  service signup has been performed.
- **Do not import:** team-wide authority shortcuts, unauthenticated room seats,
  prompt-only privacy, model markers as approval, unversioned acceptance, or
  acceptance of newly generated bytes based on an earlier review.

See [PARLEY_SOURCES.json](PARLEY_SOURCES.json) for the source and licence record,
and [CONVERSATION_PLAN.md](CONVERSATION_PLAN.md) for the broader contract.
