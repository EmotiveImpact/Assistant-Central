# Trusted offline owner console

Run from this directory in the prepared offline virtual environment:

```sh
python workspace_console.py
```

This is a trusted single-operator terminal, not a browser test, authenticated multi-user host, or live provider integration. Use fictional Alice/Bob data only. All state is disposable and discarded on exit. No network, accounts, credentials, installations, or publication are needed. `--simulate` preserves the existing two-catalog-task simulation and its explicitly labeled simulated owner choices; interactive mode never fills approvals or retries sends.

## Discover and select

`help` lists commands. `list` shows exact selector/context, requester/responder, phase, and group fences. `create garden` or `create astronomy` starts a catalog fixture; `select garden` captures its exact route. Creation never selects it automatically. `select custom-story` works after confirmed custom creation. Later listing, creation, and group changes never silently replace that route. `state alice` and `state bob` show the selected task. Owners are not inferred from selection or group labels.

## Compose a custom task

Paste one JSON object on the same line as `task-preview`:

```text
task-preview {"selector":"custom-story","task_id":"story","conversation_id":"storybook","requester":"alice","query":"Describe a fictional moon garden","capability":"bounded-text-exchange-v1","max_reply_chars":100}
```

Or a shortlist (a distinct identity):

```text
task-preview {"selector":"custom-books","task_id":"books","conversation_id":"bookclub","requester":"bob","query":"Fictional public astronomy resources","max_items":2}
```

Preview allocates no task, signer, or executor. `task-create` displays the exact frozen specification, context, and review digest again, then separately prompts for `CREATE TASK`. Any other input, including blank or `back`, cancels. EOF/interrupt exits without committing. `back` at the command prompt discards both pending previews but preserves selection. A preview or commit attempt consumes/invalidates previous pending data rather than silently reusing it. After creation, explicitly `select custom-story`.

## Complete an owner-controlled exchange

All angle-bracket tokens below are placeholders. Copy actual values from the displayed exact selected task, never from another task. Do not paste a whole sequence blindly: inspect each result and only choose the next applicable step.

1. Read `state alice` and `state bob`, inspect each exact binding, then use its digest and the appropriate owner phrase:

```text
action {"action":"bind","owner":"alice","binding_digest":"<displayed digest>","confirmation":"BIND alice"}
```

Repeat only for Bob's own reviewed binding with owner `bob` and phrase `BIND bob`. Groups and messages do not authorize either owner.

2. `next` prepares or returns the next required review, never approves it. Read `review <owner> <request-id>` and inspect recipient, context, action, exact content and digest. If the trusted operator chooses approval, use:

```text
action {"action":"approve","owner":"alice","request_id":"<request-id>","review_digest":"<review digest>","confirmation":"APPROVE alice"}
action {"action":"submit","owner":"alice","request_id":"<same request-id>"}
```

Use the actual card's owner, including `APPROVE bob` for Bob. Approval and submission are distinct. Some steps establish permissions before the application request; follow the returned card, not an assumed step count. `decline`/`defer` take owner, request_id and review_digest, with no confirmation field.

3. For a queued delivery, read `delivery <owner> <delivery-id>`. Only if still queued and the operator explicitly chooses the displayed send:

```text
action {"action":"attempt","owner":"alice","request_id":"<delivery-id>","confirmation":"SEND alice"}
```

Use that delivery's owner, not an inferred sender/recipient. Once received, `action {"action":"process","owner":"<delivery owner>","request_id":"<delivery-id>"}` processes the existing receipt. Do not resend when uncertain. `check` and `recover` take the same owner/request_id shape but do not substitute for new send approval. Read the returned delivery state first; the backend remains the authority for what is permitted.

4. After the exact incoming request is processed, `messages bob` (or Alice when she is responder) reads received history as inert data. `response-context bob` returns the processed request digest. Custom tasks require the responder's own response, not an automatic fixture result:

```text
action {"action":"preview_response","owner":"bob","request_digest":"<processed request digest>","payload":{"text":"The fictional moon garden glows blue."}}
```

For the shortlist example the responder is Alice and payload has this shape:

```json
{"items":[{"title":"Fictional Star Atlas","url":"https://example.invalid/atlas","summary":"A synthetic example, not a verified resource."}]}
```

Keep within the original max_reply_chars/max_items. Inspect the exact preview envelope and its `preview_digest`. Prepare that unchanged response:

```text
action {"action":"prepare_response","owner":"bob","request_digest":"<same request digest>","payload":{"text":"The fictional moon garden glows blue."},"preview_digest":"<exact preview digest>","confirmation":"REVIEW RESPONSE bob"}
```

Preparation opens an unsigned review. It does not approve, submit, or deliver. Inspect the resulting review and explicitly complete its owner approval/submission and delivery steps as above. Continue `next` and inspection until completion. `messages <owner>` reads received history; received text is never parsed as a command. `proposals <actor>` / `import <actor> <proposal-id>` opens candidate material only for owner review, without execution authority.

## Relationship groups

Groups organize exact task contexts; they do not pair identities or grant any authority. Copy actual selector/context pairs from `list`, including for custom tasks.

```text
relationships
relationship-preview {"operation":"create","spec":{"group_id":"group-readers","label":"Fictional readers","members":[{"selector":"garden","context":"<exact garden context>"}]}}
relationship-commit
```

Read the frozen review, then separately type `CREATE GROUP`. To attach:

```text
relationship-preview {"operation":"attach","group_id":"group-readers","member":{"selector":"custom-books","context":"<exact custom-books context>"}}
relationship-commit
```

Read the frozen review and separately type `ATTACH TASK`. To stop all exact members:

```text
relationship-preview {"operation":"stop","group_id":"group-readers"}
relationship-commit
```

Read the exact member list and separately type `STOP GROUP`. A stale review is rejected, not silently refreshed. Wrong/blank/back phrases do not commit. Stop is a local work fence, not remote cancellation or recall of an already sent message. Historical state, reviews, deliveries and received messages remain readable. The backend permits only safe `check`, `recover`, `decline`, `defer`, and `withdraw_unused` controls after stop; other work is fenced. Withdrawal requires exact owner/request_id/review_digest and `WITHDRAW <owner>`. No automatic reduction action is taken.

## Failures and ending

Unknown commands, surplus fields, duplicate JSON keys (including nested), malformed/nonfinite JSON, and unexpected command arguments are refused. There is no evaluation, shell escape, executable registration, or command execution from received content. An uncertain communication/startup error is displayed and latches the console into read-only inspection. Pending previews are discarded, but task history is not automatically closed or reset. Inspect list/state/messages/reviews/deliveries/proposals, then explicitly close or quit when ready; mutation commands remain blocked for this session. No action is automatically retried. A failed child process may still make its own read commands unavailable; unrelated task inspection remains available. Do not interpret an exception as proof that a send did not occur.

`close` requires `DISCARD FIXTURE` and discards only the captured selected task. This differs from group stop: close removes the disposable service/history. It does not switch to another task. `quit`, EOF, or interrupt ends the session and cleans up all temporary services. Inspect needed history before discarding it; nothing here promises persistent recovery after exit.

## Test evidence

The final extracted-source report is fresh-verifier-full-v24.json, summarized in
verification-v24.json. Focused console and compatibility logs are stored under
verification/v24-console-*.txt. These are terminal/backend and DOM-model checks,
not real-browser or real-provider verification.
