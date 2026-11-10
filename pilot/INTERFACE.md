# Local owner workspace

`pilot/web/` is a self-contained responsive interface served by the pilot's local
HTTP server. It has no CDN, analytics, remote font or external script dependency.
The design works from a narrow phone screen to a desktop workspace.

The workspace supports password sign-in, sign-out, exact peer enrolment,
incoming/outgoing proposals, a task-linked artifact reply, explicit release,
recipient acceptance/rejection, withdrawal, history and manual exchange sync.
The owner and assistant identity appear only after the server verifies the
session and returns a valid state. This is a local account, not verified real-world
identity. The interface labels the environment as a synthetic pilot.

## Decision behaviour

- New proposals are prepared for review. Creation never automatically releases
  the content.
- Opening a proposal fetches its exact current review. The interface checks its
  proposal ID, artifact digest, context and permitted action list against the
  selected item. Sender controls cannot become recipient controls.
- Every release, decision and withdrawal submits the exact review digest.
  Unknown operations are never inferred from a status label.
- The source's origin-only return policy and any exact provider-disclosure
  permission appear beside the reviewed content. A task-linked artifact retains
  its accepted parent, peer and context, and cannot extend the parent's expiry.
- Revoked/expired content can be withheld while the original commitment remains
  inspectable. A previously pending item can still be rejected without displaying
  unavailable content. A historical acceptance does not become renewed authority.
- One click starts one request. A lost mutation response, or failed inspection
  after a mutation response, blocks further mutations until the owner explicitly
  refreshes saved state. There is no automatic retry, sync loop or background
  unlocked assistant.
- `Sync exchange` explicitly runs the local exchange endpoint; it does not claim
  that a queued packet was accepted or that a provider executed anything.

## Content and session handling

Bearer tokens exist only in the module's memory. They are not written to browser
storage, cookies, URLs, DOM attributes or logs. Sign-out clears the local token,
proposal previews and forms before attempting server revocation. A missing
sign-out acknowledgement is shown accurately. Password fields are cleared on
submission and when the page becomes hidden.

Artifact text, titles, owner labels and history are rendered with `textContent`.
HTML, Markdown and embedded instructions are not interpreted. API calls omit
cookies, refuse redirects and apply a timeout. The server remains responsible for
authentication, exact authority, content bounds, CSRF/origin policy, time and
durable transitions; browser checks do not replace those boundaries.

## Opt-in synthetic work loop

When the host explicitly enables `--synthetic-workflow`, the task composer adds
an unchecked permission for the exact local fixture route:
`openai / synthetic-research-v1 / 128 output tokens`. This is labelled a local
synthetic adapter rehearsal, with no real model or network call. Artifacts cannot
carry this permission; switching to an artifact clears the checkbox.

An accepted incoming task can expose **Prepare synthetic run** from its exact
review only when its signed source permission names that route, its peer is
active and its lifetime is current. Preparation does not run anything. The owner
then separately inspects and approves the exact provider request, and explicitly
chooses **Run synthetic fixture once**. This is not research or a live AI result.

The original result is shown as inert text with its source, task, context,
recipient and provider/result commitments. **Stage exact artifact** creates a
draft only. The owner must open that outbox artifact and separately approve its
release, after which the original requester retains their own accept/reject
decision. No interface operation chains these approvals automatically.

Each run action must be explicitly enumerated by the server. The UI checks known
states, exact task/run bindings, source/recipient commitments, synthetic-only
flags and no-retry status before presenting controls. Uncertain or cancelled runs
remain inspectable without a dispatch retry. Disabled hosts expose retained
history but no mutation controls. Cancellation is labelled local, without a claim
of remote shutdown or recall.

## API contract

The server routes are in `pilot/server.py`:

| Method and route | Input |
| --- | --- |
| `POST /api/session` | `{password}`; returns `{token, identity}` |
| `DELETE /api/session` | `{}` plus current bearer token |
| `GET /api/state` | Current bearer token |
| `POST /api/peers` | Public identity, independently checked exact fingerprint, loopback endpoint |
| `POST /api/proposals` | Exact peer, type, title, text, context, task reference, expiry and optional accepted parent |
| `GET /api/items/:id/review` | Exact selected proposal ID |
| `POST /api/items/:id/decision` | `{review_digest, decision}` |
| `POST /api/items/:id/release` | `{review_digest}` |
| `POST /api/items/:id/cancel` | `{review_digest}` |
| `POST /api/exchange` | `{}`; explicit owner action |
| `POST /api/items/:id/workflow` | `{}`; prepare only from an eligible accepted task |
| `GET /api/workflows/:run_id` | Retained exact run status |
| `GET /api/workflows/:run_id/review` | Exact request, source binding and finite budget |
| `POST /api/workflows/:run_id/approve` | `{review_digest, expires}`; separate owner approval |
| `POST /api/workflows/:run_id/run` | `{review_digest}`; one local fixture attempt |
| `POST /api/workflows/:run_id/cancel` | `{}`; local cancellation |
| `GET /api/workflows/:run_id/result` | Exact original-result and return-artifact review |
| `POST /api/workflows/:run_id/stage` | `{review_digest}`; draft only, never release |

