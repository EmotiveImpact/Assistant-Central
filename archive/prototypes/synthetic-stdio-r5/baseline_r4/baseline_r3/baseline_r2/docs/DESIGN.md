# State and trust model

## Boundaries

The ordinary endpoint process is fixed as either fictional Alice or fictional Bob
at trusted startup. It generates one Ed25519 signing key, one X25519 decryption
key and a random incarnation. Private identity keys stay in that process's memory;
there is no private-key export command or private-key file. Each process stores
its own public descriptor, the other process's public descriptor, and one immutable
public task/context. The supervisor exchanges only public descriptors, task data,
grants, released packets and signed evidence. It never creates or receives the
private keys in the ordinary fixture.

This is application-level separation, not OS security isolation. Both processes
run as the same OS user. A compromised process or supervisor could access the
other process's filesystem or memory under that user's permissions. The fixture
holds both owner-control descriptors, so it remains trusted for the synthetic
owner approvals and initial public-key bindings. There is no identity enrollment,
human authentication, contact discovery, OS sandbox, hardened key custody, or
remote-attestation claim.

Each endpoint receives two distinct inherited anonymous-pipe lanes:

- **Owner:** `describe`, `inspect`, `packet`, `configure`, `allow_receive`,
  `revoke_receive`, `cancel`, `refuse`, `approve_send`, and `process`.
- **Peer:** only `deliver` and `evidence`, both with exactly `op` and `value`.

There is no peer-supplied actor selector, context selector, worker selection,
owner-routing field, arbitrary signer, control operation, plugin, or remote tool
execution. Unknown/extra fields are rejected. The owner pipe is privileged and
represents a synthetic owner's explicit decisions, not authenticated human UI
consent. `inspect` is owner-only; peer input cannot read the local projection.

## Immutable task and recipient-issued grant

There is exactly one task and one request/result pair per disposable endpoint
incarnation. Alice sends the request; Bob sends the result. The only capability
is `fictional-answer/1`, with a nonempty UTF-8 text payload of at most 1,024 bytes.
Text is data, never executed as code or interpreted as control instructions.
The context digest identifies an opaque fictional fixture scope, not a commitment
to the exact question. Incoming consent authorizes one bounded request/result from
the fixed peer under that scope, not a recipient preview of its exact text. The
sender owner approval separately binds its exact outgoing payload.

An incoming grant is signed by its recipient and binds:

- Exact task ID, context digest and capability/version.
- Exact sender, recipient, direction and request/result kind.
- Both public identity/incarnation descriptor digests.
- A random 128-bit nonce and recipient-owned monotonically increasing epoch.

A new `allow_receive` operation creates a fresh epoch/nonce and replaces the
current grant. The recipient requires exact equality to its locally stored active
grant, verifies its own signature, and checks the bound scope. Sender-asserted
positive epochs never override recipient-local policy. Old signed grants do not
survive revoke/regrant.

There is **no clock-based expiry**. A grant lasts until local replacement, revoke,
cancel/refuse or endpoint exit. This is a disposable-run simplification, not a
production revocation/expiry policy. The sender can check the remote grant's
signature and scope but cannot know whether the recipient has since revoked it.
The recipient's own ingress makes that decision.

## SQLite ownership and state

There is no shared application/session database. Each endpoint owns:

- `meta`: its own public identity, immutable task, peer public descriptor.
- `policy`: current local incoming grant/epoch, active flag and terminal state.
- `outbox`: its own approved-and-released outgoing message and exact packet,
  plus received/processed evidence learned from the recipient.
- `inbox`: locally accepted incoming bytes, exact packet hash, persistence receipt,
  and an optional explicit processing proof.
- `owner_operations`: exact operation ID, command hash and committed response.

A separate `processed_projection` is computed only from locally processed inbox
records. Receiving a request persists bytes and a receipt, but does not expose
its payload in that processed projection. Owner diagnostic inspection labels the
unprocessed inbox entry with a null payload. This is a projection rule, not a
claim that the owner process or local plaintext database cannot read the bytes.

Alice's outgoing-request commitment and Bob's incoming-request processing are
separate facts in separate stores. Alice does not write Bob's application state,
and Bob does not write Alice's. Outbox flags are explicitly named
`received_evidence_present` and `processed_evidence_present`: absence means no
separate proof was recorded, not that the event did not occur. Processing evidence
may arrive before a separate receipt and therefore yield false/true respectively.
No synthetic receipt is invented to fill that gap.

