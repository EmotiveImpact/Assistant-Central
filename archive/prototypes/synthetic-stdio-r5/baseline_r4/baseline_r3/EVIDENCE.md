# Implementation evidence, 2026-11-08

This is not a freeze, package verification or independent security review.
Independent review and packaging remain separate.

Commands run from this r3 root:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_bridge_checks.py`
  passed all **18** new application/SDK tests (latest run: 0.165 seconds).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_demo.py`
  passed the ordinary sequential synthetic two-process flow. Actual negotiated
  legacy protocol: **2025-11-25**. Proposal left endpoint snapshots unchanged;
  explicit owner release produced released local status; recipient SDK inbox was
  empty before owner processing and contained the exact payload after publication.
  The full request/result roundtrip also passed: Bob proposed through his SDK, his
  separate owner reviewed/released the result, and Alice processed/published it
  before observing the exact result through her SDK inbox.
- SHA-256 comparison of every original r2 file with its nested copy confirmed
  **65 byte-identical files**, no missing or extra copied files.

Tests cover real SDK ClientSession initialize/list/call, exact tools-only capability,
all four allowlisted legacy negotiations, rejection of a 2026 version, initialized
notification barrier, unknown tools/methods, extra actor/task/owner selectors,
duplicate/previously rejected request IDs, request-count limit, inert metadata,
malformed initialization, exact replay of declined/unknown text, per-actor status,
processed-only inbox, endpoint state unchanged on proposal, UTF-8 and escaped-text
bounds, decoded depth/collection/message bounds, output bounds, redacted facade
errors, post-dispatch uncertainty, and constructor/single-use contract, protocol-only ping in all three phases, correct
redacted JSON-RPC error codes, and original SDK metadata shape validation.

An implementation review identified and the implementation corrected: original
initialization shape validation before metadata sanitization; different errors for
pre-dispatch rejection versus possible post-dispatch persistence; sufficient JSON
argument budget for escape-heavy valid r2 text. Outgoing delivery failures are not
retried. The regression tests include each correction.

Available environment, no installation: Python 3.12.14; mcp 1.29.0; anyio 4.14.2;
pydantic 2.13.4; jsonschema 4.26.0; cryptography 50.0.0. Runtime checks pin mcp
exactly. These are observed versions, not a claim of compatibility with all future
or earlier dependencies.

No new process concurrency, shutdown, failure or descriptor probes were added.
The additional concurrent-shutdown/descriptor-lifecycle review remains
uncompleted; excluded from this scope. No fixture.py,
pipes.py or worker.py internals were inspected or changed (whole-tree file hashes
were compared only to establish preservation). No host authentication, raw-byte
transport validation, live transport, account enrollment, external publication,
hard SQLite preemption or lossless output drain is claimed.

Independent-review follow-up: bounded ping support was added without any tool or
capability expansion. Protocol errors now distinguish -32600/-32601/-32602, and
all admitted request/initialized notification models are validated before metadata
is stripped. Three new focused regressions pass; the full demo was rerun. No new
process lifecycle behavior was exercised or reviewed.

Optional tools/call arguments now default to {}. A real ClientSession inbox call
with no arguments passes; missing propose/status fields still return -32602.

Strict-envelope review correction: original SDK model extras are checked before
serialization can discard null fields. A parsed JSONRPCMessage with owner:null
now returns fixed -32600 without creating a proposal. The new regression and
full sequential demo both pass.
