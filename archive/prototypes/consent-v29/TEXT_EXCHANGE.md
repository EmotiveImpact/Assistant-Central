# Bounded fictional text exchange

The owner workspace supports `bounded-text-exchange-v1` alongside the original
public-resource shortlist. This is inert, offline communication between fictional
Alice and Bob, not permission to execute text, follow links, schedule work,
contact people or disclose private data. No new agent methods are exposed.

The exact text composition fields are selector, task_id, conversation_id,
requester, query, capability and max_reply_chars. Capability must be
bounded-text-exchange-v1; the operation is exchange-text. The six-field shortlist
composition remains unchanged and omits capability. There is no migration.
The complete spec is committed into the task context. Existing catalog task,
request and result hashes and old composition previews remain unchanged.

Text requests have exactly prompt and max_reply_chars. Prompt is nonempty text
up to 512 Unicode code points. Reply limits are integers from 1 to 512, excluding
booleans. Results contain only nonempty text, no longer than the request's limit.
Existing composition restrictions on leading/trailing whitespace, controls and
surrogates still apply to the fictional query. Response text is retained exactly;
it is never interpreted as HTML. No Unicode normalization or truncation is used.

Task preview is pure. Exact typed creation starts disposable fixture processes.
Binding, bilateral pairing, owner review, approval, submission, delivery and
receipt processing are still distinct. Response composition requires the exact
processed request; preview is pure and typed preparation produces an unsigned
review. Identical review history is reused even after refusal, withdrawal or
completion. New terminal content is refused. Received messages only expose
processed messages for the selected owner, with exact scope, digests and fictional
sender binding. Process isolation is not an OS sandbox, and labels/bindings are
not authentication of actual humans or providers.

Request-relative validation is shared by task projections and response authoring.
Immutable composed-result linkage and limits are also checked at the signer
boundary. Restricted-host schemas advertise the correct text payload shape
without expanding the three existing methods.

All transport limits remain unchanged: canonical envelopes 8 KiB, owner input
16 KiB, custom response frames 64 KiB, startup 8 KiB and HTTP request bodies 8 KiB.
Maximum escaped supplementary Unicode is exercised through child processes in
both directions and through HTTP handlers without increasing any limit.

Verification uses Python tests and DOM-model tests only. HTTP tests invoke real
handlers without opening sockets. No browser, native-dialog, visual/accessibility,
live-provider or real-identity acceptance claim is made. No publication, accounts,
persistent credentials, external messages or browser retries were performed.
