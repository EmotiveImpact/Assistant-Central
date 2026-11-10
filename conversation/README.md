# Persistent conversations

This is a **trusted local-host contract**, not a production group messenger or a
connection to an existing personal assistant. It uses real local password sessions,
Ed25519 signatures and encrypted SQLite payloads with fictional test identities.
It makes no network or provider calls and grants no execution authority.

## What works

- A stable conversation starts with its creator. The creator invites a pinned
  person; that person must accept using their own authenticated session. Accepting
  a third member explicitly expands the thread into a group. Existing messages
  retain their original audience. New members get **future messages only**.
- Every accepted invitation establishes a fresh membership epoch. Leaving or
  removal disables retrieval, context assembly and sending. Rejoining restores
  neither previous audiences nor previous history grants, including the person's
  own earlier messages. Explicit new approvals are required.
- Immutable, signed messages retain original author, recipient epochs, exact
  content, request identity and source-message digests. A stable sender request
  identifier deduplicates identical retries across restart; changed retries fail.
- Exact outcome inspection resolves a retained authored request without sending
  again, including messages beyond the first history page. An absent request is
  explicitly inconclusive, never proof of rollback or permission to retry.
- An author can review and approve a signed, expiring grant for their own exact
  message IDs and digests, one named current recipient epoch and the
  `local-owner-only` audience. A conversation administrator cannot approve another
  author's messages. A repeated revoked grant cannot reactivate itself.
- Quotes and summaries require declared source references. Reads, search,
  pagination and context assembly check every transitive source as well as the
  derived message. The source author's approval does not approve another author's
  summary, or vice versa. Expiry and withdrawal affect fresh reads and derived
  context. Missing or altered dependencies fail closed.
- A composer must pass the current conversation binding. A pending draft cannot
  silently broaden its audience when someone joins: stale bindings fail, requiring
  the host to show the new roster and obtain a fresh send decision.
- Retrieval returns no hidden-hit count, internal sequence or historical recipient
  list. Pagination uses the last **visible event ID**, which is checked again.
  Retrieved text is labelled untrusted; context explicitly has no execution rights.

## Run

From the repository root, with Python 3.11+ and the pinned pilot dependency:

```sh
python -m pip install -r pilot/requirements.txt
python -B -m unittest discover -s conversation/tests -v
python -B -m conversation.demo
```

The separate `.github/workflows/conversation-checks.yml` runs these and the existing
pilot component tests. The unchanged repository workflow still covers the existing
team, execution, integration, transport and UI suites.

## Trust and storage ownership

One trusted local host owns this ledger. Its coordinating storage owner's immutable
exchange key encrypts message bodies, history-grant statements and signed audit
records using the existing `pilot.storage.RecordStorage` primitive with a separate
AEAD record domain. Public-key sealing **does not authenticate authors**: independent
Ed25519 verification is mandatory on retained message and grant reads.

The host provisions a mapping of pinned fingerprints to separate genuine
`LocalOwnerAuth` instances. Each actor's operation needs that actor's current
session. The coordinating storage owner must also be unlocked for **every** API,
including empty searches and membership metadata. Actors do not receive other
actors' session tokens, passwords or private keys. Storage-owner lock and actor
logout are ordered against operations; session expiry and output authority are
rechecked before commit. Restart locks every auth vault and invalidates old bearer
sessions. Persisted history and observed revocations survive. A durable observed-time
high-water survives refused operations and restart; a rewound clock fails closed
until it catches up, rather than reviving an expired grant.

This does not isolate mutually hostile owners from the trusted Python process or
host. All authenticators are supplied by trusted provisioning, not by model input.
The host holds the plaintext during authorised queries, and its storage owner can
technically decrypt stored payloads. It is **not end-to-end encrypted between
independent owner devices**, a multi-tenant server or a proof of independent human
consent. Do not deploy it as any of those things.

SQLite transactions and a private exclusive store lease linearise concurrent
local reads, membership changes and grants. One ledger process owns the store at
a time; threads can use the locked API. Messages are durably persisted locally,
not marked received, processed or task-completed. There is no outbox, recipient ACK,
remote delivery or exactly-once external-effect claim in this package.

## Host API and integration boundary

1. Trusted provisioning creates the ledger with its storage authenticator and
   pinned actor authenticators. `create`, `invite` and `accept_invitation` are
   owner controls, never model-callable approval tools.
2. The authenticated host obtains `bind_context` and `participants`. Pin the
   binding outside model arguments. It contains the stable conversation ID,
   principal, current membership epoch and policy generation.
3. `append` takes that binding, a stable request ID, inert text and optional source
   event IDs. Supported kinds are `message`, `quote` and `summary`. The message ID
   is generated once and retained. After an uncertain outcome, use
   `inspect_message_outcome` with the original exact request commitment. Do not infer
   rollback from an absent inspection result or replay an external effect.
4. `prepare_history_grant` creates an exact review statement. A trusted owner UI
   must show the actual selected content, recipient, purpose, expiry and local-only
   audience before calling `approve_history_grant` with the review digest. A digest
   authenticates exact bytes, not human comprehension. Model-supplied JSON saying
   “approved” is inert and cannot replace a current owner session.
