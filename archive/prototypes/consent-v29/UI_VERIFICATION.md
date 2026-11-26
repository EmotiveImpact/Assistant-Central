# Local owner interface verification

This is a development checkpoint with a real-browser verification gap. Do not
call the interface browser-tested, visually reviewed or production-ready.

## V21 bounded-text capability evidence

Final aggregate counts and clean archive verification are in `verification-v21.json`.
The added checks cover exact alternative capability schemas, immutable reply bounds,
fixed operation, backward-compatible catalog and composition hashes, wrong-capability
replay, proposal/signer/linkage refusal, historical review reuse, maximum escaped
Unicode, real local subprocess lifecycle in both directions and HTTP handler flow.

A deterministic state/fault campaign subsequently found and fixed local storage
consistency gaps before publication: response composition with damaged live context
metadata and agent inbox disclosure without full history validation. New aliases
now require coherent history too. The campaign executed 1,920 top-level probes
(1,545 refused, 209 reads, 166 reopens), with separate history/fault scenarios.
These are campaign operations, not additional unittest cases. Five independent
context-review tests verify the fix; this is not a remote-agent exploit or a claim
of cryptographically authenticated storage. Initial failure logs are retained.

New DOM models exercise capability switching without mutation, old shortlist wire
shape, fresh preview requirements, typed creation, bounded text validation, exact
code-point handling, captured response previews, edit/Back/navigation, duplicate and
late outcomes, and inert received text. These are not real-browser/native-dialog,
visual, keyboard or screen-reader acceptance. No browser retry was attempted.

## V20 received-message evidence

The final clean extraction passed **609 Python tests** and **115 DOM-model checks**.
Aggregate and fresh-extraction evidence is in `verification-v20.json`.
The new checks are real local process, in-process HTTP handler and DOM-model
checks, not browser/native-dialog, visual or accessibility acceptance.

Backend/handler coverage includes both request/response directions, exact recipient
and context, content hidden before processing, receipt-only and uncertain/blocked
outcomes, processed history after cancellation, reopen, no durable writes or
proposal table creation, pending authorizations not reconciled, no owner-key/review
fields, corrupted full history and composition rejection, maximum Unicode messages,
closed/uncertain fences, catalog compatibility and no new agent command.

The received-message model suites verify read-only navigation/refresh, inert exact
payload/digest/binding display, empty and cancelled states, resource text without
links, owner/task and same-route navigation, delayed reads/errors, repeated refresh,
returned-scope mismatch and mixed-scope batch rejection before any content appears.
Independent review found no substantive new defect. No browser attempt, external
service call, publication or credential change was made.

## V19 response composer evidence

Final frozen-source checks passed **588 Python tests** and **97 DOM-model checks**.
See `verification-v19.json` for the full and fresh-archive evidence. New tests
exercise real child-process response authoring and in-process HTTP routes, plus
separate DOM models. No real browser, visual or accessibility acceptance is implied.

Response checks cover processed-request-only disclosure, exact responder/task,
pure preview without durable changes, original item bounds, malformed fields,
forged/stale previews, unsigned preparation, explicit signing/send/process, repeated
and concurrent preparation, existing imported refusal history, withdrawal/reopen,
terminal replay versus new-content refusal, hostile inert text and maximum escaped
Unicode frames. Existing input/output/envelope limits are unchanged.

New model checks cover owner visibility, add/remove limits including zero items,
exact context/recipient/reply preview, typed unsigned preparation, cancellation,
edit with retained fields and usable navigation, detached-field mutation, raw hash
changes, owner/task and same-route navigation, delayed context/preview/preparation,
duplicate clicks, lost-response uncertainty and inert received/outgoing markup.

Independent review found no additional owner-authority bypass. A local inspection
identified post-edit sidebar controls becoming inert after generation invalidation;
full view rebuild now retains draft text and refreshes all navigation callbacks.
Browser blockers remain unchanged and no browser retry or workaround was attempted.

## V18 owner composer evidence