## Approval and release, not a dispatcher

`approve_send` is deliberately a **combined owner approval and release**. It binds
the exact payload, capability/task, recipient grant and (for a result) request
link. It generates one encrypted packet and commits that packet plus the operation
response to the sender's outbox. The response then releases the publishable bytes
to the trusted fixture. Its response says `release=approved_and_released`.

There is no separate queue/dispatch service and no automatic transmission. This
differs from v29's submit/dispatch workflow. Once the response could have escaped,
those bytes may already be in flight. A lost response is not proof that approval
or release failed.

An exact repeated owner operation ID/command yields the same packet and message
ID, with `historical_replay=true` rather than renewed approval. Changing a command
under the same operation ID is rejected. Local terminal cancel/refuse blocks both
`packet` retrieval and packet-bearing `approve_send` replay. It cannot recall
bytes already released to the fixture. There is no automatic retry anywhere.

## Recipient admission

For a new packet, recipient ingress independently:

1. Checks fixed outer direction, protocol and both identity/incarnation bindings.
2. Authenticates/decrypts the envelope and verifies the expected peer's signature.
3. Checks exact message fields, ID, payload byte bound and immutable local scope.
4. Checks local task is nonterminal and its current incoming grant is active and
   exactly matches the signed grant in the message.
5. Checks the one incoming request/result slot is not already used.
6. For Bob's incoming request, requires no request link.
7. For Alice's incoming result, requires Alice's own committed outgoing request,
   exact request ID/digest, and Bob's valid `processed` claim bound to that request's
   entire message, original encrypted packet, grant, scope and Bob incarnation.
8. In one SQLite transaction, stores incoming bytes and a signed persistence
   receipt. For a result, it also stores the verified embedded request-processing
   evidence in Alice's own outbox. Failure rolls back both writes.

Bob's ordinary `approve_send` result path independently requires Bob's own inbox
request already be processed, and requires that incoming request grant still be
current. Revoking Bob's receive consent therefore blocks a new result disclosure,
even if he processed the request earlier.

Bob's result embeds his request-processing proof. Alice can thus accept a valid
result even if the standalone proof has not arrived yet. This is deliberate
ordering tolerance, not a shared state projection.

A malicious Bob holding Bob's private key can falsely claim to have processed his
request. Alice can authenticate the claim and bind it to her own authorized
request, but cannot cryptographically prove Bob's internal transition, human
approval, model work, or external-world effect. A test deliberately demonstrates
this limit. Even such a Bob cannot bypass Alice's own request commitment/current
local receive policy.

## Persistence, processing and evidence

`received` evidence attests the recipient's local inbox persistence commit only.
`processed` evidence attests its explicit local processing transition only. Both
are separately domain-signed and bind exact message ID, complete message digest,
original packet digest, grant digest, full scope, processor identity/incarnation,
and status. A receipt cannot be used as a processing proof or vice versa.

`process` is an owner operation. It rechecks current local grant and terminal state
before a new transition, then atomically stores the proof and operation record.
Evidence is returned only after commit. A peer cannot invoke processing. There is
no actual email send, calendar update, payment, model action or external side effect
represented by the processing transition.

A sender updates its own evidence records only after verifying the peer's signed
proof against its own exact outbox packet. It cannot directly mark the peer's
inbox as processed. Historical received/processed evidence remains admissible
after local cancellation, because learning that a prior disclosure happened does
not reactivate authorization. Receipt arriving after processing evidence never
downgrades the latter.

## Replay, revocation and refusal

Exact ingress replay is recognized only after authenticated decrypt/signature,
shape and scope checks and comparison of the exact original packet hash/body.
A new packet re-encrypting the same message ID is not an exact replay. Same-ID
changed content, changed wire, or a second message in the fixed incoming slot is
rejected. Exact replay returns stored historical evidence and performs no new
application transition, including after revoke/cancel. It is labeled historical.

- `revoke_receive`: disables incoming consent; no new incoming admission or
  unprocessed transition can use the old grant. Regrant does not revive an older
  received-but-unprocessed message. There is no general recovery/remapping feature.
