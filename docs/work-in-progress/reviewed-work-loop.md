# Active work: reviewed task-to-result loop

Started 10 November 2026. Coordination owner: Pepper/Codex primary agent in the Assistant-Central thread.

Status: **implementation complete; review and exact-commit check status are in [PR #8](https://github.com/EmotiveImpact/Assistant-Central/pull/8)**. This draft was opened before implementation so other agents could see the claimed scope. It now targets `main` after PRs #6/#7 merged. Do not merge without Augustus's explicit approval.

## Claimed scope

Connect one accepted incoming task to an explicitly reviewed synthetic provider run, preserve its original result and provenance, stage an exact task-linked return artifact for a separate owner review/release, then let the original requester accept or reject it. Add owner HTTP/UI controls and a two-process regression demonstration. Acceptance, provider disclosure, result review and artifact release remain separate decisions.

No live provider activation, real personal information, public hosting or production-readiness claim. The model fixture must be unmistakably synthetic and opt-in; model output never creates authority. Unknown dispatch/result outcomes must remain inspectable without automatic retry. Permissions, parent context, intended recipient and expiry must be rechecked before result staging/release.

## File ownership and coordination

| Area | Assigned lane | Claimed files |
| --- | --- | --- |
| HTTP composition and coordination | `/root` | `pilot/server.py`, test-helper/fixture switches, CI, `AGENTS.md` and coordination/evidence docs |
| Exact result staging | `/root/workloop_core` | `pilot/workflow.py`, focused core tests and `pilot/WORKFLOW.md`; narrow transactional helpers in `pilot/runtime.py` |
| Owner interface | `/root/workloop_ui` | `pilot/web/` and `pilot/INTERFACE.md` |
| Failure and authority review | `/root/workloop_review` | New `pilot/tests/test_workflow_review.py` and `pilot/WORKFLOW_REVIEW.md`; report findings before editing implementation |
| Demo and composition evidence | `/root/workloop_demo` | New `pilot/workflow_demo.py` and `pilot/tests/test_workflow_http.py` |

Other agents should avoid overlapping edits in these files until ownership is explicitly coordinated. The existing auth, encrypted transport and base runtime/provider contracts should remain stable unless a concrete blocker requires a narrow reviewed change.

Remote hosting/carrier, real-person enrolment, key recovery/rotation, encryption at rest and portable inherited-source grants are **not claimed by this PR**. They remain separate follow-on work.

Concurrent work is visible in [PR #9](https://github.com/EmotiveImpact/Assistant-Central/pull/9)
(password maintenance) and [PR #10](https://github.com/EmotiveImpact/Assistant-Central/pull/10)
(container/storage isolation). Their implementations are not included here.

## Acceptance evidence required

- [x] Exact accepted task to synthetic provider run, with signed source grant and separate recipient approval.
- [x] Reviewed original result to one exact return artifact, with no new provider dispatch or automatic release.
- [x] Revocation, expiry, cancellation, wrong recipient/context, duplicate submission, concurrent staging and uncertain commit handling.
- [x] Restart recovery and denied release after source withdrawal.
- [x] Actual two-process HTTP workflow and both interface contracts.
- [x] 195 pilot Python tests, including 54 new checks; 25 interface model tests; independent review completed.
- [x] Hosted browser exercised the new workflow; screenshot inspection led to an explicit post-release state-label regression.

The full regression workflow and browser run execute for each published head.
Check the current [PR checks](https://github.com/EmotiveImpact/Assistant-Central/pull/8/checks)
before merging; earlier passing heads do not establish a later head's result.

The PR description will be kept current with active ownership, blockers, verified results and the final implementation scope.
