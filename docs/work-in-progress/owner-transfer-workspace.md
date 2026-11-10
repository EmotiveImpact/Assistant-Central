# Owner connection and transfer workspace

Implementation owner: owner-interface maintainer, coordinated with the
integration maintainer. Draft PR #16 builds on reviewed main
`fccc516e9192edd9c4a3ec3226d2acf153914c50`, including #8 and #13.

Owned scope: server/UI, `pilot/owner_transfer.py`, the narrowly coordinated
one-shot preparation/network split in `pilot/https_exchange.py`, focused tests,
CI test invocation and documentation. No auth/runtime/provider/workflow/storage
or source-grant core edits. #14 and #15 ownership was checked before work.

The implementation adds host-selected connections, current retained outbox state,
immutable attempt inspection, exact reviewed send/retry/import/receipt controls,
and a bounded network-only worker so owner controls remain responsive.
Read [the setup and limits](../../pilot/OWNER_TRANSFERS.md).

Cumulative verification: 377 pilot Python tests, 20 isolation-harness unit tests,
30 interface model tests, both actual HTTP contracts and import integrity pass.
Independent review regressions cover uncertain worker submission and staging
cleanup. Hosted Chromium passes the existing owner flow, actual HTTP and real
disposable TLS transfers, and a mocked lost-response/failed-refresh supplement.
Desktop and mobile screenshots were inspected. Hosted Docker isolation passes.
The aggregate frozen consent checkpoint is recorded in the pull request checks.

The live transfer browser test covers original send, duplicate quarantine import
and separate cached receipt return, not first import or real-person acceptance.
Local Chromium cannot start because this environment disallows its process
singleton socket, including after a permitted escalation. No local browser pass
is claimed. No public deployment, real owner data or live credentials.
