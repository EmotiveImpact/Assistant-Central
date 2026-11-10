# Local owner conversation controls

Coordinator: conversation owner-controls implementation, with the platform integration lead reviewing scope and dependencies.

This initial commit is coordination only. The base is PR #22 at 8a02185884faaf691394c3873094b6e3055a0693. The working interface depends on the refined workspace composition in PR #23; dependency publication and independent review are required before a cumulative product tree can be published.

Claimed components: new workspace conversation facade, browser module, fixture, focused workspace shell/server integration, tests and documentation. Small authenticated read-only conversation ledger inspection methods require coordination with its current owner. Existing pilot authentication, encryption, transport, provider and runtime semantics are not edit targets. Other research, agent-bridge and receipt-recovery documentation are out of scope.

Goal: default-disabled trusted local coordinating-host owner conversations with separately authenticated existing owners, explicit future-only invitation acceptance and exact source-author historical-message grants. No live assistants, provider calls, credentials, deployment or model-facing history authority.

Verification: actual HTTP authentication/origin/schema boundaries, separate actor sessions, membership-sensitive composition and history, exact review and revocation/expiry, restart/uncertainty, hostile inert text, hidden DOM cleanup and hosted desktop/mobile Chromium when publication is authorised. Local Chromium launch is blocked by sandbox socket restrictions; no local browser success is claimed.

## Implemented candidate

The owner-controls candidate now composes reviewed conversation #22 and published
workspace/transfer #23 at 96e841fa78d2fa99e18dfbc8d58592b3fbcb3384. The latter's
product and screenshot follow-up are preserved. No unrelated receipt-recovery
or agent-bridge documentation is changed.

A new optional facade owns separately authenticated real local owner services on
the existing worker. Small ledger inspection APIs retain its transaction/session,
storage-unlock and durable-clock fences. The UI supplies future-only invitations,
visible history/search/pagination, scoped context, audience-bound message drafts,
exact author history review and issuer-only grant inspection/revocation, including
older grants and removed issuers. See workspace_ui/CONVERSATIONS.md for limits.

Local evidence: 55 conversation tests (five inspection additions), 19 actual
workspace HTTP tests, and 45 combined JavaScript validator/projection tests pass.
Fictional fixture construction and whitespace checks pass. Existing full pilot
regressions are running. Hosted browser evidence is pending publication; no local
Chromium pass is claimed. Independent integration review found UI late-completion
busy ownership and successful-write/failed-inspection ambiguity; both were fixed
with explicit regression tests. Required final exact-head review remains pending.

Further local verification: all 377 cumulative pilot tests pass. An inert-DOM
controller regression now verifies that visibility cleanup keeps a pending
mutation busy and requires inspection when the closed-view outcome settles.
Seven conversation JavaScript tests and 46 combined JavaScript tests pass. The
corresponding actual-HTTP Chromium interruption test is written but not run.

Product publication was denied before execution; no new product tree or ref was
uploaded. The draft remains coordination-only until publication is authorised.
