# Verification and activation limits

## Reproduce the bounded checks

From the repository root, with official Node 24:

```sh
npm ci --prefix agent_bridge --ignore-scripts --no-audit --no-fund
npm --prefix agent_bridge run check
npm --prefix agent_bridge test
npm audit --prefix agent_bridge --omit=dev --audit-level=moderate
```

The test runner starts with a fresh HOME and an allowlisted environment, not the
operator's credentials or telemetry configuration. OpenAI tracing and OTEL are
disabled. An outbound-network tripwire is installed before SDK imports, including
stdio children. It is a diagnostic assertion, not an OS security sandbox. The
separate workflow additionally runs all tests in an unprivileged, read-only,
capability-free Docker container with `--network none`, a private temporary
filesystem, no secret environment, and no Docker socket. The actual SDK host's
local listener needs no published port. The workflow verifies container exit and
network mode; hosted success must be checked for the exact published head.

The unit/transport suite covers strict schemas, five independent identity-scope
axes, forbidden fields, inert malicious text, content encryption canaries, exact
retry across stores/processes, conflicting retries, abandoned output recovery,
revocation across open instances, expiry at the final mutation boundary, observed
clock rollback, schema/key mismatch, corruption, quotas, malformed UTF-8/JSON,
duplicate members, frame/request bounds, handshake sequencing and redacted errors.
The independent review's malformed-initialisation regression is retained.

No provider credentials, login, paid calls, existing personal assistant, real
human data, remote peer, public endpoint or account permission has been used.
The fictional keys are generated per fixture and removed with the temporary
stores. They are not deployment keys. The two hosts prove their respective tool
execution paths, not human consent or cross-agent message exchange.

## Dependencies and provenance

Direct runtime pins: MCP SDK 1.32.2, Zod 4.6.7. Host test pins: OpenAI Agents
0.21.0 and Cursor/Grok Agent SDK 0.6.0. TypeScript 5.9.3 and Node types 24.12.0
are development-only. `package-lock.json` records exact transitive versions,
registry tarball URLs and integrity hashes; installation disables lifecycle
scripts. Packages came from the official npm registry, and the host package names
were checked against their vendors' documentation. No vendor source is copied
into this repository.

The runtime-only npm audit reported **zero** advisories on 10 November 2026.
The complete development/host-fixture closure still reported **15 moderate**
advisories, from the current Grok package's OpenTelemetry/minimatch closure.
There were no high/critical advisories after updating MCP/Zod and compatible
transitives. This is not a clean audit of the entire host stack. Telemetry/export
paths are disabled and external network is blocked in acceptance, but this does
not prove every advisory unreachable. No unsupported major dependency overrides
were imposed. Resolve/review those advisories before deploying that host stack.
An audit snapshot is time-sensitive and is not a security certification.

## Personal assistant support matrix

- **OpenAI Agents SDK:** tested application-defined host. Existing dot/ChatGPT
  session control is not established. ChatGPT's separate
  [plugin MCP server route](https://developers.openai.com/plugins/build/mcp-server)
  would need a separately reviewed authenticated remote endpoint; this stdio
  adapter does not itself provide that endpoint.
- **Cursor/Grok Agent SDK:** tested documented deterministic host tool path.
  SDK session creation/resumption and live model turns remain untested.
- **Personal Grok Bot:** official
  [overview](https://docs.x.ai/grok-bot/overview) supports custom MCP/API tooling.
  [Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
  documents owner-configured authenticated webhook starts. A successful HTTP 200
  acknowledges a start, not completion, delivery to a peer, result acceptance or
  Central owner consent. No routine, token, custom tool or webhook was created or
  called here. Existing-instance identity, binding and correlated result retrieval
  must be proved with the owner's selected instance before activation.
- **Claude Duet:** [official onboarding](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet)
  documents a personal assistant and plugins. A public API to operate an existing
  Duet instance is not established by this work. Claude model/MCP APIs or the
  Claude Agent SDK are separate products and are not relabelled as Duet.

## Activation checklist: all live items remain pending

1. Select the actual host product/build and owner-controlled instance. Verify its
   supported tool route, identity source, account rights and retention settings.
2. Authenticate the owner outside the model. Bind the exact host session and
   stable conversation, fixed intended recipient and short expiry. Never use a
   model-selected identity, continuation string, ClientInfo or message claim.
3. Provision secure key storage, backup/rotation policy and private directory
   ownership. Environment launch configuration is only a local trusted-host
   mechanism, not a remote authentication scheme. Same-user process access,
   hostile database modification, rollback/restored copies and key theft remain
   outside this proof.
4. Integrate `inspectForOwner` with the actual owner review surface and exact
   existing authority gates. Render draft text inertly. Require explicit owner
   decisions before any source disclosure, execution, send, acceptance or release.
5. Independently test native host approval, denial, restart, expiry, cancellation,
   logging, result correlation and revocation with disposable identities. Do not
   treat a provider acknowledgement as a completed result.
6. For personal Grok Bot or another remote host, separately design authenticated
   HTTP MCP/wake delivery, replay resistance, scoped credentials, bounded request
   processing and result correlation. Obtain the required owner approvals before
   creating credentials, granting persistent access or sending live messages.
7. Resolve the host-fixture dependency advisories, review exact final CI and
   complete independent integration/security review before deployment.

## Persistent conversations are a separate capability

`conversationId` is already host-bound and stable, but the task draft queue is
not a conversation log, machine-message thread, orchestration bus or group inbox.
There are no conversation/history tools, member changes, range grants or implicit
history exports in this PR. A new session or member does not inherit old drafts.

The separate conversation ledger must supply authenticated member/epoch bindings
and explicit history-range grants. A future context adapter must pin those
outside tool arguments, check revocation for each bounded retrieval, preserve
message provenance and treat retrieved messages as untrusted data. A join must
not expose earlier messages automatically. Recontextualisation, conversation
history access, task approval and result release remain different permissions.
No compatibility with that unfinished ledger is claimed by these checks.
