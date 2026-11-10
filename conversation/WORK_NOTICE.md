# Persistent conversation ledger work notice

Coordinating role: conversation ledger implementation; independent network review coordinates integration. This draft starts from main `55b7df104b12f69336055ca9d5ba0d773d8b10a5`.

## Goal and ownership

Claimed paths: new `conversation/**` and `.github/workflows/conversation-checks.yml` only. Implement a durable encrypted one-to-one thread that can expand to a group, immutable message provenance, explicit per-member historical grants, epoch-bound rejoin, revocation-aware retrieval and bounded recontextualisation. Existing pilot authentication and encrypted payload primitives are dependencies, not edit targets. Execution, live providers, peer transport and deployment remain separate.

The research work in PR #21 informs the design. The supported SDK bridge in PR #20 remains an independent inert-draft adapter; history integration is not included. Current network and owner transfer work in PRs #16–18 owns its existing components.

## Verification

Focused tests will cover restart/locked storage, future-only joins, precise historic grants, removal/rejoin, revoked ancestry in summaries and quotes, concurrent ordering, idempotency, corruption and provenance. A separate CI workflow will run the new suite and existing pilot regression suite. Run completed checks before claiming results.

The initial commit contained coordination only. The implementation now lives exclusively in the claimed paths; no existing pilot modules were changed. No real user data, live account, provider or deployment is activated.

## Implemented contract and local evidence

The ledger is a trusted local-host contract encrypted to one coordinating storage
owner, with separate authenticated actor sessions and signed message provenance.
It is not independently hosted multi-owner messaging or end-to-end encryption
against that host. Exact author-owned history grants are local-only and bind fresh
recipient epochs. The SDK bridge and UI are intentionally not connected yet.

Local evidence on 10 November 2026: 48 conversation adversarial tests pass; the
fictional encrypted history/restart/revocation demo passes; public import verifies
673 files and 17 team manifest entries. All 347 existing pilot component regressions pass. Independent review found an
expiry/restart clock-rewind gap; a durable observed-time fence now prevents it,
including when expiry is first observed during a refused output. The review
regression is retained. Final independent review is in progress. GitHub CI must be checked against the published exact head.
