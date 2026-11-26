# Optional fictional continuity possession proofs

## Contract and boundaries

This opt-in, offline, disposable core associates an existing fictional task-owner
public root with an explicitly enrolled fictional continuity public root. Two
separate task owners can each prove possession against the same continuity root.
This is **informational evidence only**, not real-person authentication, an
account, provider identity, persistence, recovery, shared task identity or shared
authority. Labels and relationship groups never infer associations.

The continuity private key exists only in a separate guarded subprocess. It
cannot sign any grants, task decisions, bindings, messages or withdrawals.
Task-owner keys remain independent and sign only a new fixed-domain possession
body through a narrow closed command. Existing task/agent wire schemas,
IdentityRegistry, authorization hashes, transport roots and authority signatures
are unchanged. Association never creates a task, binding, pairing, grant or
message. No continuity methods are exposed to the restricted agent grammar.

All core entry points run under OwnerWorkspace's existing RLock and return
fully detached public data. Single objects are bounded to 8 KiB; aggregate state
is bounded structurally by 4 lifetime identity slots and 20 lifetime association
slots. Successful, retired, failed and uncertain slots are never recycled.
Input objects have exact closed keys, bounded identifiers and integer times.

## Enablement and owner API

Construct `OwnerWorkspace(continuity=True)`. Default `OwnerWorkspace()` keeps
continuity disabled and creates no continuity registry or signer. Even opt-in
construction creates **no signing key or child process**. Enrollment preview
creates none; only explicit enrollment commit starts the disposable signer.
Task creation independently remains explicit.

The trusted owner API consists of:

- `continuity_preview(request)`
- `continuity_commit(operation, review, confirmation)`
- `continuity_state()`

The trusted workspace HTTP, console and frontend-model surfaces expose these
methods only after explicit opt-in. Use `python local_owner_app.py --workspace
--continuity` or `python workspace_console.py --continuity`; see
CONTINUITY_OWNER_GUIDE.md. Default launcher behavior stays disabled. No restricted
agent methods are added. Never infer enablement or consent from groups.

### Enrollment

Request JSON:

```json
{"operation":"enroll","identity_id":"fictional-one"}
```

Preview has exactly `operation`, `incarnation`, `identity_id`, `generation`,
`review_digest`. Commit with operation `enroll` and the exact phrase
`ENROLL CONTINUITY <review_digest>`. It returns aggregate state. The public
anchor contains exactly:

```json
{
  "incarnation":"<64 lowercase hex characters>",
  "identity_id":"fictional-one",
  "identity_version":1,
  "continuity_root":"<64 lowercase hex characters>",
  "fingerprint":"<64 lowercase hex characters>"
}
```

The fingerprint is the ordinary digest of `{"continuity_root": root}`. A startup
failure occupies an uncertain identity slot whose anchor may lack root and
fingerprint. Such an identity cannot associate. Exact enrollment retry returns
existing state and never regenerates a key. Changed reuse of an occupied ID fails.

### Association

Separately create the desired task using the unchanged task API, then request:

```json
{
  "operation":"associate",
  "identity_id":"fictional-one",
  "association_id":"proof-garden",
  "selector":"garden",
  "context":"<exact existing task context>",
  "actor":"alice"
}
```

Actor must be an actual existing owner of that exact task. Preview reads the
already-created service's public root and has exactly `body` and `review_digest`.
The body has exactly these fields:

```json
{
  "purpose":"informational-fictional-association-only",
  "incarnation":"<workspace incarnation>",
  "identity_id":"fictional-one",
  "identity_version":1,
  "continuity_root":"<enrolled public root>",
  "fingerprint":"<enrolled fingerprint>",
  "association_id":"proof-garden",
  "selector":"garden",
  "context":"<existing context>",
  "actor":"alice",
  "owner_root":"<existing task-owner public root>",
  "nonce":"<fresh authenticated 64-hex nonce>",
  "generation":1,
  "issued_at":1800000000,
  "review_expires_at":1800000120,
  "certificate_expires_at":1800086400
}
```

Example timestamps above illustrate shape only. Preview uses current integer UTC
seconds. It is pure: no child, signature, task, registry slot or mutable pending
record is created. A random nonce plus private workspace MAC prevents alteration
of stateless preview fields even if a caller recomputes the public review digest.
The digest is `digest({"domain":"fictional-continuity-review/v1","body":body})`.
Enrollment, association attempts and retirement advance the registry generation;
intervening mutations make old uncommitted association reviews stale.

