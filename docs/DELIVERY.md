# Delivery status and acceptance gates

Checked 10 November 2026. **Assistant Central is a tested local pilot with reviewed
extensions, not a fully delivered or live platform.** No existing personal
assistant, live provider account or independently controlled multi-owner,
multi-host end-to-end service has been verified.

The intended product is durable direct/group conversations between people's
assistants, optional exact old-history sharing and bounded, auditable work across
supported hosts. The [decision record](DECISIONS.md) explains the choices and
remaining decisions. This snapshot must be updated after later integration.

## Main, published components and local candidate

**Main:** [`55b7df104b12f69336055ca9d5ba0d773d8b10a5`](https://github.com/EmotiveImpact/Assistant-Central/tree/55b7df104b12f69336055ca9d5ba0d773d8b10a5)
contains PRs #6–15. It has authenticated local owners, signed/encrypted peer
packets, separate recipient decisions, password maintenance, a synthetic work
loop, container isolation, file exchange, HTTPS quarantine/send/import, encrypted
application payloads and standalone exact source grants. The owner HTTP service
remains loopback-only. See the [pilot guide](../pilot/README.md),
[storage contract](../pilot/STORAGE.md) and [source grants](../pilot/SOURCE_GRANTS.md).
The shared-team and execution examples remain separate synthetic proofs.

**Published but unmerged:** these heads have scoped review. Older component
heads have hosted evidence; fresh acceptance is running for the newer cumulative
head. They are not features of main, and individual checks do not establish
acceptance of later changes.

| Component | Published head | Scope |
| --- | --- | --- |
| [#17 cached receipts](https://github.com/EmotiveImpact/Assistant-Central/pull/17) | `3905cbc` | Recover the original receipt; missing retained state fails closed. |
| [#16 owner transfers](https://github.com/EmotiveImpact/Assistant-Central/pull/16) | `002d4af` | Exact send/retry/import reviews; includes the #17 fix. |
| [#18 distinct-network acceptance](https://github.com/EmotiveImpact/Assistant-Central/pull/18) | `b3a96a5` | Actual four-container network/mount/PID separation and TLS 1.3 on one trusted Docker host. |
| [#20 official SDK bridge](https://github.com/EmotiveImpact/Assistant-Central/pull/20) | `0e0fb92` | OpenAI Agent/Runner with deterministic responses and Cursor/Grok SDK no-model tool invocation through real MCP. Inert draft/status only. |
| [#21 pinned research](https://github.com/EmotiveImpact/Assistant-Central/pull/21) | `8bb93f6` | Sixteen inert source archives and Parley findings; no upstream integration execution. |
| [#22 conversation ledger](https://github.com/EmotiveImpact/Assistant-Central/pull/22) | `8a02185` | Durable signed/encrypted local history, history grants and clock fencing. |
| [#23 composed workspace](https://github.com/EmotiveImpact/Assistant-Central/pull/23) | `96e841f` | Correct composition of #19's refined shell with #16's transfer controls. |
| [#25 host draft review](https://github.com/EmotiveImpact/Assistant-Central/pull/25) | `0b3417e` | Authenticated inspection/dismissal of inert host drafts, with lock-time expiry and exact-schema hardening. Fresh hosted checks pending. |
| [#27 shared proposals](https://github.com/EmotiveImpact/Assistant-Central/pull/27) | `63988d9` | Exact revisions and unanimous local-owner decisions. Included in the cumulative candidate. |
| [#24 cumulative owner workspace](https://github.com/EmotiveImpact/Assistant-Central/pull/24) | `2cbf0a0` | Reviewed product composition with all later source-expiry, operation and exact-message recovery fixes. Fresh hosted checks pending. |

Use #23's corrected composition rather than applying the original
[#19 interface](https://github.com/EmotiveImpact/Assistant-Central/pull/19) alone
after #16. Do not merge the older ledger/workspace intermediate heads alone:
they omit later source-expiry and recovery fixes. The cumulative #24 candidate
preserves the published dependency ancestry and includes those fixes together.

**Reviewed cumulative product candidate:** published commit
[`2cbf0a03cba372140491b18024d9725f999d1063`](https://github.com/EmotiveImpact/Assistant-Central/commit/2cbf0a03cba372140491b18024d9725f999d1063),
tree `1e86760db0e51d77f16e6b2914ee26e59eb74e55`, is byte-identical to locally
tested product revision `c267fa59db89d54a7ede015fdfdcd0f295247544`. It composes
#25 hardening, owner conversation controls, shared proposals, source-expiry fixes,
combined workspace operation guards, exact message-outcome recovery and the exact
disclosure-review compiler with the earlier product dependencies.
It excludes #21's research archive. This separate five-file
[#26 documentation update](https://github.com/EmotiveImpact/Assistant-Central/pull/26)
is stacked above that product revision; documentation checks add no product evidence.
Fresh cumulative hosted acceptance and integration into main remain unfinished.

## What the cumulative candidate adds

- **Owner conversation workspace:** separate current local-account sessions,
  default-disabled configuration and a separately unlocked coordinating owner.
  New/rejoining members see future messages only. Exact old-history grants come
  from each original author, bind a current recipient epoch and are checked through
  the full declared source ancestry. See [owner controls](../workspace_ui/CONVERSATIONS.md).
- **Exact recovery for one uncertain message:** authenticated inspection by the
  original author/room/request/digest can prove that the signed message is retained
  and currently visible locally. The UI retains bounded session-bound metadata,
  not submitted plaintext. Absence is inconclusive and cannot permit replay.
  Other uncertain conversation mutations retain conservative holds; a reload is
  not evidence of rollback. See [message inspection](../conversation/README.md#inspect-one-uncertain-message-outcome).
- **Shared-proposal primitive:** every member of a frozen roster separately
  approves the exact revision; revisions start without approvals. Current source
  access, expiry and withdrawal matter. Unanimity is local discussion agreement,
  not execution, legal, payment or disclosure authority. There is no proposal UI
  or remote signature exchange. See [shared proposals](../conversation/PROPOSALS.md).
- **Exact disclosure-review compiler:** authenticated prepare/reinspect only.
  It reconstructs complete declared ancestry and authorised public projections;
  all source authors and the executor must already be allowed to see the full
  review. A fixed public fixture profile binds the complete proposed request.
  The closure is limited to 16 events and the whole envelope to 16 KiB; excess
  is rejected, never truncated. Ancestors shown as evidence are not silently
  included as provider input. It signs nothing, consumes no grant and is not
  wired to a provider, runtime, MCP, server or UI. See [disclosure reviews](../conversation/DISCLOSURE_REVIEW.md).
- **Combined host-draft controls:** the current owner selects only their configured
  draft queue. Exact inspection/dismissal remains bounded by the original lease
  of at most 15 minutes. Draft creation/status is not assistant dialogue, task
  release or execution. See [owner draft review](../agent_bridge/OWNER_REVIEW.md).

All conversation features trust one coordinating process and host. Encryption is
to that coordinator, which can see authorised plaintext; it is not distributed
end-to-end encryption or a multi-tenant deployment. Local passwords/signatures
establish local accounts/keys, not verified humans or comprehension of a review.
Declared-source enforcement cannot discover omitted or copied provenance.

## Verification evidence and gaps

Local product verification at the exact candidate above has passed 189
conversation/proposal/disclosure, 378 pilot, 45 actual local HTTP, 87 interface/model
and 62 bridge tests, strict TypeScript, 673 imported-file checks and 17 manifest
checks, whitespace checks and both fictional conversation demos. These are
inherited product results, not tests rerun for this documentation-only update.

Independent component review covered the recovery and disclosure boundaries,
including focused regression tests. The latest component browser scripts are
prepared but **unrun**: browser execution was unavailable in the local verification
environment. Eight hosted workflows have now started for the published cumulative
head, but their outcomes are not yet verified. Do not substitute
model tests, local HTTP tests or older browser runs for that missing evidence.

Older, narrower hosted evidence remains useful:

- Published #25 `9a11c3b` passed seven workflows, including
  [real Chromium and network-disabled official SDK-to-owner HTTP acceptance](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492371),
  [workspace browser checks](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492440),
  [bridge](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492383),
  [aggregate](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492615),
  [network](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492713),
  [isolation](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492389)
  and [ledger](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42804492631).
  They do not cover the later hardening, owner controls, proposals or recovery.
- Published #18 `b3a96a5` passed
  [actual distinct-container network/TLS acceptance](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42795921004).
  Shared-loopback isolation and distinct-network TLS are different tests. Neither
  proves independent physical devices, real owners or personal-assistant access.

No live account/provider, remote multi-owner service, security certification,
production deployment or measured scale/reliability claim follows from these tests.

## Safe setup and reproduction

Use disposable fictional data and a checkout of the revision being evaluated.
Python 3.12 and Node 24 are the CI targets. From the repository root:

```sh
python -m venv .venv-pilot
.venv-pilot/bin/python -m pip install -r pilot/requirements.txt
.venv-pilot/bin/python -B -m pilot.demo
.venv-pilot/bin/python -B -m pilot.workflow_demo
.venv-pilot/bin/python -B -m pilot.https_exchange_demo
```

These main-compatible demos use temporary identities/stores and fixed synthetic
work. The HTTPS demo uses loopback test certificates; it does not configure public
hosting or system trust. For the original browser rehearsal run
`.venv-pilot/bin/python -B -m pilot.ui_fixture --port 8765` and open
`http://127.0.0.1:8765`. The public fixture password is
`Fictional browser test password`; never reuse it or expose the fixture publicly.

On a checkout containing the local candidate, follow the
[workspace quick start](../workspace_ui/README.md#open-the-fictional-workspace)
for the refined interface. Explicit host configuration is required for
[conversations](../workspace_ui/CONVERSATIONS.md#host-setup),
[transfers](../pilot/OWNER_TRANSFERS.md#trusted-host-configuration) and
[host drafts](../agent_bridge/OWNER_REVIEW.md#optional-launcher). None is personal
assistant enrolment. Provisioning, peer pinning and account access are separate
operations, not a side effect of opening the interface.

Candidate checks, after activating the private virtual environment:

```sh
python -B tools/verify_import.py
python -B -m unittest discover -s pilot/tests -v
python -B -m unittest discover -s conversation/tests -v
python -B -m conversation.demo
python -B -m conversation.proposals_demo
npm ci --prefix agent_bridge --ignore-scripts --no-audit --no-fund
npm --prefix agent_bridge run check
npm --prefix agent_bridge test
python -B -m unittest discover -s workspace_ui/tests -v
node --test workspace_ui/tests/conversations.test.mjs workspace_ui/tests/host_drafts.test.mjs workspace_ui/tests/operations.test.mjs workspace_ui/tests/projections.test.mjs pilot/web/tests/model.test.mjs pilot/web/tests/transfers.test.mjs
```

This is the local component-check set, not all hosted or live acceptance.
[Combined workspace verification](../workspace_ui/OWNER_WORKSPACE.md),
[container isolation](../isolation/README.md#run) and
[distinct-network acceptance](../network_acceptance/README.md) give the additional
procedures. Harness self-tests do not run containers. Use an already authorised
Docker engine; an unavailable engine or browser is a missing test, not a pass.
The earlier bridge runtime dependency audit was clean at its checked revision;
its official host test dependency graph retained 15 moderate upstream advisories.
That is neither a current whole-stack audit nor a clean production bill of health.

### Existing storage and recovery

Stop **all** processes holding the affected stores before changing their format.
Read [payload migration](../pilot/STORAGE.md#existing-plaintext-stores) and
[bridge v1 upgrade](../agent_bridge/OWNER_REVIEW.md#storage-upgrade-requires-an-offline-stop)
as separate contracts. No automatic migration or plaintext fallback is provided.
For an existing known-password pilot account, the explicit migration command is:

```sh
.venv-pilot/bin/python -B -m pilot.storage_migrate --directory /private/owner
```

The path is a placeholder for an existing private directory. Enter the password
in a private terminal, not argv or an environment variable. Migration validates
the exact schema and bounded input and publishes a verified encrypted replacement.
After an uncertain/interrupted write, stop and inspect rather than blindly rerun.
An old bridge process already holding a v1 store is not retrospectively fenced
by an offline upgrade; stop every old process before upgrading.

Payload encryption leaves metadata visible. Public-key sealing permits retention
of late results but is not writer authentication. Host compromise, backup rollback,
secure erasure and revocation of old copies are not solved. Password maintenance
preserves the existing identity; lost-key recovery and rotation remain separate.

## Acceptance states that must stay separate

1. **Draft, host response or review:** inert content/status, not owner approval.
2. **Exact owner decision:** binds a current local account to specific bytes,
   recipient and scope, not human identity or approval of unrelated effects.
3. **Transport evidence:** mailbox ACK means quarantine; an original signed receipt
   means receipt of that packet, not recipient acceptance or successful work.
4. **Recipient acceptance or proposal agreement:** separate exact decisions;
   neither supplies source/provider, execution, payment or legal authority.
5. **Provider disclosure and execution:** need exact source-owner and executor
   authority, the approved live route and applicable cost/data decisions.
6. **Result review, release and receipt:** retain the original result and review
   final exact content before release; the receiving owner decides separately.

Cancellation prevents new local use when observed. It cannot recall in-flight
bytes or copies already read. A timeout/lost response is uncertain, not proof of
rollback. Inspect exact retained state before a permitted explicit retry; never
silently renew packets, leases, receipts or authority. A digest is not a secret
and can reveal low-entropy content through guessing.

## Remaining delivery gates

The [ordered roadmap](../ROADMAP.md#ordered-delivery-dependencies) is the handoff:
finish cumulative hosted acceptance and integration; build the remaining
owner review controls; prove durable supported-host dialogue/recovery; integrate
source authority atomically with dispatch; demonstrate two independently
controlled owners/hosts; then approve and verify live operation and its operational
security. No credentials, personal accounts, provider calls or deployment are
needed to review this local candidate.
