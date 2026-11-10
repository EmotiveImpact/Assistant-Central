# Owner workspace composition

This local work combines the reviewed conversation controls with the host draft
queue and exact proposal backend in one optional owner workspace.

## Coordination and boundaries

The workspace maintainer owns composition in `workspace_ui/app.mjs`,
`index.html`, `projections.mjs`, `server.py` and `style.css`, plus the narrow
fixtures, shared interface state and tests needed to verify that composition.
The conversation maintainer retains the ledger and permission service; the host
integration maintainer retains the queue service and host adapters. Pilot
authentication, runtime, transport and provider disclosure are unchanged.

The local base is `82d1d871c0502ed9c358193aad100035523625e6`; the conversation
controls input is `f0d7ac593cf7efeea8086b62f3a3532506135465`.
Pull requests #24 and #25 identify the existing component ownership. This first
commit is coordination only. Publication is held: no remote write, alternate
publication route, deployment or live account action is part of this work.

## Design and verification

The server wraps the pilot owner in `ConversationService`, then in
`HostDraftService`, preserving authenticated local-account actor selection.
Each optional feature remains disabled without its explicit host configuration.
A shared operation gate keeps pending or uncertain mutations fenced across
panels and privacy cleanup. History joins remain future-only and exact history
grants remain local-owner-only. Proposal approvals receive no new interface.

Verification will cover disposable local accounts over actual loopback HTTP,
static modules, interrupted interface state, the full cumulative Python and
model suites, and prepared desktop/mobile browser scripts. Browser execution
and hosted CI are distinct gates; unavailable checks will not be reported as
passed. The final local commit and tree will be frozen for independent review.

## Local candidate and decisions

The composed server preserves both disabled defaults and wraps conversation
account routing before host draft review. A shared lease module covers the shell
and both panels, including old-session completions and cross-panel hidden-view
restoration. The conversation maintainer also approved the narrow UI fix retaining
unsent text/request IDs across passive same-audience message refreshes. Authentication, runtime, proposal and bridge implementations are unchanged. The
only ledger changes beyond the reviewed branch's additive inspection-method merge
are the explicitly coordinated inspection deadline follow-up recorded below.

The three-account/two-queue fixture and eight new combined HTTP checks passed as
part of 39 workspace tests. Cumulative conversation, pilot, bridge, TypeScript,
model, team, execution, integration and harness checks passed. Detailed counts,
reproduction commands and limitations are in `workspace_ui/OWNER_WORKSPACE.md`.
Local Chromium failed at socket creation before any page opened. Archived
consent Python verification initially lacked a dependency on the default path;
the existing pinned local dependency closure allowed its full rerun to pass.
Browser acceptance remains an unpassed gate.

Publication remains held. A separately reproduced inherited conversation
source-expiry race is owned by the conversation maintainer; its fix is not part of
this frozen UI composition. Independent review and later composition of that
fix, exact-head hosted/browser checks and authorised publication remain pending.

## Coordinated inspection deadline follow-up

The integration lead reproduced a final-authentication expiry gap and approved a
narrow change in the three imported conversation inspection methods. Room and
invitation listing now opt into the existing final deadline hook; retained grant
listing also updates expiry status after the last authentication. Eight focused
regressions cover actor/coordinator deadlines, an independently live coordinator
session and durable expiry after restart. Seven failed before the fix; all pass
after it. Core transaction/visibility/source changes remain with the conversation
maintainer's separate hardening work.

The inherited owner-controls workflow now installs the existing pinned bridge
SDK dependencies needed by the combined HTTP fixtures, names model tests
explicitly and prepares a separate combined desktop/mobile browser step. The
integration lead approved this narrow workflow composition. No permission,
security setting, unrelated workflow or hosted state was changed.

## Scoped uncertainty correction

Independent shell review showed that a successful runtime `/api/state` read was
clearing uncertainty for other stores without inspecting their original outcome.
The shell now retains source and operation tickets across navigation/privacy
cleanup. It clears host dismissal uncertainty only after observing the exact
committed dismissal under the original binding/digest. Pending, unavailable and
mismatched results remain inconclusive. Conversation outcomes stay read-only for
that session because its current API lacks exact lost-request inspection. Another
panel, generic state refresh or stale inspection cannot clear the hold. Read-only
inspection remains usable and no request is automatically repeated. A separate
exact message outcome primitive is not included in this composition.

Known read-only conversation POSTs are explicitly classified so a failed history,
context or review/list inspection does not become a permanent uncertain write.
Mutation paths remain uncertain even if a caller mislabels them. Prepared browser
steps use separate ports, wait for teardown and fail on missed readiness checks.
Final local model evidence is 75 tests, including 21 shared controller/shell checks.
