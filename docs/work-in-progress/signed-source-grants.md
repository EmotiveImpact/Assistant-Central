# Signed source-grant contract work notice

Coordination-only initial commit, before substantive implementation.

- Coordinator: Assistant Central network integration task. Implementation owner: signed source-grants worker (Astra).
- Base: main at cca92a0f5d69a5893698689613819c83222bdb4a, containing reviewed synthetic work loop and password maintenance.
- Goal: a bounded, owner-session-authenticated signed contract for exact inherited-source disclosure, with pinned identity verification, purpose/recipient/provider destination binding, expiry, explicit version/revocation observation and single-use validation.
- Claimed new paths only: pilot/source_grants.py, pilot/tests/test_source_grants*.py, pilot/SOURCE_GRANTS.md and this work notice. No edits to auth/runtime/provider/workflow/server/UI or file/HTTPS transport; runtime integration is out of scope.
- Existing open ownership checked: #10 isolation, #11 private-file exchange, #12 HTTPS carrier and #13 authenticated HTTPS exchange. Storage/key migration is separately owned. No overlaps identified.
- Verification plan: fictional independently authenticated owners; positive multi-owner exact-scope composition and adversarial signature, identity, destination, expiry, replay, stale-version, tamper, cancellation and withdrawal tests; full pilot tests and repository checks.
- Trust boundary: signatures authenticate a pinned local owner key, not a person's real-world identity or source ownership. Offline signatures do not reveal unseen withdrawal. Transport receipts, recipient acceptance, execution approval and result acceptance remain separate.
- No real personal data, provider calls, persistent account credentials or remote deployment. No merge by this worker.

Implementation, verification and independent review are pending.

## Implementation checkpoint

The standalone contract, non-content observation/attempt ledger and focused
adversarial tests are implemented. Storage retention was coordinated with the
storage/key-migration owner: only public trust metadata, opaque operation IDs,
revisions, hashes, timestamps and veto/attempt flags persist. There is no stored
signed plan, purpose, source identifier/scope, prompt, source fragment or result.

Independent integration review identified a supersession bug: rejecting an
already-expired or ineligible newer grant before retaining its revision could
leave an older grant usable. The implementation now commits authenticated
revision/conflict observations before reporting current eligibility failures.
Three independently authored regressions reproduce the earlier defect and pass
with this change. The full contract and remaining trust boundaries are recorded
in `pilot/SOURCE_GRANTS.md`.

Final publication waits for the cumulative authenticated-HTTPS and encrypted-
storage integration base. Exact final checks and remote tree verification will
be recorded in the PR. No existing runtime/provider gate is relaxed.

## Feature-tree checks, 10 November 2026

- Full pilot discovery: 263 passed, including 46 new contract tests and three
  independently authored no-revival regressions.
- Import integrity, team (84), execution (133), integration (103), composition,
  all synthetic execution/provider/lineage/integration/acceptance/pilot/workflow
  demos, 25 UI-model checks and both actual HTTP contracts passed.
- The default frozen-consent check found missing `coincurve`. The full rerun
  with the existing verified pinned fixture dependency directory passed all
  948 Python tests and 15 DOM-model suites. All 39 isolated targeted stdio
  checks also passed.

These are feature-tree results before cumulative storage/HTTPS integration, not
hosted CI, actual browser acceptance or a production security audit.

## Decisions for review

- Use the existing password-authenticated Ed25519 owner identity and a distinct
  signing domain. Alternative: create another credential system. Reuse avoids
  competing local identities while preserving protocol separation.
- Require every declared source owner to sign the full exact disclosure plan.
  Alternative: broad source/category grants. Exact composition binds every owner
  to the payload, recipient, purpose, source snapshots and provider destination.
- Retain only hashes and minimum non-content metadata; require original signed
  grants again at consume. Alternative: store full plans and add another encrypted
  payload path. This avoids plaintext purpose/source metadata and storage coupling.
- Make supersession monotonic even when a newer authenticated grant is unusable.
  Alternative: discard expired or wrong-route updates. Discarding them could revive
  older authority, as the independent review regressions demonstrated.
- Use terminal withdrawals, cancellation, equivocation and veto-capacity fences.
  Alternative: automatic reset/eviction or resurrection. Conservative permanent
  denial preserves consent history at the cost of availability.
- Limit grants to ten minutes and consume one local attempt before any later
  effect. Alternative: reusable capabilities. This narrows replay/uncertainty,
  without pretending to observe remote withdrawal or prove global single-use.
- Keep runtime integration out of this PR. Alternative: relax inherited-source
  rejection immediately. An integration must first prove complete provenance,
  coupled atomic attempts and the existing task/provider/acceptance boundaries.

## Cumulative verification checkpoint

Integrated exact storage/HTTPS head
`9ac65ed01412a3dc8e49fa5a912ca093f72320f3` and reran the cumulative checks:
346 pilot tests, 20 isolation harness unit tests, import/team/execution/
integration/composition, all synthetic demos (including file and real loopback
HTTPS), 25 UI-model checks, both HTTP contracts, 948 frozen Python tests,
15 DOM suites and all 39 targeted stdio checks passed. No local Chromium or
actual container-isolation result is claimed for this tree.

The subsequent reviewed runtime-close/migration-lease correction was integrated
at exact storage head `65e07ad4a765bf61ea41f9e36ad57c77b11e0b12`. The final
cumulative tree passes **347 pilot tests** (including all 49 new grant tests),
20 isolation harness tests, and the complete aggregate/demo/model/HTTP/frozen
checks listed above. The source-grant implementation required no compatibility
changes. The PR records the published head/tree and hosted CI separately;
local results do not establish hosted Chromium or actual Docker acceptance.
