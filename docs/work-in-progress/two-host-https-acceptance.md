# Distinct-network HTTPS acceptance

Owner: the network acceptance engineer, coordinated by the integration lead. Draft #18 was opened with a coordination-only commit before implementation.

Original base: reviewed #13. Final cumulative base: #16 `002d4afd0784f7ac68e2e6e106a2c4a09cc9d61f`, tree `2dd0626c17e908a5322cc6f6f6e845dc620ff401`, including storage #15, source grants #14 and receipt recovery #17. Own `network_acceptance/**`, its separate CI workflow and this notice only. No product files changed. #15 storage, #16 transfer workspace and #17 receipt recovery remain independently owned; the final composed tree is checked locally and by the dedicated hosted workflow.

Implementation: four non-root containers on one internal bridge, distinct network/mount/PID namespaces, six private volumes and disposable in-memory CA. Mailboxes lack owner stores and credentials; owners get read-only quarantine. Actual TLS checks, explicit authenticated import/receipt/decision, outage and restart, cancellation, tampered ciphertext, wrong trust/sender and original-byte retries are driven through the synchronous product APIs. The driver is synthetic trusted tooling, not a new production or owner endpoint.

Verification: guard tests and local actual-TLS controller smoke are separate from the actual Docker test. The current executor has no Docker. A dedicated hosted workflow must pass at an exact published head before container acceptance is claimed. Final run links and cumulative evidence will be recorded in the pull request.

Decisions: separate the mailbox's volumes from owner credentials; use a private bridge rather than shared loopback; require the real namespace IDs and exact mount contracts; preserve observation/authority distinctions; generate CA material anew; fail rather than silently fall back to same-process tests. The local smoke substitutes only Docker controls and cannot write a passing acceptance report. All negative checks require specific product refusal classes.

Limits: one kernel and controller, fictional identities, no real provider, no Internet deployment, no production-security claim. Owner helpers close their stores per operation; their container restart is durable state reuse, not an interrupted long-lived owner server. Mailbox outage is actual. See `network_acceptance/README.md` for metadata, cancellation, persistence, cleanup and untested deployment boundaries.

Independent review found no blocker within the documented synthetic contract. Its defensive exact-role-set suggestion was applied: missing, empty or extra process observations now fail before any four-namespace evidence is reported. The final cumulative hosted verification now includes the reviewed #17/#16 product base; its exact run is recorded in the pull request.
