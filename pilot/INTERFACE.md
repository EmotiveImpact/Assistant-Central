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

## Verification

Run `node --test pilot/web/tests/model.test.mjs`. The 16 tests cover crossed
commitments, sender/recipient separation, unknown actions, immutable terminal
decisions, withheld content, parent expiry, input bounds and no unsafe markup or
token-persistence sinks. Revoked and unknown peer state cannot appear as active
trust or remain selectable in the composer.

`python -B pilot/web/tests/live_contract.py` passed against two actual local HTTP
processes. It checks the frontend's schema validators against outgoing draft,
incoming pending, accepted and cancelled state, including withheld content and
logout. It exports no password/session tokens to JavaScript or evidence. This is
real HTTP contract evidence, not browser rendering evidence.

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
Therefore no browser pass is claimed from that attempt. Hosted browser CI results
must be inspected separately; writing a browser test is not evidence it passed.
