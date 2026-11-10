# Distinct-network HTTPS acceptance

Owner: `/root/build_network_acceptance`, coordinated by `/root/advance_central_network`. Draft #18 was opened with a coordination-only commit before implementation.

Base: main `fccc516e9192edd9c4a3ec3226d2acf153914c50`, including #13. Own `network_acceptance/**`, its separate CI workflow and this notice only. No product files changed. #15 storage, #16 transfer workspace and #17 receipt recovery remain independently owned; final cumulative verification is coordinated separately.

Implementation: four non-root containers on one internal bridge, distinct network/mount/PID namespaces, six private volumes and disposable in-memory CA. Mailboxes lack owner stores and credentials; owners get read-only quarantine. Actual TLS checks, explicit authenticated import/receipt/decision, outage and restart, cancellation, tampered ciphertext, wrong trust/sender and original-byte retries are driven through the synchronous product APIs. The driver is synthetic trusted tooling, not a new production or owner endpoint.

Verification: guard tests and local actual-TLS controller smoke are separate from the actual Docker test. The current executor has no Docker. A dedicated hosted workflow must pass at an exact published head before container acceptance is claimed. Final run links and cumulative evidence will be recorded in the pull request.

Decisions: separate the mailbox's volumes from owner credentials; use a private bridge rather than shared loopback; require the real namespace IDs and exact mount contracts; preserve observation/authority distinctions; generate CA material anew; fail rather than silently fall back to same-process tests. The local smoke substitutes only Docker controls and cannot write a passing acceptance report. All negative checks require specific product refusal classes.

Limits: one kernel and controller, fictional identities, no real provider, no Internet deployment, no production-security claim. Owner helpers close their stores per operation; their container restart is durable state reuse, not an interrupted long-lived owner server. Mailbox outage is actual. See `network_acceptance/README.md` for metadata, cancellation, persistence, cleanup and untested deployment boundaries.

Independent review found no blocker within the documented synthetic contract. Its defensive exact-role-set suggestion was applied: missing, empty or extra process observations now fail before any four-namespace evidence is reported. Final cumulative hosted verification still follows #17/#16 integration.
