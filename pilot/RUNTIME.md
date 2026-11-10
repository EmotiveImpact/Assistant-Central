# Independently stored assistant runtime

`PilotRuntime` owns one enrolled assistant's private `runtime.sqlite`. It neither
opens the peer's store nor accepts owner labels as a decision authority. Each
public operation requires a current local session from `LocalOwnerAuth`; the
owner identity and key fingerprint are bound to the store at creation. The HTTP
host serves this runtime on one local worker. Its peer has a separate process,
authentication vault and database.

The implementation is a restricted synthetic pilot. Independent files and
processes do not protect against one administrator or a shared operating-system
account reading both directories. Use separately controlled OS accounts/devices
and a reviewed deployment before describing this as independent owner custody.
No live provider or real personal data was used to verify this runtime.

## Operations and authority

| Operation | Effect |
| --- | --- |
| `enrol_peer(session, public, fingerprint)` | Pins one explicitly confirmed exact peer identity; replacement or revival requires a future rotation contract |
| `propose(session, peer, kind, title, text, context, task_id, expires, ...)` | Creates an immutable local task or return artifact draft; at most one hour of validity |
| `review(session, item_id)` | Returns exact content, scope and review digest; expired, cancelled or revoked-peer incoming content is withheld |
| `release(session, item_id, review_digest)` | Signs/encrypts and queues the exact reviewed draft once; no HTTP call or recipient acceptance is implied |
| `prepare_delivery(session, message_id)` | Records uncertainty and returns only the original stored ciphertext, with the transport's bounded retry count |
| `receive(session, packet)` | Verifies enrolled peer identity and exact application scope; commits transport receipt and application admission together |
| `decide(session, item_id, review_digest, decision)` | Accepts or rejects only a local incoming item, then queues its signed decision; duplicate identical decisions preserve history |
| `cancel(session, item_id, review_digest)` | Stops local use and queues a bounded cancellation where peer authority remains active |
| `state/status(session, ...)` | Returns metadata, receipt state and audit history without source text or session credentials |

Task acceptance does not execute a model, start a tool or grant onward disclosure.
Transport receipts establish receipt of an exact packet only. An authenticated
recipient decision is a separate packet and cannot be manufactured with a sender
session. Metadata keeps the historical acceptance decision when cancellation or
expiry later removes permission for new local activity.

## Source claims and bounded artifact return

A newly created task contains a signed `owner-originated` declaration, exact
content digest, recipient identity, context and a visible `origin-only` return
policy. This is a declaration by the enrolled signing identity, not semantic
proof that the text contains no copied or undeclared sources. Synthetic-only
policy cannot automatically recognise real personal data inside arbitrary text.

A returned artifact uses `task-derived-return`, with the exact retained original
task digest as its sole upstream source. Its producer must have accepted that
signed task locally. It can return only to the original requester's identity,
with the same context/task reference and no longer lifetime. On receipt, that
requester independently checks its own original released task and cancellation
state. A third-peer route, fabricated parent or general cross-owner ancestry is
rejected. Arbitrary inherited-source sharing remains unavailable until all source
owners' independently verifiable grants have a reviewed contract.

Receiver-side logical-route uniqueness is independently enforced. A malicious
enrolled sender cannot evade rejection by changing timestamps, content or expiry
and signing another digest for the same kind/context/task/parent route. Source
cancellation received before its original proposal leaves an exact tombstone,
including that logical route, so delivery reordering cannot revive it.

## Distributed revocation and recovery

Cancellation is not instantaneous across separate stores. The receiver can accept
an unexpired proposal before a delayed cancellation packet arrives. Once the
packet is observed, new local acceptance, derived output and provider work stop;
prior acceptance remains a historical fact. Source-side
`cancel_packet_receipt_observed` is explicitly transport evidence, not proof of
global cessation or recall. `peer_cancellation_observed` is set only by a verified
incoming cancellation, never merely by cancelling an unsent local draft.

All local application transitions, their transport fences and audit events share
one `BEGIN IMMEDIATE`. An expired/revoked local session is rechecked before commit.
Unknown commit acknowledgements produce a fixed `RuntimeOutcomeUnknown`; inspect
the retained exact item. The original release cannot be recreated, but delivery
can explicitly retry the same stored encrypted packet under the transport limit.
The receiver deduplicates that packet and returns its original receipt. Duplicate
decisions are metadata-only; an opposite terminal decision is rejected.

SQLite durability does not provide rollback-resistant backup recovery, distributed
clock agreement, compromised-host defence, or a semantic proof that a recipient
performed the accepted work. All local data other than identity keys is stored
unencrypted in private files. Session invalidation and locked keys survive process
restart; the owner must sign in before decrypting or delivering peer packets.

## Provider adapter seam

The optional task `provider_disclosure` must name the exact provider (`openai`),
model and output token bound in the original source-reviewed signed task. It is
absent by default. `authorise_provider` is called under the provider adapter's
existing local transaction and rechecks the accepted task, original source grant,
model, content digest, peer pin, observed cancellation and expiry. Returned
artifacts cannot mint provider grants. The recipient owner must also approve the
adapter's separate exact review. A task acceptance alone never supplies either
approval. Remote cancellation remains subject to observed delivery as above.

## Verification

Run `python -B -m unittest pilot.tests.test_runtime` in the pinned pilot environment.
The suite uses actual encrypted packets and password-unlocked signing identities
with distinct temporary stores. It covers competing decisions, rejected/duplicate
delivery, direct-source provider grants, exact return routes, expiry, source
cancellation ordering, role substitution, restarted authentication, atomic
receipt rollback and acknowledgement loss after commit. Independent adversarial
review tests are maintained separately in `test_security_review.py`.
