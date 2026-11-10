# Owner-authenticated exact source grants

This is a standalone executable contract and local observation ledger, **not a
new runtime/provider permission path**. The existing runtime still rejects
unverified inherited inputs. Nothing in this module releases an artifact, sends
bytes, runs a provider, accepts a task/result or creates a transport receipt.
The tests use fictional accounts and disposable password-unlocked owner keys.

## What a signature establishes

`sign_statement` holds the existing `LocalOwnerAuth.authorised` guard, matches the
issuer's complete public-identity fingerprint and signs only the exact supplied
owner-review digest. Ed25519 signatures are domain-separated from transport,
prototype owner decisions and result reviews. A stale review or wrong/revoked
local session cannot sign. The trusted host must expose this method only through
an explicit owner approval interface, never to an agent proposal or an incoming
message handler. A caller presenting a session is not proof that a person read
or understood a review. There is no approval UI in this milestone.

The verifier pins complete owner/agent/signing/exchange identities. Display labels
or keys embedded by an incoming grant never enrol an identity. Reusing one
signing key under another label is rejected. Pin provisioning and the Python
host remain trusted. Local authentication establishes control of a local account,
not real-world identity, legal authority or ownership of the named source.

Each grant is a signed assertion by a **declared** source owner. A signature does
not prove that the source belongs to that owner, that the source manifest is
complete, or that a model's derived text omits other people's information.
Trusted provenance collection and source classification must establish these
facts before any future integration can use this gate. Omitting a contributing
source would bypass its owner's approval; this contract cannot discover an
omission from prose or a content hash.

## Exact disclosure plan

All contributing owners sign the same closed plan:

- Opaque operation ID and exact task/context digest.
- Pinned executor and recipient identity fingerprints.
- Exact purpose text, without interpretation or wildcard expansion.
- Exact canonical-JSON payload digest.
- Between one and sixteen sorted, unique source references, each with its declared
  owner fingerprint, source ID, positive snapshot revision, sorted scope labels
  and canonical-JSON fragment digest.
- Either no provider destination or the exact supported OpenAI Responses endpoint,
  provider name, model identifier and finite output-token bound.

Every declared owner signs the whole plan, even when they contribute multiple
sources. This also binds that owner's grant to the complete declared multi-owner
composition. The source snapshot and output payload commitments are distinct:
`consume` checks both against the supplied values. Hashing uses bounded canonical
JSON, not arbitrary file bytes. The host must transmit the reviewed representation
and enforce the actual destination; this module does not perform either step.

`recipient` is the assistant account allowed to receive the disclosure. For a
provider-bound plan it is the executor account making the provider request, so
set `recipient` to that same pinned executor; the destination separately identifies
the provider. For a peer disclosure it is the receiving peer. A provider route in
a source grant permits only that exact source disclosure. It does not activate a
live transport, supply a credential, approve spending, or replace the separate
provider request review/dispatch gate. Unknown provider routes fail closed.

Scope labels are inert descriptions, not queries or permission to fetch another
record. Source snapshot revisions identify the exact approved snapshot; grant
revisions order local observations for one owner/operation. Neither is a global
source-version oracle. Changing recipient, context, purpose, payload, source
snapshot, model or token bound requires new exact owner signatures.

## API sequence

1. A trusted composer prepares the bounded plan and exact payload/fragments. It
   independently establishes complete source provenance and pins the owners.
2. Each source owner's trusted UI calls `review_statement` with a grant statement,
   presents the exact disclosure/source data, then calls `sign_statement` with the
   current session and the approved review digest. Each grant has a positive
   revision, integer issue time and expiry at most ten minutes later.
3. The executor owner explicitly imports every signed statement through
   `SourceGrantLedger.observe`. Validating a signature alone grants no authority.
4. Immediately before a separately approved effect, the executor calls
   `consume(session, plan, payload, fragments, signed_grants)`. Fragments are in
   the plan's exact source order, with only `owner`, `source_id`, `value` fields.
   `signed_grants` maps each declared owner fingerprint to its original signed
   envelope. Exactly one current grant per declared owner is required.
5. Consumption checks all signatures, supplied data commitments, local observations,
   pins, expiry and vetoes under one SQLite write transaction. It commits one
   operation-level attempt before returning metadata. A second consume is denied,
   including with a new grant revision or after restart.

This sequence is **not yet connected** to the pilot's task/provider/workflow
ledger. A later integration must atomically couple source consumption to its
own irreversible attempt claim, recheck accepted-task/current-source authority,
and preserve session/withdrawal ordering. Treating a successful return value as
a durable bearer permission for later use would introduce a time-of-check gap.
Consumption is not sufficient permission to release/send anything.

`verify_statement` deliberately checks only grammar, pinned identity and signature.
It cannot establish expiry, latest revision, observed withdrawal, execution
approval, recipient acceptance or one-use state. It must not become an alternative
authorisation path. The API accepts bounded Python JSON objects, not wire JSON;
a future transport needs a strict bounded codec which rejects duplicate JSON keys.

## Withdrawal, cancellation and version ordering