5. `read`, `history` (including its optional text query), and `context` require the
   authenticated reader and current binding. `context` returns local-only untrusted
   data, **not permission to send it to an AI provider**. A future host adapter needs
   a separate exact provider-disclosure review and its own session binding.
6. `remove_member` and `revoke_history_grant` invalidate policy bindings. Hosts must
   discard cached bodies and rebuild through the API, not treat saved context as a
   bearer capability. Grant expiry is rechecked even without a policy change.

Identifiers accepted for conversations and client requests use ASCII letters,
digits, underscores and hyphens, at most 64 characters, matching the SDK bridge's
conversation identifier boundary. Principal fingerprints are 64-character SHA-256
identities, not display names or interchangeable bridge owner labels. A future
adapter must explicitly map and pin that distinction. The optional local owner
workspace now wraps this ledger with separate authenticated owner sessions and
exact message-outcome inspection. This cumulative composition
does not wire existing personal assistants, the SDK bridge, owner transfer UI or
peer transport to conversation history, and does not permit provider disclosure.

### Inspect one uncertain message outcome

The trusted host calls
`inspect_message_outcome(principal, session, binding, request_id=..., expected_request_digest=...)`
with the original request ID and a strict 64-character lowercase SHA-256 digest.
The current binding and session must belong to that same authenticated author and
exact room. There is no request-ID enumeration or lookup for another author.

Before sending, the host computes the commitment using
`pilot.crypto.digest({'kind': kind, 'text': text, 'source_ids': list(source_ids)})`,
including the default `kind='message'` and empty source list when applicable.
The digest covers UTF-8 JSON with sorted keys, compact separators, unescaped
non-ASCII characters and no Unicode normalisation. Source-ID order is significant.
Clients in other languages must reproduce `pilot.crypto.canonical` exactly, not
hash arbitrary JSON serialisation or an event's provenance digest. The host can
retain this bounded commitment with the original author, room and request ID after
clearing submitted plaintext; a digest is neither a bearer capability nor a secret
and can reveal low-entropy content through guessing.

- `{'status': 'committed', 'event': ...}` means the exact signed message is retained
  locally and currently visible to its author. The normal public event contains
  no request IDs, historical audiences, internal sequence or hidden-hit count.
  Both the signed fields and the recomputed request commitment must match.
- `{'status': 'inconclusive'}` means no matching retained author/room/request row
  was found in this inspection. It does **not** establish rollback, grant permission
  to resend, or clear an uncertain-write fence. A generic state refresh or partial
  history page cannot substitute for exact inspection either.
- A found but mismatched or inaccessible message produces the ordinary generic
  refusal, without its ID or body. Current membership epoch, policy binding,
  original audience or exact history grant, and every transitive source must
  still allow retrieval. Rejoining does not restore old authored messages.

Inspection does not append, sign, approve, grant access, change membership or call
a provider. Like other reads, it updates only the existing durable observed-clock
fence. Actor and coordinating-vault lifetimes and complete source visibility are
checked again after final authentication; even an inconclusive result requires
current authentication and a current binding. A clock or storage failure can
still refuse inspection rather than return an outcome.

A committed result resolves only the existence and exact content of that local
message. Neither result proves remote receipt, task completion, owner consent to
other actions or authority to execute or disclose sources. Hosts must retain an
unresolved fence when inspection is inconclusive or refused. The standalone method
adds no model tool, recovery journal or automatic retry policy. The optional
[local owner workspace](../workspace_ui/CONVERSATIONS.md) exposes a separately
authenticated exact outcome route and a session-bound UI recovery hold.

## Important limits

- Revocation prevents subsequent authorised retrieval. It cannot recall copied
  plaintext, old screenshots, provider context already disclosed, or old keys.
  A separate overlapping valid grant can still permit the same message. Revoke
  each relevant grant or remove the recipient to stop all subsequent room access.
- Enforcement knows only local accepted membership changes and observed grants.
  No remote revocation freshness, distributed consensus or offline-device deletion
  is claimed. This first lane deliberately has no remote grant-import API.
- Provenance is enforced for **host-established, declared references**. A malicious
  author can copy text into a new message and omit its sources; no semantic detector
  or complete information-flow proof is claimed. There is no external attachment
  loader, embedding index, arbitrary cross-conversation reference or summary cache.
- Routing identities, membership and invitation records, timestamps, digests and
  sizes remain metadata in SQLite. Disk observers can learn activity and may test
  guesses against digests. Query timing is not constant-time. Payload encryption
  does not hide the directory structure or protect unlocked process memory.
- Same-UID/host compromise, direct database policy tampering, backup rollback and
  deletion of whole records are outside the trust model. Signatures and AEAD detect
  changed retained payloads but are not an external append-only transparency log.
- Bounds are deliberate: 256 conversations, 32 provisioned actors/active members,
  4096 retained messages, 32 direct sources per message, bounded ancestry, 16 KiB
  message text and 50 retrieval items. No automatic history eviction. Larger-scale
  indexing, retention/deletion controls, key rotation and archive migration remain
  work. The administrator cannot leave without a future ownership-transfer flow.

Read [the work notice](WORK_NOTICE.md) for ownership and verification status. The
research conversation plan is design input, not extra authority or live acceptance.
