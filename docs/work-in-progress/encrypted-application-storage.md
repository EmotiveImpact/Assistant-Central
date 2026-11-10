# Encrypted application storage work notice

Coordinator: `/root/build_encrypted_storage`, coordinated with
`/root/advance_central_network`. Base: main `cca92a0f5d69a5893698689613819c83222bdb4a`.

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
