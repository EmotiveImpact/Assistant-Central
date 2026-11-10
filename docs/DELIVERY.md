# Delivery status and acceptance gates

Checked 10 November 2026. **Assistant Central is a tested local pilot with reviewed
extensions, not a fully delivered or live platform.** No existing personal
assistant, live provider account or independently controlled multi-owner,
multi-host end-to-end service has been verified.

The intended product is durable direct/group conversations between people's
assistants, optional exact old-history sharing and bounded, auditable work across
supported hosts. The [decision record](DECISIONS.md) explains the choices and
remaining decisions. This snapshot must be updated after later integration.

## Verified main and remaining work

**Verified main product:**
[`578a665fafb550e76c63d2d1a097408e87f8ffda`](https://github.com/EmotiveImpact/Assistant-Central/tree/578a665fafb550e76c63d2d1a097408e87f8ffda),
tree `e2ee8b174fce4f5566f38818ef669775583a1432`. The cumulative
[PR24](https://github.com/EmotiveImpact/Assistant-Central/pull/24) merged after all
eight exact-revision hosted workflows passed. Its accepted product head was
`bd1f913a5916b2dd6c0217dbd098426c16773e75`; the merged tree is identical.

Main now contains the authenticated local pilot, peer decisions, password
maintenance, synthetic work loop, file/HTTPS transfer, container/network harnesses,
encrypted payload storage, standalone source grants, supported-host draft bridge,
owner draft controls, durable conversations, exact history controls, shared
proposals, exact message-outcome recovery and inert disclosure-review preparation.
The owner HTTP service remains loopback-only. The shared-team and execution
examples remain separate synthetic proofs. See the [pilot guide](../pilot/README.md),
[storage contract](../pilot/STORAGE.md) and [source grants](../pilot/SOURCE_GRANTS.md).

PRs #16, #17, #18, #20, #22, #23 and #25 were integrated through that cumulative
merge. The exact #27 proposal head is also in main; its redundant stacked review
was closed because it contained no additional commits for main. The sixteen
inert research snapshots were merged separately through
[PR21](https://github.com/EmotiveImpact/Assistant-Central/pull/21) and are included
unchanged in the accepted product tree. Research is not dependency adoption or
execution of upstream software.

The ongoing visual-design work in
[PR19](https://github.com/EmotiveImpact/Assistant-Central/pull/19) is separate from
this accepted revision. Preserve and reverify the conversation, transfer and
uncertainty behaviour when composing those changes. This five-file
[PR26 documentation update](https://github.com/EmotiveImpact/Assistant-Central/pull/26)
adds no product code or test evidence. The remaining functional, real-host and
operational gates below are still unfinished.

## What the integrated pilot provides

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

The underlying reviewed product passed 189 conversation/proposal/disclosure,
378 pilot, 45 actual local HTTP and 62 bridge tests, strict TypeScript,
673 imported-file checks and 17 manifest checks, plus both fictional conversation
demos. The final browser fixes increased the interface/model suite to 89 passing
tests. Independent component review and retained adversarial regressions cover
source, expiry, identity and uncertainty boundaries.

All eight hosted workflows passed on accepted head
`bd1f913a5916b2dd6c0217dbd098426c16773e75`:

- [Conversation owner controls](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838370059): actual separate local owner sessions and combined host-draft/conversation desktop/mobile Chromium flows.
- [Central workspace](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369658): actual authenticated owner HTTP and transfer controls through disposable TLS.
- [Host draft review](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369653): Chromium and network-disabled official SDK-to-owner HTTP acceptance.
- [Supported SDK bridge](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369560): real MCP paths using deterministic/no-model official SDK fixtures, without external networking.
- [Conversation ledger](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369602): durable history, adversarial checks and existing pilot regressions.
- [Offline aggregate](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369635): component suites, demos, contracts and pilot Chromium.
- [Container isolation](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369657): actual filesystem/process/Unix-permission boundaries.
- [Distinct-network HTTPS](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838369632): four separate container network/mount/PID namespaces with actual TLS 1.3 and restart/outage checks.

GitHub test merge `804d44018f51096bf0ca11b4da390e6a2f05879f` and the final main
merge have the same accepted tree. The
[owner-browser screenshots](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42838370059/artifacts/13774334554)
were inspected, including the exact history-review dialog and combined mobile
workspace. Artifact ZIP SHA-256:
`57aeb97acf12cd1663cc24d72f21e1c47a590985e584be17e640ce2401de24ee`.
Two real browser defects were reproduced and fixed with regressions: selector
accessible names including option text, and a shadowed variable preventing the
history-review dialog from rendering. Failed runs were not skipped or relabelled.

The unchanged research snapshots were separately reverified under Python -O:
16 snapshots, 23,322 included source files and 254,536,445 uncompressed bytes;
all eight verifier fixtures passed. No upstream software was executed.

These are fictional local-account and trusted-container-host tests. They do not
prove independent physical devices, real human ownership, existing personal
assistant access, live account/provider operation, security certification,
production deployment or measured scale/reliability. Documentation-only changes
add no new product evidence. Repeat applicable checks for later code changes.

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

On a checkout containing the accepted revision, follow the
[workspace quick start](../workspace_ui/README.md#open-the-fictional-workspace)
for the refined interface. Explicit host configuration is required for
[conversations](../workspace_ui/CONVERSATIONS.md#host-setup),
[transfers](../pilot/OWNER_TRANSFERS.md#trusted-host-configuration) and
[host drafts](../agent_bridge/OWNER_REVIEW.md#optional-launcher). None is personal
assistant enrolment. Provisioning, peer pinning and account access are separate
operations, not a side effect of opening the interface.

Component checks, after activating the private virtual environment:

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
preserve the accepted baseline while integrating remaining visual work; build the remaining
owner review controls; prove durable supported-host dialogue/recovery; integrate
source authority atomically with dispatch; demonstrate two independently
controlled owners/hosts; then approve and verify live operation and its operational
security. No credentials, personal accounts, provider calls or deployment are
needed to review this local candidate.
