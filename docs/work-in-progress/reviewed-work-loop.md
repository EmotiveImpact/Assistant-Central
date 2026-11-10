# Active work: reviewed task-to-result loop

Started 10 November 2026. Coordination owner: Pepper/Codex primary agent in the Assistant-Central thread.

Status: **work in progress, implementation not yet verified**. This draft is opened before implementation so other agents can see the claimed scope. Based on PR #7 (`66ec206d517d53c7648db0a756774d057176f6fb`), itself stacked on #6. Do not merge without Augustus's explicit approval.

## Claimed scope

Connect one accepted incoming task to an explicitly reviewed synthetic provider run, preserve its original result and provenance, stage an exact task-linked return artifact for a separate owner review/release, then let the original requester accept or reject it. Add owner HTTP/UI controls and a two-process regression demonstration. Acceptance, provider disclosure, result review and artifact release remain separate decisions.

No live provider activation, real personal information, public hosting or production-readiness claim. The model fixture must be unmistakably synthetic and opt-in; model output never creates authority. Unknown dispatch/result outcomes must remain inspectable without automatic retry. Permissions, parent context, intended recipient and expiry must be rechecked before result staging/release.

## File ownership and coordination

| Area | Assigned lane | Claimed files |
| --- | --- | --- |
| Backend composition and HTTP | Primary agent | `pilot/workflow.py`, `pilot/server.py`, associated boundary documentation and workflow wiring |
| Owner interface | Interface agent, assignment recorded in PR | `pilot/web/` and `pilot/INTERFACE.md` |
| Failure and authority review | Independent review agent, assignment recorded in PR | New `pilot/tests/test_workflow_review.py` only; report findings before editing implementation |
| Demo and composition evidence | Demo agent, assignment recorded in PR | New `pilot/workflow_demo.py` and focused workflow tests |

Other agents should avoid overlapping edits in these files until ownership is explicitly coordinated. The existing auth, encrypted transport and base runtime/provider contracts should remain stable unless a concrete blocker requires a narrow reviewed change.

Remote hosting/carrier, real-person enrolment, key recovery/rotation, encryption at rest and portable inherited-source grants are **not claimed by this PR**. They remain separate follow-on work.

## Acceptance evidence required

- [ ] Exact accepted task to synthetic provider run, with signed source grant and separate recipient approval.
- [ ] Reviewed original result to one exact return artifact, with no new provider dispatch or automatic release.
- [ ] Revocation, expiry, cancellation, wrong recipient/context, duplicate submission, concurrent staging and uncertain commit handling.
- [ ] Restart recovery and denied release after source withdrawal.
- [ ] Actual two-process HTTP workflow and interface contract/browser checks.
- [ ] Existing regression suites and independent review.

The PR description will be kept current with active ownership, blockers, verified results and the final implementation scope.
