# Central workspace composition verification

The composed shell retains PR #19 at
`83a7d1539e9cf13abf5911157fdc265aea20a00f` and PR #16 at
`002d4afd0784f7ac68e2e6e106a2c4a09cc9d61f`. The interface calls the unchanged
owner API and uses the shared model and transfer validators.

## Verification boundary

`workspace_ui.demo` uses disposable fictional owners and real local authentication.
`workspace_ui.transfer_fixture` adds disposable real TLS mailboxes and explicit
owner transfer controls. These are synthetic fixtures, not human consent, physical
host acceptance, real-person onboarding or production deployment. Live provider
calls remain disabled. The fixture result is not completed research or AI output.

## Regression coverage

- Recursive relative-module HTTP closure includes the exact shared `model.mjs`
  and `transfers.mjs`, without broadening the static allowlist.
- Default-disabled trusted transfer configuration delegates to the reviewed loader.
- Eight state-backed views, search, list/board layouts and keyboard actions.
  Navigation, search and layout never write owner state.
- Exact accept/reject, separate synthetic approval/run/stage/release and inert
  hostile text remain covered against the real owner API.
- Transfer confirmation, exact connection/fingerprint binding, explicit send and
  retry, stale/malformed review refusal, quarantine import and original receipt
  controls use the same owner session and mutation gate.
- Deliberately lost responses after actual committed writes and failed inspections
  fence further mutations; recovery requires explicit saved-state inspection.
- A second fictional owner explicitly imports the delivery, separately returns
  its original signed receipt, and the first owner explicitly imports that receipt.
  Outbox receipt state remains distinct from proposal acceptance; prior attempt
  uncertainty is immutable.
- A fixture-only gate holds completion after actual TLS transmission, so in-flight
  withdrawal is tested without timing guesses or claiming to recall retained bytes.
- Named dialogs, keyboard skip without route mutation, actual-surface quiet and
  placeholder contrast, desktop/tablet/mobile layout and hidden-content logout
  cleanup are browser assertions.

## Local results, 10 November 2026

- **377 pilot tests pass** in 163.699 seconds, including the combined transfer,
  storage, source-grant and receipt-recovery regressions.
- **9 workspace HTTP/static/configuration tests pass** in 12.083 seconds.
  Removing only `/transfers.mjs` makes the recursive HTTP graph test fail with
  status 400; restoring that exact route makes it pass.
- **39 shared model, transfer and workspace projection tests pass**.
- **20 isolation-harness unit tests pass**; actual Docker isolation remains a hosted
  check, not a claim based on these unit tests.
- Both actual HTTP-to-interface contracts pass.
- Team (84), execution (133) and integration (103) suites pass, together with their
  synthetic demos, execution/proposal composition, separate-process pilot demo and
  reviewed-workflow demo.
- Public import integrity passes for 673 imported files and 17 team entries.
- JavaScript syntax and whitespace checks pass.

## Hosted evidence

The unmodified dependency composition at `6bb22b2c29fe0e0078ffcaa7c6a6664358cb2be1`
failed actual Chromium startup in
[run 42796784062](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42796784062)
even though its former seven HTTP and nine projection checks passed. The recursive
module-graph test now covers that missing boundary.

The historical PR #19 workspace run
[42792553357](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42792553357)
passed on its exact head. It does not establish browser acceptance for the composed
transfer shell. The final composed-tree browser and aggregate runs are pending and
will be recorded in the PR with exact head/tree identifiers and screenshot evidence.

No local Chromium was attempted during this composition. The assigned environment
has a known process-singleton socket restriction; it was not bypassed. Hosted
Chromium must execute the actual combined application before this work is accepted.
