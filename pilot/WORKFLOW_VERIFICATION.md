# Reviewed work-loop evidence

Local verification on 10 November 2026:

| Check | Result |
| --- | --- |
| `python -B -m unittest discover -s pilot/tests -v` | 195 passed: original 141 plus 17 work-loop core, 11 actual HTTP and 26 independent review tests |
| `node --test pilot/web/tests/model.test.mjs` | 25 passed: original 16 plus 9 workflow cases, including truthful post-release state labels |
| `python -B pilot/web/tests/live_contract.py` | Existing actual HTTP-to-interface contract passed |
| `python -B pilot/web/tests/workflow_contract.py` | New actual HTTP workflow contract passed |
| `python -B -m pilot.workflow_demo` | Two separate processes/stores completed the synthetic result and return-artifact loop |
| `python -B tools/verify_import.py` | 673 imported files and 17 team manifest entries verified |
| `git diff --check` | Passed |

The two-process demo observed separate task acceptance, request approval, one
fixture dispatch, original-result review, draft-only staging, separate release
and requester acceptance. It also observed rejected work, offline delivery,
restart on the original pinned endpoint, invalidation of the old session,
unchanged original result/review, duplicate staging and blocked dispatch after
observed source withdrawal. A second live server cannot share the endpoint.

The [independent review](WORKFLOW_REVIEW.md) records the reproduced disabled-mode
compatibility defect and its repair, together with cancellation rollback,
concurrent staging and uncertainty evidence.

The hosted browser extension exercises the real owner HTTP service through the
complete sequence of separate approval, run, result review, staging and release
clicks. Its new result-review screenshot supplements desktop and mobile captures.
Local Chromium was attempted but failed before opening a page because Unix
sockets are blocked (`EPERM`). The hosted browser passed the new sequence on
implementation `95c3ef01dfadcb1c3884c987faba91101b3a7e14` in
[run 42781429103](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42781429103).
All three screenshots were inspected after verifying the downloaded archive's
SHA-256, `29abfe3d9349d54b57d0cc780308881831622f6f4cf756de7e571f6da08365e2`.

Visual review found that the task subtitle still called a released artifact a
draft. The UI now displays the actual artifact state, with a model regression
and a browser assertion after release. That correction requires its own hosted
run. Browser/full-regression results for the current commit and screenshot artifacts
are linked in [PR #8](https://github.com/EmotiveImpact/Assistant-Central/pull/8).
The earlier PR #7 browser pass does not validate this interaction sequence.

No model or research was run, no provider was contacted and no real people were
enrolled. The fixed labelled output is a local fixture. Separate same-UID processes
do not establish hostile-host isolation or a separately hosted deployment. Remote
carrier, real-owner enrolment and live-provider acceptance remain future work.