- `cancel` / `refuse`: terminal locally, disables incoming consent and blocks new
  outgoing approval/release, new admission and new processing. The first terminal
  state wins. These names have the same security effect, with distinct reason labels.
- Exact historical owner-operation replay does not execute again. A historical
  `allow_receive` response may return an old public grant but cannot reactivate it.
  Packet-bearing replay is separately fenced by terminal local state.

Neither side can infer the other's current cancellation state from silence or a
sender-signed assertion. No cancellation notice protocol is implemented. Alice
cancelling after releasing a request cannot stop Bob accepting those already
released bytes while Bob's own grant remains active. This is explicitly tested.
Recipient-local revoke/cancel is what blocks later acceptance at that recipient.
Previously disclosed bytes cannot be recalled.

## Cryptographic experiment

This uses the installed `cryptography` implementation of Ed25519, X25519,
HKDF-SHA256 and AES-256-GCM. The new envelope is **not pinned A4A wire code** and
has no demonstrated A4A or native-host interoperability.

Each message uses a fresh ephemeral X25519 key and random 96-bit AES-GCM nonce.
The recipient's static X25519 public key and ephemeral key derive the encryption
secret. HKDF uses the canonical full outer header as info; AES-GCM authenticates
the same header as associated data. The plaintext contains the signed complete
message. Ed25519 signature domains distinguish message, grant, received and
processed under `independent-peer-experiment/1`.

Public key descriptors are trusted local fixtures, not certified identities.
There is no peer privacy review or key-rotation/recovery design. In particular,
compromise of a recipient's static private decryption key can expose captured
past packets; this is not a forward-secrecy claim.

Outer headers disclose protocol, sender/recipient labels, binding digests,
ephemeral public key, nonce and ciphertext size. Routing/timing/linkability and
receipt metadata are not hidden. The local stores contain plaintext application
bodies and public proofs. The supervisor sees grants and owner-released artifacts.
There is no complete metadata hiding, secure erasure, memory zeroization, core-dump
protection, log-retention policy, or production storage encryption claim.

## Pipes, deadlines, failures and restart

The wire is a four-byte big-endian length followed by strict UTF-8 JSON, with
1–65,536 payload bytes. JSON rejects duplicate keys, nonfinite/float values,
non-scalar Unicode, oversized integers/strings/collections, and excessive lexical
nesting before recursive JSON construction. Schemas then impose semantic bounds.

Owner and peer lanes are separately multiplexed. There is at most one in-flight
request/response per lane, with 4KiB read/write service chunks, a one-second
absolute partial-frame budget from the first byte, and a one-second pending-output
budget. Unread peer output does not indefinitely block owner controls: the owner
can act on its lane before the finite process failure. Same-lane concurrent client
calls are rejected, not silently interleaved. Peer framing errors, deadline expiry
or lane EOF end the disposable process. These are I/O bounds, not hard SQLite,
cryptographic CPU, scheduling, memory, or whole-action deadline guarantees. There
are no traffic quotas or production resource-isolation guarantees.

SQLite uses full synchronous commits and a rollback journal. Application writes
and operation records commit together. A failure before commit rolls back. A
failure after commit but before response leaves an uncertain result; tests inject
both boundaries. Explicit exact replay or authenticated evidence can reconcile
lost replies only while that endpoint incarnation remains available. The fixture
never automatically retries or replaces a process.

The client treats malformed responses, I/O faults and timeouts as uncertain,
poisons the session, closes descriptors, and attempts to stop/reap the process.
Shutdown uses finite grace/terminate/kill waits. Every child and temporary-state
cleanup is attempted even if another cleanup fails. Cleanup failures are reported
as uncertainty, not success. Client-side local encoding errors occur before I/O
and are not treated as a submitted mutation.

Private keys exist only in process memory. A new process refuses any occupied
SQLite store instead of adopting it with new keys. There is no same-identity
restart, durable-key recovery or receipt recovery after key loss. The fixture's
normal and failure teardown removes temporary state; it does not promise retained
diagnostic databases. Tests inspect temporary DBs before cleanup only. Beginning a
new experiment creates new keys, task, grants and empty stores, not a continuation.

The subprocess environment is a minimal explicit map, not inherited ambient
credentials/settings. Ordinary stderr uses a fixed redacted failure message.
Test-only malicious and fault workers are chosen solely by the trusted test
harness at startup and are never selected by peer messages.
