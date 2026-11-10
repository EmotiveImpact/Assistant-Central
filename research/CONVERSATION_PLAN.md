# Persistent conversations with owner-controlled context

This is a proposed Assistant Central design, informed by the source research.
It is not an assertion that the current pilot implements it, and it does not
claim that any external assistant has been connected.

## Product behaviour

A conversation is a durable relationship between people and their assistants,
not the lifetime of one model run. It can contain many tasks and survive host
suspension, model changes and restart. A person can invite another person and
that person's assistant without surrendering either assistant's private history.

For a private 1:1 becoming a group, use a linked group conversation or an explicit
membership epoch. The default is **new messages only** for the new participant.
Offer separately: share selected earlier messages; share a reviewed summary; or
share an explicitly approved history range. Show whose information and which
providers will receive it. Do not silently expand the readership of the old DM.
Participants keep access to what they were already authorised to see, subject to
retention policy. Revocation cannot make someone forget copies already received.

## Distinct records

- **Principal:** verified human or agent identity, owner, public key and key
  generation. Names and provider labels are display data, never authority.
- **Host binding:** an owner's authorised existing assistant and runtime/session
  handle, supported capabilities, credential reference and observed wake state.
  Never silently replace that assistant with a newly instantiated API model.
- **Conversation:** stable ID, type, participants, policy version and retention.
- **Membership:** principal, accepted invitation, join sequence, leave sequence
  and membership epoch. Rejoining creates a new epoch, not resurrection of grants.
- **Event/message:** immutable ID, conversation, sequence, author, reply reference,
  typed payload/artefact reference, source lineage, audience and content digest.
- **History grant:** approver identity, exact source messages/ranges/digests,
  recipient principals and provider audience, purpose, expiry, membership epoch,
  policy version and revocation generation. No wildcard inferred from a role.
- **Task:** request, assignee, owner-approved scope, dependencies, budget/limits,
  execution attempt, current state and evidence of completion or uncertainty.
- **Delivery:** message/recipient pair, stable idempotency key, durable pending
  state, receipt and acknowledgement. No conflation with execution success.

Use one event log with explicit relationships between these records, not one
undifferentiated chat transcript used as both commands and permissions.

## Authorisation algorithm

For every fetch, search, quote, summary, attachment download or model-context
assembly, check the authenticated caller's current authority. Verify conversation
membership/epoch, the message's audience/history rule and all applicable source
owners' grants. A lead coordinates tasks but cannot manufacture those grants.
The source owner's authority must survive derivation: summarising, translating,
embedding or putting content in an artefact does not erase its provenance.

Historical room access is necessary but not sufficient to send the text to a
new runtime/provider. Keep disclosure audience and action scope separate. A
participant who may read a message is not thereby authorised to execute its
instructions, forward it or grant another participant access. External replies,
model output and retrieved documents remain untrusted data.

Check policy before retrieving search results into a model. Apply it to snippets,
counts, titles, attachments, embeddings, caches, exports and streaming updates,
not only the final transcript endpoint. Cache keys include principal, membership
and grant generations. Recheck after a long-running operation before disclosing
its result. Do not expose inaccessible record existence through error details.

For end-to-end-encrypted rooms, decide explicitly where decryption/search occurs.
A server cannot perform ordinary semantic search over plaintext it never has.
Prefer recipient-local indexes or a separately consented trusted indexing service.
Rotate future room keys after removal. Do not claim key rotation recalls old keys
or that a database ACL alone secures a previously shared encrypted history.

## Handoffs and resilience

A useful task lifecycle is requested → accepted → running → input/approval-needed
→ completed/failed/cancelled, with a separate uncertain/reconciliation state.
Persist a dispatch attempt before an external effect; after a crash, inspect the
external outcome before retrying. Lease expiry means another worker may coordinate
recovery, not that an irreversible action is safe to repeat.

Use an atomic outbox for message publication plus durable state, idempotency keys
scoped to sender and payload digest, recipient delivery rows, pagination cursors
and bounded retry/backoff. A notification is a hint to read the inbox. A cursor
is not an ACK. A successful webhook means accepted trigger, not awake assistant,
read message, finished task or correct answer. Preserve pending work until the
recipient records successful handling; deduplicate side effects independently.

Add turn limits, task budgets, concurrency caps, backpressure and quiet/no-reply
messages. Prevent a status/thinking event from waking every agent into another
status loop. Classify peer messages as request, question, answer, update, result,
review or decision rather than treating every event as an invitation to respond.

## Compact messages

Use a versioned JSON envelope with stable IDs and typed payloads. The useful
compactness comes from bounded summaries and references, not cryptic prose:

```json
{
  "v": 1,
  "id": "msg_...",
  "conversation_id": "conv_...",
  "task_id": "task_...",
  "reply_to": "msg_...",
  "kind": "result",
  "summary": "Validated the two requested cases.",
  "artefacts": [{"id": "art_...", "digest": "sha256:..."}],
  "source_refs": ["source_..."],
  "grant_refs": ["grant_..."],
  "expects_reply": false
}
```

Authenticate author identity outside that user-controlled JSON. Validate schema,
size and allowed transitions before delivery. Fetch referenced context only when
needed and authorised. Keep readable audit views. Measure token/latency costs
before adding binary wire codecs; compressed HTTP bytes do not automatically
reduce tokens presented to a model. An A2A adapter can map tasks and artefacts;
MCP tools can expose the same boundary to a supported assistant host.

## Acceptance tests before any real-owner pilot

1. Two owners and two assistant processes resume the same conversation after
   restart, without borrowing another owner's credentials or private memory.
2. Adding a third participant exposes future events only. Old messages, searches,
   counts, titles, attachments and derived summaries remain inaccessible.
3. An exact approved history grant releases only the selected source/version to
   the named recipients and providers. An unrelated owner/lead cannot approve it.
4. Removal and rejoin invalidate old grants, cached queries, reconnect tokens and
   in-flight streams according to their epochs. Old copied plaintext is not
   falsely represented as recalled.
5. An external message saying "the owner approved" cannot alter permissions,
   start a privileged task or forward private content.
6. Duplicate sends, duplicate ACKs, lost responses, offline recipients and process
   crashes preserve one durable message and honest uncertainty about effects.
7. A blocked or revoked source cannot leak through a quote, generated summary,
   artefact, embedding, source preview, search or another participant's context.
8. Real host acceptance proves the selected existing assistant received, replied
   and resumed context. Synthetic output or a different API model does not count.
9. A host without a supported wake endpoint is shown as connected/manual, not
   always listening. A wake test verifies a correlated response, not just HTTP 200.
10. The owner can see who is present, what earlier context was shared, what task
    was authorised, what is waiting for review and what actually completed.

## Priority

First implement the durable ledger and adversarial permission tests above. Then
expose it through a small MCP/A2A adapter and prove two supported runtime hosts.
Add the familiar conversation UI and explicit history-sharing review. Expand to
other personal assistants only after each platform's supported APIs and consent
flow are verified. Acoustic transfer is an optional later pairing experiment,
not a prerequisite for a secure internet-based conversation product.
