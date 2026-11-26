# Independent decoded-stream MCP review

Date: 2026-11-08. Reviewed an isolated source snapshot; the earlier v27 archive was preserved.

## Result

No unresolved application-authority blocker identified within the narrow trusted-composition, decoded-SessionMessage interface. This is not a complete MCP conformance audit, host acceptance, raw transport security review, or production security approval.

Independent regression file: `tests/test_mcp_adapter_review.py`. Fifteen tests pass using installed MCP SDK 1.29.0 and the offline dependency path. The suite uses actual SDK ClientSession for discovery/call interoperability and direct JSONRPC SessionMessage streams for adversarial cases. All input/output transport endpoints are anonymous in-memory streams. No network, browser, install, host configuration, credentials, relay, or external-agent action occurred.

Command:

    python -W always::ResourceWarning -m unittest discover -s tests -p test_mcp_adapter_review.py -v

## Resolved findings

- SDK BaseSession request/notification validation logs can contain malformed input values. Typed prevalidation now occurs before forwarding, with fixed errors or notification drops. Sentinel tests verify malformed metadata and cancellation payloads do not reach those diagnostics.
- SDK unknown-tool lookup logs the requested name. Unknown names are now intercepted with a fixed tool error before SDK lookup. Sentinel regression passes.
- Explicit internal stream cleanup and test-owned endpoint cleanup produce no ResourceWarnings in the independent run.

## Verified boundaries

- Discovery exposes exactly propose, proposal_status, inbox; no resources, roots, sampling, elicitation, or owner signing capabilities are advertised.
- ClientInfo title, capabilities, and protocol metadata are accepted as inert protocol information. They cannot change task/actor routing, authorize owner operations, or enter callback commands.
- Exact application types remain strict despite SDK lifecycle model coercion. Boolean, float, string, and out-of-range application integers are rejected; foreign actor/task/context envelopes never dispatch.
- Null arguments are rejected before SDK's `arguments or {}` normalization; tool-shaped notifications never dispatch.
- Owner-shaped extra output fields and wrong-direction inbox envelopes are redacted. Callback exception text does not escape the tool response.
- Concurrent duplicate request IDs execute once; an exception after a callback's effect does not permit retry under the same request ID.
- Cancellation after the callback's committed effect and before client response consumption closes the application binding without replay. Adapter instances cannot be reused.
- Initialize and initialized notification are required before tools. Request/message budget exhaustion terminates cleanly. JSON-RPC string IDs accept any valid-Unicode string whose UTF-8 encoding is at most 256 bytes, including empty strings, ordinary punctuation, URI-like strings, and non-ASCII text. Exact 256-byte ASCII and emoji IDs correlate unchanged in success and duplicate-error responses. Over-bound ASCII/emoji IDs and isolated surrogates terminate silently without dispatch rather than fabricate an SDK-invalid null error ID. Application identifiers remain lowercase ASCII `[a-z0-9_-]{1,64}`. Integer JSON-RPC IDs remain restricted to the safe range -9007199254740991 through 9007199254740991.
- Size/depth bounds reject before callback. Four supported versions negotiate as declared; unsupported 2026-07-28 requests receive 2025-11-25 fallback, never a claim of 2026 support.

## Important limits and remaining integration choices

- Bounds apply after transport parsing/Pydantic construction. They do not establish raw-byte limits, lexical type preservation for protocol fields, duplicate-key rejection, or protection from parser allocation. A future frontend needs independent bounded framing and parsing.
- SDK transport metadata is removed; protocol `_meta` remains inert. This does not authenticate the host or caller. Exact dispatch/task/actor composition remains trusted Python code, not an OS or hostile-code sandbox.
- Synchronous callback execution preserves current storage affinity but is not preemptible. Cancellation cannot undo a committed proposal. No hard callback deadline, OS isolation, client supervision, reconnect recovery, or live timeout guarantee is established here.
- The 1,024 request and 2,048 message budgets and per-message bounds are scoped session guards, not a global rate limiter or total memory guarantee. Lifecycle metadata may be normalized by SDK models; strict application payload checks are separate.
- Invalid-ID silent termination and SDK fallback negotiation are deliberate restricted behaviors. Native clients must be tested against the exact runtime/build. SDK usage alone does not establish universal standards conformance.
- SDK logging and exception pathways were reviewed in installed Server.call_tool, ServerSession._received_request, and BaseSession._receive_loop. Library internals are version-dependent, hence the exact SDK pin matters.
- A host-launchable stdio frontend, approved host choice/configuration, real identity/custody, native acceptance, relay transport, and wake remain separate unimplemented/unverified gates.


## Targeted SDK diagnostic limitation

A focused ephemeral logging check (not an additional test-count claim) enabled the SDK's `mcp` DEBUG logger and sent a valid initialized notification with a synthetic `_meta` marker. Installed SDK 1.29.0 `Server.run` logged that marker verbatim in `Received message: %s`. Thus the adapter does not guarantee universal log redaction: valid client-controlled initialized-notification metadata can appear in DEBUG diagnostics.

The same check sent a valid cancellation notification with synthetic reason and metadata markers for an absent request; neither cancellation marker appeared. `BaseSession._receive_loop` consumes cancellation before the lowlevel incoming-message log. Separately, source inspection of `Server._handle_request` shows that its cancellation/duplicate-response-suppression INFO branch includes the client-controlled request ID; its transport-closed DEBUG branch also includes that ID. These branches are source-confirmed, not claimed as reproduced by the absent-request cancellation check.

These normal SDK diagnostic behaviors are distinct from the corrected malformed-input and unknown-tool WARNING echo paths. Callback exception text and disallowed owner output remain blocked by the application boundary. No global logging filter or SDK patch was imposed. Future host composition must deliberately choose diagnostic level, collection, retention, and access; logs must not be treated as a universally redacted output channel.
