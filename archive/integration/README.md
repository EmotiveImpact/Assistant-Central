# Offline team-to-protocol binding

The original staging adapter below now has a separate
[synthetic recipient acceptance extension](RECIPIENT_ACCEPTANCE.md). It adds
explicit per-source-owner release and exact recipient accept/reject controls in
the trusted local team database. The original adapter and wire tools retain their
staging-only contract; independent authentication and transport remain unimplemented.

This is a trusted, local composition of the rebuilt team coordinator and the
recovered r5 proposal/wire building blocks. It stages **one unsigned local
proposal** for one exact accepted artifact and downstream task. It does not
connect independent assistants, authenticate a human, start recipient work,
approve a release, send a peer message, or claim recipient processing.

## Run

Use Python 3.12 with the pinned fixture dependencies already installed according
to the root verification instructions:

```sh
python -B integration/run_checks.py
python -B integration/demo.py
```

The demo uses only fictional data and scripted owner choices. Its JSON output
shows the mapping, the three recovered tool replies and the recipient task still
in `planned`. The runner and demo reject network and child-process audit events;
the only socket-construction exception is asyncio's local Unix wakeup pair. This
is an accidental-I/O guard, not an OS sandbox or protection against hostile Python.
Do not supply private data or real owner credentials.

## Exact mapping

A trusted operator constructs `BoundArtifactProposal` with a team workflow, exact
source artifact ID, exact recipient task ID and expected immutable team context.
The constructor and `binding_review()` do not stage an artifact. The adapter:

1. Requires the source task to be completed with the current accepted artifact.
2. Checks the artifact content digest, team context and original start-review digest.
3. Requires an explicit, current disclosure grant from the source agent's owner
   for that exact artifact, recipient agent and dependent task purpose. Sharing
   with the lead, a work scope, or two agents having the same owner is insufficient.
4. Commits the complete source/recipient task and agent references, artifact
   digest, start-review and disclosure-review digests into a versioned mapping.
5. Uses that mapping's SHA-256 as the protocol task context, its first 32 hex
   characters as the task ID, and the existing `fictional-answer/1` capability.
6. Stages the exact nonempty artifact text, bounded to 1,024 UTF-8 bytes. It never
   truncates, normalizes or rewrites the owner's reviewed content.

Protocol roles `alice` and `bob` mean source agent and recipient agent in this
mapping. They are not the team owners with those names. The mapping records the
actual team owner references separately. The public key descriptors are unchanged
public RFC fixtures, not enrolled identities or usable owner authentication.

## Exposed tool boundary

Only the existing recovered tools are exposed: `propose`, `proposal_status` and
`processed_inbox`. The r3 bridge requires the exact `AssistantFacade` type, so the
adapter narrows only the constructed instance's methods. No frozen prototype
source, r5 standalone launcher or launcher allowlist is changed.

- `propose` accepts only the exact artifact text. A caller cannot select an actor,
  owner, task, recipient, key, endpoint or grant.
- `proposal_status` accepts only this mapping's exact proposal ID and returns
  history without the artifact text. History remains readable after revocation.
- `processed_inbox` accepts no selectors and returns the initial empty snapshot.
  A nonempty or changed publication is rejected rather than disclosed.

The demo passes JSON/LF bytes through the unchanged r4 raw parser and r3 tool
bridge using in-memory streams. Fragmented UTF-8, duplicate members, rejected
owner tools and redacted error responses are covered. This is not an actual
stdio launch, native-host acceptance, peer transport or v29 runtime integration.

## Consent, expiry and uncertainty

The adapter revalidates the current team context, source artifact and exact
current disclosure under the team's `BEGIN IMMEDIATE` transaction immediately
before staging. A competing revocation cannot commit between that check and the
local staging operation. Revocation, terminal recipient work or lead withdrawal
blocks further staging. A historical record is not new permission.

Team start approvals expire before a task starts. Their expiry does not retroactively
invalidate a completed artifact. Disclosure grants in the current team model are
revocable but have no timer. Staging does not consume or renew the recipient's
work approval, and never bypasses its independent approval or expiry checks.
There is no release authority or delivery timer in this adapter.

The proposal store is a separate SQLite transaction. If staging or the enclosing
team transaction fails after the staging attempt begins, `OutcomeUnknown` is
raised with a fixed message. Inspect the exact proposal ID; do not automatically
retry, reset, reassign or treat an exception as proof that nothing committed.
Existing declined, unknown or other historical proposal states are not renewed.
Repeated successful staging uses the same deterministic proposal ID and record.

Revocation cannot erase the text from a previously staged local record or recall
content already read. This adapter does not mark a team disclosure as read: it
has not delivered the artifact to its recipient. It provides no cross-database
atomicity, durable distributed outbox, receipt or recipient-owned inbox.

## Trust and remaining gates

The constructor, team owner APIs, Python objects, local files and process are
trusted harness controls. An owner label is not authentication. The integration
must not be exposed as a selector-bearing tool or treated as a secure multi-user
service. Hash verification requires a trusted, nonconcurrently modified checkout;
it establishes consistency, not authenticity or runtime isolation.

Next work must supply authenticated owner controls and protected key custody,
independently enforced receiver acceptance and release controls, and safe persistent
transport/reconciliation before any real cross-owner sharing. A nominated lead
must never gain authority to approve another owner's actions or disclosure.
