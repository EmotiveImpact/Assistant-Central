# Assistant Central: agent orchestration landscape and reuse plan

Research snapshot: 8 November 2026. Scope: a Python-based Assistant Central that coordinates agents from different providers and different owners while preserving each owner's credentials, workspace, approvals and private state.

## Recommendation

Do not select a single framework as “the best agent orchestrator.” The candidates solve different layers.

1. **Keep Assistant Central's owner-controlled collaboration model independent of any agent framework.** Its durable task ledger, membership, consent, artifact access, audit history and acceptance rules are product responsibilities.
2. **Retain A4A behind a transport adapter** for encrypted personal-agent messaging. Add an **A2A adapter** for interoperable remote tasks and results. They are complementary options, not interchangeable implementations of the same protocol.
3. **Evaluate LangGraph first for durable coordination**, and **Pydantic AI first for a typed, provider-neutral Python execution adapter**. Choose a minimal combination after a common proof-of-concept. Do not introduce two overlapping workflow engines simply because both are capable.
4. **Use DSH Squad as the closest architectural reference for multi-owner delegation**, rather than adopting its DSH-specific TypeScript runtime. Borrow its receiver-owned authority, explicit task acceptance, private/local session separation, immutable revisions and failure semantics.
5. Keep OpenAI Agents SDK, Microsoft Agent Framework, Google ADK and CrewAI as optional execution adapters. A participant should not need to migrate their existing agent into Assistant Central's preferred framework. Evaluate Agno/AgentOS as a broader platform alternative if a centrally managed service fits the ownership model.
6. For a permissively licensed core, prefer MIT/Apache-2.0 components with a per-component licence inventory. Do not casually copy AGPL code or modified-Apache product code into that core.

These are fit-based recommendations, not measured performance rankings.

## Method and limits

Reviewed current public GitHub READMEs, licence files, repository metadata, release feeds, selected implementation files, tests and official documentation. Code inspections were selective, not a security audit. The projects were not installed or benchmarked against each other. “Implemented” below means source or documentation supports the capability, not that every production failure case was independently exercised.

Repository push timestamps and release history indicate activity, not reliability. Stars indicate attention, not suitability. Some default-branch features may be ahead of a released package, so production decisions must be repeated against pinned release commits.

## The four layers that must stay distinct

- **Agent execution:** model calls, tools, local memory, handoffs, sandbox interaction. Examples: Pydantic AI, Agents SDK, ADK, CrewAI.
- **Workflow orchestration:** state machines, fan-out/fan-in, durable pauses, retries, checkpoints and cancellation. Examples: LangGraph, Microsoft Agent Framework, Temporal.
- **Interoperability and transport:** remote-agent discovery, task/status/result exchange, encrypted messages, or host-to-agent communication. Examples: A2A, A4A, Agent Client Protocol, MCP.
- **Multi-owner control plane:** who owns each agent; who may delegate; who approves which exact action; what may leave a workspace; who can access an artifact; what is owed and accepted; revocation and audit. This is Assistant Central's differentiating layer.

A multi-provider API wrapper is not automatically multi-owner. A coordinator spawning ten local agents under one credential set is not a federation of ten independently controlled personal agents.

## Comparison of the principal candidates

