# What existing projects already do

## Direct answer

Yes. Several projects already implement substantial parts of Assistant Central.
**OpenAgents Workspace is the closest broad product comparison**: persistent
threads, mixed people/agent teams, shared context, resource sharing, approvals
and runtime adapters. **AgentPeerChat is the closest small messaging layer**.
**Buzz is a broader human/agent team workspace**. None of the reviewed sources
establishes the complete Assistant Central vision: independent owners' existing
personal assistants across providers, with explicit historical disclosure,
source-owner consent that survives derived summaries, and separately authorised
actions and provider disclosure.

That gap is specific, rather than a reason to rebuild every messaging primitive.
The useful product is a familiar conversation experience combined with stronger
owner and source boundaries, adapters to supported existing assistants, and
verifiable delivery/task state.

## How to use this evidence

Every source link below has a matching locally copied, pinned snapshot in
[SOURCES.json](SOURCES.json). The inventory records the exact revision; follow its
commit link rather than assuming a mutable `main` branch still behaves the same.
Code pointers identify concrete reading targets. We inspected the named areas
and documentation, not every line in all repositories, and did not run their
software. Maturity statements are upstream descriptions plus repository activity
observed on 10 November 2026, not security certifications or production approval.

## Comparators and methods to mine

### OpenAgents: broad persistent collaboration

