# Exact shared proposals

This is an independently implemented **trusted local-host primitive**, inspired by
the shared-draft and bilateral-review interaction described in the Parley research.
No Parley code is copied. It is not a live negotiation service, a provider adapter,
a remote group messenger or independent-device end-to-end encryption.

## The owner's experience

A member proposes exact text for the current room. The proposal fixes its content,
source-message references, full owner roster and membership epochs, room policy
generation and expiry. The proposing owner's signature identifies the author;
it is **not** their approval. Every member of that frozen roster must independently
review and approve the same revision using their own current local password session.
The coordinating storage owner cannot approve on anyone else's behalf and is not
an extra approver unless they are themselves a room member.

A host can show each immutable signed approval and signed withdrawal separately.
It must also show whether those records are currently applicable. Historical
signatures do not turn into permanent consent. A new revision, including identical
text generated again, starts with no approvals. Withdrawal is final for that owner's
approval of that revision. Agreeing again requires a new revision and fresh reviews.

**Even unanimous current approval is only an expression of local discussion
approval.** It does not send anything, accept an external legal agreement, authorise
execution or payment, grant access to historical sources, or permit disclosure to a
model/provider. The returned flags explicitly carry no such authority. A future
integration must obtain the separate approvals required for those actions.

## Host API

Import `LocalProposals` from `conversation.proposals`. Construct it with the existing
`ConversationLedger` plus the coordinating storage owner's current principal/session.
Construction initialises the separate schema under the ledger transaction. A narrow
optional final-check hook in the ledger orders proposal checks after final authentication;
existing ledger callers retain their default path. No authentication, transport,
provider or UI implementation is changed.

- `create`: pass the current `ContextBinding`, a stable request ID, exact text,
  absolute expiry and optional declared message sources. The proposal is signed
  but has no approvals. All current roster members must already be permitted to
  read every transitive declared source; this API never creates disclosure grants.
- `inspect`: obtain the exact signed proposal, separate signed approvals and
  revocations, current approval owners and `all_owners_approved`. Authenticate and
  authorise every inspection; do not use a previously returned object as authority.
- `inspect_request`: reconcile a missing create response by its stable request ID.
  An absent request returns `None` only after current authentication and room checks.
  Only the original proposer's requests are queried. There is no cross-owner search.
- `prepare_approval`: build the current owner's review. The host must show the actual
  exact proposal content, declared sources, complete roster, revision, expiry and
  local-discussion-only scope, then pin the returned review digest outside model input.
- `approve`: pass that complete review and the expected digest from the trusted
  owner control. The immutable signed statement binds proposal ID and digest,
  series/revision, content and source digests, full roster/epochs, room generation,
  owner/epoch and original expiry. Another owner's session or a JSON assertion of
  approval cannot replace the correct authenticated local owner control.
- `revoke`: withdraw only the calling owner's retained approval. The immutable
  original approval remains inspectable, with a separate signed revocation.
- To revise, call `create` with a new request ID and `replaces` set to the latest
  proposal ID. Only its original author can revise it. Declared source ancestry is
  retained automatically. The roster/epochs must be unchanged, so a revision cannot
  silently expose the old proposal chain to a newcomer. After membership changes,
  compose a fresh proposal with independently authorised sources instead.

Verify signed records against the owner's pinned public identity in the ledger,
not a key supplied inside generated content.

Only the trusted owner host may invoke approval/revocation controls. Do not expose
these as agent/model tools or take a principal/session/binding from generated text.
A digest and valid session bind exact bytes and a local account, not human comprehension,
physical identity, independent devices or proof that someone read the review screen.

## Currency, access and recovery

All operations share the ledger's authenticated, exclusive, serial transaction and
persistent observed-time fence. Actor and coordinating storage vault must be unlocked.
The current authenticated caller must still belong to the proposal's original audience
with the same membership epoch and have current access to every transitive source.
This is checked again before returning source-derived content.

