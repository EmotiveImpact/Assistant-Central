# Authenticated owner HTTPS exchange

This synthetic-only adapter connects the authenticated runtime to the optional
[HTTPS quarantine carrier](HTTPS_MAILBOX.md). The CLI adds no public deployment, provider call, automatic import, background
retry or execution. The optional [owner transfer workspace](OWNER_TRANSFERS.md)
now exposes separately reviewed operations through host-selected connections.
Both the owner service and any other process holding its store must be stopped
before using the CLI. The mailbox is a separate, explicitly enabled process and
never gets an owner password or session. Use disposable fictional owners only.

## Explicit operations

First enrol the exact peer fingerprint independently, create and review an exact
proposal, then release it using the existing owner workspace. Stop that workspace
before running the CLI. Configure the recipient's separate mailbox as described
in HTTPS_MAILBOX.md. This adapter neither starts it nor provisions certificates.

```sh
python -B -m pilot.https_exchange --directory /private/owner-a send \
  --message-id proposal-EXACT_ID \
  --destination https://chosen-host:443/v1/quarantine \
  --recipient EXACT_RECIPIENT_FINGERPRINT
```

The command privately prompts for the existing local owner password. Passwords
and bearer sessions are never accepted as command arguments or sent to a peer.
An unsafe/echoing password prompt is refused. `--ca-file /private/test-ca.pem`
selects an explicit disposable test CA for this connection, not system trust.
TLS verification cannot be disabled. Destinations cannot contain user information,
queries or fragments. Only the exact `/v1/quarantine` route is accepted, with no
redirects. A TLS hostname is not an enrolled owner fingerprint.

Every command is one explicit owner operation. The owner chooses both destination
and expected recipient; neither comes from packet content. `send` reads the
original signed ciphertext from the runtime's retained outbox, not a caller's
exported file. Unreleased, expired, cancelled, revoked or exhausted packets fail
closed. Queued proposals additionally recheck their retained source permissions
and, for returned artifacts, their accepted, current original task and exact
origin-only route. No new packet, identity, expiry or grant is minted for a retry.

After a previous delivery attempt (including file export), plain `send` refuses.
Inspect the selected message and its retained attempts first:

```sh
python -B -m pilot.https_exchange --directory /private/owner-a status \
  --message-id proposal-EXACT_ID
# Only after choosing another attempt, repeat send with --retry.
```

`--retry` permits one additional transport attempt only. It does not renew source
rights, recipient acceptance or execution consent. Outbox sends share the existing
five-attempt bound with file export; HTTPS sends also have a five-attempt bound
per message and a 1,024-entry total journal with no eviction. Cached receipt sends
have their own five-attempt bound. A different destination still consumes an
attempt for the same original packet. Manual carrier/file copies outside this
adapter cannot be recalled or counted by it.

## Import is separate from quarantine

Choose one exact digest-named private file from the recipient's quarantine. The
SHA-256 file digest identifies bytes, not sender authenticity. Supply the expected
sender fingerprint separately; do not trust one copied from an unknown packet.

```sh
python -B -m pilot.https_exchange --directory /private/owner-b import \
  --input /private/quarantine/EXACT_FILE_DIGEST.json \
  --file-digest EXACT_FILE_DIGEST --sender EXACT_SENDER_FINGERPRINT
```

The adapter verifies the name and selected raw-byte digest, bounded strict packet
JSON, expected sender and local recipient. Private, descriptor-pinned, no-follow,
single-link file checks apply. It leaves quarantine bytes unchanged. The existing
authenticated runtime then checks enrolled peers, signatures, encryption, expiry,
replay, source permissions and cancellation, and atomically applies the inert
item plus its original cached signed receipt. Import never accepts or executes
work. A separate reviewed local recipient decision is required. The importer
does not automatically scan, delete, repair or acknowledge quarantine entries.
An explicit duplicate import recovers the same cached receipt rather than
renewing it. The runtime's existing duplicate/replay semantics remain unchanged.

Explicitly send that original cached receipt back, using the original incoming
message ID, not the receipt's own ID:

```sh
python -B -m pilot.https_exchange --directory /private/owner-b send-receipt \
  --message-id proposal-EXACT_ID \
  --destination https://chosen-return-host:443/v1/quarantine \
  --recipient EXACT_ORIGINAL_SENDER_FINGERPRINT
```

For receipt-send attempt history, `status --message-id` takes the receipt message
ID returned by `send-receipt`, not the original incoming ID.

