# Offline bounded MCP JSON and LF bridge

This adds raw byte admission to the existing single-use SDK adapter. It does not
select or launch a host, open stdio, a socket or listener, authenticate anybody,
choose a relay, read credentials, install packages, or extend owner authority.
The existing three proposal-only tools and trusted task/actor binding are unchanged.
SDK 1.29.0 and the four legacy versions documented in MCP_ADAPTER.md still apply.

## Trusted composition API

`decode_record(bytes)` returns a DecodedRecord with either a SessionMessage,
a fixed JSON error byte string, or neither (silent rejected notification).
`encode_record(dict)` produces bounded UTF-8 JSON without a literal newline.
`await serve_lf(reader, writer, adapter)` connects a pre-bound adapter to caller
supplied asynchronous byte streams. Reader must implement receive(max_bytes),
returning at most that many bytes, or raise AnyIO EndOfStream. Writer must implement
send(bytes), completing the whole send or raising. This is not the partial-write
contract of os.write. The bridge never owns or closes these external endpoints.
Neither module contains a launcher. The caller may use in-memory byte endpoints;
these tests do not prove OS write atomicity, flush, delivery, deadlines or native
host interoperability.

## Wire limits and classification

Each record is UTF-8 JSON followed by LF. Fragmented/coalesced records are supported.
The raw record ceiling is 16,384 bytes excluding LF; reads are at most 4,096 bytes.
CR before LF is ordinary JSON whitespace. An empty line is malformed JSON.
Partial EOF never decodes or dispatches its unfinished record. Oversize stops the
session without resynchronization. Even ordinary clean EOF can cancel SDK handlers/egress and discard queued responses;
there is no EOF drain guarantee. Complete records preceding any EOF or oversize may already
have executed, even if no response arrived.

Strict UTF-8, duplicate-member rejection (at every object), nonfinite rejection,
and valid Unicode scalar strings are required. A string-aware nesting scan bounds
nesting before Python JSON decoding. Existing depth 32/node 2,048 tree validation
then applies, counting object keys as nodes. The byte bound limits parse allocation;
this is not a precise heap or CPU bound. Ordinary JSON decoding and encoding create
bounded transient copies. Integers, floating-point spellings (2.0 and 2e0), and
booleans remain distinct through SDK construction so application validation cannot
silently accept a float or boolean as an integer. This preserves numeric type/spelling
categories, not a lossless source-text representation (e.g. -0 becomes integer 0).

IDs are checked before SDK validation: exact int within +/-9,007,199,254,740,991 or
valid Unicode string of at most 256 UTF-8 bytes. Float, bool and null are rejected.
Cancellation requestId uses this same check before SDK notification parsing,
so bool/float values cannot cancel integer-ID requests.
ID reuse remains the existing adapter's concern and cannot execute another callback.
Raw-layer rejections do not enter the adapter or consume its request-ID registry;
they do consume the raw record budget. A later valid request with that id is a new
admission. Durable proposal IDs remain separate. Extra protocol-envelope metadata is inert;
application arguments remain closed. Params, when present, must be an object.

Malformed bounded JSON returns -32700 with null id. Invalid envelopes return -32600
with a safely extracted valid id, otherwise null. Parsed id-absent method envelopes
are recognizable notifications and receive no invalid-envelope error. Undecodable,
duplicate-member or complexity-invalid records have no trusted envelope and receive
a null-id error. Operational notifications cannot dispatch tools. Arrays/batches,
responses and missing-method envelopes are invalid for this proposal-only server.
The raw layer emits null IDs itself because SDK error models cannot represent them.
All peer error text is fixed and contains no submitted data or exception diagnostic.

At most 2,048 raw complete records are processed, including malformed and silent
records; the adapter separately retains at most 1,024 request IDs. Output is at most
32,768 bytes excluding LF, with JSON escaping and serialized whole-frame sends.
The writer lock prevents interleaved records. It does not guarantee a response is
flushed before the next callback. The existing adapter may have pending handlers
within its finite budget. There is no automatic callback retry, resend or reconnect.

## Lifecycle and remaining embedding duties

BridgeEnd is a fixed trusted-local report, never a peer diagnostic. Its
outcome_unknown flag is conservative: true after any request was admitted, even if
a response was sent. It is never proof of non-execution, delivery or owner approval.
Input/output/session exceptions produce stream_or_session_failed without original
exception text. Cancellation propagates normally and may follow committed work;
no callback or response is retried. A malformed/oversize record does not erase
uncertainty for earlier requests. Inspect durable proposal_status in a separately
composed authorized session where appropriate.

Embedding owns endpoint lifetime, byte-stream contract compliance, authentication,
trusted binding, admission/rate/global-session limits, deadlines and backpressure,
safe SDK logging and shutdown. Synchronous application callbacks cannot be preempted.
The bridge does not alter global logging. Python objects in the same process are
not isolated. There is no new host integration, security certification or conformance
claim. Existing readiness gates remain open.

Focused tests: `python -m unittest discover -s tests -p 'test_mcp_raw*.py' -v`
with the already available optional dependencies on PYTHONPATH. Independent bytes
exercise malformed input/framing; an actual SDK ClientSession exercises initialization,
three-tool discovery and closed inbox arguments through the LF bridge. Existing
adapter tests remain required for the full owner boundary and durable state suite.
