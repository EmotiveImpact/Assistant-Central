# Owner connection and transfer workspace

The loopback owner workspace can inspect and explicitly transfer original packets
through host-configured HTTPS mailboxes. This is synthetic pilot functionality,
not an Internet deployment or a real-owner identity guarantee. Live provider calls
remain disabled. The owner service itself still listens only on `127.0.0.1`.

## Trusted host configuration

Create a private mode-0600 JSON file under a private mode-0700 directory. Supply
its absolute path at startup with `python -B -m pilot.server serve --directory
/private/owner --transfer-config /private/transfer-config.json`. The configuration
is read once. Changing it requires a restart, which invalidates existing sessions.
The configuration is not a credential store and must contain no passwords or tokens.

```json
{
  "version": "assistant-central-owner-transfer/1",
  "connections": [
    {
      "id": "fictional-peer",
      "label": "Fictional peer mailbox",
      "peer_fingerprint": "REPLACE_WITH_INDEPENDENTLY_VERIFIED_64_HEX_FINGERPRINT",
      "destination": "https://chosen-host:443/v1/quarantine"
    }
  ],
  "quarantine_directory": "/private/owner-quarantine"
}
```

This example is not usable until the exact fingerprint and host are deliberately
configured. The optional `ca_file` connection field selects a private absolute
path to a disposable test CA; TLS verification cannot be disabled. Omit it for
system trust. The quarantine directory is optional if imports are not needed.
At most 16 connections are permitted. Connection IDs, labels and peer fingerprints
are unique per ID; no destination is inferred from incoming content. A host
configuration is not peer enrolment or permission to send.

Under **Trusted peers**, independently verify the full public identity and
fingerprint with the other owner, then select the exact configured connection.
Enrolment does not send anything. Local loopback enrolment remains available and
separate. Only the operator can change a connection, CA path or quarantine root.
The browser accepts connection IDs and digest selections, never filesystem paths,
URLs, credentials, activation flags or arbitrary packet content for a transfer.

## Separate owner actions

1. Prepare, review and release an exact proposal in the existing workspace.
2. Open **Transfers**, choose an exact retained outbox packet and connection.
3. Inspect its destination, complete recipient fingerprint, original packet digest,
   expiry, current outbox state and immutable HTTPS attempts. Confirm the unchecked
   exact-transfer statement and choose **Send original packet once**.
4. Refresh saved state explicitly to inspect the transport observation. A fixed
   mailbox ACK is untrusted. It never changes an attempt row from `uncertain`.
5. At the receiver, choose one quarantine digest and independently expected sender
   connection. Inspect and explicitly import it. Signature/current permission
   checks happen at import; the review labels packet metadata as untrusted.
6. Inspect any resulting proposal and make a separate accept/reject decision.
   Import does not send a receipt. To return one, separately inspect and send the
   original cached receipt under **Original cached receipts**.
7. The sender separately imports that returned receipt. Current outbox state may
   then show **Signed receipt observed**, while the original attempt rows remain
   uncertain historical facts. Neither is recipient acceptance or execution consent.

The **Sync exchange** button continues to perform only the pre-existing local
loopback exchange. It does not send to HTTPS destinations. No page visit, refresh,
review, import or startup automatically sends an HTTPS packet or retries one.

## Concurrency, failures and honest limits

The owner thread validates the current session, exact review digest, selected
connection, retained packet, peer, source permissions and expiry. It records the
attempt before any network operation and stages the original ciphertext in a
private temporary file. The review digest includes current attempts, so resending
a stale POST cannot silently consume another retry, including after a lost response.
A subsequent retry requires a new review and a separate explicit action.

One network-only worker consumes a one-shot prepared capability. It cannot read
or mutate the runtime database, access owner keys or re-authorise a packet. An
original-expiry/clock-rollback check and five-second monotonic start window prevent indefinitely
retained preparation from starting a late send. The single transfer slot rejects
new sends while one is in flight rather than queueing them. A consumed, failed,
expired or abandoned capability cannot dispatch again. Its attempt stays consumed.

Status, withdrawal and sign-out remain responsive while the network worker is
running. The authenticated final gate occurs during owner-thread preparation;
a logout or cancellation after that gate cannot guarantee prevention or recall,
even if network dispatch has not yet started. The bounded worker start check is
not a second authority check. Completion does not update an outbox row and cannot
overwrite a later withdrawal. An ACK is only an in-memory observation and is lost
on restart; durable immutable attempts remain inspectable.

A timeout, lost response or failed post-mutation refresh fences browser mutations
until an explicit successful state refresh. Even then, a fresh exact transfer
review is needed. Quarantine entries remain untouched; duplicates recover original
receipts, never renew them. The UI does not edit, purge or reset attempt history.
Local cleanup removes normal temporary staging; a host crash may leave a private
ciphertext copy. No browser token, password, decrypted body or CA path is returned
in transfer metadata. Existing outbox metadata and HTTPS destination history are
not encrypted by this feature.

DNS/network I/O still lacks a hard overall deadline. One slow transfer can occupy
the transfer slot and delay graceful server shutdown, but not owner HTTP controls.
Do not claim prompt delivery, instant withdrawal, cross-device acceptance or
production isolation. Mailbox provisioning, certificates and deployments are
separate explicitly operated tasks. Same-UID/root compromise is outside this pilot.

## Routes and tests

- `GET /api/state` adds redacted `transfers` metadata, with all retained outbox
  states (including received/stopped), original cached receipt references,
  digest-only quarantine choices and the last in-memory transport observation.
- `GET /api/transfers/:connection/:kind/:id` reviews `outbox`, `receipt` or
  `quarantine`; it cannot create a receipt or change attempt accounting.
- `POST .../outbox/:id/send` or `.../receipt/:incoming_id/send` takes only
  `{review_digest, retry}`. Exactly one action is permitted from the fresh review.
- `POST .../quarantine/:digest/import` takes only `{review_digest}`.
- Enrolment can take `connection_id` instead of a local loopback `endpoint`, never both.

All routes retain bearer authentication, exact origin/Host checks, strict JSON and
no-store responses. Targeted checks: `python -B -m unittest
pilot.tests.test_owner_transfer`, `node --test pilot/web/tests/transfers.test.mjs`
and `node pilot/web/tests/browser_transfers.test.mjs` with the existing Playwright
setup. The browser suite mocks only HTTP, while Python tests exercise the real
owner server, authentication, SQLite and transfer preparation. Existing HTTPS
adapter tests retain their real loopback TLS coverage. Hosted browser evidence is
recorded on the pull request; do not infer it from source inspection.
