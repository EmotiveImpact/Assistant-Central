# Independent bounded raw MCP review

Reviewed 2026-11-08 in an isolated implementation copy before integration. This is an offline parser/stream composition review, not host acceptance, universal MCP conformance, production transport or security certification.

## Results

The independent file `tests/test_mcp_raw_review.py` contains 16 passing tests. Command:

    python -W always::ResourceWarning -m unittest discover -s tests -p test_mcp_raw_review.py -v

No ResourceWarnings appeared. The tests use independent bytes and caller-owned in-memory endpoints. One test runs actual SDK ClientSession initialization, three-tool discovery and inbox through an independent client-side byte encoder/decoder and three-byte fragmentation. No sockets, listeners, browser, installation, credentials, external agents or publication were used.

## Findings and disposition

- Initial raw invalid-envelope errors lost an otherwise safely extracted valid request ID. Correlation was corrected; independent empty/Unicode/safe-integer ID regression passes.
- Confirmed clean EOF can discard queued SDK responses, with response presence varying by fragmentation and scheduling. This is retained SDK lifecycle behavior, not fixed by draining. Guide explicitly discloses it. Independent tests distinguish live-open fragmentation equivalence from EOF response loss and require conservative outcome_unknown for an admitted request. No EOF delivery/drain guarantee is established.
- Suggested cancellation request-ID validation before SDK construction. Investigation showed installed SDK ClientNotification already rejects Boolean and floating request IDs, so no SDK coercion/miscancellation defect was demonstrated. The added raw check consistently enforces the local safe-integer and UTF-8 length limits; tests verify invalid notifications remain silent.

No unresolved application-authority blocker was identified within this bounded caller-provided-stream scope.

## Verified boundaries

- Boolean, null, float/exponent, unsafe-integer and oversized Unicode RPC IDs return null-ID errors without SDK coercion; valid IDs survive invalid-envelope errors.
- Duplicate members including escaped equivalent keys, nested duplicates, nonfinite literals/overflow, malformed UTF-8, isolated surrogates, BOM and trailing garbage are rejected before SDK message construction.
- Recognizable id-absent method notifications with malformed params produce no invalid-envelope response. Undecodable or complexity-invalid records instead have no trusted notification identity and produce fixed null-ID errors, as documented.
- Application Boolean/float/integer/string/null types survive raw conversion unchanged.
- Exact 16,384-byte record ceiling excludes LF and includes CR. Oversize terminates without subsequent callback; partial EOF is not admitted. UTF-8 output limits count bytes, escaped newlines remain one record. Exact depth 32 and 2,048-node limits count root/key/value nodes.
- Live-open fragmentation/coalescing at 1, 2, 7 and 4,096-byte chunks preserves expected responses. Malformed records consume the raw message admission budget.
- Postcommit output failure and cancellation with blocked output do not replay callbacks. Binding closes; adapter remains single-use; external endpoint lifetime stays with caller. Exceptions yield fixed local reports, without private exception text.

## Precise limits

Raw byte ceiling and string-aware lexical nesting scan precede JSON parsing. Node validation follows parsing, and output validation follows construction of trusted callback/SDK objects. These are not exact heap/CPU bounds. Existing decoded adapter re-encoding limits can additionally reject a raw record within the byte ceiling.

The writer's contract is an asynchronous whole send or exception, not a partial OS write/flush API. The lock serializes frames but does not ensure an earlier response is flushed before another callback. SDK handlers can remain pending within finite session budgets. No hard deadline, aggregate/global memory bound, global session/rate limit, or preemptible synchronous callback is established.

Clean EOF can lose responses; input/output loss and cancellation can follow a committed effect. outcome_unknown is intentionally conservative even when responses were sent. Durable state must be queried through a separately composed authorized session; no automatic replay occurs.

Raw null-ID error support does not change the older decoded adapter's invalid-ID behavior. Legacy version negotiation, SDK diagnostic logging limitations, trusted actor/task/dispatch composition, owner gates and host readiness remain as documented in MCP_ADAPTER.md. No new native host or modern protocol version support is inferred.
