# Durable local execution boundary

This is an **offline fictional composition** with the rebuilt team coordinator.
It implements the safe-retry part of [the research plan](../docs/research/orchestration-landscape.md#what-assistant-central-still-needs-to-own):
a started task is different from a dispatched attempt, an original result, a
candidate artifact, and the lead's acceptance. It is not a live provider adapter,
a peer protocol, or proof that two people independently control the system.

## Run

Python 3.11+ and the standard library are sufficient:

```sh
python -B execution/run_checks.py
python -B execution/demo.py
```

Both commands apply the team's socket/subprocess audit guard. That guard is a
regression check, not an OS security boundary. The demo scripts fictional owner
choices, loses a result receipt, restarts, blocks a second dispatch, reconciles
the original result, and passes the accepted artifact to a separately approved
copy task. It makes no external calls and leaves the new copy awaiting its
producer's separate disclosure consent.

After installing the repository's pinned fixture dependencies, run
`python -B execution/check_composition.py` to check the additional local seam:
an execution result becomes a candidate artifact, receives separate disclosure
and lead review, and is staged by the protocol binding as an unsigned proposal.
Revocation blocks restaging. This does not start the downstream task, send a
message or imply transport acceptance. Execution and protocol binding deliberately
load the same trusted team module so their exact-class checks compose correctly.

## Contract

Trusted local composition constructs `ExecutionLedger(workflow)` and obtains an
agent-bound facade. Never expose the workflow, constructor, database, or owner
methods as model tools. The facade has five transitions:

1. `prepare(task_id, run_id, artifact_id)` binds one already-started task to one
   immutable run and output identifier. It neither starts work nor grants access.
2. `claim(run_id)` checks the current team context, task, assignee, exact approved
   start and dependency disclosures inside one SQLite transaction. It records
   **uncertain** before returning the inert input envelope to its assigned local
   harness. No second claim is ever returned, including after a restart.
3. `record_result(run_id, claim_digest, content)` records the original bounded
   text result. The digest binds the exact claim, not an authenticated provider.
   Exact retries are metadata-only; changed content is rejected. A late result
   after revocation can be retained locally, but receives no publication rights.
4. `publish(run_id)` submits that exact output to the existing local candidate
   artifact/review gate. It does not send, render, run, accept or disclose it.
   "Publish" here is local artifact admission, not public or peer publication.
5. `status(run_id)` returns only run/task state and hashes to the bound agent.
   It returns neither the input envelope nor result text. It never gives a retry
   grant. Same-owner sibling agents have no implicit access.

A run persists in `prepared`, `uncertain`, `result_recorded`, or `published`.
Task and lead states are reported separately. A revoked task can still have an
uncertain attempt: cancellation does not establish that dispatched work stopped.
It also cannot erase information already returned to a harness. Input read
counters record committed releases, including a crash before the caller sees the
return; they conservatively mean "may have been read," not proof of consumption.

The fixed execution domain, context, run, owner/agent/provider references, task,
start-review digest, exact input artifacts and output identifier are part of the
claim digest. Task text and artifact content are always untrusted data. There is
no instruction interpreter, tool registry, provider discovery or callback dispatch
inside the ledger. Provider labels remain unverified references.

## Restart, conflict and cancellation semantics

The SQLite claim commit is the local dispatch fence. Competing connections cannot
both claim a run. If a process dies immediately after that commit, it may have done
no work at all. If it dies after doing work, the response may be lost. The ledger
cannot tell those situations apart, so both remain uncertain. A timeout, exception,
expired original start grant, new run ID or changed output ID does not authorize
another attempt. There are no timers, background retries, leases or reassignment.

An original result may be reconciled under its original claim digest. Submission
to the team artifact table and recording that fact in the execution ledger are
two transactions. A crash between them is safe to reconcile because the team API
compares the whole immutable artifact body under the same artifact ID. This path
never runs an adapter. If the task was later revoked, reconciliation may record
that the exact historical artifact already exists; it cannot create a new artifact,
revive a task, reapprove a disclosure or replace the output.

Revocation before claim stops input release. Revocation before a new artifact
submission stops admission. Source disclosure withdrawal, owner scope revocation
and lead withdrawal use the team's existing fences. Historical state remains
visible without implying current permission. The team still owns resource locks,
review, scope use limits and terminal task state.

## Deliberate limits and next gate

- **Synthetic-only.** A team start is not consent to transmit inputs to a model
  provider, spend money, invoke tools, create a PR or deploy. Replacing the local
  fixture with a real provider call is not an approved integration. That needs
  authenticated owner control, exact provider/data/tool/budget grants, reviewed
  credential custody and independently tested transport/host boundaries.
- **Trusted local state.** One operator and one SQLite database control this
  experiment. Bound Python objects and hashes do not authenticate humans,
  providers or arbitrary code in the same interpreter. The database is not
  tamper-evident, encrypted, or a protected multi-tenant store.
- **One attempt per task.** A lead request for changes does not dispatch another
  attempt. Revision/retry approval and failure reconciliation need a separate
  explicit contract. No result is automatically regenerated.
- **One durable database.** Do not fork the database to create two authorities,
  restore a stale backup and redispatch, or treat deletion as a safe retry. Storage
  rollback, power-loss durability, remote exactly-once execution and recovery from
  lost/corrupt state are not claimed.
- **Retained content.** Exact input envelopes and results remain in the local
  database. Status and audit events omit content, but this is not a privacy or
  retention service. Real personal data is out of scope.
- **Version coupling.** This composition deliberately uses rebuilt-r1 private
  helpers. It does not modify frozen team/protocol sources or the separate
  team-protocol-binding lane. Re-review on any team schema/API change.

The [provider disclosure rehearsal](PROVIDER_DISCLOSURE.md) now composes this
dispatch fence with exact route reviews from each data owner, still entirely
local and synthetic. Run `python -B execution/provider_demo.py` for the bounded
example. Its owner controls remain unauthenticated, and it grants no live access.
The next useful milestone is independently authenticated owner control and a
conformance-tested adapter. Do not count different fixture provider labels as
cross-provider proof.
