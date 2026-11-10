# Exact message outcome inspection: local coordination notice

- Coordination: conversation integration maintainer. Implementation:
  conversation implementation maintainer.
- Exact base: `20bc01bc210446b44d76f997ba40e07a2e8568c3`, tree
  `7620b1963c00926e2e750aaaf37cd73a475feba6`.
- Goal: inspect one authenticated actor's exact room and message request after an
  uncertain acknowledgement without replaying a write or broadening disclosure.
- Claimed files: `conversation/ledger.py`,
  `conversation/tests/test_message_outcomes.py`, `conversation/README.md` and this
  notice. No owner UI, server, proposal semantics, schema or provider changes.
- Separate local worktree and branch: `assistant-central-exact-message-outcomes`,
  `local/exact-message-outcomes`. File ownership was confirmed with the
  conversation integration and owner-workspace maintainers before implementation.
- GitHub publication is blocked. This notice substitutes for a remote draft;
  no remote write, ready/merge action or attempt to bypass the block is authorised.
- Planned verification: fictional genuine local sessions; lost commit reply,
  absent/changed requests, owner and room scoping, current membership and grant
  lineage, signature/commitment verification, final authentication/scan expiry,
  durable clock rollback, unchanged rows, conversation/proposal and pilot suites.
- Initial commit is coordination only. No implementation or passing tests claimed.

## Local implementation and verification

The isolated `inspect_message_outcome` method accepts only an exact request ID and
strict lowercase SHA-256 request commitment, alongside the authenticated actor,
session and current room binding. It returns `committed` with the usual public
event or `inconclusive` without an event. A found but mismatched or inaccessible
request is generically refused. The signed fields are independently rehashed;
current complete source visibility and final actor/coordinator lifetime guards
remain mandatory, including for absence. See the README for canonicalisation.

No message, grant, audit, membership or approval rows are added or changed by
inspection. The existing durable observed-clock fence can advance, as for other
reads. There is no schema, transaction-hook default, append, proposal, UI, HTTP,
provider or automatic-retry change.

Verified locally with Python 3.12 and cryptography 50.0.0:

- `python -B -m unittest discover -s conversation/tests -v`: 134 passed, including
  all 20 new exact-inspection tests and the pre-existing 114 conversation/proposal
  checks.
- `python -B -m unittest discover -s pilot/tests -v`: all 378 passed.
- `python -B -m conversation.demo` and `python -B -m conversation.proposals_demo`:
  both passed using fictional local owners with no live provider activation.
- `python -B -m compileall -q conversation/ledger.py conversation/tests/test_message_outcomes.py`
  and `git diff --check`: passed.

Coverage includes an actual SQLite message commit with a lost acknowledgement;
inspection beyond the first 25 history records; unchanged retained rows; absent
and changed requests; other authors, rooms and sessions; stale membership,
removal/rejoin and exact renewed grants; signature and commitment corruption;
missing, altered, cross-room and transitive sources; revoked or expired grants;
locked coordinator; actor/coordinator expiry at final authentication and during
final scans for both found and absent requests; expiry at the exact deadline;
restart session invalidation and durable clock rewind refusal; exact UTF-8 digest
semantics and bounded input. Passing tests are local evidence, not distributed
end-to-end acceptance or a claim about existing personal assistants.

Independent maintainer review and any later composition remain separate. No GitHub
publication, remote write, merge or deployment was attempted.