- A higher **observed** grant revision replaces a lower revision for the same
  issuer/operation. The exact older grant then fails, even if its signature and
  expiry are otherwise valid. Authenticated supersession is retained even when
  the new grant is already expired, future-dated, for another executor, or names
  an unpinned recipient. `observe` reports ineligibility only after committing
  that high-water mark; it never restores an older grant. Future grants still
  cannot be consumed before their issue time. An identical observation is
  idempotent, not a new use. A lower revision is rejected.
- Two valid different statements at the same revision permanently fence that
  issuer/operation. The conflict is committed before denial is reported; rolling
  back this record would accidentally restore the older authority. A higher
  revision cannot clear the fence.
- A signed `withdrawal` is the issuer's terminal veto of all its grants for that
  operation, including versions arriving later. It can arrive before a grant.
  It has no expiry: a delayed authentic withdrawal must not become ineffective.
  Future-dated withdrawals are rejected. Withdrawal of one operation is not
  blanket revocation of a source or permission concerning another operation.
- `cancel` is a separate authenticated **local executor** veto of an operation,
  including an operation not yet observed. It is not a remote recipient's decision
  or a source-owner signature. A source withdrawal by a recipient who contributes
  no declared source does not become executor cancellation.
- `revoke_pin` permanently distrusts an enrolled identity locally, fencing its
  source grants and use as a recipient/executor. It does not withdraw signatures
  at another host. Trust roots cannot be silently replaced on reopen; key rotation
  and migration are deliberately outside this milestone.
- Consumed history survives all these events. Status never claims recall, remote
  shutdown, successful disclosure, transport delivery or recipient acceptance.

A disconnected verifier cannot observe a new grant revision, source update,
withdrawal, cancellation at another host or remote key compromise. It may accept
an older, locally current grant until expiry. `remote_revocation_known` is always
false. Ten-minute expiry reduces this window; it does not eliminate it. Secure
future integration needs authenticated observation delivery or an appropriately
fresh authoritative check. A signature alone is not a distributed revocation
service, and the ledger must not imply otherwise.

## Storage, bounds and failure behaviour

The trusted host supplies one dedicated standalone SQLite ledger, private storage
and lifecycle controls. Do not add these tables to a legacy runtime database: the
runtime migration deliberately refuses unreviewed optional schemas. Future shared-
transaction integration needs its own reviewed schema/migration work. No filesystem
or encrypted-storage wrapper is introduced here. The
new tables store public pin/configuration metadata, opaque operation IDs,
revisions, hashes, timestamps and irreversible veto/attempt flags only. They do
not retain signed plans, purposes, source IDs/scope labels, source fragments,
prompts or results. Callers supply original signed grants again at consumption.
Use non-sensitive opaque operation IDs; hashes and public identity labels still
reveal metadata and may permit guesses about small input spaces.

Each statement/envelope/payload is bounded to 16 KiB and eight JSON nesting levels.
Pins are capped at 32, source references at 16, scope labels at 16, and each
history table at the immutable configured limit (default 1,000, maximum 10,000).
The revoked-pin table is bounded by the pin set. A full observation or claim table
rejects new records; existing tombstones are never evicted. If a new withdrawal
or cancellation cannot fit its table, the ledger commits a permanent global
consumption fence instead of silently retaining usable authority. Existing exact
withdrawals/cancellations remain idempotent. This conservative denial of service
requires manual investigation; there is no automatic reset or history-pruning API.

A successful local consume burns the operation even if the later effect never
runs. Lost commit acknowledgement is uncertain: inspect `status`, do not retry
or invent another operation ID to evade the fence. Database errors are fixed
messages, without copied payloads. Nested transactions are rejected rather than
implicitly committed. Session revocation is serialised through commit, expiry is
checked again immediately before commit, and observed clock rollback fails
closed across reopen. The trusted system clock can still be wrong or frozen.

Same-account/root compromise, direct trusted-process/database manipulation,
restoring an old backup, copying the database into independent executors and
operating duplicate ledgers are outside the boundary. They can defeat local
replay/observation state. Single-use is local to one retained executor ledger,
not globally enforced across machines. Do not create another ledger to recover
capacity or uncertainty without a separately designed migration protocol.

## Reproduce and current scope

```sh
python -B -m unittest pilot.tests.test_source_grants -v
python -B -m unittest discover -s pilot/tests -v
```

The focused suite exercises real local password sessions and signatures from four
fictional identities. It covers exact multi-owner composition, wrong/missing
signers, signature and field tampering, domain separation, recipient/context/
purpose/model/destination substitution, exact data and source scope, bounds,
future/expired grants, expiry crossing commit, stale/revoked sessions, key reuse,
withdrawal ordering, cancellation, pin revocation, revision rollback/equivocation,
replay after restart, competing connections, lost acknowledgement, SQLite
rollback, clock rollback and non-content persistence. It explicitly demonstrates
the unseen-withdrawal limitation rather than making a false revocation claim.

No production ownership verification, live owner interaction, provider call,
network transport, hosted service or cross-host consent enforcement is claimed.
