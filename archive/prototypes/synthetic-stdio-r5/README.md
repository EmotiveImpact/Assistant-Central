# Synthetic-only stdio pilot r5

**An actual local stdin/stdout launcher, tested only with synthetic local clients. No native host acceptance, installation, host configuration, provider call or peer exchange is claimed.**

This is one host-to-tool path for the broader cross-provider relationship-based assistant experiment. It does not replace a host's provider selection, make a scheduling product, or add a provider router. There is no model/provider selector in this launcher.

## What is implemented

Actual POSIX pipe bytes → unchanged r4 `RawBridge` → unchanged r3 `OfflineBridge` → exact frozen `AssistantFacade` instance → `ProposalStore(':memory:')`.

The only tools remain `propose`, `proposal_status`, and `processed_inbox`. The fixed fictional actor is `alice`. The store starts empty, with publication 0 and no published snapshot. No owner, publisher, identity or endpoint object is constructed. Dormant owner and crypto definitions load from frozen code, with guarded constructors/key-generation/import methods. This is trusted local composition, not authority or module isolation.

The r3 bridge requires the exact `AssistantFacade` type, so a wrapper object or subclass cannot be supplied without changing frozen code. Instead this launcher narrows **only the constructed instance's `propose` entry point** with a closure. That closure checks exact argument shape and an exact one-element public-fixture text allowlist before invoking the original bound method. No frozen source is edited.

The sole allowed text, with no leading/trailing whitespace, is:

> SYNTHETIC ONLY: Count three paper moons in the fictional garden. Do not send anything.

The exact tool argument is `{"text":"SYNTHETIC ONLY: Count three paper moons in the fictional garden. Do not send anything."}`. The frozen generic tool schema does not advertise this extra restriction. Other text gets a fixed tool error and does not reach the facade's write method. Callers can still submit arbitrary bytes to stdin: rejected bytes can transiently enter bounded parser memory. The allowlist is a storage/processing restriction, **not a guarantee that every input is synthetic or that the input never entered process memory**. Input and exception text are not logged.

The public fixture is copied unchanged from the preparation artifact. Its public key descriptors are publicly known RFC test vectors, unsuitable for real identities; no private vectors or keys are included or generated. They are only binding data in this run.

## Run the targeted local checks

Use the already installed Python 3.12 environment with existing dependencies. Nothing here installs anything:

```
/path/to/existing/python -I -B /absolute/path/agent-network-synthetic-stdio-r5/run_checks.py
```

`run_checks.py` discovers only `tests/test_launcher.py`. It does **not** run inherited r1/r2/r3/r4 runners, peer processes or their lifecycle suites. These 20 checks cover a real pipe subprocess and a real SDK `stdio_client` + `ClientSession`, along with synthetic reader/writer seams and startup integrity failures. SDK client acceptance is not acceptance by a native host or provider.

The fixed launcher command itself is:

```
/path/to/existing/python -I -B /absolute/path/agent-network-synthetic-stdio-r5/launcher.py
```

It accepts **no arguments** and requires pipe stdin/stdout, Python 3.12, `-I`, `-B`, and POSIX. Running it directly in a terminal or with redirected regular-file stdin/stdout is intentionally rejected. Windows/native-host portability has not been established. A local subprocess client supplies the pipes. `SETUP_AND_ROLLBACK.md` documents a later decision, not setup already performed.

## Integrity, environment and diagnostics

Before frozen imports, the launcher checks the r4 manifest SHA-256 `ded41439c7fe7a35370019b30fcbb6a773bcd82e67de1f406a98104c2fb7d71c`, all 67 referenced files, resolved-path containment, and public fixture SHA-256 `2a6d3fef6cb8e9f88838a0cdd42cb4822d9e46311b113d85205f75e3eac37869`. It rejects symlinks and unmanifested Python/extension module files anywhere in the baseline import tree. Extra documentation/evidence files are not executable inputs. These checks require a trusted, nonconcurrently-modified directory; they are not a race-safe filesystem sandbox or a signature of the launcher itself.

