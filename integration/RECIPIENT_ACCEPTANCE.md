# Exact recipient acceptance rehearsal

`recipient_acceptance.py` extends an existing unsigned `BoundArtifactProposal`
with an explicit synthetic release and a separately controlled recipient
accept-or-reject operation. All content and owner choices are fictional. One
trusted local operator and the team SQLite database still control this fixture.
This proves a local authority contract, not independently authenticated assistants.

```sh
python -B integration/run_checks.py
python -B integration/acceptance_demo.py
python -B execution/check_composition.py
```

Use the repository's pinned fixture environment. The runner and demos forbid
audited socket/subprocess activity; this is a regression guard, not an OS sandbox.
The new demo closes and reopens the team database, accepts one exact artifact,
retains a rejected alternative, deduplicates original delivery and blocks a second
release. The composition check connects an execution result, candidate artifact,
lead review, unsigned proposal, explicit release and recipient acceptance.

## Separate authority at each transition

| Operation | Trusted control | Effect |
| --- | --- | --- |
| `register(bound)` | Local composition | Captures one exact pending unsigned stage; creates no release permission |
| `source_control(owner).review/decide` | Each source owner's fictional control | Approves or rejects that owner's contribution to this exact artifact and recipient; approval expires within one hour |
| `source_control(owner).release` | Outgoing artifact owner's fictional control | Rechecks every source owner and original disclosure; commits one release fence before returning an inert envelope |
| `recipient_control(owner, agent).receive` | Exact recipient's fictional control | Records the original envelope as pending review, once; does not accept or execute it |
| `recipient_control(owner, agent).review` | Exact recipient's fictional control | Shows the exact released text and its immutable review digest while permissions remain current |
| `recipient_control(owner, agent).decide` | Exact recipient's fictional control | Accepts or rejects that review, durably; cannot change a terminal decision |
| Bound `status` | Relevant source or exact recipient control | Returns metadata and current source authority separately from historical acceptance |

These constructors and owner controls are **not model tools**. The sender control
has no recipient decision operation. The recipient control has no source approval
or release operation. The nominated lead cannot use either role for someone else.
Sharing an owner does not bypass either decision or grant access to sibling agents.
The control factory remains trusted: anyone able to invoke arbitrary Python or
modify the database can impersonate fixture labels. Do not expose it remotely.

Acceptance admits an inert artifact into this lane's local inbox history. It does
not start a task, consume or renew work approval, authorise a provider call, publish
content, execute instructions, grant tools or permit onward disclosure. The
existing team-local read/start APIs remain a separate fixture, not a bypass-safe
multi-user runtime. The recovered wire still exposes only its original three
tools, and its `processed_inbox` stays empty: this lane does not claim processing
through the old protocol.

## Exact commitments and source rights

One immutable offer binds the original proposal ID, full team mapping, source
artifact ID and digest, source start review, target task and agent, owner
references, context, exact text and complete recorded dependency lineage.
Historical dependency disclosure review digests are verified and committed even
when the intermediate tasks have completed. The same artifact/target route cannot
be registered under another alias in the same team database.

Every direct and upstream producer owner receives a separate release review.
Each preview includes only their own original sources, plus the hashes of derived
artifacts affected by those sources. Raw ancestral text is not appended to the
recipient envelope. Owners are approving their contribution to exact output
hashes; an upstream owner is not represented as having seen foreign derived text.

The release envelope and recipient review bind the intended recipient, exact
artifact, proposal, offer commitment, task, context and expiry. The recipient's
decision digest additionally binds the recipient owner, agent and accept/reject
choice. Altered, crossed, expired or previously unissued envelopes cannot create
a receipt. Hashes establish local consistency only; they authenticate nobody.

Registration reads the old proposal under the team's lock followed by the proposal
store's lock. Only unsigned pending stages qualify. The proposal store is a
read-only input snapshot, and is never marked delivered or accepted. Subsequent
decisions for this lane live in the team database. The old standalone
`OwnerReview` release path is neither constructed nor exposed here; it is a
different fixture and must not be operated as a second authority for this offer.
Use the new source controls to reject or withdraw this lane's release permission.

## Revocation, expiry and uncertainty

All new transitions and original team permissions share `BEGIN IMMEDIATE`.
Source approval, release, first receipt, recipient review and acceptance recheck
the immutable mapping and ancestry. A revocation that commits first prevents
acceptance; acceptance that commits first remains a historical fact. Both lock
orders are tested with competing connections. An accepted result later reports
source authority as unavailable after withdrawal, without erasing its history.

The earliest source approval expiry bounds release, first receipt, content review
and acceptance. Approval cannot be renewed. A rejection can close a received
offer after expiry or withdrawal using its retained review digest, without a new
content preview. Existing work approval expiry is independent and is not extended.

Release is durably `released` with recipient outcome `uncertain` before the one
original envelope is returned. A timeout, lost return or restart cannot issue a
second envelope. There is no automatic dispatch, retry or reassignment. If the
original envelope has been lost, this fixture provides no reissue/recovery claim.
Preserve the databases and inspect the exact offer ID.

A retained original envelope can be explicitly presented after restart while
permissions are current. Duplicate delivery returns metadata, never another
payload, decision or read increment. Exact duplicate decisions similarly return
the original outcome. Opposite decisions are rejected. Receipt, decision and
their audit events commit atomically; injected failures before and after commit
test rollback and uncertain acknowledgements. Errors disclose no exception detail.

Receipt increments the original direct disclosure's conservative read counter
once, because the recipient may now have seen the text. Rejection or later
revocation cannot erase that exposure. No historical upstream read counters are
incremented merely for inspecting lineage.

## Limits and the next implementation sequence

This uses one SQLite file, not two independently controlled inbox/outbox services.
The source has no method that can mint a recipient decision, but the trusted
operator controls both constructions. No new signing keys, encryption, credential
loader, provider, HTTP endpoint or transport is introduced. Stored synthetic text
is unencrypted; there is no backup rollback defence, retention service or proof
that a real human reviewed anything. Provenance covers declared task inputs,
not arbitrary copied text, undisclosed context or third-party rights.

| Next gate | Concrete acceptance criterion |
| --- | --- |
| Authenticated owner controls | A real session can approve only its own enrolled assistant, exact request and finite policy; model-supplied owner labels are rejected |
| Independently controlled receiver | Two separately owned processes and stores enforce the same contract; the sender cannot write recipient decisions, even with a modified client |
| Identity and protected credentials | Enrolled peer identity, protected keys, rotation, compromise revocation and recovery are tested; approval proof binds identity and context |
| Persistent encrypted exchange | Durable outbox/inbox, authenticated messages, bounded payloads, replay defence, receipts, expiry and cancellation are tested through loss, duplication, reordering and restart |
| One real host/provider adapter | Synthetic inputs only initially; test startup, permissions, logging, cancellation, cost limits, secret isolation and rollback against one named host |
| Limited two-person pilot | Independent security review, retention/deletion policy and incident/recovery checks pass before introducing personal data |

The next product milestone should be two people, each controlling their own
assistant, exchanging one task and one reviewed artifact with visible approval,
rejection and cancellation history. Broader teams, more providers and scale
claims should follow that demonstrated boundary.
