# Conversation final-boundary expiry hardening

Local coordination notice only. Publication and all GitHub writes remain on hold.

- Coordinator: Assistant Central integration work. Implementation owner: conversation security work.
- Exact local base: `82d1d871c0502ed9c358193aad100035523625e6`, tree `e8068d9cb3dd9ebe0f0e461c89c3bfe42751c90a`.
- Goal: refuse stale source-sensitive ledger output or commits when final authentication or policy checks observe an expired history grant or session.
- Claimed files: `conversation/ledger.py`, new focused conversation tests, and this notice. No proposal, owner interface, server, provider, bridge or authentication implementation changes.
- Plan: add independent regressions before changing implementation; reuse the existing transaction final-check hook and durable clock fence. Preserve exact owner approvals, future-only joins, member epochs, transitive lineage, actor sessions and the coordinating owner's unlock lifetime.
- Verification: targeted expiry, refusal, restart and rollback cases; all conversation/proposal and pilot tests; patch checks. Additional checks will be recorded only after running them.
- Boundaries: fictional local identities only, no publication, remote readiness changes, merge, real credentials or live provider activation. The public draft notice is held with all other writes.
- This first commit contains coordination only, not a working fix.

## Implemented boundary

`append`, `read`, `history` (including search and pagination), `context`,
`prepare_history_grant` and `approve_history_grant` now explicitly opt into the
existing transaction's final-check hook. The transaction's default remains
unchanged. The optional hook captures the exact actor session's deadline and the
coordinating owner's latest retained session deadline while both authentication
locks are held. Another current coordinator session can keep storage unlocked;
another current actor session cannot extend the particular token being used.

Source checks reuse the ledger's existing visibility and transitive-lineage
algorithm. The shared assertion samples time at both ends of the complete output
scan, and refuses if any non-revoked room grant expires within that interval.
This is deliberately conservative: an unrelated or overlapping grant can cause
a generic refusal, even when fresh inspection would still be authorised. No
hidden IDs, totals or grant details are returned. Empty history and search still
receive lifetime checks; a pagination cursor remains part of the final visibility
check even if there are no matching results.

Grant preparation and approval check the exact statement's expiry after final
authentication. Approval still owns only the original author's immutable events,
requires the recipient's current membership epoch, rejects a stale new review,
and performs its legitimate policy-generation increment. An identical already
retained approval remains idempotent while current, without rechecking it against
its own generation increment. Expired or revoked approval retries cannot revive
it. The final hook does not mutate a retained statement or give a source author's
approval authority over another author's content.

Opted-in body, authentication and policy refusals persist the observed clock
outside the rolled-back message or grant transaction. Restart with a rewound
clock therefore cannot revive authority. SQLite failures remain uncertain,
including a lost commit acknowledgement combined with a clock refusal. Inspect
the stable request after reopening rather than assuming rollback or automatically
retrying an external effect. Ordinary identical message retries still return the
same retained message when its current visibility permits.

Actor and coordinator deadline comparisons remain after the extra checks, with
no trailing authentication callback that would reopen the original gap. This is
an observed-time boundary under the existing local locks, not a claim that wall
clock progression and SQLite commit are mathematically simultaneous. No remote,
distributed or independent-device security claim is added.

## Verification approach

The first regression commit preceded the implementation. On the unchanged base,
11 new test methods exposed 21 failing subcases, while exact-retry and uncertain
commit controls passed. The final focused file contains 14 methods, adding exact
expiry, conservative overlapping/unrelated grant behaviour and uncertainty during
clock rewind. The examples use only fictional identities and disposable local
authentication stores.

Final local verification on 10 November 2026:

- `python -B -m unittest conversation.tests.test_final_source_expiry -v`: 14 tests passed, with multiple adversarial subcases.
- `python -B -m unittest discover -s conversation/tests -v`: 114 tests passed, including all existing proposal, concurrency, schema and lifecycle reviews.
- `python -B -m unittest discover -s pilot/tests -v`: 378 tests passed.
- `python -B -m conversation.demo` and `python -B -m conversation.proposals_demo`: passed with fictional local fixtures and no live transport/provider calls.
- Python compilation and `git diff --check`: passed.

These results cover this isolated local branch, not the separately composed owner
workspace or remote CI. Publication remains held. Independent review and any
later local integration must use the exact frozen commit and tree supplied with
the implementation handoff, then rerun the combined checks.
