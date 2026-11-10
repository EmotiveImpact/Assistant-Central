# Encrypted application storage work notice

Coordinator: storage implementation, with independent integration review. Base: main `cca92a0f5d69a5893698689613819c83222bdb4a`.

Goal: encrypt local pilot application payloads at rest without changing existing
SQLite transaction, delivery, consent or provider-dispatch fences. This is a
bounded local building block, not production security certification.

Claimed existing components: narrow changes in `pilot/auth.py`,
`pilot/runtime.py`, `pilot/provider.py` and `pilot/workflow.py`. New files:
`pilot/storage.py`, a stopped-service migration command, encryption tests and
storage documentation. No transport, server, UI, isolation or CI changes planned.

Plan: domain-separated encryption independent of password rewrapping; explicit
migration of existing plaintext; fixed failures for unavailable/corrupt records;
transaction interruption, restart, original-packet and workflow regressions.
Metadata/indexes and hostile-host/backup rollback protection are outside scope.
No actual owner credentials, provider accounts or personal data are accessed.

This first commit contains coordination only. Implementation and verification
are pending. Inspect open PR ownership before expanding this scope.

## Implementation decisions

- Retain ordinary SQLite transactions. Field encryption was chosen over replacing
  the database engine or snapshotting the whole database at each transaction.
- Encrypt content, provider request/result/review, workflow review and audit data.
  Metadata/indexes remain visible, explicitly outside this confidentiality claim.
- Use ephemeral public-key sealing to the immutable owner exchange key. This
  preserves late results after logout without retaining an unlocked decryption
  key. It is not writer authentication or an anti-rollback consent ledger.
- Existing plaintext needs explicit stopped-service migration. Build only in
  memory, verify exact logical rows, VACUUM in memory, then fsync private encrypted
  output and atomically replace. Never promise old filesystem blocks were erased.
- Shared normal-runtime leases preserve concurrent SQLite connections; migration
  requires an exclusive lease. An early exclusive-runtime version broke existing
  concurrency regressions and was corrected before publication.
- Independent review caught a constructor lease leak on malformed SQLite and an
  implicit standalone-provider plaintext fallback. Both were fixed and regression
  tests added. Fixtures now explicitly opt in and concrete owner auth cannot.
- Two pre-existing adversarial fixture reads now use the runtime helper rather
  than expecting plaintext from SQLite. Their forgery assertions are unchanged.

Verification remains in progress; final PR evidence records exact tested heads.

A further independent migration review found that table-name allowlisting could
copy an added private plaintext column. Migration now checks exact reviewed
column contracts and required table groups, refuses unknown/missing/generated
columns, and tests optional HTTPS journal preservation. Speculative future
source-grant tables are refused until their runtime integration is reviewed.
