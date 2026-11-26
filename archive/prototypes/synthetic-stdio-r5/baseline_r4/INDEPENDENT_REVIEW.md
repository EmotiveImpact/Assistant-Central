# Independent r4 raw-byte boundary review

## Result

The independent suite passes **24 tests**. The candidate suite was also rerun and passes **32 tests**, including its real MCP SDK ClientSession test with independently serialized request and response fragments. No implementation defect was demonstrated within this review's scope. This is a narrow offline boundary result, not production or native-host approval.

The independent test file constructs its own JSON byte records, literal malformed records, reader/writer stubs and in-process endpoint/store setup. It does not use the candidate memory reader, writer, handshake, exchange or call helpers. Requests traverse RawBridge and the existing real MCP SDK Server except for explicitly identified codec unit tests and mocked output-rejection paths. Response decoding uses standard JSON. Endpoint operations in the processed-inbox test are explicit synthetic owner steps outside MCP.

## Findings

- Record length is checked before UTF-8 decoding and parsing. A 16,384-byte record is accepted, including CR when using CRLF. One additional CR causes rejection. LF is excluded from the input cap. Oversized input stops without draining; a reader-returned bounded chunk can already contain bytes beyond the cap.
- Fragmented and coalesced records work. An undelimited final object is never dispatched. Earlier accepted outputs remain recorded after partial EOF or reader failure. Empty byte returns and nonbytes/overlong returns fail the input contract.
- Duplicate keys, escaped duplicate aliases, invalid UTF-8, nonfinite values, unpaired surrogates, excessive nesting, collection/node bounds and normalized-size overflow are rejected. A lexical depth check runs before JSON parsing. Postparse bounds do not imply allocation isolation.
- ID checks occur before SDK model construction. Boolean, floating-point and null IDs cannot create proposals. Safe raw rejection IDs are consumed; integer and string IDs remain distinct. Parse/duplicate-key failures provide no trusted ID. Separate finite raw-record and consumed-ID budgets prevent unbounded raw error handling.
- Notification silence is specific: a decoded object with jsonrpc exactly `2.0`, string method and no id is silent even if params or extra fields are invalid. Missing/wrong version is not classified as a notification and receives an uncorrelated error. The design's broad phrase “Decoded notifications never receive a reply” should be read with this exact qualification; spelling out the predicate would improve precision.
- The output cap includes LF. Output serialization rejection uses a fixed uncertainty message. Reader/writer exceptions do not leak their text in the propagated LocalFailure. Writer failure or cancellation during send is uncertain and is never retried; input cancellation alone does not claim output uncertainty. Partial writer count returns are rejected.
- The proposal-persistence flag is deliberately conservative: an admitted propose-shaped request rejected by r3 before initialization still sets it even though no proposal exists. Accepted output means local writer acceptance, not remote delivery or rollback.
- Mixed NUL, quotes, backslashes and newline text totaling exactly 1,024 UTF-8 bytes and 1,024-byte emoji text survive proposal persistence and replay. Endpoint state remains unchanged by MCP proposal calls. Inbox content remains absent until explicit owner processing and explicit publication. Owner-style methods, tool names and actor selectors are rejected.

## Preservation

`hashes-before.json` and `hashes-after.json` record SHA-256 hashes for 12 relevant new runtime/test/document files and the directly used frozen r3 bridge interface. All 12 matched at the end of this review. `hash-comparison.txt` lists each comparison. These are scoped hashes, not a claim of independently revalidating the entire inherited source tree. Candidate sources and old archives were not edited. All review artifacts were written only in this review directory.

## Limitations

This review used caller-owned synthetic byte streams and sequential in-process endpoints/stores. It added no peer processes, listeners, sockets, live networking, stdio transport, host installation, credentials or enrollment. No inherited fixture.py, pipes.py or worker.py internals were inspected or tested. The additional concurrent-shutdown/descriptor-lifecycle review remains uncompleted and excluded.

Frozen r3's reported 124-test evidence was not rerun here. The candidate's sequential demo was not independently rerun here; its raw persistence/inbox behavior was independently tested. SDK logging confidentiality remains unverified; response and local-exception redaction do not establish logging isolation. No hard CPU/memory isolation, synchronous operation preemption, wall-clock availability, authenticated human-owner, live transport or delivery guarantee is established. The peer wire remains custom experimental r1; MCP is only the local tool interface, not an A4A interoperability claim.

## Reproduce

From the workspace containing the candidate and review directories:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python agent-network-raw-boundary-review-r4/test_independent_raw.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python agent-network-independent-peer-raw-r4/run_raw_checks.py
```

`test_independent_raw.py` and `review_bootstrap.py` are the full portable independent suite. They can remain in this sibling review directory, be placed together in another directory with RAW_R4_ROOT set to the candidate root, or be copied together into the candidate's raw_tests directory. The latter placement is supported but was not performed on this candidate. No dependencies are installed by the bootstrap. Existing dependencies include mcp==1.29.0.

Logs: `independent-tests.txt` (24 tests) and `candidate-tests.txt` (32 tests). Run with bytecode disabled and ResourceWarning elevated to error, as shown above.
