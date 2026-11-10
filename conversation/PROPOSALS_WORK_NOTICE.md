# Exact shared proposal work notice

Coordinating role: proposal primitive maintainer. The integration maintainer owns independent review and merge sequencing. Base: conversation ledger PR #22, exact head 8a02185884faaf691394c3873094b6e3055a0693.

Claimed paths: conversation/proposals.py, conversation/tests/test_proposals.py, conversation/proposals_demo.py and conversation/PROPOSALS.md, plus this notice. The coordinated scope now also includes an optional final-check hook in conversation/ledger.py and the independent proposal boundary regression module. No authentication, UI, bridge, provider, transport or research archive edits. Owner conversation controls PR #24 remain separate and are not included.

Goal: immutable shared proposal revisions with exact content/source/audience/epoch/expiry commitments and separate authenticated local-owner approval and revocation records. Approvals are not source/provider disclosure permission, delivery, execution or legal agreement. This is a trusted local-host contract, not independent-device end-to-end messaging or a live negotiation deployment.

Planned verification: genuine separate local password sessions; stale reviews; content revision; membership change and rejoin; revocation and expiry; persisted clock rewind; locked owners/storage; concurrent and lost-response/idempotent approval; corruption; transitive source access. Existing conversation and pilot regression checks and a fictional local demo will run before publication.

This first commit contains coordination only. Implementation and exact verification remain pending. No live hosts, personal data, external service or provider will be activated.

## Implementation and review boundary

The initial commit was coordination only. The local implementation now contains
an encrypted, signed exact-revision primitive, separate owner approval and final
withdrawal records, current source/audience/expiry checks, durable retry inspection,
and a fictional two-owner demo. The five initial proposal files, one independent regression module and the narrow
ledger transaction hook are the complete scope. No authentication, UI, bridge or
provider implementation has been imported or edited. The hook retains existing
callers' default path and both authentication checks; opted-in proposal operations
also check policy and observed actor/coordinator deadlines immediately before commit.

Independent review and implementation publication remain pending. Exact test and
review evidence will be recorded on the draft PR. The existing conversation workflow
automatically discovers the new test module. See [the contract](PROPOSALS.md) for
verification commands, the trusted-host boundary and intentionally separate permissions.
