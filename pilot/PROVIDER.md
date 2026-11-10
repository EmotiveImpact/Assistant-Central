# OpenAI Responses adapter

`provider.py` implements a bounded, text-only adapter for
`https://api.openai.com/v1/responses`. It is **disabled by default**. This change
makes no live provider call, creates no API key and claims no native-host or
live-account acceptance. Tests use fictional text and an injected response fixture.

## Runtime composition

```python
adapter = ResponsesAdapter(
    runtime.db,
    runtime.authorise_provider,
    runtime.auth.authenticate,
    budget=ProviderBudget(max_requests=1, max_output_tokens=256),
    transport=None,
)
```

The adapter derives `auth.authorised` from the bound authentication callback, or
requires an explicit `authorised=` session context. This guard stays held across
the runtime transaction and commit. Authentication and session expiry are checked
again immediately before commit. Logout cannot pass a successful dispatch fence
and then retroactively claim that the release was unauthorised. After commit,
logout and cancellation cannot establish that a remote provider stopped.

The accepted-input binding is exactly:

```json
{
  "item_id": "exact-received-task-id",
  "context": "64-character-context-digest",
  "payload_digest": "64-character-content-digest",
  "provider": "openai",
  "model": "explicit-model-reference",
  "max_output_tokens": 128
}
```

`runtime.authorise_provider` runs inside the same write transaction as the
provider operation. It must recheck the authenticated local assistant, accepted
incoming task, original signed source permission, exact route, expiry and any
observed cancellation. Merely accepting peer work does not authorise provider
disclosure. The pilot runtime supports only direct, owner-originated task text
with an explicit provider disclosure in the signed proposal. Arbitrary artifacts
and inherited source graphs remain rejected at this adapter boundary. The older
fictional `execution.ProviderGate` is not treated as authenticated consent.

The current route names a provider and model, not a verified billing account or
provider terms. Account-specific source review, credential ownership, retention
policy and live-provider acceptance remain required before enabling real calls.
Remote cancellation has distributed semantics: the receiver can enforce it only
after receiving it, or when the original permission expires. No callback can
observe a revocation that has not crossed the network.

## Owner controls and immutable dispatch

1. `prepare(session, run_id, binding)` revalidates accepted input and builds an
   exact review of the request, endpoint, route and resource budget. One accepted
   item has one run; aliases cannot mint another dispatch.
2. `review(session, run_id)` returns the exact provider-visible request to its
   authenticated local owner, while current source authority is valid.
3. `approve(session, run_id, review_digest, expires=...)` records a separate
   owner decision expiring within one hour. It cannot be renewed or retargeted.
4. `dispatch(session, run_id)` rechecks both authorities, input commitments,
   expiry and finite budgets under `BEGIN IMMEDIATE`. It commits `uncertain`
   **before** returning request bytes to the transport. No second dispatch is
   permitted, including after timeout, restart or lost acknowledgement.
   Source/task authority and provider approval expiry are checked again after
   request construction immediately before commit; expiry during construction
   rolls back the claim and consumes no request budget.
5. `status` returns metadata; `result` returns the retained original text only
   with a current owner session and current source permission. Neither publishes
   the result or grants onward disclosure.

The request contains only explicit model reference, fixed instructions and the
accepted task text. It has no tools, tool execution or conversation continuation.
It sets `tool_choice: none`, `store: false`, `stream: false`, `background: false`
and an explicit `max_output_tokens` ceiling. Input bytes and response bytes are
bounded. Status excludes prompts, model output, session tokens and API keys.

`ProviderBudget` persists unchanged in the receiver database. Maximum requests,
input bytes and output tokens bound resource use, including uncertain attempts.
They are **not a currency spending guarantee**: model prices and account settings
require separate review. Reopening with increased budgets is refused.

## Failure and cancellation

Any timeout, non-200 response, malformed response, refusal, unexpected tool call,
oversized output or lost result-recording acknowledgement leaves the original
claim unavailable for redispatch. No response body or transport exception is
copied into an error message. Accepted responses must be completed text output
within the approved token and byte bounds.

Cancellation before dispatch prevents all transport. Cancellation after the
durable claim records a local stop request, preserves uncertainty or original
completion, and reports `remote_cancel_confirmed: false`. A late original result
may be retained for accounting, but cancellation or observed source withdrawal
blocks its content-return path. This adapter does not issue a remote cancellation
request and does not treat a timeout as proof that no model ran.

After a failed acknowledgement, inspect the original run. A stored completed
result can be read under current authority; an uncertain run cannot be safely
reissued. There is no automatic response retrieval or reconciliation service.
The same request is never retried by the transport or adapter.

## Future live activation

`OpenAIResponsesHTTP(private_key_supplier, enabled=False)` performs one fixed
HTTPS POST only when explicitly enabled. `ResponsesAdapter` also independently
defaults `allow_live=False`; both controls must be enabled by trusted composition.
The pilot HTTP/UI does not activate them.

The key supplier is read only at send time and must source credentials privately.
No environment scan, key creation, plaintext key file or credential-bearing
fixture payload is introduced. Redirects are refused, TLS verification remains
enabled, and responses are bounded. The Python process and key supplier remain
trusted; these controls do not protect against code execution within that process.

Before live acceptance, verify a named provider account and model, key custody,
account-specific owner/source approvals, logging and retention, billing controls,
actual response behaviour, cancellation expectations and operational rollback.
Use synthetic inputs for that acceptance session. A fixture test is not evidence
that a provider accepted the request or honoured any data policy.

## Verification and official schema sources

```sh
python -B -m unittest pilot.tests.test_provider -v
```

The tests cover separate source and local owner approval, exact bindings, expired
and revoked authority, session guards, budgets, one dispatch under concurrency,
restart, lost acknowledgements, malformed responses, cancellation and fixed
credential destination. An additional composition test uses two actual encrypted
pilot runtimes and password-authenticated local owners with a fixture model.

The request/response schema was checked against the official OpenAI documentation
on 10 November 2026:

- [Create a model response](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Response storage and conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [API error codes](https://developers.openai.com/api/docs/guides/error-codes)

`store: false` controls response retrieval storage; it does not establish zero
retention, special account terms or successful provider integration.
