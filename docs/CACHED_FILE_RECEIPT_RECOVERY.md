# Cached file receipt recovery

Coordination-only notice, before implementation.

Owner: `/root/advance_central_network/fix_cached_file_receipts`, coordinated by
`/root/advance_central_network`.

Base: main `fccc516e9192edd9c4a3ec3226d2acf153914c50`, including file exchange #11
and authenticated HTTPS #13.

Goal: require an existing cached receipt inside the file-receipt runtime
transaction. Recovery must not mint a replacement receipt if the inbox remains
but the original receipt cache has gone missing.

Owned paths: `pilot/file_exchange.py`, a new
`pilot/tests/test_file_receipt_recovery.py`, and this notice. No transport core,
auth/runtime/provider/workflow, signed-grant, server or web changes.

Planned verification: reproduce missing-cache renewal; prove missing-cache
recovery leaves no new receipt or output file; preserve byte-identical cached
recovery and related fail-closed boundaries; run focused and full relevant
suites and inspect exact-head CI. No tests are claimed by this initial notice.

Other active ownership inspected: #14 signed grants, #15 application storage,
and #16 owner connection and transfer workspace. No overlapping edits intended.
No live credentials, personal data, provider calls or deployment. Parent owns
review and merge; leave this pull request in draft.
