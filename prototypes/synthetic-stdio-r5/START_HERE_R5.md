# Synthetic stdio pilot r5

**An actual local MCP stdio launcher now works with synthetic clients. It has not been connected to a native assistant or model provider.**

This additive checkpoint preserves the earlier experimental r4 inside `baseline_r4/`. Earlier releases and the minimal-pilot planning bundle remain unchanged. Start here rather than interpreting an older nested report as the current release status.

## New evidence

- **39 checks pass:** 20 implementation checks and 19 independent checks. Only r5 tests were run; the earlier r4's 180 checks are historical unchanged evidence, not additional checks run for this release.
- Actual local subprocess stdin/stdout and the installed MCP SDK's `stdio_client` + `ClientSession` both complete the three-tool flow. An independent local client also verifies all four legacy protocol versions from 2024-11-05 through 2025-11-25.
- Independent review found no blocking defect in the assessed application/stdio scope. Its report and evidence are in `review/`. That is not a security certification or native-host acceptance.
- Source-integrity, exact-text restriction, partial-write handling, fixed diagnostics and conservative uncertain-outcome behavior are tested. Runtime source checks pin the baseline's 67 manifest-referenced files and the public fixture. All 128 inherited r4 files remain byte-identical.

## What the launcher permits

Only `propose`, `proposal_status`, and `processed_inbox`, bound to one fictional actor/task and public RFC test descriptors. The sole allowed proposal text is:

> SYNTHETIC ONLY: Count three paper moons in the fictional garden. Do not send anything.

The proposal stays unsigned and `pending` in SQLite memory. Exact replay within that same store returns the same record. The inbox remains empty with publication 0: no trusted snapshot was published. No Identity, Endpoint, owner-review or publisher object, private key, signing, owner release, peer address or delivery exists in this composition. Dormant definitions are loaded; this is not module or OS isolation.

Other text cannot become a proposal, but rejected bytes can transiently enter parser memory. The frozen tool schema is generic and does not advertise this extra one-text restriction. Do not send real data, even to test rejection.

## Reproduce only the offline checks

With the existing compatible dependencies and Python 3.12 on POSIX:

```sh
/path/to/existing/python -I -B /absolute/path/to/agent-network-synthetic-stdio-r5/run_all_checks.py
```

No installer, host configuration or network listener is included. `launcher.py` itself accepts no arguments and requires FIFO stdin/stdout pipes, not a terminal or regular-file redirection. See `README.md` for its exact contract, required versions and exit codes. The process uses local asyncio wakeup sockets; no network connection or listener is used. Windows and native macOS/desktop-host behavior remain untested.

## Important limits

The launcher never restarts or replays an uncertain operation. A partially written output may be truncated, and OS pipe acceptance is not proof that the client read it. The 300-second per-read inactivity timeout is not a session deadline. Closing or restarting destroys proposal history and cannot resolve a previously unknown outcome. A native host might independently restart a server; that behavior must be checked separately.

Python guards, environment clearing and isolated interpreter flags are defense in depth for trusted code. The interpreter, installed packages/startup hooks and source directory remain trusted. There is no race-safe filesystem sandbox, complete dependency lock, hard CPU bound, lossless shutdown guarantee, persistent recovery or production security claim.

The additional peer-process cross-lane concurrency/shutdown/descriptor-lifecycle review remains uncompleted and excluded. None of these tests revisit it. No peer processes, key-generating inherited demos, native hosts, model providers, credentials, installation or active configuration were used.

## Next decision

Choose the exact existing host, machine/OS and model/provider. Then review its actual build, protocol, temporary configuration, permissions and restart/logging behavior before approving a synthetic native trial. Native Codex and Claude Code have documented stdio paths; Hermes remains an option with unresolved release/roots-policy questions. Local native MCP is not dot's cloud-plugin integration.

`SETUP_AND_ROLLBACK.md` provides the clean-environment and exact-entry rollback checklist. Those steps are future decisions, not changes already made. The chosen host/provider may see the fictional prompt, schemas, arguments and results.

This proves one host-to-local-tool layer, not the broader relationship network. Real owner authentication, key custody, persistent identity, named-peer enrollment/transport, multi-task permissions, cancellation and wake still require separate design, review and authorization.
