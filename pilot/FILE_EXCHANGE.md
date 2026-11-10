# Owner-controlled encrypted file exchange

This optional offline adapter lets separately controlled devices exchange the
pilot's existing signed ciphertext through a transport their owners select.
It does not host a public service, enrol peers, release drafts, accept tasks,
execute work, enable providers, or change source permissions. Tests use only
fresh disposable owners, fictional passwords and synthetic text. Actual
cross-device deployment and real-person identity verification remain untested.

## Explicit handoff

Use the pinned dependency in `pilot/requirements.txt`. First independently
compare and enrol the full peer fingerprints using the existing owner workflow.
Review and release a synthetic proposal there. Take its exact message ID from
the authenticated outbox. Stop that owner's server before these commands: the
CLI takes the same exclusive authentication-store lock and refuses if it is held.
It never kills a running service. Both existing auth and runtime stores are
required before prompting; a missing runtime is not silently initialised. This
is not full backup/rollback protection. Restart invalidates old sessions. Passwords
are entered privately, never accepted in arguments; unavailable private terminal
input fails closed instead of falling back to echoed input.

Create a locally owned, mode-0700 handoff directory on each device. On device A:

```sh
python -B -m pilot.file_exchange --directory /private/owner-a export \
  --message-id proposal-EXACT_DIGEST --output /private/handoff/task.json
```

Transfer the encrypted file with a channel you explicitly choose. This tool
neither selects nor performs that transfer. On device B, place the file in its
private handoff directory, owned by its local user with mode 0600:

```sh
python -B -m pilot.file_exchange --directory /private/owner-b import \
  --input /private/handoff/task.json --receipt-output /private/handoff/receipt.json
```

Move the receipt back through your chosen transport and import it on A:

```sh
python -B -m pilot.file_exchange --directory /private/owner-a import \
  --input /private/handoff/receipt.json
```

A receipt means **durable receipt only**, never owner acceptance, execution,
provider permission, or successful recall. Restart the normal owner service to
review and accept/reject the inert received proposal. Decisions, return
artifacts and cancellation packets use the same export/import path. Cancellation
cannot recall copied files and takes effect remotely only after observed.

## Recovery, not automatic retry

Export calls the existing authenticated `prepare_delivery` first, durably
marking the exact original packet uncertain and incrementing its attempt count.
Output success does not prove delivery. Failed output also consumes that attempt;
never infer rollback from an exception. The existing five-attempt limit, expiry,
revocation and cancellation remain authoritative. This module never reseals a
proposal, resets attempts, renews expiry or sends in the background.

Import uses one authenticated runtime transaction for verification, application,
replay history and the original signed receipt cache. Duplicate packets return
the same cached receipt without reapplication. Receipts never generate receipts.
If import committed but saving the receipt failed, inspect history then recover
the original using the incoming message ID and a *new* output filename:

```sh
python -B -m pilot.file_exchange --directory /private/owner-b receipt \
  --message-id proposal-EXACT_DIGEST --output /private/handoff/recovered.json
```

Recovery does not renew a receipt's one-hour validity. An expired receipt may be
saved unchanged for inspection but cannot newly acknowledge delivery at the peer.
If a runtime or filesystem call is interrupted, its outcome may be uncertain.
Inspect retained runtime state and files before choosing any explicit next step.
Partial files are retained, never deleted or overwritten automatically.

## File boundary

Only exact encrypted packet objects are stored. Actual input bytes, including
whitespace, are bounded to 32768 before strict UTF-8 JSON parsing; duplicate
members, nonfinite constants and malformed packet shapes are refused. Reads
reject detectable concurrent size/timestamp changes. Signature and pinned-peer
checks still occur in the authenticated runtime before any application.

Directory components are opened without following links and held by descriptors.
Ancestors must be owned by root or the current user and not group/world writable,
except root-owned sticky directories such as `/tmp`. The immediate parent must
be private and locally owned. Inputs must be private, locally owned regular files
with one hard link; symbolic links, FIFOs and devices are refused. Outputs use
exclusive mode-0600 creation and file/directory fsync, never overwrite or follow
an existing target. Failed writes may leave a partial or complete private file.
The runtime/auth stores retain their existing protection model.

These controls do not protect against root or a malicious process with the same
OS account that can modify the owner's memory/stores, race file contents, or
change permissions. Ciphertext still reveals protocol metadata and approximate
content size. A selected transfer service can retain copies. Do not use real
credentials, private source data or production workloads in this pilot.

## Verify

```sh
python -B -m unittest pilot.tests.test_file_exchange -v
python -B -m unittest discover -s pilot/tests -v
python -B -m pilot.file_exchange_demo
```