## Verification

Run `node --test pilot/web/tests/model.test.mjs`. The 25 tests cover crossed
commitments, sender/recipient separation, unknown actions, immutable terminal
decisions, withheld content, parent expiry, input bounds and no unsafe markup or
token-persistence sinks. Revoked and unknown peer state cannot appear as active
trust or remain selectable in the composer.
The additional workflow cases cover explicit source opt-in, host activation,
terminal/unknown actions, disabled history, exact provider binding, substituted
result text, source/recipient/parent commitments and stale result reviews.

`python -B pilot/web/tests/live_contract.py` passed against two actual local HTTP
processes. It checks the frontend's schema validators against outgoing draft,
incoming pending, accepted and cancelled state, including withheld content and
logout. It exports no password/session tokens to JavaScript or evidence. This is
real HTTP contract evidence, not browser rendering evidence.

`python -B pilot/web/tests/workflow_contract.py` passed against two explicitly
enabled real HTTP processes. It validates the frontend schema throughout accepted
task preparation, separate request approval/run, original-result review and
draft-only artifact staging. No credentials are exported to the validator.

`pilot/web/tests/browser.test.mjs` provides an optional Playwright browser check
against a **mocked HTTP boundary**. That script is UI-only evidence, never an
end-to-end server, real-owner or live-provider acceptance claim. Example:

```sh
CHROMIUM_PATH=/usr/bin/chromium node pilot/web/tests/browser.test.mjs
```

The same entry point switches to the actual-server test when `LIVE_PILOT_URL` is
set. This mode does not install any mocked API route. With the disposable
`pilot.ui_fixture` running, it exercises authenticated login, two exact
accept/reject decisions, sync, saved activity, public identity display, inert
content, mobile layout and logout. `PILOT_SCREENSHOT_DIR` captures desktop/mobile
screenshots before sign-out. The fixture password is fictional test data, not a
production credential. Playwright 1.62.1 is the version used to prepare this test.

```sh
LIVE_PILOT_URL=http://127.0.0.1:8765 \
LIVE_PILOT_PASSWORD='Fictional browser test password' \
PILOT_SCREENSHOT_DIR=/tmp/pilot-ui-evidence \
node pilot/web/tests/browser.test.mjs
```

In the initial managed workspace, launching local Chromium failed before a page
was created: the browser's process-singleton Unix socket returned `EPERM`.
Therefore no browser pass is claimed from that attempt. On 10 November 2026 the
hosted Chromium run subsequently passed against the actual HTTP service. Its
desktop and mobile screenshots were downloaded, their archive digest checked,
and both images visually inspected. See the [verification record](VERIFICATION.md)
for the exact tested commit, workflow and evidence artifact. This automated
fictional-owner check does not establish real-person or live-provider acceptance.

The work-loop extension adds a fourth fictional browser task and verifies the
independent owner clicks through source-granted acceptance, preparation, request
approval, one-shot fixture run, exact result review, draft-only staging and a
separate artifact release. It also checks that an artifact cannot retain the task
composer's fixture permission. A result-review screenshot is added to the two
existing viewport screenshots. The new local Chromium attempt again failed before
page creation with process-singleton Unix-socket `EPERM`; the new flow requires
its own hosted CI evidence and is not covered by the earlier browser pass. The
new sequence subsequently passed on implementation `95c3ef0`. Visual inspection
then found and corrected a stale post-release artifact subtitle; the interface
now reflects the actual artifact state and a browser assertion checks that it
does not describe released content as an unreleased draft. The work-loop model
suite has 25 passing tests in total. Current hosted results and screenshots are
tracked in [PR #8](https://github.com/EmotiveImpact/Assistant-Central/pull/8) and the
[work-loop verification record](WORKFLOW_VERIFICATION.md).