Current consensus additionally needs the latest revision, unchanged room generation
and full roster, unexpired proposal, no revoked required approval and current source
access for **every** required member. Source-grant expiry can invalidate consensus
without any membership or generation change. Old signed records remain historical;
where the caller still has content access, inspection reports their current status
as false. When the caller loses source access, inspection refuses the entire result.
There are no inaccessible-item counts, snippets or search results.

Retries of an identical create request return that exact retained revision, with its
current status, never a newer revision. Changed payloads under the same request ID
are refused. Retried exact approvals have one record per proposal/owner and cannot
reactivate a withdrawn, expired or superseded approval. Simultaneous approvals and
revisions are ordered by the same transaction as membership changes and revocations.

A failed SQLite operation may report `ConversationOutcomeUnknown`, even if a commit
actually happened. Reopen and inspect the stable request or proposal first; do not
infer rollback or retry an external effect. This package performs no external effect.
Final-output/commit checks fail closed if expiry or authority changes during an
operation; the observed-time fence is retained even when the operation is refused.
The final gate checks captured actor-session and coordinating-vault deadlines after
policy checks, under the same auth locks. It rejects deadlines actually observed
before commit; it does not claim mathematically instantaneous wall-clock/commit
atomicity. If any room grant expires during the complete source-derived output
scan, the operation conservatively refuses and requires fresh inspection. Even an
unrelated grant expiry can cause that refusal; there is no silent retry.
Restart and clock rewind cannot revive an observed expired approval.

## Storage and limitations

Proposal, approval and revocation bodies are separately encrypted using the existing
reviewed storage primitive, a disjoint AEAD domain, and the coordinating owner's
exchange key. Each retained body is independently signature-verified. The opt-in ledger hook reads only the maximum coordinator-session expiry from
private authentication metadata under the existing real-auth locks. It does not
return tokens or session rows. Changes to that private auth schema need a coordinated
review of this dependency. New tables
coexist with the existing ledger format and clock sentinels; partial schema or missing
proposal-version rows fail closed. There is one ledger process, with thread-safe
local access. No duplicate remote service, outbox or transport is added.

An approval is a durable record, not a bearer session. Signing out or locking an
approver blocks their new operations; it does not withdraw their earlier approval.
Use explicit withdrawal, expiry or a new revision to invalidate it.

The base ledger's trust and rollback limits apply. One trusted host sees authorised
plaintext and supplies genuine owner authenticators. Public-key encryption alone
is not author authentication. Direct host/database compromise, complete removal of
extension state, backup rollback and deletion of whole signed records are not an
external transparency-log problem solved by this primitive. Metadata, including
identities, request IDs/digests, series and revision numbers, remains visible in SQLite.
A digest can reveal a guessed low-entropy message; encryption does not hide metadata.
Revocation cannot recall plaintext or screenshots already copied.

Lineage covers declared host-established message references, not semantic detection
of an author copying text while omitting sources. There is no arbitrary file loader,
provider context assembly, proposal-history sharing grant, attachment format,
remote signature import or UI in this milestone. The existing owner conversation
controls and supported-host bridge remain separate work.

Text is bounded to 16 KiB, direct sources to 32, expiry to at most 24 hours at creation,
and proposals to 4,096 retained revisions. The exact text digest is SHA-256 of its
UTF-8 bytes, without Unicode or newline normalisation. Other signed commitments use
the existing canonical JSON digest. Data does not expire by automatic deletion.

## Verification

From the repository root with the pinned `pilot/requirements.txt` dependency:

```sh
python -B -m unittest conversation.tests.test_proposals -v
python -B -m unittest discover -s conversation/tests -v
python -B -m unittest discover -s pilot/tests -v
python -B -m conversation.proposals_demo
```

The existing conversation workflow discovers the new test module automatically.
The demo uses fictional identities, real separate local authentication, signed
approvals, revision invalidation and durable reopen. It makes no provider/network
calls and is not evidence of live independent-owner or personal-assistant acceptance.
See [the work notice](PROPOSALS_WORK_NOTICE.md) for the current review/publication state.