Final frozen-source verification passed **566 Python tests** and **72 DOM-model
checks**: 19 legacy, 29 workspace, six prior independent review, 15 composer and
three independent composer review. All are local fixtures or handler/DOM models,
not actual-browser acceptance. See `verification-v18.json` and `verification/v18-*`.

The 29 added Python cases cover pure preview without process/slot allocation,
exact typed creation, spec/schema bounds, context commitment, isolated custom
services, explicit real-subprocess request/result lifecycle, unchanged catalog
hashes, HTTP parser/origin routes, duplicate/capacity races, input/catalog mutation,
startup/cleanup tombstones and bounded IPC. Custom request processing waits for a
separately proposed response; no browsing, provider operation or tool is executed.

Independent review first caught an accepted Unicode query exceeding its serialized
startup limit. Maximum-input process tests then caught a public review response
exceeding the old 16KiB response frame. Custom-task responses are now bounded at
64KiB; all input frames and legacy response frames remain 16KiB. Review caught and
fixed an accidental expansion of the parent input guard while making that change.
A maximum 512-astral-character question with maximum IDs completes explicit
bindings, pairing, review, signing, delivery and processing, followed by an
explicit large Unicode response. Exact/over-limit and malformed framing checks
pass. These tests do not establish OS isolation or arbitrary-host compatibility.

The composer model checks cover inert preview, exact typed task creation, edit and
Back without authority, captured input snapshots, navigation invalidation, duplicate
confirmation, delayed responses/errors, lost-creation uncertainty and catalog
inspection. A waiting status is kept visible rather than erased by navigation.
No browser attempt, screenshot, external communication, account/credential setup,
public service or denial workaround was performed. Native dialogs, visual layout,
keyboard/screen-reader acceptance and mobile layout are still unverified.

## V17 generic workspace evidence

The final clean archive extraction passed **537 Python tests** after all review
fixes and additions. It also passed 29 workspace DOM-model checks, six
supplemental review model checks and all 19 legacy model checks. These are not
real-browser tests. See `verification-v17.json` and the fresh v17 logs. The earlier
528-test implementation run is retained separately.

The separate `--workspace` mode has 21 new in-process HTTP/handler and real
fixture-service tests (no browser dependency). These cover exact selector/context
routing, both complete fictional task workflows, no automatic creation, isolated
closure, startup/cleanup uncertainty, imported unsigned reviews and retained
history, legacy mode compatibility and inherited HTTP defenses. No socket is
needed for these added handler tests. The full suite also retains older tests,
including their existing loopback HTTP client test.

The separate workspace JavaScript suite has 29 passing DOM-model checks:
read-only navigation, explicit creation/binding, exact review/recipient/owner
confirmation, Bob binding from an Alice view, stale confirmation cancellation,
raw hash changes, detached actions, double clicks, delayed reads and mutations,
lost/truncated response uncertainty, inert hostile text/URLs, imported-review
navigation using the actual response shape, task-only close, blocked cleanup and
startup uncertainty, deferred review, replacement/withdrawal/pairing, and receipt
checking separate from send/process. Existing legacy checks remain 19/19 passing.
CSS/HTML assertions check only model-testable responsive/focus affordances. They
are not viewport, keyboard, screen-reader or native-dialog acceptance.

Evidence logs: `verification/v17-workspace-http-tests.txt`,
`verification/v17-workspace-dom-tests.txt`, `verification/v17-legacy-dom-tests.txt`,
`verification/v17-python-tests.txt` and `verification/v17-syntax-checks.txt`.
Independent review adds 9 Python cases and 6 separate DOM-model checks. Review
identified numeric exponent overflow (`1e9999`) passing JSON parsing as infinity:
closed action schemas rejected the demonstrated malformed action, so this was
not an observed authority bypass. Both HTTP modes now reject nonfinite float
results before service dispatch, using the same error as literal NaN/Infinity.
Post-fix focused HTTP/service tests and all DOM-model suites pass; see
`verification/v17-http-post-review-tests.txt` and
`verification/v17-workspace-review-dom-tests.txt` for exact results.