[openagents-org/openagents](https://github.com/openagents-org/openagents),
Apache-2.0. Active Workspace v1.1 with a launcher and SDK; the repository has
several layers, so distinguish workspace features from older SDK demos.

Study `workspace/backend/app/models.py`, `services/access_model.py`,
`routers/groups.py`, `routers/approvals.py`, `routers/sharing.py`,
`workspace/docs/permission-model-v1.md` and the runtime adapters in
`packages/agent-connector/`.

The useful pattern is separate human/agent identities, resource ownership,
thread participants, security groups, explicit grants and a common permission
service. It demonstrates much of the desired room experience. However, at the
pinned revision its access-model contract deliberately retains full access for
legacy machine callers without an agent identity, and agents inherit their
human owner's accessible resources. That is a materially different boundary
from a narrowly authorised Assistant Central participant. Do not carry that
legacy compatibility shortcut into new code. Thread participation is not proof
of each source owner's permission to redistribute earlier private context.

### AgentPeerChat: a small durable mailbox and group UI

[AgenticsWorks/AgentPeerChat](https://github.com/AgenticsWorks/AgentPeerChat),
MIT. Early v0.1.x project, created October 2026. Study `src/index.ts`,
`migrations/0001_initial.sql`, `docs/protocol.md`, `SECURITY.md` and its receiver
adapters.

Mine deterministic direct-thread IDs, group membership, separate per-recipient
ACK rows, stable idempotency keys, bounded pagination, durable unread delivery,
and notification hints that do not pretend to prove model execution. Its Grok
Bot wake flow distinguishes trigger acceptance from a correlated reply and ACK.

Do not adopt its privacy defaults: authenticated humans observe all conversations;
new members receive the whole group's historical visibility; mentions only affect
notifications, not who can read the message. `threadAccess` in `src/index.ts`
checks membership for agents but not human principals. The README and protocol
also disagree about default invitation/sign-in privileges. Pin and test the code,
not the marketing description. It is not end-to-end encrypted.

### agent-talk and retalk: independent agent messaging

[xhluca/agent-talk](https://github.com/xhluca/agent-talk) and
[xhluca/retalk](https://github.com/xhluca/retalk), both MIT. Small active-era
projects; their security documents explicitly say they have not been independently
audited. agent-talk is mostly a host-facing skill/listener layer, not the crypto
implementation.

Study agent-talk's `bin/spool-writer.py`, host inbox extensions and history/group
skills as data. Study retalk's `src/retalk/user.py`, `store.py`, `server.py`,
`docs/STANDARD.md` and group/E2EE tests. Useful methods include pinned peer
fingerprints, durable local history, stable message IDs, group IDs independent of
names, client-side fan-out and explicit partial-send results. The relay's
ciphertext is not a shared searchable transcript; local decrypted history and
host wake-up remain separate concerns. The relay still sees traffic metadata.
Neither project supplies a cross-owner task approval or source-lineage model.

### Open Agent Bridge: coding-session hub

[kevinArgueta96/open-agent-bridge](https://github.com/kevinArgueta96/open-agent-bridge),
MIT. Small project, five stars at inspection; this is the likely match for the
voice discussion about connecting coding sessions.

Study `src/registry/channel-store.ts`, `src/client/conversation-session-store.ts`,
`codex-app-server-bridge.ts`, `claude-inbox-socket.ts` and the associated tests.
It shows how registry identity, an inbox and a runtime's actual session identifier
can be separated. It is primarily local coding-session coordination, not a
federation of owners' persistent personal assistants.

Some adapters use host-specific internals such as local language-server/session
state. They must not be treated as a supported personal-assistant API. Documentation
claims that delimiters prevent prompt injection; that is not a security boundary.
Use supported host interfaces and enforce authority outside message text.

### Open Agent Bridge: self-hosted coordination service

[munboon/open-agent-bridge](https://github.com/munboon/open-agent-bridge),
Apache-2.0, separate from the project above. Upstream labels v0.1.0 early access
and Ubuntu-first. It has a recorded independent Codex process pilot, while its
signed-enrolment path is described as integration-tested rather than having the
same independent pilot.

Study `src/lib/messaging.ts`, `tasks.ts`, `request-proof.ts`, `agent-enrollment.ts`,
`transfers.ts`, `db/001-bridge.sql` and `tests/recovery-regressions.test.ts`.
Useful methods are permitted peer edges, retained pair conversations, signed
requests, claim/session generations and an explicit `needs_reconciliation` state
when work may have happened before a crash. Receipt or reconnection must not
silently rerun an external effect. It does not wake stopped agents. Ordinary
messages are readable by the service operator; encrypted files are a separate
mechanism. Its existing kits' broad filesystem/no-interactive-approval mode is
not an appropriate default for our adapters.

### Buzz: humans and agents as room members

[block/buzz](https://github.com/block/buzz) and
[block/buzz-app](https://github.com/block/buzz-app), Apache-2.0. The former is the
supported 0.x relay/workspace source; the latter says Buzz 1.0 is beta. Inspect
both instead of treating a repository move as a stable API guarantee.

Study the original `ARCHITECTURE.md`, `SECURITY.md`, `crates/buzz-auth`,
`crates/buzz-relay`, `crates/buzz-audit` and `crates/buzz-acp`; the new client's
`src/features/agents/` and message features show the UI/runtime split.

Mine individually signed events, first-class agent identities, channel membership,
threaded history, audit/event correlation and a JSON-first CLI. It is a strong
workspace reference, but membership is the original relay's coarse read/write
boundary, not source-specific disclosure consent. Signatures establish attribution,
not confidentiality or truth. Its own security document explains that a database
writer can recompute a keyless hash chain, so keep external audit checkpoints when
claiming tamper evidence. Do not confuse the beta client with independent security
validation of the relay.

### A2A: interoperability and task envelopes

[a2aproject/A2A](https://github.com/a2aproject/A2A), Apache-2.0. Established open
protocol with multiple SDKs; current documentation describes the v1.0 generation.
Study `specification/a2a.proto`, `docs/topics/life-of-a-task.md`,
`docs/specification.md` and `docs/topics/enterprise-ready.md`.

Use its Agent Cards, task/context identifiers, lifecycle/status, typed message
parts, artefacts and asynchronous updates as an external adapter contract. A2A
preserves an agent's opaque internal state; it does not make private transcripts
universally queryable. Authentication/authorisation is the implementation's
responsibility. An A2A context is not our human-room membership/history policy,
and an Agent Card's capability advertisement is not permission to act.

### CHAP: structured accountable decisions

[BrightbeamAI/chap](https://github.com/BrightbeamAI/chap), code Apache-2.0,
specification CC BY 4.0. Upstream calls 0.3 a public draft with potentially breaking
minor releases. Study `profiles/`, `packages/coordinator-py/chap_coordinator/`,
`conformance/` and `SECURITY.md`.

Mine explicit review, approve/reject/override, handoff propose/accept/decline and
escalation envelopes, with audit ordering and optional signatures/identity
profiles. The dual-language conformance approach is useful for our protocol.
Do not mistake a human-looking identifier or a recorded approval event for
verified owner consent; select and enforce the identity/security profiles. It is
an accountable work protocol, not the complete persistent chat product.

### Matrix specification: historical visibility and room membership

[matrix-org/matrix-spec](https://github.com/matrix-org/matrix-spec), Apache-2.0.
This is the specification, not the Synapse server; licences of server/client
implementations must be checked separately. Study
`content/client-server-api/modules/history_visibility.md`, membership/event APIs
and `modules/end_to_end_encryption.md`.

The crucial lesson is that membership and history visibility are different state.
Matrix distinguishes shared history from history visible only since invitation or
joining. Use the distinction when adding someone to a conversation. Matrix's
room rule alone still does not represent permission from every owner whose
external private content appears in a summary. Encryption key sharing and
historical authorisation must agree; a database filter cannot retract plaintext
already received.

### OpenFGA: relationship checks outside the model

[openfga/openfga](https://github.com/openfga/openfga), Apache-2.0. Mature,
actively maintained authorisation service, not an agent or chat application.
Study `pkg/typesystem`, `internal/check`, command tests and the maintained
[task-based agent authorisation guide](https://openfga.dev/docs/modeling/agents/task-based-authorization).

The useful pattern is checking both the requesting user's authority and the
specific agent/task's grant. Model ownership, membership and time-bounded grants
as data and evaluate them server-side. Do not make model-generated claims or
cached search snippets the source of truth. It is an option to evaluate after
our permission semantics are precise, not a required new service for the MVP.

### LangGraph and Microsoft Agent Framework: execution, not the network

[langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) and
[microsoft/agent-framework](https://github.com/microsoft/agent-framework), MIT.
Both are large actively maintained frameworks. Study LangGraph's
`libs/checkpoint/`, `libs/checkpoint-postgres/` and persistence interfaces;
Microsoft's `python/packages/orchestrations/agent_framework_orchestrations/`
contains sequential, concurrent, group-chat and handoff implementations.

Mine checkpoint IDs, resumable state, interrupt/resume boundaries, bounded
orchestration and clear cancellation semantics. A framework's group chat usually
means model/agent orchestration inside an application, not independently owned
humans' assistants joining a persistent social room. A checkpoint is neither
external-action exactly-once execution nor proof of a user's approval.

### ggwave and GibberLink: optional acoustic transport

[ggerganov/ggwave](https://github.com/ggerganov/ggwave) and
[PennyroyalTea/gibberlink](https://github.com/PennyroyalTea/gibberlink), MIT.
ggwave is an established small data-over-sound library; GibberLink is a demo,
with its latest observed code push in July 2025. Study ggwave's `include/ggwave`,
`src/ggwave.cpp`, Reed-Solomon code and examples; the GibberLink demo's application
code shows negotiation around the transport.

The documented rate is 8–16 bytes/second. It is not encryption, secret language,
identity verification or an advantage over normal IP networking. Anyone with a
suitable microphone/decoder may receive it. Use, at most, for an optional physical
pairing experiment carrying a short-lived authenticated token, never a private
transcript. Encrypt and authenticate at the application layer, prevent replay and
require visible user intent. Bluetooth is radio, not this acoustic channel. Neither
belongs on the critical path for persistent conversations.

## What to build and what not to duplicate

Keep the current signed owner/source-grant foundation. Add a durable conversation
layer, typed message history and owner-aware membership above it; map externally
through A2A or a small MCP service. Borrow mailbox/idempotency patterns, not
another product's broad trust defaults. Add one independently verified host
adapter at a time. Existing personal-assistant continuity is the acceptance test,
not a model API returning a reply.

The detailed data model, history-expansion rule and adversarial acceptance tests
are in [CONVERSATION_PLAN.md](CONVERSATION_PLAN.md). The research does not establish
that any source can simply be dropped into the current pilot or that real Grok Bot,
Duet or dot accounts have been connected.
