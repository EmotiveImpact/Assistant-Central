# Preserve original transport receipts

This change was opened as draft PR #17 with a coordination-only notice before
implementation. The implementation owner is
`/root/advance_central_network/fix_cached_file_receipts`, coordinated by
`/root/advance_central_network`. The final cumulative base is #14 commit
`a9d6737654042ef4705a37fbe63b9f0c601dc3d4`, tree
`1d1f4cfc0f4fba8cab06eef21bee26327893402f`, including final #15 storage.

## Decision and scope

An existing inbox row is not permission to issue a replacement receipt.
`FileExchange.receipt` now requires the original `peer_receipts` row inside the
same authenticated runtime transaction used to retrieve it. `PilotRuntime.receive`
requires that row for duplicate non-receipt imports before calling `receipt_for`.
The latter protects both file and selected HTTPS imports without duplicating
checks across adapters. Missing cache fails closed with no replacement receipt,
application mutation or receipt output file.

First atomic imports still create their first receipt. Importing a receipt never
creates another receipt. Existing cached receipts retain their exact signed
bytes and original expiry, including after restart. Offline recovery and duplicate
imports may return an expired receipt unchanged for inspection; this does not
renew it or make it acceptable as a fresh acknowledgement at the peer. Existing
signature and pinned-peer checks remain authoritative.

The alternative of resealing a missing receipt was rejected because it changes
ciphertext and renews expiry despite the recovery contract. Changing the transport
helper itself would remove the initial-import creation path, so the guards live
at the two caller boundaries instead.

Owned changes are limited to `pilot/file_exchange.py`, the duplicate-import guard
in `pilot/runtime.py`, `pilot/tests/test_file_receipt_recovery.py`, and this note.
Runtime ownership was coordinated with #15 before editing its final integrated
base. No transport core, auth/provider/workflow, source-grant, server or web edits.
No real credentials, personal data, live provider calls or deployment.

## Verification

Ten dedicated regressions cover missing-cache recovery after restart/expiry,
transaction placement, byte-identical expired recovery, revoked peers, damaged
cache, missing-cache duplicate runtime/file/HTTPS imports, unchanged cached
replays, and receipt-loop exclusion. Two recovery regressions reproduced failures
before the file guard; three duplicate-import regressions reproduced failures on
the cumulative encrypted base before the runtime guard. The final 43-test focused
recovery/file/HTTPS suite passes. The pull request records cumulative checks and
exact-head hosted CI separately; local passes are not hosted CI results.

All 357 cumulative pilot tests passed, alongside import/team/execution/integration
checks, synthetic demos, UI-model and HTTP contracts, 20 isolation harness tests,
the full frozen consent checkpoint and targeted stdio checks. Independent review
reran the ten new regressions and found no blocker. Container integration and
Chromium acceptance are checked separately in hosted CI; Docker is absent locally.

These guards detect missing receipt history, not rollback or malicious database
rewrites by a process controlling the same OS account. Keep the original cached
bytes. Inspect retained state if history is missing; this change provides no
automatic repair, retry or cache regeneration.
