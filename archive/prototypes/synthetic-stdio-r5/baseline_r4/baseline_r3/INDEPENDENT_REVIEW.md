# Independent offline MCP application review

Reviewed 2026-11-08. Scope: the new decoded-message MCP application bridge and its three-tool contract.

## Result

The final revision passed **18 supplied bridge tests and 15 additional independent tests**. No unresolved authority-escalation defect was found within the examined scope. This is a focused application review, not a complete security or MCP conformance certification.

Reviewed file hashes are recorded in `final-code-hashes.txt`; all matched before and after the final test runs. Logs are `final-existing-tests.log` (18 tests, 0.166 seconds) and `final-independent-tests.log` (15 tests, 0.116 seconds). The independent suite is `test_independent_bridge.py`.

## Verified behavior

- Only propose, proposal_status and processed_inbox are advertised and callable. Unknown tools, owner/actor/task selectors and malformed arguments are rejected. Proposal operations leave endpoint state unchanged.
- Tool operations require initialize followed by a valid initialized notification. Protocol-only ping succeeds in every phase without advancing the initialization gate, including through ClientSession.send_ping.
- Unsupported methods, invalid parameters and invalid request/state/duplicate-ID cases use the intended distinct error codes with fixed redacted text.
- Original supported SDK request/notification shapes are validated before metadata is discarded. Malformed metadata does not create a proposal or open the initialization gate. Null-valued top-level envelope extras are rejected before serialization can hide them.
- All four allowlisted legacy versions negotiate through the actual SDK server. The real ClientSession tests use 2025-11-25. Tools-only capabilities and the explicit initialization barrier are preserved.
- UTF-8 bounds, JSON escaping, NUL text, exact Unicode normalization differences, collection/depth/node constraints and output limits are exercised. Valid 1,024-byte escape-heavy text remains exact.
- Full 64-record history does not evict old proposals. Exact replay preserves declined content history. Integer and string request IDs are distinct; duplicate IDs do not repeat a call.
- Existing scoped tests verify actor-specific status, processed-only publication and explicit owner separation. Metadata and peer-like instruction text do not become authority.
- A real outer-output bound failure after a successful local write reports -32603 uncertainty, retains one pending proposal, and does not retry on duplicate request ID. A separate post-write handler exception returns only the fixed tool uncertainty message. Text content and structured content agree in successful independent exact-text cases.

## Corrections verified during review

The final revision resolves the examined malformed-initialize sanitization, escape-heavy argument-budget and post-forward uncertainty issues. It also adds legacy ping support and protocol error distinctions, rejects malformed metadata before stripping it, supports omitted empty arguments for processed_inbox, and rejects null-valued extra envelope fields. Earlier shape/interoperability observations are retained in the initial logs; they do not describe the final tested behavior.

## Boundaries and remaining concerns

- Already-decoded objects have been allocated before this gate. These bounds do not cover raw transport decoding, prior allocation cost or OS resources.
- Concrete AssistantFacade type checks are trusted logical composition, not protection against arbitrary Python/OS code or mutation by the embedding application.
- **Response redaction is not logging confidentiality.** Proposal text is forwarded to the SDK. SDK debug logging and the embedding application's logger configuration were not audited or isolated; request data could appear in diagnostic logs.
- Synchronous SQLite work has no demonstrated hard preemption/timeout guarantee. Output can fail after persistence, so the uncertainty wording matters. Stream lifetime and lossless output-drain guarantees were not studied.
- No native host, live transport, stdio, MCP 2026 or full protocol conformance claim is established.
- The additional peer-process concurrency/shutdown/descriptor-lifecycle audit remains uncompleted and excluded from this scope.

## Method and provenance

No candidate file was edited by this review. Tests used sequential local Endpoint/ProposalStore objects and SDK memory streams. Two raw-stream helper functions were reused from the supplied tests; independent test bodies and assertions are separate. Test runs used PYTHONDONTWRITEBYTECODE=1 and PYTHONWARNINGS=error::ResourceWarning.

The root START_HERE_R3.md, DESIGN.md, EVIDENCE.md, mcp_bridge code, bridge tests and run_demo.py were read. README.md was absent; START_HERE_R3.md is the entry document. The facade application contract was read as needed. The demo source was inspected but its two-process execution was not independently run. No baseline aggregate or process probes were run; fixture.py, pipes.py and worker.py internals were not examined. No live connections, credentials, account operations, installations or external writes occurred.

Reproduce from the containing workspace:

    PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python agent-network-independent-peer-mcp-r3/run_bridge_checks.py
    PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python agent-network-mcp-bridge-review-r3/test_independent_bridge.py
    sha256sum -c agent-network-mcp-bridge-review-r3/final-code-hashes.txt

## Packaging finalization

The independent test bootstrap now also resolves correctly when copied unchanged into the candidate bridge_tests directory. Only root-path resolution changed; test bodies and assertions are unchanged. All 15 tests passed again. Its SHA-256 is fdec749b7044c093e00b9b666db95d2b102e1d6f8f5d410e27d43af0f58a5c9d.

START_HERE_R3.md received documentation-only finalization after the initial review, describing packaging, aggregate execution and logging limitations. It was reread and its recorded hash refreshed. The new aggregate runner, dependency manifest and package-verification machinery are outside this runtime review scope.
