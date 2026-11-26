# Assistant team orchestration: rebuilt offline checkpoint r1

This is a **new replacement implementation**, written on November 8, 2026. It is
not recovered source and does not reproduce or claim the identity of the missing
local commit `538a77b4fd2a93abb73968dfa3dffa3060b5e6d8`.

The recovered v29 consent/protocol prototype and r5 synthetic stdio launcher are
published as companion source directories, with non-code evidence paths normalized. See the root PROVENANCE.md. This team module does not yet
connect its state machine to either transport. It is not a native host, MCP server,
provider integration, distributed authority system, or production service.

## What is implemented

- An immutable team plan with a nominated lead, multiple agents per owner,
  provider-reference labels, dependent tasks and parallel work.
- Explicit acceptance by the nominated lead's owner. Nomination never supplies
  another owner's permission.
- Exact start proposals and separately applied owner approval or bounded
  preapproval for named tasks, with a one-hour maximum validity and use limit.
- Separate exact artifact disclosure consent for the nominated lead's review or
  one named downstream agent/task. Agents sharing an owner do not share access.
- SQLite-backed atomic resource locks, grant consumption, decisions, artifact
  records and audit events. Conflicts do not consume permission.
- Immutable text artifacts, hashes and the exact approved start/input-review
  commitment. Revised outputs need fresh disclosure consent and lead review.
- Refusal, scope/task/disclosure revocation and lead withdrawal, with terminal
  fences and dependency stopping. History is retained, not erased.
- A fully fictional five-output demonstration: research, copy, slide outline,
  website draft and PR draft. Nothing is published and no actual PR is created.

## Run

Python 3.11+ and its standard library suffice. Tested here on Linux/Python 3.12.
No package installation or keys are needed.

```
python -B run_checks.py
python -B demo.py
```

The test runner prevents audited socket and subprocess activity. This is an
additional regression check, not an OS security boundary. The demo explicitly
simulates each fictional owner's choices; it cannot establish that a real human
approved anything. Its temporary SQLite file and outputs are discarded at exit.
Five example JSON artifact files are preserved under `evidence/demo-artifacts/`.

Use `TeamWorkflow(database, plan)` directly for a persistent **fictional** local
experiment. Reopen only with the exact same immutable plan; changed scope is
rejected. Reusing a proposal ID cannot change its task; new aliases preserve the
original refusal. An exact successful start retry is a read-only status result,
not fresh permission or a second scope use. There is no automatic retry loop.

## Authority and sharing boundaries

`TeamWorkflow` owner methods are **trusted harness controls**. Passing an owner
label is not authentication, a signature, or proof of human approval. Never expose
those methods to an agent, peer message, or public API. `AgentFacade` is bound by
trusted construction and offers only the assigned work, start, submit, read and
lead-review operations. It is not an object-capability sandbox against arbitrary
Python code with access to the same interpreter or database.

The stored plan is trusted local input. Provider labels do not verify a provider,
owner identity, account or installed assistant. No real model executes a task.
Output kinds are inert descriptions, not tool permissions. Content is never
evaluated, rendered, fetched, sent or passed to another application.

A work scope binds exact owner, team context, tasks, assignees, objectives,
dependencies, output kinds and resource names. It authorizes **starting** those
tasks, not content disclosure, publication, payment, repository access, or all work
by that owner. The scope permits use of separately disclosed accepted outputs from
the exact named dependencies. Manual approval commits the actual dependency
artifact hashes. Expiry limits new starts; it does not retroactively recall a
started local task. Explicit scope revocation stops its unfinished work.

The producer agent can read its own artifacts. Any other agent, including another
agent of the same owner, needs exact disclosure permission. Review and downstream
task purposes are separately namespaced. Disclosure is durable until explicitly
revoked, task/role withdrawal, or the fictional database is discarded; it is not
renewed automatically. Revoked disclosures cannot be reapproved in the same plan.

Withdrawing input disclosure stops the corresponding unfinished downstream task
and its unfinished dependents, releases locks and prevents future reads for that
task. Revoking a source task also fences its outgoing grants. Already completed
downstream results are historical facts, not magically recalled. Lead withdrawal
stops unfinished work and revokes lead-review access. Content already read cannot
be erased from a recipient's knowledge; read counters preserve that distinction.

Task refusal is terminal. A changed plan or genuinely new work needs a new plan
context and separate permission. This checkpoint deliberately has no automatic
reassignment, successor creation, leader election, context migration or recovery
from corrupted/lost state.

## Limits and next integration gate

This is a local team coordinator, not cross-owner distributed enforcement. One
trusted operator and one SQLite database control the fixture. Its plan labels and
audit rows are not tamper-evident signatures. SQLite serializes competing local
connections; resource names are exact logical identifiers, not verified OS files,
cloud locks or external-resource leases. The same resource must be represented by
the same exact identifier. There is no fairness, lease timeout or crash-recovery
claim for outside work. A lock left by unfinished work requires explicit owner
revocation or continuation from the retained database.

The next integration must bind authenticated local owner controls and one scoped
agent/tool route to this plan, map its task/artifact digests explicitly to the
existing v29/r5 protocol, and retain separate disclosure and recipient authority.
It must not let the lead mint other owners' grants or silently turn text artifacts
into execution instructions. Real owner/key custody, peer transport, cancellation
propagation, host acceptance, retention and confidentiality remain separate gates.

See `VERIFICATION.json` and `evidence/` for this rebuild's own results. Old counts
belong to their old artifacts and are not presented as tests of this module.
