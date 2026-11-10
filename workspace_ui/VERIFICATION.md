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

The actual combined implementation passed both hosted Chromium suites on head
`715793b216fb8caf00c146df54ed1d1e55d797c4`, tree
`c6f5ff3abc93da93579d99bf803afb9564d87f6f`:

- [Combined Central browser run 42799055963](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42799055963)
  passed nine HTTP tests, 39 model/projection/transfer checks, the original owner
  workflow browser suite and the new two-owner real HTTP/TLS transfer suite.
- [Container isolation run 42799065770](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42799065770)
  passed actual Docker/UID isolation. Its PR merge tree was verified identical to
  the implementation tree above.
- [Screenshot archive 13754453383](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42799055963/artifacts/13754453383)
  was downloaded and its SHA256 verified as
  `a02849e50948c43f6dc094722b48f682f234060cb0bc1fb8092b2a40c836d875`.
  Desktop overview, board, artifacts, assistants, result review and transfer
  screenshots were inspected. The first transfer mobile capture caught the drawer
  transition, so the capture helper now waits for inert, fully hidden navigation
  and uses viewport-sized mobile captures. This is a test-evidence correction,
  not a product-authority change.

The latest exact-head aggregate runs and corrected mobile screenshot archive are
recorded in [PR #23](https://github.com/EmotiveImpact/Assistant-Central/pull/23).
The run and tree identifiers above deliberately identify immutable evidence;
subsequent code changes require their own passing checks rather than inheriting it.

No local Chromium was attempted during this composition. The assigned environment
has a known process-singleton socket restriction; it was not bypassed. The browser
evidence comes from actual hosted Chromium against the combined application.
