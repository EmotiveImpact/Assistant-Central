# Owner connection and transfer workspace

Implementation owner: `/root/build_transfer_interface`, coordinated with
`/root/advance_central_network`. Draft PR #16 builds on reviewed main
`fccc516e9192edd9c4a3ec3226d2acf153914c50`, including #8 and #13.

Owned scope: server/UI, `pilot/owner_transfer.py`, the narrowly coordinated
one-shot preparation/network split in `pilot/https_exchange.py`, focused tests,
CI test invocation and documentation. No auth/runtime/provider/workflow/storage
or source-grant core edits. #14 and #15 ownership was checked before work.

The implementation adds host-selected connections, current retained outbox state,
immutable attempt inspection, exact reviewed send/retry/import/receipt controls,
and a bounded network-only worker so owner controls remain responsive.
Read [the setup and limits](../../pilot/OWNER_TRANSFERS.md).

Local 288-test cumulative checks and 30 UI model tests pass. Independent review
identified an uncertain worker-submission gap; capability-owned dispatch state
now fixes it, with both independent regressions passing. Final cumulative checks
and hosted desktop/mobile Chromium evidence are in progress. The hosted actual
HTTP UI suite passes; the supplementary transfer script needed an explicit wait
for a newly opened dialog before checking its freshly unchecked confirmation. Local Chromium cannot start because the environment disallows its
process singleton socket, including after a permitted escalation. No browser
pass is claimed here. No public deployment, real owner data or live credentials.
