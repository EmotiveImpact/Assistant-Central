# Offline raw framing r4 candidate

This additive layer feeds frozen r3's exact `incoming.receive() -> SessionMessage`
and `outgoing.send(SessionMessage)` interfaces. The complete r3 tree is copied
unchanged into baseline_r3, including its original nested r2. No earlier roots or
archives are modified. This is a candidate for review, not frozen or packaged.

## Byte boundary

Caller-owned `reader.receive(n)` returns strictly bytes, 1 through n bytes, or
raises anyio.EndOfStream. Empty bytes are a contract failure, not EOF. Each read
requests 4096 bytes. Over-return and nonbytes fail locally without truncation.
Caller-owned `writer.send(bytes)` must accept a whole message or raise and return
None on success; partial byte-count returns fail locally. This is not an OS write
adapter. Nothing closes, reopens, reconnects or retries either stream.

LF is the sole delimiter. The input record cap is 16,384 bytes excluding LF and
including any CR. CRLF is explicitly accepted; CR is ordinary JSON whitespace,
not a second delimiter. A blank line is a malformed record, not a keepalive.
A complete-looking JSON object without its LF is an incomplete record at EOF and
is never dispatched. Coalesced and fragmented records share the same bounded
buffer. Before appending a segment the cap is checked. An oversized record emits
one fixed uncorrelated parse error and terminates without draining. The already
returned bounded 4096-byte chunk exists before this check; no claim is made to
bound allocation inside a malicious caller's reader.

At most 160 raw records (including malformed and ignored notifications) are
handled. A cap-exceeding attempt also counts before termination. A partial EOF
is reported separately, never parsed. At most 128 safe IDs are consumed, including
IDs on raw protocol rejections. Integer and string IDs are distinct. Duplicate
keys/undecodable JSON never provide a trustworthy ID or consume an ID. Accepted
IDs are nonnegative 31-bit integers or 1–64 ASCII alphanumeric/underscore/hyphen
characters; boolean, float and null IDs are rejected before Pydantic.

Strict UTF-8 decoding follows the byte cap. A string-aware escape-aware lexical
scan permits at most nine open collections before JSON parsing (root depth zero).
Custom JSON hooks reject all duplicate keys, including escaped aliases and nested
keys, and NaN/Infinity tokens. No model_validate_json coercion is used. After JSON
parsing the frozen r3 bounded traversal checks depth 8, collection size 64, total
512 visited values/keys, finite numbers, integers strictly between -2^53 and 2^53,
scalar Unicode, and normalized compact UTF-8 JSON size 16,384. These are distinct
post-allocation checks. Top-level batches/scalars and all envelope extras,
including null extras, are rejected before SDK model construction. Params must be
an object when present; null is not omission. Valid r2 text of up to 1024 UTF-8
bytes is preserved, including escaped NUL, quotes, backslashes and newlines.

## Errors, results and authority

Notification silence applies exactly to parsed objects with jsonrpc equal to
"2.0", a string method and no id, including invalid params or extra fields.
Objects with a wrong or missing jsonrpc version are not classified as notifications
and may receive an uncorrelated error. Undecodable JSON has no trustworthy shape or ID and
receives a fixed -32700 with id:null. Other raw errors are fixed `Request rejected.`
with safe correlation or id:null. Unsupported valid methods retain -32601;
recognized-method invalid params retain -32602; envelope errors use -32600.
Frozen r3 still enforces its state, method, argument and ID rules. No owner method
or callback is added. Raw data never becomes authority. The only application
surface remains proposal, proposal status and processed-only inbox.

Output is UTF-8 compact JSON with LF; the 32,768-byte OUTPUT_CAP **includes LF**.
The r3 tree limits are independently reapplied before output serialization.
A rejected SDK output becomes a fixed -32603 outcome-uncertain error, never a raw
exception. No uncertain write is retried. Fixed local failures are exceptions,
not extra wire responses. SDK logging confidentiality remains unverified:
redacted responses are not logging isolation.

## Local facts and uncertainty

RawBridge.facts reports termination, raw record count, admission to r3, output
attempts and accepted outputs, uncertain output, partial EOF bytes, and whether
a propose-shaped request was admitted. Admission is not proof that r3 accepted
or persisted a proposal. The proposal flag is conservative and says only that
local persistence is possible. Writer acceptance is not peer delivery. Later
reader failure/partial EOF does not undo previously accepted outputs. A failure
after proposal admission can leave an unsigned local proposal persisted.

Cancellation propagates. No lossless drain, hard CPU/memory/OS isolation, bounded
wall-clock latency or preemption of synchronous SQLite is promised. Neither
single-use adapter can restart. The caller controls availability and lifetime.

## Evidence scope and exclusions

A real SDK ClientSession test independently serializes/parses JSON/LF on its
client side and fragments both byte directions, covering initialize, ping, tool
listing, propose, status and inbox. It does not reuse the server codec for client
encoding or parsing.

New tests and the two-way demo use only synthetic memory bytes and sequential
in-process Endpoint/ProposalStore objects. The demo independently performs
synthetic owner grants/review/release, delivery, processing and publication; no
raw MCP operation performs them. These are not authenticated human owners.
No new process/fault/concurrency/shutdown probes were made. No fixture.py,
pipes.py or worker.py internals were inspected, reviewed or modified. The additional concurrent-shutdown/descriptor-lifecycle review remains
uncompleted and excluded.
No network, listeners, sockets, stdio setup, native host, browser, accounts,
credentials, enrollment, installs or third-party communication occurred. MCP is
only a local tool protocol; the peer envelope is custom experimental r1, not an
A4A interoperability claim.
