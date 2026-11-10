# Authenticated HTTPS exchange work notice

Coordination-only first commit, before implementation.

- Coordinator: Assistant Central integration task; implementation owner: authenticated HTTPS exchange worker.
- Exact base: PR #12, branch `feat/https-ciphertext-mailbox`, commit `2b7e478c67b0bc53c37d2e8147d4d41156ba08e4` (depends on #11 file exchange).
- Goal: authenticated owner adapter/CLI for explicit ciphertext HTTPS sending and quarantined packet import. Preserve original packet bytes, record uncertain delivery before network, require explicit recipient/destination and retries, and never interpret HTTP acknowledgement as receipt, acceptance or execution.
- Claimed new paths only: `pilot/https_exchange.py`, `pilot/https_exchange_demo.py`, `pilot/HTTPS_EXCHANGE.md`, `pilot/tests/test_https_exchange*.py`, and this notice. No edits to auth/runtime/server/UI/file exchange/HTTPS carrier/mailbox or other workers' files.
- Verification: authenticated two-owner synthetic loopback TLS flows, restart and duplicate receipts, wrong/stale sessions, cancellation/source/recipient/expiry/revocation gates, malformed quarantine, failed/lost/dishonest ACKs, exact bytes, explicit retry accounting, CLI safety, focused/full tests and existing checks.
- Boundaries: no real providers, remote deployment, persistent credentials/certificates, personal data or external-agent communication. Only disposable local identities/TLS fixtures. No merge by this worker.
