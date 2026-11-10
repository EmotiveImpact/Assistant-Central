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
