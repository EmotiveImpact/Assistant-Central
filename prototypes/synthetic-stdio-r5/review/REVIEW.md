# Independent review: synthetic-only stdio pilot r5

Date: 8 November 2026, UTC.

## Decision

**No blocking defect found within the permitted ordinary application/stdio review.** The reviewed build passes the local synthetic-only stage in this existing Linux/Python environment. It is suitable to take to a separate native-host acceptance decision, not to claim native-host acceptance, deployment, relationship-network readiness, or permission to install/configure anything.

The final reviewed `launcher.py` SHA-256 is:

`4df94f7f454989f864ac327da182b1054fff8952e4288915cb988fe891529571`

**39 distinct targeted tests pass:** the builder's 20 checks independently rerun on that final source, plus 19 independently written checks. The independent 19 also pass from a relocated temporary release with an unrelated working directory and a deliberately invalid `STDIO_R5_ROOT`, proving the colocated test bootstrap selects the relocated release instead of the original checkout. Repeated executions are not counted as additional distinct tests.

No candidate source changes were made by this reviewer. No open actionable defect or required source fix resulted from this review.

## What was reviewed

- The new launcher, public fixture, targeted builder tests/runner, README, evidence summary and setup/rollback guide.
- The narrow frozen `raw_bridge` framing/transport, `mcp_bridge` dispatch and facade/store APIs needed to trace the three-tool proposal-only path. These dependencies were not modified.
- Whole-file preservation hashes. The additional independent-peer cross-lane concurrency/shutdown/descriptor-reuse audit was **not** performed. Its fixture, pipe and worker internals were not inspected or tested, and no equivalent substitute probes were added. Opaque copying/hashing of those files supplies preservation evidence only.
- Actual single-launcher local stdio clients, including the builder's installed MCP SDK `stdio_client`/`ClientSession` test. No peer process, native host CLI/configuration, browser, provider, external agent, credential, installation or network connection/listener was used.

The environment was Python 3.12.14 on POSIX/Linux with existing MCP 1.29.0, AnyIO 4.14.2, Pydantic 2.13.4 and cryptography 50.0.0. All Python executions used `-I -B`.

## Findings and evidence

### Proposal-only boundary holds in the tested composition

The script creates a fixed in-memory proposal store and an exact frozen `AssistantFacade`. Its instance-level `propose` closure rejects anything except the exact allowlisted fixture string before calling the original facade method. There is no model/provider selector or configurable actor, fixture, endpoint, owner channel or storage path.

The installed SDK sees exactly `propose`, `proposal_status` and `processed_inbox`. Accepted proposals remain pending with no operation, command, message or packet IDs. Repeated semantic text, including equivalent JSON Unicode escaping, produces the same proposal. Text variants are rejected, the empty inbox remains unpublished, and clean new sessions cannot recover an earlier in-memory proposal. The latter is an expected limitation, not evidence that an earlier operation never occurred.

The generic frozen `propose` schema does not advertise the launcher's extra exact-text restriction. The README explains this and provides the exact argument. A later synthetic native-host acceptance script must use that argument; this is not general-purpose drafting support.

### Framing, protocol and ordinary I/O checks pass

The builder checks actual pipes, SDK interoperability, framing and record limits, malformed UTF-8/JSON, duplicate IDs/keys, fixed diagnostics, input rejection, partial writes and no operation replay.

The independent checks add:

1. Exact negotiation of all four documented protocol versions; unsupported versions fail without fallback, and a later valid initialization needs a new request ID.
2. Client capabilities and metadata do not expand server capabilities or echo synthetic private-looking metadata.
3. Non-tool MCP methods are rejected while the ready state and empty inbox remain intact.
4. CRLF and equivalent JSON-escaped exact text preserve proposal identity; whitespace, casing, nonbreaking-space, BOM, NUL and newline text variations do not enter the allowed proposal path.
5. A partial trailing frame is not dispatched after a prior successful proposal, and a non-scalar Unicode value receives a bounded rejection without echo.
6. Regular-file stdin or stdout is rejected at startup.
7. Real AnyIO cancellation scopes enforce short test timeouts around **synthetic** blocked read/write seams. A partial write never replays the already accepted prefix. This is ordinary adapter contract testing, not a peer/process shutdown or descriptor-lifecycle test.
8. Falsy nonbytes are rejected rather than mistaken for EOF, boolean read sizes are rejected, and a maximum-sized write completes exactly once through synthetic partial writes.
9. A changed or missing manifest-referenced codec causes startup rejection before protocol output; internal same-byte symlinks and unmanifested module/bytecode shadows are rejected.