No new browser attempt, screenshot, dependency installation, public server,
remote upload, live-provider call or persistent credential was used. Existing
Chromium IPC and managed-browser loopback blockers remain unresolved. The legacy
`browser_ui_check.py` does not verify the new workspace mode; a future authorized
real-browser exercise must cover both task contexts and visual/accessibility
acceptance separately.

## Earlier checkpoint evidence (historical counts)

- 400 Python unittest cases, retaining all prior consent, identity, delivery and
  owner-workflow regressions.
- 21 new service/HTTP cases: exact binding consent, read-only views, stale reviews,
  wrong-owner access, concurrent approval, raw-command refusal, uncertainty,
  cancellation, cleanup and recovery, Host/Origin checks, duplicate critical
  headers, bounded JSON, static-file allowlisting and bounded concurrent handlers.
- A real loopback HTTP end-to-end test completes 12 received/processed messages,
  refuses cross-origin approval attempts, then shuts down and removes temporary
  records. This uses HTTP clients, not a browser.
- 19 JavaScript DOM-model checks: navigation/refresh, defer/resume, approval-dialog
  cancellation and exact targets, double action suppression, stale asynchronous
  responses, network/truncated-response uncertainty, receipt-only checks, text-only
  rendering and explicit cleanup status. These model DOM behavior; they do not
  prove browser compatibility, native dialog behavior, accessibility or layout.
- V8 adds 30 core/process/adapter review-replacement cases and two DOM-model
  cases; these do not alter the real-browser verification gap.
- V9 adds 30 core/process/adapter pairing-recovery cases and two DOM-model
  cases. Separate owner approvals, typed direction, history, race/rollback and
  source-return checks do not substitute for real-browser acceptance.
- V10 adds 22 core/process/adapter unused-authorization withdrawal cases and
  three DOM-model checks. These validate local consent and history, not actual
  provider compatibility or distributed revocation.
- V11 adds 24 generic core/encrypted integration tests, not new owner-browser
  coverage. Generic tasks are not yet integrated into this owner workspace.
- V12 adds 15 separated generic signer/executor, service-API and console tests.
  Generic service support is not generic browser-launcher/HTML support.
- Python compile checks and JavaScript syntax checks.

## Blocked / not verified

The installed Chromium could not launch in this execution environment. It failed
while creating its local process-singleton IPC socket with `Operation not permitted`.
An additional launch attempt encountered the same restriction. No browser page,
pixel layout, screenshot, native dialog or mobile viewport was inspected.

`browser_ui_check.py` is provided for a later authorized environment with working
installed Playwright and Chromium. It starts its own isolated loopback server,
blocks nonlocal page requests, exercises the guided UI and cleans up. It has not
passed here. The app itself does not require Playwright or Node; those are only
optional verification tools.

```sh
python browser_ui_check.py --chromium /path/to/installed/chromium
```

A successful browser run should be followed by actual visual/accessibility review
before this interface is presented as usable beyond the fictional development
fixture. Closing this verification gap remains required before browser acceptance.
Independent offline resilience fixes may continue, without adding real accounts,
keys or relays.

## Security scope

This is one trusted local operator controlling fictional owners. Role selection,
the fixed JSON header and loopback origin checks are not authentication. No real
identity, persistent credential or remote service is created. The server accepts
only exact `127.0.0.1:<port>` Host/Origin values, serves an explicit local resource
allowlist, denies cross-origin requests, and exposes only the owner-workflow API.
No external scripts, fonts, images or analytics are loaded.

Keep the launcher running while using the UI. Closing a tab retains the fixture
in that process; stopping the launcher or choosing Discard fixture removes its
temporary records and disposable keys. Cleanup faults block new actions and are
reported as incomplete, not silently called success. This is not persistent
multi-user software, secure key custody, distributed cancellation, or a complete
host-compromise/denial-of-service defense. Do not expose it publicly or enter real
calendar/private data.

### Final v21 extraction