| Project | Licence and architecture | Useful, supported capabilities | Fit and remaining gap |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT; Python graph/state execution, separate checkpoint/store implementations; JavaScript sibling | Durable graph state, subgraphs, branching, fan-out, interrupts and human review, streaming, persisted state and memory | Strong candidate for Assistant Central's coordinator. Does not itself establish an independent owner's identity, permission to receive data, or authority to approve remote tools. Keep those outside graph state callbacks. |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai) | MIT; typed Python agent loop, graph and harness packages | Provider adapters, validated structured outputs, tool delegation, isolated subagent histories, deferred/approval-required tools, usage propagation, OpenTelemetry, durable-engine integrations | Strong Python runtime adapter. Its type system helps define the contract between providers. Its runtime approval flag is not a signed, cross-owner consent system. Durability requires deliberate backend selection. |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | MIT; Python/.NET, separate Go project; graph workflows and middleware | Sequential/concurrent/handoff/group collaboration, checkpoints, human input, streaming, provider integrations, OpenTelemetry, A2A hosting examples | Strong alternative if enterprise workflow breadth and .NET interoperability matter. Heavier than a narrow adapter. Owner-local grants, tenancy and artifact sharing still require application design. Prefer it over starting a new AutoGen dependency. |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | MIT; lightweight Python agent runner, handoffs and agents-as-tools | Multiple model providers, MCP tools, sessions, run tracing, guardrails, nested tool approvals, serializable paused RunState; newer sandbox capabilities | Good local execution adapter, especially for existing OpenAI users. Not an organization directory or cross-owner task ledger. Permission scopes need particular care when sharing approval state across agents. |
| [Google ADK](https://github.com/google/adk-python) | Apache-2.0; Python agents and graph-based Workflow runtime | Current ADK 2.0 source documents task delegation, fan-out/fan-in, loops, retry, state, nested workflows, human input and tool confirmation; model/deployment agnostic with Gemini optimization | Good adapter for Google-oriented participants. Workflow and artifact/session capabilities do not eliminate the need for owner isolation or recipient-bound consent. Do not assume every feature is independent of a specific backend. |
| [CrewAI](https://github.com/crewAIInc/crewAI) | MIT core; Python Crews and Flows | Role-based task collaboration, programmatic/event-driven workflows, delegation, provider integrations and human-input patterns | Good for predefined business-process teams. “Crew member” normally describes an application-controlled role, not an independently governed person’s agent. Keep enterprise service terms separate from the OSS core licence. |
| [Agno / AgentOS](https://github.com/agno-agi/agno) | Apache-2.0; Python agents, teams, workflow and service platform | AgentOS API/MCP, authentication and role-based authorization, human approvals, durable jobs, scheduling, per-user data isolation; Company OS task/project routes; Claude/Codex harness integration | Serious build-versus-adopt candidate, not merely an agent loop. Centrally hosted user isolation is still different from independent owners keeping credentials and workspaces on separate nodes. Review the chosen deployment and control-plane UI terms independently. |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | MIT; higher-level Python harness built on LangChain and LangGraph | Planning, isolated-context subagents, filesystem/sandbox backends, context management, memory, skills, MCP and tool review | Useful ready-made local worker when LangGraph alone is too low-level. Its own security guidance says permissions must be enforced in tools/sandboxes, not by trusting model self-restraint. It is not a separate federation layer. |
| [DSH Squad](https://github.com/zhouCode/dsh-squad) | MIT; TypeScript DeepSeek Harness plugin; signed local nodes plus Relay or Direct transport | Owner/Admin/Member directory, invitations, local execution policy, reviewed team-plan drafts, immutable task revisions, persistent offline delivery, signed receipts, private HumanTodo/session state, explicit outcomes | Closest product model for cross-owner collaboration. DSH-specific, small project; trusted relay can read content, no E2EE. Port selected contracts/patterns/tests rather than replace the Python application. |
| [A4A](https://github.com/a4a-network/a4a) | MIT original code; Python SDK/MCP, Rust relay, signed event protocol | Portable cryptographic identity, owner mandates and revocation, contact handshake, E2EE private messages, acknowledgements, encrypted file references, task/status/result events, bilateral agreements | Strong match for private personal-agent transport. Not a complete scheduler, task DAG or multi-owner approval UI. Host tool availability is not automatic inbox/wake availability. Young public repository; cryptographic and operational claims need validation. |
| [A2A and Python SDK](https://github.com/a2aproject/a2a-python) | Apache-2.0; protocol plus client/server SDKs | Agent Cards, remote tasks, status and artifacts, streaming/push interaction; current Python SDK supports protocol 1.0 and 0.3 compatibility across JSON-RPC, HTTP+JSON and gRPC; SQL task stores | Best-fit standard-facing boundary for independent remote runtimes. An interoperable task protocol does not decide whether a particular owner consented or whether an artifact may be shared. Build a verified identity/grant mapping at the boundary. |
| [GitHub Squad](https://github.com/github/squad) | MIT; repo-native team state and client projections | Persistent named specialists, routing, decisions/history, task coordination, Copilot execution, projections into Claude Code, Codex, OpenCode and other hosts | Useful patterns for readable team state and coding-agent adapters. Multi-client support is not proof of independently governed multi-owner federation. Default-branch 2.0 features need preview/stable distinction. Do not copy its suggested unrestricted execution defaults. |
| [Agent Squad](https://github.com/2FastLabs/agent-squad) | Apache-2.0; Python/TypeScript routing and supervisor framework, Swift runtime | Intent routing, conversation storage, provider-specific agents, parallel supervisor delegation and agents-as-tools | Good narrow reference for routing and conversational handoffs. A classifier plus shared context is not a durable multi-owner project-management system. Current home is 2FastLabs, formerly awslabs. |
| [Temporal Python SDK](https://github.com/temporalio/sdk-python) | MIT SDK; durable workflow engine integration | Long-running workflows, timers, signals, updates, retries, cancellation, child workflows, replay and worker recovery | Consider when crash recovery and multi-day coordination outgrow a local ledger. It is infrastructure, not an agent framework or owner-consent system. Workflow determinism and activity idempotency remain application obligations; the workflow sandbox is not a security sandbox. |

Sources: the linked repositories, their current README capability descriptions and licence files. Detailed code evidence and constraints follow.

## A4A: useful transport, not a complete control plane

A4A provides more than a bare chat pipe: it has owner-to-agent delegation, revocation, connection requests, task events, acknowledgements, agreement events, trust assertions and encrypted attachments. Its model is genuinely relevant to agents representing different people. It is independent of A2A, not an A2A extension. [Protocol and implementation overview](https://github.com/a4a-network/a4a/blob/main/README.md).

Concrete reuse candidates:

- [SDK outbox journal](https://github.com/a4a-network/a4a/blob/6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e/sdk-python/a4a/outbox.py): persistent encrypted envelopes and distinct sending, acknowledged, dead-letter, publish-failed and interrupted states.
- [Encrypted file references](https://github.com/a4a-network/a4a/blob/6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e/sdk-python/a4a/files.py): per-file encryption, signed hash references and explicit separation of parsing/encryption from network I/O.
- [Delegation implementation](https://github.com/a4a-network/a4a/blob/6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e/sdk-python/a4a/delegation.py) and [interoperability vectors](https://github.com/a4a-network/a4a/tree/6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e/interop): candidates for compatibility tests and mandate handling.
- [Safe-connect guidance](https://github.com/a4a-network/a4a/blob/main/docs/onboarding/safe-connect.md): useful separation between installing MCP tools and separately authorizing/validating automatic reception.

Important boundaries:

- At-least-once delivery and a “processed” receipt do not prove a business action occurred exactly once or met acceptance criteria.
- Relays do not automatically federate/replicate. The SDK writes to configured relays; revocation must reach the relevant relays.
- Message encryption does not hide every metadata field. Recipient routing information remains visible.
- File references do not themselves upload a blob or verify the bytes at a remote URL. Assistant Central still needs explicit artifact storage, retention, access, scanning and recipient authorization.
- The file code explicitly notes that compromised recipient keys can decrypt archived references and recover file keys: do not advertise forward secrecy.
- Keys stored on disk and host reception privileges require a threat model beyond a signed message.
- Review/reputation scores are advisory and not a substitute for real identity, policy or authorization.

These constraints are acknowledged by upstream, not speculative accusations. [Security limitations](https://github.com/a4a-network/a4a/blob/main/README.md#security--limitations), [file implementation](https://github.com/a4a-network/a4a/blob/main/sdk-python/a4a/files.py).

Public GitHub metadata showed repository creation on 21 October 2026, 3 stars and no GitHub Releases at this snapshot. That measures the public repository, not the age of all underlying development. Treat it as a promising young dependency, pin commits, retain interoperability tests, and avoid implying broad production validation.

## DSH Squad: the most relevant reference model

Use the specific project [zhouCode/dsh-squad](https://github.com/zhouCode/dsh-squad), not a similarly named local fleet manager.

Its central principle is that the sender submits goals, context, acceptance conditions and attachment references while the recipient retains actual execution authority. Relay stores signed messages and a signed directory, but does not hold everyone's private sessions or credentials. Team planning produces drafts that are reviewed before dispatch; dispatch authorization does not grant the recipient permission to execute.

The current design also distinguishes:

- human-gated tasks;
- agent-assisted tasks with local human judgment or final review;
- autonomous tasks only when receiver policy allows them;
- sender-visible public outcomes versus private local HumanTodo/session details;
- queued, relay-persisted and recipient-received delivery;
- interrupted execution with unknown side effects versus safe-to-retry delivery.

[English README and design](https://github.com/zhouCode/dsh-squad/blob/main/README.en.md).

Best source locations to study or selectively port under MIT:

| Source | Reuse opportunity |
|---|---|
| [contracts.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/shared/contracts.ts) | Versioned, validated delegation and outcome envelopes |
| [state.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/shared/state.ts) | Explicit allowed transitions; terminal status handling |
| [automation.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/shared/automation.ts) | Receiver-defined rules and minimum-of-limits composition |
| [native-executor.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/host/native-executor.ts) | Local runtime boundary; explicit structured outcomes; untrusted remote task framing |
| [database.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/host/database.ts) | Durable local state, inbox/outbox and task records |
| [team-plan.ts](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/shared/team-plan.ts) | Draft-review-dispatch model with stable task identities |
| [host tests](https://github.com/zhouCode/dsh-squad/tree/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/packages/plugin/src/host) and [smoke test](https://github.com/zhouCode/dsh-squad/blob/4855be3a5f03f9144f86a7c9e8dfdd1c085a47f5/scripts/smoke-delegation.mjs) | Offline delivery, restarts, receipts, plan approval and local/private projection acceptance scenarios |

Cautions: it is bound to DeepSeek Harness APIs and an exact compatibility range. Direct mode supplies no NAT traversal or distributed store-and-forward. Its relay is a trusted plaintext intermediary, not E2EE. Pattern matching on an objective is not itself a security boundary; enforced tool/resource limits matter. The v0.9.2 release is dated 17 September 2026, with only 2 GitHub stars at this snapshot. That supports “small and specialized,” not “production proven.”

## Python execution and durability shortlist

### LangGraph

The attraction is explicit state transitions and persistent interrupts, not a claim of superior agent intelligence. It can run without LangChain. The checkpoint packages contain SQLite and PostgreSQL implementations and dedicated conformance tests. [Checkpoint source](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint), [PostgreSQL implementation](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres), [conformance suite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-conformance).

Use a real persistent checkpointer for restart survival; an in-memory saver loses state when the process ends. A checkpoint does not make external side effects exactly-once. Isolate irreversible actions, bind approvals to their exact parameters, and make retries idempotent or require reconciliation. [Persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence), [interrupt documentation](https://docs.langchain.com/oss/python/langgraph/interrupts).

### Pydantic AI

Especially attractive if Assistant Central needs a compact Python runtime adapter with typed input/output contracts and provider switching. The implementation exposes [ApprovalRequiredToolset](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/toolsets/approval_required.py), and the current documentation describes subagents, programmatic handoffs and graph control. [Multi-agent patterns](https://github.com/pydantic/pydantic-ai/blob/main/docs/multi-agent-applications.md).

Distinguish persisted conversation/step snapshots from durable replay. Its durable integrations wrap model/tool calls using an explicit engine and document engine-specific coverage. Do not attach multiple durability engines to the same agent. [Durable execution](https://github.com/pydantic/pydantic-ai/blob/main/docs/durable_execution/overview.md).

### OpenAI Agents SDK

Good lightweight alternative when existing integrations already use it. Human-in-the-loop interruptions can propagate from nested agents and paused runs can be serialized. However, local shell and patch approval is opt-in; the documentation also warns that persistent approvals for these tool types may match across agents sharing the same approval state. Assistant Central should use per-call decisions or fresh permission-scoped contexts, not share a global “always approve” wrapper across owners. [Exact approval semantics](https://github.com/openai/openai-agents-python/blob/main/docs/human_in_the_loop.md).

### Microsoft Agent Framework

Its current README and releases support serious consideration for Python/.NET graph orchestration, checkpoints and A2A hosting. Compare it against LangGraph using the same offline/approval/restart scenario rather than choosing based on vendor branding. [Workflow samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows), [hosting samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting).

### Agno / AgentOS

Agno deserves a separate build-versus-adopt evaluation because its current source goes beyond orchestration into a platform: [authorization implementation](https://github.com/agno-agi/agno/tree/main/libs/agno/agno/os/authz), [approval routes](https://github.com/agno-agi/agno/tree/main/libs/agno/agno/os/routers/approvals), [job queue](https://github.com/agno-agi/agno/blob/main/libs/agno/agno/os/job_queue.py) and [company project/task routes](https://github.com/agno-agi/agno/tree/main/libs/agno/agno/os/routers/company). If the first product is a centrally administered team service rather than a federation of independently owned devices, this could save substantial platform work.

Authentication and authorization must be configured deliberately. Its documentation distinguishes JWT identity from scope enforcement, shared security-key access and no-auth mode; setting JWT variables alone is not equivalent to enabling scope checks. Test REST, MCP, A2A and channel interfaces separately. [Security documentation](https://docs.agno.com/agent-os/security/overview). The public repository was active on 8 November 2026. Do not assume the externally hosted AgentOS UI has identical terms or deployment properties to the Apache-licensed source.

## A2A, ACP and MCP: avoid protocol confusion

[A2A](https://github.com/a2aproject/A2A) is the standards-oriented boundary for remote opaque agent systems. The current [Python SDK](https://github.com/a2aproject/a2a-python) supports protocol 1.0 with 0.3 compatibility and three transports. Its [database task store](https://github.com/a2aproject/a2a-python/blob/main/src/a2a/server/tasks/database_task_store.py) stores task state, artifacts and history with an owner resolver. That is reusable infrastructure, but “owner” must be resolved from authenticated, verified context in Assistant Central, not accepted from a caller-supplied string.

[Agent Client Protocol](https://github.com/agentclientprotocol/agent-client-protocol) is Apache-2.0 and standardizes code-editor/agent communication. It is useful for a local coding-agent adapter, not a substitute for cross-owner collaboration governance. Negotiate the wire protocol version; schema package versions are separate.

The older [IBM/BeeAI Agent Communication Protocol](https://github.com/i-am-bee/acp) uses the same ACP acronym but is a different project. Its repository is archived and announces incorporation into A2A. Do not begin a second independent protocol integration from an outdated ACP comparison.

MCP is the tool/data integration boundary. Exposing delegation as an MCP tool can be useful, but tool access does not establish permission to contact another owner, persist credentials, wake an agent automatically, or execute a delegated task.

## Other projects worth knowing, but not default foundations

- **[Mastra](https://github.com/mastra-ai/mastra):** a strong TypeScript alternative with provider routing, graph workflows, stored suspend/resume, memory, MCP, evaluations and observability. Less natural as the replacement core for an existing Python application, but useful as an external runtime adapter. The core is Apache-2.0 while any `ee/` directory has a separate enterprise licence, including auth and editor-related areas. It is not uniformly Apache-2.0. [Licence mapping](https://github.com/mastra-ai/mastra/blob/main/LICENSE.md).
- **[AutoGen](https://github.com/microsoft/autogen):** valuable historical message-passing and multi-agent patterns. Current README directs new users to Microsoft Agent Framework and contains maintenance/archival language. GitHub API still reports the repository as not archived, so report this as a maintenance transition rather than claiming the archive flag is set. Code is MIT; documentation is CC-BY-4.0. [Code licence](https://github.com/microsoft/autogen/blob/main/LICENSE-CODE).
- **[Claude Squad](https://github.com/smtg-ai/claude-squad):** useful Go/TUI local-session manager using tmux and git worktrees for multiple coding agents. It is **AGPL-3.0**, not MIT. Local workspace parallelism is not multi-owner federation. Use as an independent optional tool or study the concepts; do not copy it into a permissive core without a deliberate copyleft strategy. [Licence](https://github.com/smtg-ai/claude-squad/blob/main/LICENSE.md).
- **[lobs-ai/squad](https://github.com/lobs-ai/squad):** MIT gateway-centric TypeScript platform with shared task lists, subagent sessions, channel-rendered questions and approval rules. Interesting protocol/UI ideas, but its README explicitly lists multi-user, plugin sandboxing and an isolated exec backend as not shipped. Repository last push was June 2026 despite the README's “actively developed” wording.
- **[Langflow](https://github.com/langflow-ai/langflow):** MIT visual Python workflow authoring, API/MCP exposure and integrations. A useful optional builder or UI reference, not proof of independent-owner security boundaries. Avoid importing a full visual platform merely to obtain a task dashboard.
- **[Dify](https://github.com/langgenius/dify):** broad product platform, but its **modified Apache licence** restricts multi-tenant operation without written authorization and removal of frontend branding. That is particularly material for Assistant Central. Do not label it ordinary Apache-2.0 or assume a permissive fork is allowed. [Actual licence](https://github.com/langgenius/dify/blob/main/LICENSE).
- **[Flowise](https://github.com/FlowiseAI/Flowise):** now archived. Its licence is Apache-2.0 for much of the code but excludes enterprise directories and certain explicitly marked files under commercial terms. Avoid selecting it from stale “top frameworks” lists. [README](https://github.com/FlowiseAI/Flowise/blob/main/README.md), [licence](https://github.com/FlowiseAI/Flowise/blob/main/LICENSE.md).

## Maintenance snapshot

Observed release samples, not a guarantee that every default-branch feature is included:

| Project | Recent release observed |
|---|---|
| LangGraph | [1.2.20, 5 November 2026](https://github.com/langchain-ai/langgraph/releases/tag/1.2.20); SDK/CLI have separate release streams |
| Pydantic AI | [v2.66.0, 4 November 2026](https://github.com/pydantic/pydantic-ai/releases/tag/v2.66.0); v1 maintenance release also present |
| Microsoft Agent Framework | [python-1.25.0, 7 November 2026](https://github.com/microsoft/agent-framework/releases/tag/python-1.25.0) |
| CrewAI | [1.15.37, 7 November 2026](https://github.com/crewAIInc/crewAI/releases/tag/1.15.37) |
| Google ADK | [v2.14.0, 7 November 2026](https://github.com/google/adk-python/releases/tag/v2.14.0) |
| OpenAI Agents SDK | [v0.24.0, 15 October 2026](https://github.com/openai/openai-agents-python/releases/tag/v0.24.0); newer alpha builds also present |
| A2A Python | [v1.3.0, 27 October 2026](https://github.com/a2aproject/a2a-python/releases/tag/v1.3.0) |
| DSH Squad | [v0.9.2, 17 September 2026](https://github.com/zhouCode/dsh-squad/releases/tag/v0.9.2) |
| GitHub Squad | [v2.0.0-preview.3, 1 November 2026](https://github.com/github/squad/releases/tag/v2.0.0-preview.3), explicitly prerelease |
| Agent Squad | [python_1.1.4, 23 September 2026](https://github.com/2FastLabs/agent-squad/releases/tag/python_1.1.4) |
| Claude Squad | [v1.0.20, 20 August 2026](https://github.com/smtg-ai/claude-squad/releases/tag/v1.0.20) |
| A4A | [No GitHub Releases listed](https://github.com/a4a-network/a4a/releases); README identifies protocol v0.4 and published Python packages |

LangGraph, Pydantic AI, Microsoft Agent Framework, CrewAI, Google ADK and Agents SDK all had repository pushes on 8 November 2026. Fresh activity is encouraging, but increases the importance of pinned versions and compatibility tests.

## Licence compatibility and reuse rules

This is an engineering due-diligence summary, not a legal opinion.

- **MIT:** generally suitable for a permissive or proprietary core, but preserve copyright and licence text in copies or substantial portions. A rewrite that incorporates substantial source is not a way to erase attribution.
- **Apache-2.0:** generally compatible with a permissive/commercial product; preserve the licence, relevant notices and notices of modifications. Its patent provisions and NOTICE obligations matter. Do not relabel upstream files as solely MIT.
- **GPL:** distribution of a combined derivative work can trigger source and copyleft obligations. Version matters; Apache-2.0 compatibility with GPLv3 does not imply compatibility with GPLv2-only.
- **AGPL:** adds source-offer obligations for users interacting with a modified covered program over a network. A process boundary is not an automatic legal escape. Decide on a copyleft-compatible distribution model or use an independently implemented adapter after review.
- **LGPL:** assess the actual library, linking/packaging and users' replacement/debugging rights. “It is a sidecar” does not by itself settle compliance.
- **Modified Apache / commercial exceptions:** read the actual file and relevant directory licences; GitHub's badge or popularity is insufficient.

Primary licence references: [Apache-2.0 terms](https://www.apache.org/licenses/LICENSE-2.0), [Apache/GPL version compatibility](https://www.apache.org/licenses/GPL-compatibility.html), and [AGPL section 13 in Claude Squad's distributed licence](https://github.com/smtg-ai/claude-squad/blob/main/LICENSE.md#13-remote-network-interaction-use-with-the-gnu-general-public-license).

A4A deserves an explicit check because Assistant Central already adapts it. A4A's original code is MIT, but [THIRD_PARTY_LICENSES.md](https://github.com/a4a-network/a4a/blob/main/THIRD_PARTY_LICENSES.md) describes separately licensed test fixtures, optional notary dependencies such as OpenTimestamps and python-bitcoinlib under LGPL-3.0-or-later, and GPL-covered components included in some container distributions. Copying selected SDK code is a different distribution from shipping all images or the optional notary. Audit the exact bytes shipped.

Before publishing a release:

1. Record each copied component, upstream repository, immutable commit, original path and local path.
2. Keep the relevant upstream copyright/licence text and modification notice.
3. Separate Assistant Central's own chosen licence from third-party components.
4. Generate an SBOM for actual release wheels/binaries/images, not merely the source checkout.
5. Review transitive dependencies, native binaries, test fixtures and container layers.
6. Keep optional copyleft or commercially restricted components out of the default bundle until deliberately reviewed.

## What Assistant Central still needs to own

The reviewed sources did not establish that any one project supplies all of the following, together, for arbitrary agents belonging to different people:

1. **Identity and membership:** separate human owner, agent identity, runtime identity and organization role; verified key binding; revoke membership without deleting audit history.
2. **Capability grants:** receiver-owned scope for tools, destinations, data categories, workspace boundaries, budgets, duration and maximum delegation depth.
3. **Approval receipts:** bind approval to the owner, agent, task version, exact action parameters, target, data scope and expiry. Prevent replay after task revision or owner change.
4. **Durable task ledger:** separate delivery state from execution state, result publication and requester acceptance. A delivered message is not a completed task.
5. **Safe retry semantics:** stable idempotency keys, leases, deduplication, bounded retries and a distinct “side effect outcome unknown” state.
6. **Artifact governance:** content hash, producer, task/version, recipient access, classification, retention, scan status and immutable revisions; publish selected artifacts rather than entire private sessions.
7. **Coordination:** dependencies, blocking questions, review gates, cancellation propagation, reassignment and conflict handling.
8. **Observability and cost:** shared trace/task IDs while private traces remain local; provider-specific usage normalized with provenance; per-owner budgets and spending policy.
9. **Human UX:** clear indication of who must act next; separate draft, dispatch, accept, execute, publish and approve steps; mobile-friendly review and rejection reasons.
10. **Conformance:** one cross-provider test suite so an adapter cannot silently bypass authorization or misreport completion.

A4A and DSH Squad already address parts of this list; the gap is the complete provider-neutral, consistently enforced product.

## Proposed implementation sequence

### Phase 1: make the existing prototype's boundaries explicit

Define stable Python contracts for Owner, AgentEndpoint, Task, Delegation, Approval, ArtifactManifest and AuditEvent. Put transport and runtime behind separate interfaces. Preserve A4A-specific fields in adapter metadata rather than forcing every task to be an A4A agreement.

Create a registry that advertises verified capabilities, supported interaction modes and protocol versions. A sender may request a mode, but only the receiving owner can grant it.

Keep credentials and raw private transcripts local. Expose only a public task projection, explicit progress and approved artifacts. Record uncertainty rather than automatically re-executing an interrupted external action.

### Phase 2: prove real cross-provider execution

Use two actual runtimes owned/configured separately, for example a Python runtime adapter and a local coding-agent adapter. Support submit, status, cancel, resume-after-approval and artifact publication. Use A2A at the remote boundary and retain A4A as an encrypted transport option.

Do not claim “cross-provider” based only on changing a model name in one process. Demonstrate different processes, separate credential stores, independent approvals and a restart/offline scenario.

### Phase 3: add durable coordination and reviewed team plans

Evaluate LangGraph against a minimal existing ledger implementation using the same tests. Adopt it if checkpoints, branching and interrupts reduce code without weakening boundaries. Evaluate Microsoft Agent Framework as the alternative when .NET/enterprise integrations are a requirement.

Use Temporal only when the operational requirements justify another service and its replay discipline. Keep durable workflow state distinct from private runtime conversation history.

### Phase 4: governance, interoperability and release hardening

Add expiring grants, membership revocation, replay protection, artifact ACLs and retention. Add provider/protocol conformance tests, load tests, audit export and release SBOMs. Pin framework versions and verify upgrade/recovery behaviour.

## Proof-of-concept acceptance tests

Before calling any combination “best for Assistant Central,” require the same scenario from every shortlisted stack:

- Owner A delegates to Owner B without receiving B's API keys or workspace access.
- B is offline; the task survives sender/relay restart and arrives once.
- Duplicate delivery and a replayed approval cannot cause duplicate action.
- B rejects or edits a task; original and revised versions remain auditable.
- B approves one exact tool call; that approval cannot authorize A, another tool, another destination or a later revision.
- A malicious task description or attachment cannot elevate tool permissions or extract secrets.
- A long-running task pauses for human input and resumes after process restart.
- A canceled or revoked task does not silently resume with stale authority.
- A crash after a side effect but before acknowledgement produces reconciliation, not blind retry.
- An artifact's bytes, access and provenance can be verified; private session data does not appear in the shared outcome.
- Two providers produce normalized status, usage and failure events.
- A requester can separately accept, reject or request revision of a completed result.

Measure end-to-end completion reliability, duplicate side effects, recovery time, approval correctness, adapter code size, cost and latency. Do not rank by star count or marketing benchmarks alone.

