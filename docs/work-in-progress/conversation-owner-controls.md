# Local owner conversation controls

Coordinator: conversation owner-controls implementation, with the platform integration lead reviewing scope and dependencies.

This initial commit is coordination only. The base is PR #22 at 8a02185884faaf691394c3873094b6e3055a0693. The working interface depends on the refined workspace composition in PR #23; dependency publication and independent review are required before a cumulative product tree can be published.

Claimed components: new workspace conversation facade, browser module, fixture, focused workspace shell/server integration, tests and documentation. Small authenticated read-only conversation ledger inspection methods require coordination with its current owner. Existing pilot authentication, encryption, transport, provider and runtime semantics are not edit targets. Other research, agent-bridge and receipt-recovery documentation are out of scope.

Goal: default-disabled trusted local coordinating-host owner conversations with separately authenticated existing owners, explicit future-only invitation acceptance and exact source-author historical-message grants. No live assistants, provider calls, credentials, deployment or model-facing history authority.

Verification: actual HTTP authentication/origin/schema boundaries, separate actor sessions, membership-sensitive composition and history, exact review and revocation/expiry, restart/uncertainty, hostile inert text, hidden DOM cleanup and hosted desktop/mobile Chromium when publication is authorised. Local Chromium launch is blocked by sandbox socket restrictions; no local browser success is claimed.
