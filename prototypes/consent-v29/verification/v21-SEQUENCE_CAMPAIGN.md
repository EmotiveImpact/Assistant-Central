# Offline consent state-sequence campaign

Scope: isolated fictional v21 copy. No external/provider/browser execution,
publication, accounts, credentials, dependency installation or security changes.

## Confirmed defects and bounded fixes

1. An already-open generic session did not recheck its durable `sessions` context
   on projection restoration. Changing/deleting that row after processing a request
   allowed response context/preview/history lookup to disclose it, while the owner
   received-message view correctly refused. The invariant is now enforced in
   `GenericPersistentSession._restore`, shared by projection consumers.
2. Agent inbox read and individually validated at most two raw transition rows.
   Invalid linkage, duplicated transitions, or an altered composed request could
   therefore be exposed without validating complete history. Inbox now validates
   the entire projection and exact composed request/result before selecting any
   recipient content. Its returned schema and lack of owner authority are unchanged.
3. New proposal aliases could skip projection validation when a matching fingerprint
   existed. New aliases now require a coherent restored projection. Valid terminal
   exact-history aliases still work and cannot resend or renew authority.

These are local durable-store-corruption defenses, not demonstrated remote agent
exploits. The local database remains trusted storage. Legacy scheduling is untouched.

Changed production paths: `generic_session.py`, `generic_owner_workflow.py`,
`agent_proposals.py`. New reusable tests: `tests/test_state_sequence_campaign.py`.

## Unique campaign work (not multiplied by verification reruns)

Seven unittest methods, with subcases rather than inflated per-seed test counts.

- Ordered interleaving seeds: 918273, 271828, 314159, 161803.
- Each seed schedules four scopes (both capabilities, each requester direction),
  five lifecycle phases and 24 probes per scope/phase. Exactly 1,920 scheduled and
  executed top-level probes: 1,545 expected refusals, 209 reads, 166 storage reopens.
  Each probe compares all four durable snapshots; no invalid call changes another
  scope. Nested assertions/read calls and fixture setup are not counted as probes.
- Five explicit progression steps per scope separate approval, submission, receipt,
  processing and the response lifecycle. Receipt-only phases expose no contents.
  Caller mutation, wrong owner/scope/capability/linkage, forbidden agent methods,
  authority-field injection, stale review digests and reopen are interleaved.
- Eight history/fault schedule seeds: 73000 through 73007, each with all four
  capability/direction combinations: 32 scenario instances. Scenarios cover repeated
  defer then decline; expiry plus explicit replacement; contact revocation; signed
  unused withdrawal; lost receipt; failure before receipt plus cancellation;
  receipt-before-cancellation blocking; and injected transaction failure.
- Those 32 instances use 128 distinct proposal alias IDs and 384 alias dispatch/import
  calls (256 before scenario action, 128 after reopening). Exact original review IDs
  remain fixed across expiry, replacement, refusal, withdrawal and terminal states.
- Additional deterministic subcases cover changed/deleted session rows, malformed
  linkage/duplicate/altered history, coherent terminal aliasing, and SQLite-trigger
  failure during processing followed by reopen/retry with one dispatch attempt.
- One selected real disposable signer/executor process regression proves corrupted
  durable context blocks both response and agent-inbox disclosures, then recovers
  after exact restoration. Existing aggregate tests separately cover concurrent
  preparation, stream/parser bounds, HTTP and other process paths.

No new random concurrency scheduler or OS-crash campaign was added. Random schedules
are deterministic; cryptographic fixture keys/nonces are intentionally freshly
created. The seven tests use 64 in-process scoped fixture instances and one real
process fixture, not thousands of child startups.

## Evidence and failed attempts

- `sequence-initial.txt`: initial response-context corruption reproduction, 1 test,
  24 failed subchecks (3 entry points x 2 corruptions x 4 capability/direction cases).
- `sequence-inbox-initial.txt`: initial raw-inbox reproduction, 1 test, 7 failures.
  That run stopped during the first scope after the final non-subtest assertion;
  it did not execute the remaining three scope instances. Final tests do cover them.
- `sequence-focused.txt`: final seven-test focused run and exact probe counters.
- `sequence-full.txt`: aggregate run started before the final alias/check additions;
  do not treat it as final immutable-source verification.
- `sequence-full-final.txt`: aggregate run after production/test changes were frozen.

Remaining limits: no real-provider acceptance, native browser/dialog/accessibility
verification, persistent inbox deployment, production key custody, remote identity,
network transport, multi-process SQLite contention or arbitrary disk corruption
recovery claim. The suite fails closed on tested corruption; it does not repair it.

Constructor limit: creating/reopening a generic session still reconstructs a missing
metadata row from the trusted immutable Task, then validates remaining transitions
against it. The fix rejects missing or mismatched metadata for already-open projection
consumers; it does not authenticate storage or prohibit that existing initialization
behavior. Reconstructing metadata has not demonstrated an authority bypass. An
existing mismatched context is rejected on reopen. No constructor change was made.

Final verification: all 635 Python tests pass on frozen source; all 137 existing
DOM-model checks pass (not browser tests); changed Python files compile. Source
SHA-256 records in `sequence-source-sha256.txt` were rechecked after the final run.
The final aggregate's probe counters match the focused campaign exactly. Verification
reruns are not additional unique seeds or scenarios.
