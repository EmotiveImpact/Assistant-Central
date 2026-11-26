# Targeted evidence

- Date: 2026-11-08 UTC.
- Command: existing Python interpreter, `-I -B run_checks.py`.
- Result: **20 tests passed** in the recorded candidate run (see the test log for timing).
- `evidence/targeted-tests.stderr.log` is the unittest report. The unittest runner intentionally reports to stderr; the successful launcher itself has empty stderr.
- `evidence/targeted-tests.stdout.log` is empty.
- Python 3.12.14; MCP 1.29.0; AnyIO 4.14.2; cryptography 50.0.0; Pydantic 2.13.4. Existing dependencies only, no install. MCP alone is version-enforced by the launcher; tested versions are not a fully locked environment.

## What ran

Actual local subprocess stdin/stdout checks cover initialization at 2025-11-25, initialized notification, exactly three tools, the exact public-fixture proposal, exact pending fields, status, replay under a fresh request ID, an empty never-published inbox, arbitrary-text rejection, selector/owner-tool rejection, state errors, unknown methods, duplicate IDs, duplicate JSON keys, malformed UTF-8/JSON, notification silence, the input frame boundary, record budget, ordinary EOF, partial EOF, fixed startup diagnostics and required isolated/no-bytecode flags.

The SDK check uses the installed `mcp.client.stdio.stdio_client` and `mcp.ClientSession` to launch the actual script and exchange MCP over OS pipes. It verifies initialization, tools/list, inbox, proposal/status/replay and nonallowlisted rejection. This is not a native host or model/provider test.

Synthetic unit checks cover partial write offset advancement, transient interrupted/would-block writes, failure after a partial write without prefix replay, invalid write counts, reader EOF/contracts, bounded fixed diagnostics, exact allowlist rejection before its delegated facade method, guard event decisions, all pinned inputs, altered manifest/fixture rejection, unmanifested top-level import module rejection, symlink rejection, and conservative runtime-escape exit 70. They do not simulate or inspect excluded peer-process/descriptor lifecycle scenarios.

## Preserved inputs

`evidence/preserved-inputs-before.json` records full file hashes of the original r4 and public-fixture preparation roots before implementation. The launcher startup checks the 67 manifest-referenced frozen files and fixture on every run. The parent will independently verify preservation and any final package before delivery. No inherited test runner was executed.

## Limits

No native host, provider, peer, credentials, external account, install, deployment or configuration was used. No claim of zero sockets: asyncio may use local AF_UNIX wakeup sockets. No read of excluded fixture/pipe/worker implementation logic occurred; opaque copying/hashing does not review those internals. There is no new evidence about the excluded concurrency/shutdown/FD-reuse question.

No independently reviewed acceptance is claimed by this candidate evidence. Independent review findings should be recorded separately without rewriting earlier frozen reports.
