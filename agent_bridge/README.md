# Scoped assistant-host bridge

A new, isolated MCP boundary for **inert task drafts**, with executable conformance
checks using two official agent-host SDKs. It does not activate a personal
assistant, route work to a peer, or replace the pilot's owner controls.

## What is actually integrated

| Host | Pinned package | Executed proof | Not proved |
| --- | --- | --- | --- |
| OpenAI Agents | `@openai/agents` 0.21.0 | Real `Agent` and `Runner`, tool discovery, model-selected tool dispatch and result feedback through a real MCP stdio child. Only model responses are deterministic doubles. | Live model, existing ChatGPT/dot, paid calls or personal-account access. |
| Cursor/Grok Agent SDK | `@grok/agent-sdk` 0.6.0 | Real `serve` host and documented `handle.callTool` dispatch of advertised MCP tools, through a real MCP stdio child. No model turn is requested. | Existing Grok Bot, a Cursor model turn, persisted Cursor conversation or account access. |

These are actual host SDK executions, not two raw model APIs or two renamed MCP
clients. Both use fictional, separately provisioned identities and separate
stores. They do **not** exchange a message with each other. The second proof is a
supported deterministic host execution path, not evidence of model reasoning.

Official documentation, checked 10 November 2026:

- [OpenAI Agents MCP](https://openai.github.io/openai-agents-js/guides/mcp/)
- [Cursor Agent SDK overview](https://cursor.com/docs/agent-sdk)
- [Cursor MCP connections and trusted per-session identity](https://cursor.com/docs/agent-sdk/reference/connections)
- [Cursor direct host tool calls](https://cursor.com/docs/agent-sdk/reference/tools)
- [Cursor session/HTTP API](https://cursor.com/docs/agent-sdk/reference/http-api)

The Cursor documentation identifies `@grok/agent-sdk` as its official package.
The package's own 0.6.0 declarations and bundled Markdown documentation were also
inspected. No private application internals or reverse-engineered account route
is used. Google ADK was investigated as a fallback and is not a dependency.

## The boundary

Exactly two model-facing tools exist:

- `create_task_draft({requestId, title, instruction})` stores an inert draft.
- `task_draft_status({draftId})` returns only a known draft's fixed status in the
  exact bound scope. It cannot enumerate drafts, return their contents or read
  another scope.

Both return an opaque draft identifier and the explicit states
`awaiting_owner_review` (or `dismissed` after an explicit owner decision),
`ownerConsent: not_requested`,
`transportReceipt: none`, `execution: not_started`. No tool grants, accepts,
sends, retries transport, executes, activates a provider, releases a result,
enrols a peer or changes permissions. No owner runtime or broad dispatch callback
is reachable. A host SDK's own tool permission is never Central owner consent.

The trusted embedding supplies and freezes this binding outside model input:

`ownerId, hostId, sessionId, conversationId, recipientId, expiresAt`

Identifiers are opaque ASCII letters/digits/underscore/hyphen, at most 64
characters. `recipientId` is a fixed intended routing label, **not** proof that a
peer exists or has enrolled. The host must authenticate the human and obtain the
identity/session/conversation mapping before provisioning. ClientInfo, model
output, MCP `_meta`, user text and tool arguments are not identity evidence.

In this implementation the trust channel is a local process spawned by the
trusted host, with a host-supplied environment configuration. There is no network
listener in the bridge, bearer token, OAuth flow or public identity endpoint.
The SDK test host opens an ephemeral loopback-only listener as part of its
actual `serve` implementation, with schedules/reminders disabled and no built-in
file/shell tools. This is not a deployed service.

## Trusted host composition

`src/server.ts:createBridge(store, binding)` binds the SDK server to a provisioned
scope. `src/stdio.ts` is the concrete bounded stdio entry point. Its
`AC_BRIDGE_LAUNCH` environment value is validated by `Launch`: an absolute private
store path, 32-byte root key in hex and the exact binding. The environment value
is removed from the server's environment after reading; memory erasure is not
guaranteed. No auto-provisioning, default owner or implicit new scope occurs.

`DraftStore.provision` and `revoke` are trusted host APIs, not tools. A duplicate
active provision with the identical binding is a no-op preserving counters and
history. Changed expiry is refused. Revocation of an unknown or mismatched
binding explicitly fails, rather than claiming a future fence. Known revocation
is terminal and repeatable. A new session is a new separately authorised scope.

`inspectForOwner(binding, draftId)` is a bounded, exact, host-only read returning
the encrypted draft's validated contents and inert status. The embedding must
authenticate that owner independently before calling it. Revoking agent access
does not erase the owner's retained review record. The content is still
untrusted text and must not be rendered as HTML or treated as instructions.

The workspace has an **optional, default-disabled authenticated owner queue**
for exact inspection and local dismissal only. See [owner review](OWNER_REVIEW.md)
for the private host configuration, real fingerprint binding and offline schema
upgrade requirements. The queue requires the original active host lease, at most
15 minutes; it is not a retained owner archive or automatic notification.
`awaiting_owner_review` remains an inert state, not consent or delivery. A future
proposal integration would still need independent source grants, recipient
acceptance, provider approval, release, transport receipt and result acceptance.

## Storage, replay and revocation

- Private owner-controlled directory (no group/other permissions), regular
  owner-controlled 0600 database, no final symlink or hardlink. POSIX/Node 24 only.
- SQLite format/key marker and exact known schema are verified; unknown formats,
  triggers and wrong keys fail closed. No migration or key rotation is automatic.
- Draft content is AES-256-GCM encrypted with a fresh 96-bit nonce and authenticated
  scope/draft linkage. HKDF-SHA256 separates encryption and HMAC keys. The root key
  is supplied by the trusted embedding and never persisted in this database.
- Owner/host/session/conversation/recipient bindings, request IDs and payload
  commitments persist only as keyed HMAC values. Opaque draft IDs, timestamps,
  expiry, counters and revocation flags remain visible. This is not whole-file
  encryption or protection against a hostile same-user process or database editor.
- Exact request ID/content retries recover the same draft after process restart;
  reuse with different contents fails. RPC IDs and durable request IDs are distinct.
- Each scope allows at most 32 drafts and 256 admitted operations, including
  unsuccessful lookups and retries. A database admits at most 64 scopes. There is
  no agent-facing quota reset, garbage collection, deletion or session renewal.
- A lease lasts at most 15 minutes. Expiry or an observed backwards clock fences
  the scope permanently. Time is checked again before the transaction completes;
  a late operation rolls back its draft and retains the fence.
- `BEGIN IMMEDIATE` serialises dispatch with committed revocation. No synchronous
  callback is pre-empted. A revocation ordered after a committed draft cannot make
  that draft never have existed. Lost output and cancellation are not proof of
  failure: inspect/retry the exact request only, never invent replacement work.

The bounded audit stores only `sequence, scope, action, outcome, observed_at`.
Actions are `create`, `status`, `reject`; outcomes are fixed codes. It covers
admitted operations, not a comprehensive human or OS security log. Unknown,
revoked, expired and exhausted scopes cannot grow it without bound. Host/library
logging and a model provider may still retain inputs if live use is later enabled.

## Protocol and resource profile

The runtime uses official `@modelcontextprotocol/sdk` 1.32.2 and Zod 4.6.7, with
an additional bounded LF stdio transport. The SDK handles MCP initialisation,
tool discovery/calls, ping and cancellation. The transport validates the initial
request and successful negotiated response before admitting `initialized` and
subsequent calls. Reinitialisation or reused RPC IDs terminate the connection.
The pinned SDK's legacy negotiation is used; there is no invented protocol or
claim of HTTP, SSE, modern extensions, tasks, sampling, roots or elicitation.

Input is limited to 16 KiB per frame, depth 16, 1,024 parsed nodes, 512 frames and
256 unique safe integer/string request IDs per connection. Duplicate JSON keys,
nonfinite numbers, invalid Unicode, batches and requests before handshake are
rejected before SDK dispatch. Output is capped at 32 KiB with bounded queued
writes. Partial frames have a five-second deadline and connections a two-minute
lifetime. These are deliberate local profile restrictions, not general MCP rules.
Timers do not pre-empt synchronous SQLite work; busy wait is limited to one second.
