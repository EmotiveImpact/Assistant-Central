# Central workspace

An optional platform interface for the existing Assistant Central pilot. The
overview, work queue, artifact library, assistant network and activity views use
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
Provisioning and password maintenance remain in the reviewed pilot CLI. This
launcher has no password argument and creates no missing account.

## Boundary and implementation

`WorkspaceHTTPServer` retains the existing pilot server and changes only its
static GET handler before serving. An exact allowlist serves the new HTML, CSS
and client modules; `/model.mjs` comes directly from `pilot/web/model.mjs`.
Static files are bounded and opened with `O_NOFOLLOW`. Source files, arbitrary
paths, query strings and directory traversal are refused.

Owner API and peer packet operations are inherited unchanged. Host and Origin
checks, CSP, no-store headers, session requirements and the dedicated owner
thread are preserved. The client retains sessions only in memory. Browsing,
filtering and searching do not accept work, disclose content, run a provider or
release a proposal. Each of those operations still requires its existing exact
review step. An uncertain result requires inspection before another mutation.

This branch does not incorporate the separately owned transfer workspace in
PR #16. Its network settings and HTTPS attempt UI need a later composition and
regression pass. Remote hosting, live providers and real-owner onboarding remain
outside this component.

## Verification

```sh
python -B -m unittest discover -s workspace_ui/tests -v
node --test pilot/web/tests/model.test.mjs
```

The HTTP tests exercise the actual owner server: exact static content, path and
symlink refusal, size bounds, foreign-origin rejection, session invalidation,
the authenticated fixture state and terminal exact decisions. Browser evidence
and the final combined regression results are recorded in the PR.