All requested protocol rejections can coexist with process exit 0 at ordinary EOF. Exit 0 is therefore not blanket tool success. Partial frames and finite budgets terminate with 65; runtime, output and idle conditions retain uncertainty. The README states these distinctions accurately. The final source also sets pipe stderr nonblocking before startup gates and conservatively classifies an exception escaping runtime entry as 70.

### Integrity and preservation checks pass

The pinned r4 manifest has SHA-256 `ded41439c7fe7a35370019b30fcbb6a773bcd82e67de1f406a98104c2fb7d71c`; its 67 referenced files and the pinned public fixture verify. All 12 explicitly recorded reviewed files have unchanged before/after hashes.

An independent opaque hash comparison against the builder's preimplementation record confirms:

- All 128 files in the candidate's `baseline_r4` match the original r4 input tree.
- All 128 original r4 files remain unchanged.
- All 8 original fixture-preparation files remain unchanged.
- No `.pyc` files were generated in the candidate.

The 67-file manifest verifies the launcher's designated frozen imports. The 128-file comparison is separate whole-tree preservation evidence; these counts should not be conflated. Hash checks require a trusted, nonconcurrently modified directory and do not authenticate a modified launcher.

## Limits that remain relevant to a native trial

- This establishes local synthetic client compatibility only. No Codex, Claude, Hermes, dot cloud plugin or selected model/provider accepted the launcher in this review. No broader relationship exchange, owner release, signing or peer transport was exercised.
- Python 3.12, POSIX FIFO stdin/stdout, `-I -B`, no application arguments and the documented finite protocol budgets are hard constraints. Windows and another host's actual startup, approval, cancellation/restart and logging behavior remain untested.
- Only MCP 1.29.0 is enforced by the program. The tested environment is not a complete dependency lock or a clean-install validation. Future setup requires its own approved environment and repeat checks.
- The exact-text restriction protects proposal admission, not confidentiality of every byte a client sends. Rejected input may be parsed transiently. The native host/provider may also see synthetic prompts, schemas, arguments and outputs.
- Guards and constructor patches support this trusted composition, not malicious-code isolation. The interpreter, installed site packages and startup hooks remain trusted. CPython's local AF_UNIX asyncio wakeup sockets exist. No zero-socket or OS-sandbox claim is justified.
- The 300-second limit applies per receive, not per completed record or whole session. Output acceptance by a pipe is not client receipt. A prefix may be emitted before failure; a diagnostic may be absent. Restarting loses the in-memory history and does not resolve uncertainty.
- No cross-lane peer concurrency/shutdown/descriptor-reuse, forced process termination, reconnect, lossless drain or excluded lifecycle property has gained evidence from these checks.
- The setup/rollback guide describes a later decision, preserves host provider choice and distinguishes configuration cleanup from transcript deletion or secure erasure. Its external documentation links were not fetched anew in this offline review. Exact native host/build documentation and effective policy must be checked when that later decision is made.

## Reproduce and package without checkout confusion

From this standalone review directory, explicitly select the release:

```
STDIO_R5_ROOT=/absolute/path/to/agent-network-synthetic-stdio-r5 python3.12 -I -B /absolute/path/to/agent-network-stdio-review-r5/independent_tests/run_checks.py
```

For the combined release, copy this review's `independent_tests` directory to the release root, producing `release/independent_tests/run_checks.py` and `release/independent_tests/test_independent.py`. Then run:

```
python3.12 -I -B /absolute/path/to/release/independent_tests/run_checks.py
```

The bootstrap prefers that colocated release. Only when it is absent does it require an explicit `STDIO_R5_ROOT`; it has no original-workspace fallback. The runner imports its own exact sibling test file rather than discovering another checkout's modules. The parent may place this report and evidence under `release/review` without moving the tests out of the documented layout.

The builder suite remains separately invoked through `release/run_checks.py`. Neither runner invokes inherited baseline suites or key-generating demos.

Exact commands and results are in `evidence/COMMANDS.md`; stdout/stderr logs and hash records are in the same evidence directory. All temporary mutation/relocation copies were removed normally after their checks. The original candidate and prior artifacts were left in place.
