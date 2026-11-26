# Optional trusted-owner continuity controls

This is an offline fictional fixture, not authentication or host interoperability.
Continuity associates existing task-owner public roots with an explicitly enrolled
fictional public root. It grants no task, approval, message or account authority.

## Explicit enablement

- Browser launcher: `python local_owner_app.py --workspace --continuity`
- Console: `python workspace_console.py --continuity`

The browser flag without `--workspace` is rejected before constructing a service.
Without `--continuity`, continuity is disabled: no registry, signer, process or
key is created. Opt-in construction and preview still create no signing process
or key. Only separately confirmed enrollment starts the disposable signer.
These controls are trusted-owner surfaces, never restricted-agent methods.

## HTTP contract

Existing exact loopback Host/Origin, local JSON header, size, duplicate-field,
finite-number and closed-schema guards apply. No sockets or browser acceptance
are implied by in-process HTTP tests.

- `GET /api/continuity`, without query fields, returns `{"enabled":false}` when
  disabled, or `{"enabled":true,"incarnation":...,"identities":...,"associations":...}`.
- `POST /api/continuity-preview` receives the exact core request, without wrapper.
- `POST /api/action` receives exactly `action`, `review`, `confirmation`. Action is
  `continuity_enroll`, `continuity_associate`, or `continuity_retire`. Results are
  the unchanged core commit results, not a fabricated active-success assertion.

See CONTINUITY_PROOFS.md for closed requests, public data and status semantics.
No process handle, private key or preview MAC secret is returned.

## Console review and confirmation

Use `continuity-state` to inspect public state. For enrollment:

```
continuity-preview {"operation":"enroll","identity_id":"fictional-one"}
continuity-commit
```

The console displays a detached frozen review and asks for the full exact phrase
`ENROLL CONTINUITY <review_digest>`. Association uses `ASSOCIATE CONTINUITY
<review_digest>` and retirement uses `RETIRE CONTINUITY <review_digest>`. Enter
the digest actually displayed, not placeholder text. Blank, wrong or abbreviated
phrases cancel. `back`, failed replacement previews and every commit attempt
consume or discard the pending review. No preview is regenerated automatically.

Association requires an independently created task and its exact selector,
context and actual owner actor. It never creates or selects a task for you.
Retirement stops local continuity recognition only. It does not cancel a task,
revoke a grant or stop messages; use the existing explicit task/group controls.

Uncertain communication or an uncertain continuity tombstone clears previews
and leaves the console inspection-only. `continuity-state` remains allowed;
continuity preview/commit and other effectful commands are refused. Explicit
close/quit retain the existing cleanup behavior. No automatic signing retry,
key regeneration, replacement route or clean-discard claim follows uncertainty.

## Historical evidence

Read the returned status and active flag, not signature verification alone.
Exact core association retries return original history, including retired,
closed, stopped, expired or uncertain results; they do not renew or sign. The
console intentionally requires a fresh explicit preview for each commit and
cannot retry an occupied association by regenerating it. HTTP callers retaining
an exact review must not blindly retry after uncertain outcomes. Retirement
cleanup retry, when explicitly requested through the core/API, only attempts
cleanup, never new signing. Public records are disposable with this workspace.

## Offline checks

`python -m unittest discover -s tests -p 'test_continuity_owner_surfaces.py' -v`
uses scripted console inputs and the existing in-process, no-socket HTTP harness.
Run full unittest discovery as well; use already available offline dependencies.
