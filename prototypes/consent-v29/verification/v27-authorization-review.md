# Bounded authorization and transport review

No new confirmed routed authorization or disclosure defect was found in this
focused local review. No production patch was proposed. This is not security
certification or live-host acceptance.

## Verified boundaries

- Cancellation's legacy task-ID field is separately protected by the signed exact
  task context and enrolled owner; no compatibility-alias substitution path found.
- Exact approvals bind actor, recipient, context, message, transport bindings and
  contact versions. Revocation/re-pairing does not restore old authority.
- Review resolution rechecks current permissions and immutable durable state.
- Withdrawal applies only to provably unsubmitted authority. Queued execution
  evidence prevents an unsafe claim that the approval is unused.
- Dispatch rechecks validity after enqueue. A started attempt can still arrive
  after cancellation, while further processing is fenced. Receipt recovery records
  actual disclosure evidence; delayed processing is not another transmission.
- Request/result linkage and processed-only inboxes are enforced. Context/history
  fault tests reject disclosure rather than show queued or receipt-only content.
- Changed decision nonce reuse fails. Exact retries preserve original review
  history and do not mint approval, follow successors or duplicate transitions.
- Restricted callers cannot select a new actor/context or route owner operations.

## Evidence and scope

201 existing focused tests passed in an isolated source copy. These are reused
regression cases, not additional new tests or separate security guarantees. The
11 reviewed authorization/session/transport/proposal/protocol source files match
the checkpoint source. See v27-authorization-audit-tests.txt for retained output.

Owner UI authentication, trusted constructor/callback integrity, local DB/files,
and executor pipes remain host assumptions. Arbitrary trusted-host rewriting was
not characterized as a remote exploit. Testing used fictional identities, local
SQLite, controlled clocks and anonymous pipes. No browser, sockets, network,
external services, installation or real accounts were used. Real authentication,
provider transport, hostile-host isolation and production readiness are unverified.