The sender must independently import the returned quarantine file under their
own authenticated session. Only that signed import can record durable receipt.
There are no receipts for receipts. The cached receipt is never renewed; expired
receipts cannot be sent. Cancellation and decision control packets are original
signed historical facts and can be transported explicitly even after their
associated item stops, subject to their own expiry and peer/attempt gates. A
cancellation receipt proves exposure only, not successful recall.

## Durability, authority and races

The adapter inserts a durable `uncertain` attempt journal row in the **same
runtime SQLite transaction** as the outbox attempt increment. Receipt sends
journal the original cached receipt in that transaction. Both commit before
staging or any network operation. A failed journal insert rolls back the outbox
increment. A crash after commit but before network conservatively consumes an
attempt; it is never reset or automatically retried.

A private temporary mode-0600 file contains the original canonical bytes retained
in the queue or receipt cache, unchanged. It is normally removed after the call;
a process/host crash can retain the private ciphertext copy. No owner password,
session, plaintext payload or private identity key enters the file or journal.
The journal retains message IDs, digests, recipient, packet kind and the explicit
credential-free destination URL in plaintext as transport metadata. It never
stores an HTTP response or upgrades its `uncertain` state on an ACK. Keep the
owner directory private and include metadata in the deployment threat model.

Immediately before handing off to the carrier, the adapter rechecks current
owner authentication, peer, expiry and proposal/source gates. It releases both
auth/runtime locks and holds **no SQLite transaction across network I/O**. A
logout, expiry or cancellation after that final gate cannot prevent or recall
an in-flight send. No post-network mutation can overwrite a later cancellation.
DNS, multiple resolved-address connection attempts and filesystem I/O inherit
the carrier's lack of a hard overall deadline. Do not claim instantaneous remote
withdrawal or prompt network completion. Runtime SQLite objects keep their
existing single-thread usage constraints. The optional owner workspace prepares
an accounted one-shot capability on that thread and dispatches only network I/O
on one bounded worker. The CLI still dispatches synchronously. A prepared
capability has a five-second monotonic start window, original expiry and clock
rollback check; a late start consumes the attempt without sending. These checks
do not re-authenticate or guarantee cancellation after the final owner gate.

A successful fixed HTTP ACK is an untrusted peer claim of quarantine. Even a
malicious mailbox returning that ACK produces `delivery: uncertain`,
`owner_acceptance: not_established` and `authorises_execution: false`. It cannot
create a signed receipt or an inbox entry. A signed receipt also is not owner
acceptance or execution permission. Unknown outcomes, including interrupted
preparation/import/staging/network, require state inspection and a fresh explicit
operation. No caught error triggers a fallback send or retries a different host.

## Verification and decisions

```sh
python -B -m unittest pilot.tests.test_https_exchange -v
python -B -m unittest discover -s pilot/tests -v
python -B -m pilot.https_exchange_demo
```

The demo uses existing disposable certificate fixtures, fresh fictional owner
identities, private temporary stores and two actual loopback TLS servers. It
exercises explicit send/import, original receipt return and duplicate recovery,
reviewed recipient acceptance, origin-only artifact return and cancellation.
It never prints credentials, creates persistent PKI, contacts a provider or uses
real personal data. This is not evidence of cross-device or Internet deployment.

Decisions:

- Use retained runtime packets rather than arbitrary exported paths, so every
  adapter send rechecks owner gates and accounts for an original attempt.
- Use one runtime transaction for journal and outbox accounting rather than a
  separate journal database with an unmodelled crash gap.
- Keep ACKs observational and all send rows uncertain rather than allowing a
  transport success to imply signed receipt, acceptance or work permission.
- Require a selected digest and sender for import rather than auto-ingesting all
  mailbox files; quarantine remains untrusted and no implicit enrolment occurs.
- Release locks before network rather than block owner controls behind DNS; an
  in-flight operation remains inherently non-recallable.
- Bound original receipt sends separately rather than queue/reseal receipts or
  create receipt-of-receipt loops. This adds an adapter journal, not a new grant.

Local verification on the cumulative #8–#12 base: 272 pilot tests (22 new adapter
and independent-review regressions), 20 isolation-harness unit tests, import
integrity, team/execution/integration/composition checks, synthetic demos,
25 interface-model tests and the actual HTTP/workflow contracts pass. The
consent full checkpoint passes with its pinned fixture dependencies, and all
39 targeted synthetic stdio checks pass. Actual Docker isolation and Chromium
are separate hosted checks; this adapter change does not claim a new local run
of either. Hosted exact-head evidence is recorded in the pull request.
