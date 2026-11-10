# Roadmap

## Current position

Checked 10 November 2026. Verified main is `578a665`, tree
`e2ee8b174fce4f5566f38818ef669775583a1432`. The cumulative PR24 product merge
passed all eight hosted workflows, including actual separate-owner and combined
workspace Chromium, container isolation and distinct-network TLS acceptance.

Main combines the authenticated encrypted local pilot, transfer controls, Central
workspace, official SDK draft bridge, durable local conversations, owner controls,
shared-proposal approvals, exact message-outcome recovery and inert disclosure
review preparation. The pinned research archive is also merged. This is a tested
local pilot, not a deployed service or a proven connection to existing personal
assistants. Separate visual work and the functional/live gates below remain.

See the [delivery guide](docs/DELIVERY.md) for exact status, evidence and setup,
and the [decision record](docs/DECISIONS.md) for choices and alternatives.

## What the building blocks establish

- The [team](team/README.md), [execution ledger](execution/README.md) and
  [offline binding](integration/README.md) exercise bounded work, retained result
  correlation and separate release/recipient decisions. Their scripted fictional
  approvals are not real owners' consent. The
  [provider-disclosure rehearsal](execution/PROVIDER_DISCLOSURE.md) is synthetic.
- The [pilot](pilot/README.md) has real local password sessions, private identity
  vaults, pinned signed/encrypted packets and separate runtime stores. A password
  identifies a local account, not a verified human. Its
  [reviewed work loop](pilot/WORKFLOW.md) produces a fixed fixture, not model output.
- [File exchange](pilot/FILE_EXCHANGE.md), [HTTPS quarantine](pilot/HTTPS_MAILBOX.md)
  and [explicit send/import](pilot/HTTPS_EXCHANGE.md) preserve exact retained
  packets and uncertainty. A transport acknowledgement is not recipient consent.
- [Payload encryption](pilot/STORAGE.md) protects content columns, not metadata,
  a hostile running host or restored backups. Existing plaintext stores need an
  explicit stopped-service migration; replacement does not securely erase copies.
- The local [conversation ledger](conversation/README.md) has encrypted durable
  history, future-only joins, exact original-author history grants and transitive
  declared-source checks. One trusted coordinator can see authorised plaintext;
  this is not distributed end-to-end encryption.
- [Owner controls](workspace_ui/CONVERSATIONS.md) combine separate local sessions
  with conservative interruption handling. Exact message inspection can establish
  that an original signed message is retained locally; absence is inconclusive.
- [Shared proposals](conversation/PROPOSALS.md) require every frozen member to
  approve the exact revision. Discussion agreement grants no execution, payment,
  legal or provider-disclosure authority. This primitive has no proposal UI yet.
- The [disclosure compiler](conversation/DISCLOSURE_REVIEW.md) prepares and
  reinspects bounded, exact fictional request reviews from complete declared
  ancestry. It signs nothing, consumes no grants and has no provider/server/UI
  integration. [Signed source grants](pilot/SOURCE_GRANTS.md) remain standalone.
- The [official SDK bridge](agent_bridge/README.md) exposes only inert draft
  creation and scoped status. [Owner draft review](agent_bridge/OWNER_REVIEW.md)
  permits inspection/dismissal within the original lease, not sending or execution.

## Ordered delivery dependencies

1. **Preserve the accepted baseline while integrating visual work.** Compose
   the remaining design branch with current main, retaining transfer/conversation
   behaviour and exact owner decisions. Require fresh applicable hosted, Chromium,
   container and network acceptance for the resulting revision. The accepted
   baseline is not evidence for later changes.
2. **Complete owner-facing review.** Build exact shared-proposal and disclosure
   review controls on the reviewed primitives, preserving separate sessions,
   unchanged rosters, source visibility and the executor's distinct decision.
   Resolve uncertain membership/grant/proposal operations without automatic replay.
   An inspection screen must never silently grant history access.
3. **Connect supported assistant sessions deliberately.** Prove durable inboxes,
   cursors, body-free wake hints, restart/reconnect and original-result correlation.
   Map host identities outside model input. The SDK fixtures do not prove access
   to a person's existing dot, Duet, GrokBot or other personal assistant.
4. **Design atomic source authority and dispatch.** Bind every required source
   owner's and executor's exact approval to the final request and destination.
   Integrate grant consumption with the irreversible dispatch/uncertainty fence;
   standalone consumption is not bearer permission for a later provider call.
   Keep source evidence distinct from selected provider input.
5. **Prove two independently controlled owners and hosts.** Start with synthetic
   input, independent fingerprint checks, rejection/cancellation, restart and
   uncertain delivery. Container namespaces on one trusted host are supporting
   evidence, not this acceptance. Define hosting, certificate and revocation
   operations before exposing any service beyond loopback.
6. **Approve and verify live operation separately.** Obtain the precise account,
   credential, data-audience, cost and deployment decisions before activating a
   provider or personal assistant. Exercise the approved route with synthetic
   input before real data. Review recovery/rotation, retention/deletion, backups,
   metadata exposure, incident response and external security findings.
7. **Measure before scaling.** Establish realistic workload, reliability and
   failure evidence. Python remains the current orchestration language; evaluate
   Rust only for a measured boundary or bottleneck with clear interoperability
   and maintenance benefits. Memory safety does not replace owner authority.

The first live network milestone is a two-person pilot in which each person
controls their assistant, reviews one exact task and return artifact, and can
inspect decisions and recovery history. It has not been demonstrated yet.

## Research and reuse

The [landscape review](docs/research/orchestration-landscape.md) compares orchestration,
workflow and messaging candidates. The separate
[pinned research archive](https://github.com/EmotiveImpact/Assistant-Central/pull/21)
adds sixteen inert source snapshots and Parley findings. These are design inputs,
not selected dependencies or tested integrations. Preserve licences and review
reuse obligations before copying code. Parley's private brief/shared floor/review
patterns are useful without adopting bearer-room authority or automatic disclosure.

Acoustic transfer remains optional research, not a faster assistant language or
Bluetooth. It is off the critical path and cannot replace authentication,
encryption, replay protection or explicit owner intent.
