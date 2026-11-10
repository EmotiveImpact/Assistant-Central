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

- `node --check workspace_ui/tests/browser.test.mjs` passes.
- Local Chromium was attempted on 10 November 2026. The executor rejects its
  process-singleton socket with `Operation not permitted` before any page opens.
  This is not a passing local browser run.
- The dedicated `Central workspace interface` GitHub Actions workflow runs the
  full browser suite against the actual disposable owner service, and uploads
  overview, work-board, result-review and mobile screenshots. Its first hosted
  result is pending.
