# Central workspace

An optional platform interface for the existing Assistant Central pilot. The
overview, work queue, artifact library, assistant network, transfers and activity views use
the real owner HTTP API. This component does not replace the runtime, identity,
disclosure, exact-review or delivery boundaries.

The visual direction uses the restraint, typography and spacing of the Linear
reference, with an original Central identity. It is a working local interface,
not a claim of production readiness or a hosted service.

## Open the fictional workspace

From the repository root, with `pilot/requirements.txt` installed:

```sh
python -B -m workspace_ui.demo --port 8877
```

Open `http://127.0.0.1:8877` and use the public fixture password:
`Fictional browser test password`.

The demo creates a new temporary workspace on every invocation. Blair's Beacon
assistant has three fictional peers (Atlas, Mira and Orbit), nine actual saved
proposals, separate recipient decisions and one accepted artifact. All seed
operations go through authenticated runtime methods. There are no mocked HTTP
responses, external requests, real accounts or personal information. The demo's
owner decisions are scripted fixture actions, not authenticated human consent.
The temporary stores are removed on a normal exit.

`Shape the launch narrative` is a pending task with the exact synthetic provider
grant. `Map the onboarding journey` is an accepted grant-bearing task. These can
exercise separate acceptance, request approval, fixed local result generation,
original-result review, staging and release. The fixture result is not research
or AI output. Live provider calls remain disabled.

## Use an existing pilot owner

```sh
python -B -m workspace_ui.server serve --directory /path/to/fictional-owner --port 8877
```

This requires a previously provisioned pilot owner and binds only to
`127.0.0.1`. Stop its other pilot server before opening the same owner directory.
Add `--synthetic-workflow` only to enable the existing fixed local rehearsal.
HTTPS transfer controls remain disabled unless the host explicitly supplies
`--transfer-config /private/transfer-config.json`. The launcher uses the existing
reviewed `pilot.owner_transfer.load_config`, with its private-file, exact schema,
TLS trust and bounded connection checks. It reads this trusted configuration once
at startup. It does not create a configuration, infer a peer, enable a provider
or send anything. See [host configuration](../pilot/OWNER_TRANSFERS.md#trusted-host-configuration).
Provisioning and password maintenance remain in the reviewed pilot CLI. This
launcher has no password argument and creates no missing account.

## Boundary and implementation

`WorkspaceHTTPServer` retains the existing pilot server and changes only its
static GET handler before serving. An exact allowlist serves the new HTML, CSS
and client modules. `/model.mjs` and `/transfers.mjs` come directly from their
reviewed `pilot/web/` files. No other pilot asset is served.
Static files are bounded and opened with `O_NOFOLLOW`. Source files, arbitrary
paths, query strings and directory traversal are refused.

Owner API and peer packet operations are inherited unchanged. Host and Origin
checks, CSP, no-store headers, session requirements and the dedicated owner
thread are preserved. The client retains sessions only in memory. Browsing,
filtering and searching do not accept work, disclose content, run a provider or
release a proposal. Each of those operations still requires its existing exact
review step. An uncertain result requires inspection before another mutation.

The refined shell composes the reviewed owner transfer controls from PR #16,
using one owner session, mutation gate and uncertainty latch. Its shared validators
bind the exact connection, full recipient fingerprint, original digest, expiry and
attempt history. Enrol a peer under **Assistants** using either its existing local
endpoint or one host-approved connection; independently verify the full fingerprint.
Configuration alone is never peer enrolment or permission to send.

Under **Transfers**, choose and inspect one retained outbox packet, original cached
receipt or quarantine file. Each send, retry and import requires its own unchecked
confirmation. Imports never automatically send a receipt. A mailbox acknowledgement,
a signed receipt, recipient acceptance and execution approval remain distinct.
An in-flight transfer cannot be recalled by closing a dialog, withdrawing work or
signing out. Inspect saved state after an uncertain response, then review again
before any permitted retry. No automatic retry or additional queue is introduced.
**Sync exchange** is for existing local loopback exchange only.

Persistent conversations remain a separate authority in PR #22. This work does
not create a second thread ledger or present proposals as chat history. Remote
hosting, live providers and real-owner onboarding remain outside this component.

## Optional host draft review

The **Host drafts** view is disabled unless the launcher receives an explicit
private `--host-draft-config` file. It connects existing supported-host drafts
to the authenticated owner for exact inspection and local dismissal only.
No task is approved, staged, sent or executed. The original host lease is at
most 15 minutes; an expired or revoked connection is unavailable, not an empty
queue. See [setup, security boundaries and migration](../agent_bridge/OWNER_REVIEW.md).

## Verification

```sh
npm ci --prefix agent_bridge --ignore-scripts --no-audit --no-fund
python -B -m unittest discover -s workspace_ui/tests -v
node --test workspace_ui/tests/host_drafts.test.mjs workspace_ui/tests/projections.test.mjs pilot/web/tests/model.test.mjs pilot/web/tests/transfers.test.mjs
```

The HTTP tests exercise the actual owner server: exact static content, path and
symlink refusal, size bounds, foreign-origin rejection, session invalidation,
the authenticated fixture state and terminal exact decisions. Browser evidence
and the final combined regression results are recorded in the PR.
