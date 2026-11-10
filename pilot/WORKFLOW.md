# Reviewed synthetic work loop

`SyntheticWorkLoop` composes the existing recipient, provider and artifact
boundaries into one owner-controlled workflow. It accepts only an already
accepted incoming task with the exact signed fixture route:

```json
{"provider":"openai","model":"synthetic-research-v1","max_output_tokens":128}
```

This is a synthetic declaration for the existing Responses adapter shape.
`synthetic-research-v1` is an internal fixture identifier, **not an OpenAI model**.
The workflow never instantiates the live HTTP transport, reads a credential,
contacts a provider, performs research or executes a tool. Its fixed result says
that no model or research ran and includes the original request commitment.
Reported fixture token counts are zero, not measurements of a real model.

## Explicit decisions

1. The source owner creates and separately releases an exact task with the signed
   fixture declaration. No provider declaration is added by default.
2. The intended recipient accepts that task. Acceptance does not approve a run.
3. `prepare(session, item_id)` derives the only allowed run ID,
   `work-<exact-item-id>`, and an immutable provider binding from that task.
4. `review` exposes the exact synthetic request and its finite budget. `approve`
   accepts its digest with a finite expiry. The owner then separately invokes
   `dispatch` with that same digest.
5. The existing provider ledger claims one attempt before the fixture receives
   bytes. The original response is retained. An unknown outcome cannot be retried.
6. `review_result` exposes the exact original output and intended return artifact.
   `stage_result` accepts that separate result-review digest and atomically creates
   one local draft, its provenance mapping and audit event.
7. The draft still requires the ordinary artifact review and explicit release.
   The original requester then independently accepts or rejects it.

The fixture output cannot approve a run, change the peer, grant additional source
permission or release itself. Result editing is deliberately absent: a changed
output cannot be presented as the original reviewed provider result.

## Stable result and artifact commitments

The result review binds the original run and task, provider-review digest, result
digest, response identifier, original source-permission digest, exact requester,
context, expiry, title and full artifact proposal body. The retained text digest
is recomputed rather than trusted as a label.

The proposed artifact uses the provider claim timestamp and original task expiry.
Its ID therefore remains stable across review delays, duplicated requests and
restart. This timestamp records the dispatch claim used to define the proposal;
it is not a claim that a remote model completed at that time. The artifact can
return only to the original task owner and cannot grant onward provider access.

Staging holds the current owner's session guard and the runtime's SQLite write
transaction. It rechecks accepted task/source authority, peer trust, the original
result and the exact artifact before commit. The draft, run-to-artifact mapping
and audit event either commit together or roll back together. A lost commit
acknowledgement is uncertain; inspect the original run. A repeated identical
stage returns metadata for the original artifact, even after withdrawal, without
returning source/result text or creating another proposal.

`status` and `list_runs` return metadata, including nullable `artifact_id`,
`artifact_state` and `result_review_digest`, plus an explicit `allowed_actions`
list. They contain no request/result text or bearer token. Withdrawn or expired
authority removes content-bearing actions but preserves historical metadata.

## Cancellation and uncertainty

Workflow cancellation atomically marks its provider run cancelled and cancels
the linked artifact, if one has been staged. An unreleased draft becomes
unreleasable. If it was already released, the existing authenticated cancellation
packet is queued; peer observation remains a separate fact. Cancellation cannot
recall content already seen or establish immediate remote shutdown.

Source-task cancellation observed by the recipient blocks future result review,
staging and release. A disconnected recipient cannot observe an unreceived source
withdrawal; the original expiry still limits authority. Receiving an artifact or
a delivery receipt does not imply requester acceptance.

Dispatch errors, invalid fixture results and lost acknowledgements retain the
existing one-attempt provider fence. This composition exposes no resend or new
run-ID mechanism. A result whose original completion was not established cannot
be staged. Runtime failures report fixed errors without copying private payloads.

## Host opt-in and compatibility

`SyntheticWorkLoop(runtime)` defaults to disabled. Without retained workflow
metadata it creates no provider schema, reserves no provider budget and returns
an authenticated empty run list. This preserves a pre-existing standalone
provider adapter store unchanged. With recognised workflow metadata, disabled
restart permits history inspection but exposes no mutating/content review actions.

Explicit enable fixes the shared provider ledger budget to three total attempts,
128 output tokens per request and 8192 input bytes. It never expands an existing
incompatible budget. A store previously configured with a different standalone
provider budget must use a separate pilot directory; there is no silent migration
or budget reset. The stored workflow version and fixture model are checked on
reopen. Host opt-in is separate from every owner decision above.

These are resource bounds for an offline fixture, not currency spending limits,
live-provider permission or verified account terms.

## Verification

```sh
python -B -m unittest pilot.tests.test_workflow -v
python -B -m unittest pilot.tests.test_workflow_review -v
```

The focused suite uses distinct password-authenticated owner vaults, runtime
stores, signed source packets and the actual provider ledger. It covers default
disable/legacy-budget compatibility, distinct decisions, exact output review,
duplicate staging, expiry at commit, source withdrawal, original-result integrity,
transaction rollback, lost commit acknowledgement, restart, concurrent SQLite
connections, cancellation propagation and uncertain dispatch. Independent review
and actual HTTP/browser evidence are recorded separately in the PR.

This closes the local task/result composition gap only. It does not establish
remote hosting, separately controlled machines, real-person identity, real model
output, independently verifiable inherited-source grants or production readiness.
