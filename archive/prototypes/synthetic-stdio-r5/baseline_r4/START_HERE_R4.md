# Experimental r4: bounded raw MCP framing

The new raw_bridge layer composes the byte-preserved frozen baseline_r3. It checks
UTF-8/LF message bytes before they reach the decoded MCP tools. This is synthetic
memory-stream framing, not stdio/HTTP/native-host integration. Every earlier
artifact remains unchanged.

From this directory, with the already installed environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_all_checks.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_raw_checks.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_demo.py
```

DESIGN.md specifies the byte interface, exact bounds, consumed-ID rule, explicit
CRLF/EOF behavior, local uncertainty and exclusions. EVIDENCE.md records tests.
INDEPENDENT_REVIEW.md records the separate review. Final combined counts and fresh
archive results are in verification-r4.json and evidence/. Worker-stage evidence
predates the combined release checks.

The combined command verifies RAW_SOURCE_MANIFEST.json, checks all 94 inherited
r3 files against BASELINE_R3_FILES.json, runs r3's original aggregate unchanged,
then runs the new implementation/independent byte-boundary checks and demo.
Original r3 and nested r2 commands remain runnable inside their own directories.

## What is demonstrated

- A real SDK ClientSession exchanges independently serialized/parsed JSON over
  fragmented synthetic byte channels with the server. The negotiated version is
  2025-11-25. The inherited decoded suite separately tests four legacy negotiations.
- Input records are capped at 16 KiB before decoding. Strict UTF-8, duplicate keys,
  raw ID types, early nesting and post-parse structure checks reject malformed
  records before proposal dispatch. Output is capped at 32 KiB including LF.
- Partial records at EOF do not execute. Safe IDs remain consumed after raw
  rejections. Finite raw-record and ID budgets prevent unbounded session history.
- Exact Unicode text, including escaped controls, survives without truncation or
  normalization. Proposal calls remain unsigned local writes, never approval or
  permission to send. Only the same three narrow application tools are exposed.
- Failed writes are never retried. Local admission and accepted-output facts are
  separate from delivery. Later failure does not erase an already observed result
  or roll back a persisted proposal.

New raw tests and the full two-way owner-controlled demo use sequential in-process
endpoints with separate stores. The inherited r3 aggregate also reruns its existing
two-process demo. The new raw layer itself has not been exercised against a live
host, actual stdio/HTTP transport, or separately authenticated human owners.

## Remaining boundaries

MCP here covers local tool calls only. Peer packets still use the custom experimental
r1 envelope; no A4A interoperability or broad cross-provider network is claimed.
No real account, credential, host installation, identity enrollment, listener,
socket, browser action or live connection was involved.

The additional peer-process concurrent-shutdown/descriptor-lifecycle review remains
uncompleted and excluded from this work. Response redaction does not establish SDK
logging confidentiality. Reader allocation costs, whole-process resource isolation,
hard synchronous-SQLite preemption and lossless output drain are not guaranteed.
These targeted checks are not production acceptance or full MCP conformance.
