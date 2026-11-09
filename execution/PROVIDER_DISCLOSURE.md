# Exact provider disclosure rehearsal

This is **synthetic, local-only**, not a connected provider adapter. It makes the
next authority gap executable: permission to start a task, read an artifact in
one agent's workspace, or coordinate as lead does not also authorize sending that
content to a model provider. All owner choices below are fictional trusted
harness calls, not authenticated human consent.

Run with Python 3.11+ and no dependencies:

```sh
python -B execution/run_checks.py
python -B execution/provider_demo.py
```

The runner and demo install the existing socket/subprocess audit guard. This is a
regression check, not an OS sandbox. The demo exercises distinct fictional
research and copy provider labels; it does not establish provider compatibility.

## Exact approval contract

Trusted composition creates `ProviderGate(ExecutionLedger(workflow))`, then binds
a facade to the task's exact assignee. Only an already-prepared, already-started
execution can propose a route. There is one immutable request per run, and one
run per task. Repeating the proposal returns metadata, not data or a new grant.

The `ProviderRoute` binds an exact provider label matching the assigned agent,
account reference, model reference, and bounded data-policy text. They are
unverified labels, not credentials, endpoints, provider guarantees or accepted
legal terms. Changing any field cannot reuse a previous approval or replace the
request. Refusal, revocation and expiry cannot be sidestepped by aliases.

A request constructs one explicit minimal payload:

- Task objective and output kind, plus the exact accepted dependency artifact
  IDs and text. Artifact metadata, agents' private context, source task objectives,
  start-review details and resource names are not forwarded.
- Exact destination labels and common task/run/context metadata.
- Explicit synthetic-only, untrusted-content and no-external-actions fields;
  an empty tool permission list and zero spending limit.

The task owner must approve their task text. **Every input artifact's producer
owner** must separately approve that artifact's onward disclosure. When one owner
has several roles or inputs, one exact review enumerates all their data. Sharing
an owner or provider label does not remove approval; sharing an owner does not
provide sibling agents access. The nominated lead can approve only data they
actually own, never another owner's data.

`owner_review` returns common route/purpose metadata and only that owner's exact
text, with full-request/payload commitments. It does not expose other owners'
input text or the task objective to a source owner. This is a scoped content
review, not a claim that every owner saw the full payload. The common task ID and
output kind state the bounded purpose; any richer shared purpose in a live design
would need its own reviewed disclosure. Reviews and decisions bind exact context,
run, data, route, owner and execution claim.

Owner methods `owner_review`, `decide` and `revoke` are trusted local controls and
must never be exposed as agent tools. `decide` approves or refuses one pending
review. Approval requires an explicit finite expiry within one hour. The expiry
limits the initial local release, not a later retained original-result receipt.
It cannot be extended or renewed. Revocation can be recorded before approval or
after release. Status reports expired grants as expired, without erasing history.

## Atomic release and recovery

The agent facade provides `propose`, `release`, `record_result` and metadata-only
`status`. There is no discovery, credential loader, HTTP client, callback, adapter
execution, timer, retry, publication or spend mechanism.

`release` holds the same SQLite write transaction as the team's original
permissions and the execution ledger. It rechecks the current task, exact start
review, accepted input artifacts and their agent/task disclosures, every owner
review, and every disclosure expiry. It commits the original execution claim as
**uncertain**, increments conservative input-read counters, and records the exact
provider release digest before returning one immutable inert payload. Any failure
before the transaction commit rolls back both fences and the counters.

Two competing connections cannot both receive a release. A process crash after
commit, lost return, timeout, restart or later expiry cannot cause another release.
A raw local execution claim taken first also prevents provider release. It cannot
be repackaged after the fact as a provider-approved attempt. The original local
ledger remains usable for its independent synthetic fixture; it is not a live
provider path or bypass around this gate.

`record_result` reconciles only the original release digest and immutable bounded
text receipt. A matching digest authenticates no provider. The returned data is
not executable and does not itself create or accept an artifact. Local artifact
admission still uses the execution ledger; output disclosure and lead acceptance
remain separate team decisions. An exact result retry is metadata-only.

Provider disclosure withdrawal blocks future release but cannot recall data
already returned. It does not assert that external work stopped and does not
withdraw the separate, previously approved team-local task or input disclosure.
Use those team controls to stop local work or artifact admission. A late original
receipt may be retained even after either kind of revocation; it never restores
permission. Historical release and current withdrawal are reported separately.

## Limits and next gates

- **No live authorization.** A simulated approval and returned payload are never
  permission to call a real provider. Authenticated owner controls, actual
  provider/account identity, reviewed terms, credentials, data handling, tool and
  budget policy, transport and cancellation acceptance remain separate gates.
- **Trusted local operator.** One operator and SQLite file control this fixture.
  Labels, Python facades and hashes are neither human authentication nor isolation
  from arbitrary code in the process. Do not expose these owner methods remotely.
- **Direct artifact ownership only.** Owners come from the immutable team plan and
  the current artifact producer. The fixture does not infer data provenance inside
  text or transfer third-party rights. Derived content and embedded personal data
  need an explicit provenance/authority model before real use.
- **Stored synthetic content.** Requests and owner previews retain exact text in
  the same local database. Status and audit events omit raw text, routes and
  receipts. There is no encryption, retention/deletion service or backup rollback
  protection. Do not use personal data.
- **Immutable single attempt.** Destination changes, reapproval, revisions,
  independent recipient acceptance and real dispatch require future contracts,
  not deletion of the database or automatic retries.

Tests cover missing and crossed approvals, source/task/lead/scope withdrawal,
expiry, minimal owner previews, route changes, separate output disclosure,
transaction rollback, concurrent release/revocation, restart and lost receipts.
They exercise the existing team and execution contracts, not a live provider.
