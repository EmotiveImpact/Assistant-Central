# Encrypted pilot exchange

`crypto.py` and `transport.py` provide real cryptographic packet validation and
durable local exchange records for the synthetic two-assistant pilot. They do not
make network requests. They are a new experimental protocol composition, not an
independently audited messaging standard or a production-security claim.

The primitive choices follow the upstream documentation for
[X25519 and HKDF](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/x25519/)
and [AES-GCM authenticated encryption](https://cryptography.io/en/stable/hazmat/primitives/aead/).
The repository uses its pinned `cryptography==50.0.0` dependency. Private keys
remain behind the local owner's authenticated `sign` and `exchange` operations.

## Pinned identities and exact packets

A public identity has exactly `owner_id`, `agent_id`, `signing_key` and
`exchange_key`. Keys use canonical unpadded base64url. The fingerprint is SHA-256
of the canonical public descriptor. Enrolment requires the exact fingerprint
explicitly supplied through the authenticated local owner's control. There is no
trust on first receipt, automatic pin replacement or revival after revocation.
Exchanging a fingerprint through a trustworthy independent channel is still the
operator's responsibility; a hash alone does not verify a person's identity.

Every packet uses a fresh ephemeral X25519 sender key and random 96-bit AES-GCM
nonce. HKDF-SHA256 derives the 256-bit encryption key from the shared secret,
using the complete canonical header hash as salt and a protocol-specific info
string. AES-GCM authenticates that header as additional data. The sender's
Ed25519 key signs the header and ciphertext. The receiver verifies the explicitly
enrolled sender and exact recipient fingerprint before invoking its protected
key exchange operation.

The closed header binds protocol version, message ID, kind, sender and recipient
fingerprints, immutable context, artifact ID, proposal ID, creation time, expiry,
ephemeral public key and nonce. Supported kinds are `proposal`, `decision`,
`cancel` and `receipt`; the runtime validates each kind's application payload.
The packet limit is 32 KiB, payload limit 16 KiB, maximum nesting depth eight and
maximum lifetime one hour. Noncanonical encodings, unknown header members,
invalid signatures, foreign recipients, expired originals and oversized payloads
are rejected. An HTTP JSON parser must additionally reject duplicate raw JSON
members before constructing the packet object.

This construction does not claim forward secrecy: compromise of a recipient's
long-term exchange key can expose recorded packets addressed to that key.
Key rotation and recovery require a separately reviewed identity transition;
this initial pin store refuses silent replacement.

## Persistence and exact retries

`PeerExchange(db, local_public, clock=...)` binds one immutable identity to one
SQLite connection. Its tables use a `peer_` prefix. Methods join an existing
transaction or create a `BEGIN IMMEDIATE` transaction when called alone.
The runtime must wrap `receive` and its proposal/decision admission in the same
transaction. Committing a transport receipt separately and then attempting the
application effect would lose that atomicity guarantee.

| Method | Contract |
| --- | --- |
| `enroll_peer(public, expected_fingerprint)` | Explicit immutable active pin; no automatic discovery |
| `queue(packet)` | Stores one exact authenticated outgoing packet; the message ID cannot be rebound |
| `prepare_attempt(message_id)` | Commits `uncertain` and increments the attempt count before returning the exact stored ciphertext |
| `pending()` | Metadata for unexpired, active-peer packets with remaining attempts |
| `receive(packet, auth, session)` | Authenticates the local session, validates/decrypts an enrolled peer's original and durably deduplicates it |
| `receipt_for(auth, session, incoming_id)` | Creates or returns the same cached signed/encrypted durable-receipt packet |
| `cancel(message_id)` | Stops local attempts; does not recall exposure or assert recipient cancellation |
| `revoke_peer(fingerprint)` | Blocks new sends/receives through that pin; never removes history |

The sender may retry only the original stored ciphertext, at most five explicit
attempts and only before expiry. There is no background retry loop. A restart or
missing HTTP response does not generate another encryption, message ID or
application operation. The inbox rejects an existing message ID with a different
packet digest; exact duplicates return metadata without decrypted payload. Both
databases retain finite history and never evict replay records automatically.

Local cancellation of an uncertain outbox entry preserves uncertainty about what
the recipient has already received. A later valid receipt is retained alongside
the local cancelled state. Application cancellation uses its own authenticated
`cancel` message and runtime tombstone rules; transport cancellation alone cannot
undo an accepted artifact or executed work.

## Receipts and loss

An HTTP response such as `{stored: true}` is only an untrusted quarantine result.
It cannot update the cryptographic outbox state. A transport receipt must itself
be signed, encrypted, received from the original pinned recipient, and bind the
original packet digest, message ID, context, artifact and proposal. Its payload
says `durably_received_only`. It does not prove owner acceptance, execution,
provider authority, cancellation or onward-disclosure permission.

Receipts are created only for a previously validated non-receipt inbox entry.
There are no receipt-of-receipt loops. Once created, the same cached receipt is
returned to duplicate deliveries. A different receipt cannot replace the first
correlated receipt. Cached receipts expire and are never silently renewed; an
unreconciled sender can remain uncertain after their lifetime ends. The pilot
must preserve that uncertainty instead of creating new work to hide it.

If receipt/application admission rolls back, the inbox fence rolls back with it.
If commit succeeds but its acknowledgement is lost, a retained original packet
can be submitted again: duplicate admission returns metadata and the same cached
receipt. All of these claims depend on retaining the original local databases.
Backup rollback, deletion of replay history, a compromised local process and
same-UID/root access remain outside this prototype's protection.

## Verification

Run:

```sh
python -B -m unittest discover -s pilot/tests -p test_transport.py -v
```

The 29 transport tests exercise exact encryption/signatures and direction,
explicit enrolment, changed pins, malformed packets, bounds, expiry, sessions,
altered-ciphertext replay, concurrent duplicate delivery, restart, bounded exact
retry, cancelled outbox history, wrong/forged receipts, transactional rollback and
the actual encrypted owner-vault signing/key-exchange API. Test identities and
payloads are disposable fiction. These local tests do not prove Internet
interoperability, independently administered operating systems or production
protocol security.
