# Reviewed work-loop adversarial review

This review covers the synthetic task-to-result composition introduced in PR #8,
including its actual owner HTTP routes. A separate agent from the implementation
authors supplied the tests and reviewed the transaction, cancellation and result
bindings. This is independent review within the same engineering exercise, not
third-party security certification.

## Authority and consistency checks

The reviewed path starts with a signed, explicitly accepted incoming task. The
source grant must name the exact synthetic adapter route, and the recipient must
separately approve the exact provider request. A deterministic local fixture
returns explicitly labelled fictional text. It performs no model call, network
research, tool execution or external action.

Reviewing a completed result does not stage or release it. Staging binds the
original result text and recomputed digest to an exact draft body, parent task,
context, requester, source permissions, provider review and original expiry.
Draft insertion, the run-to-artifact mapping and audit event commit together.
Release remains a separate owner operation, and recipient acceptance remains a
separate decision at the original requester's runtime.

The review exercised these distinctions using actual encrypted owner vaults,
sessions, SQLite runtime stores and signed source proposals. Concurrent staging
uses independent connections to the same recipient store. Commit-acknowledgement
loss is injected after a real commit, then recovered from retained metadata.

## Reproduced finding and repair

The initial default-disabled workflow constructor still instantiated the provider
adapter with the new three-request, 128-output-token budget. This had two
observable effects:

- Starting the default-disabled feature on a fresh store reserved a provider
  budget without opting into the feature.
- Opening a store containing the prior standalone adapter's immutable
  one-request, 256-output-token budget raised `ProviderDenied`, even with the new
  workflow disabled.

The implementation now defers provider/workflow initialisation when the feature
is disabled and no workflow history exists. Existing workflow history remains
inspectable while disabled. Explicitly enabling the workflow against an
incompatible standalone budget is refused without changing that budget. Both
fresh-store and existing-store regressions pass.

Cancellation of an already staged artifact was also raised during design review.
The implementation atomically cancels both the run and its linked artifact;
released artifacts retain the existing signed cancellation-notice semantics.
Independent tests cover denied later release and rollback of the run, artifact
and signed notice together when a final audit write fails. This was a design
requirement verified in the implementation, not a separately reproduced bypass.

No additional authority bypass was reproduced in the tested synthetic scope
after the repair. Passing this suite does not establish absence of all defects.

## Verification

On 10 November 2026, this command passed **26 independent tests** in 12.391 seconds:

```sh
python -B -m unittest pilot.tests.test_workflow_review -v
```

| Area | Tests | Observed coverage |
| --- | ---: | --- |
| Runtime and composition | 19 | Distinct host enable/source grant; pending/rejected task denial; wrong-owner denial; no automatic artifact release; crossed result reviews; source/peer/session withdrawal; expiry before and during staging; post-stage source withdrawal; workflow cancellation; corrupted retained result detection; duplicate/concurrent staging; lost commit acknowledgement and restart; audit rollback; uncertain dispatch across vault/runtime restart without retry; atomic cancellation rollback. |
| Disabled compatibility | 2 | No provider budget creation on default-disabled startup; existing standalone budget preserved and incompatible explicit enable refused. |
| Actual HTTP boundary | 5 | Default-disabled operation cannot be activated by a request; caller-selected route/result/context/run alias refused; bearer and same-origin requirements; complete approve/run/review/stage path leaves an inert draft; logout before dispatch prevents the run. |

The HTTP tests start the actual loopback server and make real HTTP requests. They
use freshly generated fictional owner identities and a real signed incoming
task. They do not mock the owner route handlers or use provider credentials.
The suite also confirms result text is absent from routine state responses.
Browser rendering, the full two-process demo and broader regressions have their
own verification records and are not implied by this HTTP review.

## Limits that remain

- The output is a deterministic fixture. A useful research result from a model,
  real provider account behaviour, billing and data policy remain unverified.
- The local fixture route label does not establish an approved real OpenAI model
  or authorise live activation. The owner HTTP service exposes no live transport.
- Source withdrawal is enforced when observed or at expiry. It cannot instantly
  revoke an offline peer's unseen permissions or recall text already exposed.
- The origin-only return contract does not prove semantic provenance or support
  arbitrary inherited source grants. A host controlling its own store and code
  remains trusted; corruption tests are consistency checks, not hostile-host
  isolation claims.
- Local passwords prove control of a configured vault. This fictional-owner
  exercise does not establish real-person identity, informed consent, separately
  controlled devices, internet delivery, key recovery or production readiness.
- The workflow composes the reviewed provider result path. Existing manual
  artifact drafting remains a separate owner operation and does not become
  proof that an artifact was generated or reviewed by a model.

No live provider calls, real personal information, public deployment or merge
were performed by this review.