The launcher's process environment is cleared before its third-party imports. `-I` ignores Python environment injection and user site packages, and `-B` prevents bytecode writes. Python's interpreter, installed site packages and earlier startup hooks are still trusted. MCP is checked at exactly 1.29.0. The tested dependency versions are in `EVIDENCE.md`; this is **not** a complete lockfile or supply-chain validation.

Protocol stdout uses only the frozen encoder and explicit `os.write` through the whole-message adapter. Python stdout/stderr objects are discarded, logging is disabled before dependency imports, and Python warnings are suppressed. Failures emit at most one short fixed best-effort stderr diagnostic. Stderr pipe writes are nonblocking. This controls trusted Python diagnostics, not adversarial native code writing directly to file descriptors.

## Byte I/O and uncertainty

Input uses nonblocking pipe reads and asynchronous readability waits, bounded at 4096 bytes per read. A 300-second inactivity timeout applies to one receive call, not the entire session or each completed JSON record. Slow trickle input can extend the session; no hard wall-clock or CPU bound is claimed.

Output uses nonblocking writes with a 10-second asynchronous timeout. Partial success advances the byte offset within the **same encoded reply**. A write that returns zero, an invalid byte count, or fails aborts the session. It never resends the prefix, retries an admitted tool operation, or starts another process. A partially emitted final reply can be truncated; the recipient must treat it as uncertain rather than as rejection. OS pipe acceptance is not client delivery or reading.

Frozen framing remains strict JSON/LF, with a 16,384-byte input-record cap excluding LF, a 32,768-byte output cap including LF, 160 raw-record and 128 safe-ID bounds. Complete-looking JSON without its final LF is not dispatched. Oversize input ends the session without draining. Malformed bounded records can receive fixed errors and allow later records until the budget. No cancellation, concurrent shutdown, descriptor-reuse, reconnect, lossless-drain, or OS-isolation claims are added.

Exit statuses:

- **0:** ordinary EOF. This does not mean every request succeeded, a proposal was delivered, or anything was sent to a peer.
- **64:** startup gate/integrity rejection (`SYNTHETIC_STDIO_STARTUP_REJECTED`).
- **65:** partial final record, oversized record, or record/message budget termination (`SYNTHETIC_STDIO_INPUT_TERMINATED`). Previously admitted proposals may already have existed in memory.
- **70:** local runtime failure (`SYNTHETIC_STDIO_LOCAL_FAILURE_OUTCOME_UNCERTAIN`). Any exception escaping after runtime entry is conservatively classified here, even if it happened before admission.
- **74:** output failure (`SYNTHETIC_STDIO_OUTPUT_FAILURE_OUTCOME_UNCERTAIN`). A whole reply or prefix may already have been written.
- **75:** idle receive timeout (`SYNTHETIC_STDIO_IDLE_TIMEOUT_OUTCOME_UNCERTAIN`). Earlier operations are not undone.

Normal interpreter/process exits outside the handled Python path, such as a forced OS kill, need not use these codes. Failed diagnostics can be absent or partial. There is no auto-restart. Closing the in-memory database loses records. Restarting with a fresh empty store cannot resolve an old uncertain outcome and is not evidence of nonexecution or safe replay.

## Offline scope and exclusions

An audit guard denies process creation, nonmemory SQLite databases, and audited socket activity except CPython asyncio's local AF_UNIX/SOCK_STREAM wakeup-socket creation. **Local wakeup sockets exist; zero-socket execution is not claimed.** No network connection/listener, browser, host CLI, host/provider configuration, auth/credential lookup, identity enrollment, persistent key, external agent/provider communication or peer process is used by the launcher.

Import guards deny the endpoint and peer transport modules. The additional peer-process cross-lane concurrency/shutdown/descriptor-reuse audit remains excluded and uncompleted. Its fixture, pipe and worker internals were not inspected or executed for this work. Their frozen bytes are only copied and hashed as opaque baseline inputs. Existing reports/archives and both source input trees remain unchanged.

Python guards and exact allowlisting protect this particular trusted composition. They are not a malicious-code sandbox. This pilot proves only local synthetic client → MCP tool compatibility and exact local proposal/status/empty-inbox behavior. A later native trial needs separate approval and must keep fake data only; an actual host/provider can see prompts, tool schemas, arguments and results.