The final frozen 112-source-file archive passed 640 Python tests and 137
DOM-model checks in a fresh extraction. See `verification-v21.json` and its
listed logs. This includes five independent durable-context regression cases.
No browser, visual, native-dialog or real-host validation was performed.

## v22 relationship task groups

Fresh extracted source passed 703 Python tests and all 174 DOM-model checks
across 13 suites, including 24 relationship implementation checks and 13
independent relationship checks. The final independent review caught preview substitution and inaccessible
stopped-task history controls, which were fixed before publication. Additional
checks cover malformed group reads, unknown
contexts and visible read failures. Strict source verification includes 121 local
source files and 13 unchanged upstream files.

See fresh-verifier-full-v22.json for exact results. Python output is a bounded
final tail with its exact test count, not a retained unlimited transcript. All
work is offline and fictional. No actual browser, native-dialog, visual or
accessibility acceptance is claimed, and no denied browser operation was retried.

## v23 fixture-process hardening regression

The unchanged frontend passed all 174 DOM-model checks again. Fresh extracted
source passed 725 Python tests, including 20 IPC implementation/independent cases
and two workspace/startup integration cases. All 125 frozen local source hashes
and 13 upstream hashes matched. See verification-v23.json and
fresh-verifier-full-v23.json. Linux fixture communication deadlines do not prove
real-host integration, whole-action/group-stop deadlines, preemption, OS isolation
or browser/native-dialog/accessibility acceptance.

## v24 terminal parity regression

Fresh extraction passed 756 Python tests and all unchanged 174 DOM-model
checks. New evidence includes 27 implementation/independent terminal cases and
four cross-layer recovery combinations, with 128 frozen local source files and
13 upstream hashes checked. Terminal tests do not verify browser behavior. Real owner/provider identity, native hosts, browser/visual/
accessibility behavior, persistence and production security remain unverified.
See verification-v24.json and fresh-verifier-full-v24.json.

## v25 optional informational continuity

Fresh extraction passed 814 Python tests and 273 DOM-model checks across 15 suites.
The new interface has 52 implementation and 47 independent modeled cases. Review
caught and fixed overly narrow exact-duration comparisons; valid shorter bounded
review/certificate intervals are accepted, while nonpositive or excessive windows
remain rejected. Tests cover frozen request scope, malformed/duplicate records,
partial uncertain anchors, history fences, single-attempt commits, late callbacks
and inert text. All 137 local source hashes and 13 upstream hashes matched.

The UI displays server-reported historical signatures; it does not independently
verify them in a browser or authenticate people/providers. Retirement does not
stop task messages. No real browser, native-dialog, visual or accessibility
acceptance was performed. See verification-v25.json and fresh-verifier-full-v25.json.

## v26 scripted-client regression

The unchanged frontend passed all 273 DOM-model checks again. Fresh extracted
source passed 833 Python tests, including 19 two-client integration and independent
fault cases, with 142 local source hashes and 13 upstream hashes matched. These
process/terminal tests add no browser, visual, native-dialog or accessibility
acceptance. See verification-v26.json and fresh-verifier-full-v26.json.

## v27 mixed-language scripted-client regression

Fresh extraction passed 882 Python tests, including 49 mixed-client implementation
and independent checks, plus all unchanged 273 DOM-model checks. All 145 local source
hashes and 13 upstream hashes matched. Python 3.12.14 and Node 24.22.1 ran on Linux.
New JavaScript coverage verifies a fixed client process, not browser behavior.
No native-dialog, visual, accessibility or provider acceptance was performed.
See verification-v27.json and fresh-verifier-full-v27.json.

## v28 SDK adapter regression

Fresh extraction passed 922 Python tests, including 40 SDK adapter, independent-review
and prerequisite cases, plus all unchanged 273 DOM-model checks. All 149 local source
hashes and 13 upstream hashes matched. SDK interoperability tests use memory streams;
they add no browser, native-dialog, visual, accessibility or actual-host acceptance.
See verification-v28.json and fresh-verifier-full-v28.json.