Commit with operation `associate` and exact phrase
`ASSOCIATE CONTINUITY <review_digest>`. One exact confirmation authorizes both
informational signatures for that exact body. The owner signer is pinned at task
startup to this workspace incarnation and task selector, and independently checks
context, actor, its own public root, exact anchor, purpose and review lifetime.
It cannot sign arbitrary owner contexts or authority-shaped bodies. The second
signer is pinned at enrollment to incarnation, identity ID and its own root.
Both reject repeat association IDs. The trusted workspace never automatically
retries signing.

The row result contains exactly `association_id`, `status`, `active`,
`historical`, `review`, `certificate`. Certificate is null for uncertain attempts;
otherwise exactly `body`, `owner_signature`, `continuity_signature`. The two
signatures use distinct domains:

- `fictional-continuity-task-possession/v1`
- `fictional-continuity-identity-possession/v1`

`verify_certificate(certificate, incarnation)` verifies **historical possession
signatures only**, not active recognition, current membership or authorization.
Fresh workspace incarnations reject old certificates. Recognition is determined
only from the current workspace's pinned record and fences. Do not use verifier
success as a current-active claim.

An exact association commit retry returns original history with current status,
even after expiry, retirement or closure. It never renews or signs. Changed ID
reuse fails. Before the first IPC write the slot is pinned as uncertain. Any IPC
or proof-verification failure leaves that tombstone; no automatic signature retry
or new grant is allowed. An uncertain signature may have existed in a child but
is never published as a successful association.

### Expiry and status

**Review acceptance window** is 120 seconds from preview creation. Commit checks
this window before either signature and rechecks it after both IPC responses,
before activation; after a certificate exists, review expiry
has no effect on it. **Certificate active lifetime** is at most 24 hours from
preview creation. It is never renewed by inspection or retry.

Active recognition means local recognition of a historical certificate, not
present signer-process health, live possession, human identity or permission.
Signer death alone does not invalidate historical recognition and never triggers
key or process recreation.

Rows always carry historical evidence (or a historical uncertain tombstone).
`active` is true only when status is `active`. Possible statuses:

- `active`: successfully proven, certificate unexpired, enrolled identity active,
  selected task open, workspace open and task not group-stopped.
- `retired`: successfully proven but continuity identity no longer active.
- `closed`: task or workspace no longer open.
- `stopped`: existing relationship stop fence is active for that exact task.
- `expired`: certificate lifetime elapsed.
- `uncertain`: proof attempt failed or outcome could not be established.

If multiple inactivity reasons apply, precedence is retired, closed, stopped,
expired. Whole-workspace cleanup retires identities, so it normally shows retired.
Historical signature verification stays possible regardless of these statuses.
New signing is fenced by retirement, workspace/task closure and group stops.
Historical inspection and exact association retries remain readable.

### Retirement

Request `{"operation":"retire","identity_id":"fictional-one"}`. Preview
contains exactly operation, the five anchor fields and review_digest (an uncertain
startup anchor may contain fewer fields). Confirm operation `retire` with exact
phrase `RETIRE CONTINUITY <review_digest>`. Retirement commits the irreversible
local recognition fence before attempting continuity-key disposal. If disposal
fails, phase stays retired and cleanup is uncertain; explicit exact retirement
retry may retry cleanup, never signing. Successful cleanup is reported disposed.

Retirement **does not cancel any task, revoke any task grant or stop messages**.
Use the existing explicit relationship group stop or task controls separately.
There is no reactivation, in-place rotation, automatic migration or recovery.
Public historical evidence remains until this disposable workspace is discarded.

### Aggregate state

State has exactly `incarnation`, `identities`, `associations`. Each identity has
exactly `anchor`, `phase` (`active`, `uncertain`, `retired`) and `cleanup` (`live`,
`uncertain`, `disposed`). Associations are row results above. No private key,
process handle, preview MAC secret, grant or authority registry is exported.
Task cleanup and continuity cleanup are independent best-effort operations;
whole-workspace close attempts both even if one reports uncertain cleanup.

## Offline checks

Use the existing offline dependencies. Focused tests:

```sh
python -m unittest discover -s tests -p 'test_continuity*.py' -v
```

Run the unchanged full unittest discovery and existing DOM fixtures before
integrating a checkpoint. No browser, network, installation or live provider is
needed. Checkpoint manifests must match the exact source tested in a fresh extraction.
