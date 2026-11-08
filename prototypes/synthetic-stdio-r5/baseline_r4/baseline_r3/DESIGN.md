# Offline tools-only MCP bridge r3

This additive experiment composes the byte-preserved r2 baseline with the real
`mcp==1.29.0` Server and ClientSession. It is not native host integration or a
production transport. Root scripts insert only the fixed sibling `baseline_r2`
into Python's import path as trusted local composition; no host setup or install
is performed. Original r1/r2/v29 and earlier archives are not changed.

## Surface and authority

One single-use OfflineBridge receives exactly one concrete AssistantFacade. Its
three tools are `propose({text})`, `proposal_status({proposal_id})`, and
`processed_inbox({})`. Explicit branches map them to the facade. There is no owner
object, privileged callback, actor/task selector, ingress, packet, grant, approval,
release, processing or publication operation in the bridge. Python access and the
supervisor remain trusted, not isolated. Tool annotations are hints, not policy;
propose is explicitly not read-only, because it writes the local proposal store.

The caller creates and owns in-memory SessionMessage streams. A serial gate
validates decoded messages before forwarding them to the real SDK server. It
requires initialize, then notifications/initialized, before list/call. No other
application methods are admitted, including cancellation, resources, prompts or tasks.
The protocol-only empty-params ping is handled by the real SDK in any phase; it
preserves phase and obeys the same message, ID and count limits.
Only tools capability is advertised. Client capabilities are replaced by empty
capabilities; clientInfo is replaced by inert fixed information. Bounded `_meta`
and stream-side message_metadata are discarded. None is identity/routing authority.
There is no sampling, elicitation, roots, wake, experimental tasks or host auth.
Peer text is untrusted data. This bridge cannot govern a host's unrelated tools.

The SDK's supported legacy versions are explicitly allowlisted: 2024-11-05,
2025-03-26, 2025-06-18, 2025-11-25. Unknown/new versions are rejected before the
SDK can negotiate a fallback. Evidence reports actual negotiated versions. No
MCP 2026, spec completeness, native host acceptance, stdio or HTTP claim is made.

## Exact limits

- Decoded message JSON: 16,384 UTF-8 bytes. Each string is checked before encoding;
  the eventual compact JSON encoding must also fit (including JSON escaping).
- Tool argument JSON: 8,192 bytes. Text itself must be nonempty Unicode scalar
  text of at most 1,024 UTF-8 bytes; JSON Schema maxLength is supplementary, not a
  byte constraint. The argument budget accommodates JSON escaping of every valid
  r2 text; input is never truncated or normalized.
- Each checked tree: depth at most 8 (root is zero), 64 elements per collection,
  512 visited values/keys total. Finite floats only; integers strictly between
  -2^53 and 2^53. Non-JSON objects are rejected.
- Result payload JSON: 16,384 bytes. Full outgoing SDK message: 32,768 bytes,
  with the same depth/collection/node bounds. Results contain both structured
  content and JSON text, so the full response check is independent.
- IDs: integer 0 through 2^31-1, or 1–64 ASCII alphanumeric/underscore/hyphen
  characters. A valid ID is consumed even if its request is rejected. No reuse.
  At most 128 distinct IDs, and 160 total decoded incoming messages, per instance.
  At the message limit the run ends; remaining messages have no promised response.
- Tool names and exact argument keys are allowlisted. Extra top-level call params,
  selectors and task augmentation are rejected. Omitted arguments default to an
  empty object (valid only for processed_inbox); explicit null is rejected. Status IDs are 64 lowercase hex.
  r2 additionally enforces the bound actor/store, 64-record no-eviction history,
  exact content replay, and processed-only publication.

This is **already-decoded input**, not pre-decode raw-byte validation. JSON/Pydantic
objects have already been allocated by trusted caller/SDK code; validation does
not bound that prior cost or provide OS resource isolation. No batch is admitted.
Duplicate-ID errors use the same correlation ID but do not execute a new call.
Malformed notifications/uncorrelatable IDs are discarded without a reply.

All pre-forward protocol rejections return only `Request rejected.` when a safe
ID exists: -32600 for envelope/state/duplicate-ID violations, -32601 for
unsupported methods, and -32602 for recognized-method parameter violations. Tool failures return a fixed isError result:
`Tool operation unavailable; local proposal persistence may be uncertain.`
After forwarding, protocol/output failures instead return code -32603 and
`Operation outcome unavailable; local proposal persistence may be uncertain.`
Outgoing delivery failures escape without an attempted second send. Original
supported request and initialized-notification params are SDK-model-validated
before their inert metadata is replaced or stripped.
Raw exceptions, paths, rejected input and SQL details are not returned. No automatic
retry occurs. A result can be lost/rejected after synchronous persistence: that is
uncertainty about a **local unsigned proposal**, not authority to approve/send.
Owner state transitions remain separately explicit and follow frozen r2 semantics.

## Execution and exclusions

Stream processing is sequential; SDK internals use their normal task group. There
is no hard cancellation/preemption of synchronous SQLite work, timeout guarantee,
or lossless output-drain guarantee. The caller must manage stream lifetime and
availability. Run cancellation is not a proposal rollback. Instances cannot be
restarted. These are application limits, not lifecycle-audit conclusions.

The demo uses only the already documented ordinary sequential Experiment API with
two endpoint processes and four separate stores. SDK proposal, owner review/
approve/release, peer delivery, owner processing/publication and SDK inbox are
explicitly distinct steps. The additional concurrent-shutdown/descriptor-lifecycle review remains
uncompleted; excluded from this scope. New tests
exercise application/SDK behavior using local endpoint objects, never new process
lifecycle or descriptor probes. No fixture.py, pipes.py or worker.py internals were
inspected or modified. No accounts, keys enrollment, live network, listeners,
sockets, browser use, installation or external communications occurred.
