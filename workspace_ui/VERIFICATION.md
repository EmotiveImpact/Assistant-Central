# Central workspace verification

The browser regression runs against `workspace_ui.demo`, with temporary fictional
owners, real local authentication and the existing runtime. The new interface does
not establish live-provider, remote-host or production acceptance.

## Browser regression coverage

- Seven state-backed views, search, list/board layouts and keyboard actions.
- Navigation and filtering cause no owner-state writes.
- Exact accept and reject decisions carry immutable review digests.
- Synthetic request approval, fixture execution, original-result staging and
  artifact release remain separate explicit operations.
- A deliberately lost response after a real committed release cannot trigger an
  automatic or duplicate retry; explicit inspection recovers the saved state.
- Creating a proposal saves only a draft; embedded hostile HTML is displayed as
  inert text during exact review.
- Public identity contains only the expected public keys and labels.
- Desktop, tablet and mobile layout; logout clears rendered sensitive content and
  session state; artifact text stays inert.

No check is claimed as passed until a run is recorded below. Screenshots are
browser captures of disposable synthetic runtime state, not design mock-ups.

## Results

- All **272 existing pilot tests** pass locally (96.570 seconds), including
  authentication, transport, HTTPS exchange, provider and reviewed-workflow
  regressions on this branch's base.
- All **7 workspace HTTP/static tests** pass locally (9.383 seconds).
- All **25 existing interface model tests** pass. Both actual HTTP-to-interface
  contracts pass, including separately approved synthetic work and draft-only
  result staging.
- All **9 new projection tests** pass, including exact accepted-only filtering,
  uncertainty presentation, literal search and unchanged authoritative state.
- `node --check workspace_ui/tests/browser.test.mjs` passes.
- Local Chromium was attempted on 10 November 2026. The executor rejects its
  process-singleton socket with `Operation not permitted` before any page opens.
  This is not a passing local browser run.
- The first hosted actual-browser suite passed on head `689c1d` in
  [run 42791642581](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42791642581).
  This exercised the actual disposable owner service, including lost committed
  response recovery. The first mobile capture caught the closing drawer during
  its CSS transition, so captures now wait for the drawer to finish closing.
- Final typography, projection filtering and screenshot refinements require the
  next exact-head hosted run. The suite now includes accepted-task metric
  assertions plus initial mobile viewport, artifacts and assistant-network
  captures. A historical passing run is not evidence for these later changes.
