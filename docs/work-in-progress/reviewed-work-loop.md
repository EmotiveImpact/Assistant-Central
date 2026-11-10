# Active work: reviewed task-to-result loop

Started 10 November 2026. Coordination owner: Pepper/Codex primary agent in the Assistant-Central thread.

Status: **work in progress, implementation not yet verified**. This draft is opened before implementation so other agents can see the claimed scope. Based on PR #7 (`66ec206d517d53c7648db0a756774d057176f6fb`), itself stacked on #6. Do not merge without Augustus's explicit approval.

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

## Acceptance evidence required

- [ ] Exact accepted task to synthetic provider run, with signed source grant and separate recipient approval.
- [ ] Reviewed original result to one exact return artifact, with no new provider dispatch or automatic release.
- [ ] Revocation, expiry, cancellation, wrong recipient/context, duplicate submission, concurrent staging and uncertain commit handling.
- [ ] Restart recovery and denied release after source withdrawal.
- [ ] Actual two-process HTTP workflow and interface contract/browser checks.
- [ ] Existing regression suites and independent review.

The PR description will be kept current with active ownership, blockers, verified results and the final implementation scope.
