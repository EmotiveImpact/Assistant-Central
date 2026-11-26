# Synthetic stdio pilot: future setup and rollback

This is a decision checklist, not an installation already performed or permission to configure a host. The current work uses a local synthetic client only. No Claude, Codex, Hermes, dot, model provider, account or live peer was contacted.

## Current executable contract

The launcher requires an existing **Python 3.12 on POSIX**, interpreter flags `-I -B`, no application arguments, and FIFO pipes for stdin and stdout. Its invocation is the selected Python executable followed by `-I -B /absolute/path/to/launcher.py`. It is not an interactive terminal program, a regular-file filter, an HTTP server or a Windows-supported build. Do not use shell redirection to a regular file as a substitute for its pipe contract. A native host must actually supply compatible stdio pipes.

The offline test runner is `python3.12 -I -B run_checks.py` from the release directory. It uses local synthetic clients, not a native assistant or model. These commands are an execution contract for review, not commands run on a user's machine by this document.

The tested dependency versions are MCP 1.29.0, AnyIO 4.14.2, Pydantic 2.13.4 and cryptography 50.0.0, on Python 3.12.14/Linux. The launcher rejects an MCP version other than 1.29.0. This is not a full transitive lock, an installer or a guarantee for another platform.

## Choose the target before changing it

1. Identify the exact existing host product/build, machine/OS and model/provider. Native Codex, Claude Code and Hermes are different integration surfaces; a cloud Codex binary is not evidence of a user's native configuration. Local stdio does not connect this server to dot's cloud plugins.
2. Name the operator who can approve tool calls. Agree the exact fictional prompt/tool interaction, configuration scope, model-provider visibility and retention. The host may send synthetic prompts, schemas, arguments and returned results to its model provider.
3. Check the chosen host's current official documentation and effective policy. Do not assume that the documentation checked on 8 November 2026 matches an installed build. Do not bypass prompts, use broad auto-approval or change security settings to make the trial pass.

## Prepare a clean runtime after approval

- Keep this release and all earlier releases in separate directories. Verify the release manifest and its pinned frozen baseline and public fixture before execution. Do not repoint an active server at a mutable development checkout.
- Prefer an existing compatible Python environment for an initial acceptance check. If a new isolated environment or package installation is needed, approve the exact official package sources and dependency set first. Nothing in this document installs them. Do not alter system Python or unrelated project environments.
- The tested runtime versions are evidence for this environment, not a complete transitive dependency lock or a Windows/macOS compatibility claim. A clean target needs its own reviewed lock and repeat of the included synthetic checks before connecting a native host. A version mismatch must not be hidden by changing a constant.
- Use a dedicated empty working directory and an explicit minimal subprocess environment. The launcher must not receive credentials, real data, unrelated handles or owner controls. Interpreter isolation and clearing environment variables reduce accidental inheritance; they are not an OS sandbox and do not prevent same-user filesystem access.
- The server has a fixed public fixture, exact proposal-text allowlist and in-memory store. It has no private-key, Endpoint, owner-channel, peer-address or relay configuration. Do not add such parameters to fit a host.
- Run only the documented synthetic checks first. Do not use a host's MCP test/reload command as a harmless YAML validator: it can execute the server. An inactive review file outside active configuration is the safe place for a draft.

## Future host-specific configuration review

Use the exact launcher invocation from the release's main README, including required interpreter flags. All host paths below are review targets, not settings touched by this work.

- **Native Codex:** local desktop/CLI/IDE may share configuration. Review the exact configuration file and any existing entry before editing. The documented `enabled_tools` list should contain only `propose`, `proposal_status`, `processed_inbox`; use prompt approval mode, not auto-approval. A disabled draft remains outside active settings until approval. Verify the selected build supports the syntax.
- **Claude Code:** prefer a temporary interactive session with an explicit strict MCP configuration and built-in tools disabled where supported. `--allowedTools` auto-approves calls and is not an exposure filter. Review exact permission ask rules and effective managed rules/hooks. Legacy negotiation is a documented protocol choice but still needs acceptance; do not use a security bypass or pretend MCP2026 is supported.
- **Hermes:** exact tool inclusion, resource/prompt wrappers off, sampling/elicitation off, untrusted trust level and normal approvals. Do not invent a roots-disable setting. Pin and verify the actual release/SDK behavior first. Configuration reload/watchers may launch or reconnect automatically; stderr can be retained in profile logs.

Official references: https://learn.chatgpt.com/docs/extend/mcp?surface=cli ; https://code.claude.com/docs/en/mcp ; https://code.claude.com/docs/en/cli-reference ; https://code.claude.com/docs/en/permissions ; https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp . The earlier minimal-pilot planning bundle contains the detailed source review.

## Approve and accept a native session separately

Before launch, approve the exact host agent and machine, executable/source digest, temporary configuration change and listed synthetic calls. The selected provider may see the fictional interaction and session metadata. Any unexpected installation, authentication, new legal terms, persistent access, security setting or other tool use is a stop-and-decide point.

Record the actual host/build, runtime, negotiated protocol and exposed schemas. Require exactly three tools. Test the exact allowlisted text, pending status/replay and never-published empty inbox. Denied calls must not reach the server. Invalid text or owner operations must not create records. Protocol rejection or an unexpected method must not silently widen capability. The synthetic subprocess tests do not stand in for these native-host checks.

Keep the first session short and within the fixed record/ID limits. Verify the chosen host's reconnect/restart behavior rather than assuming that the launcher's lack of automatic restart controls the host. The launcher exits after a 300-second receive inactivity timeout; a host-driven restart would create a new empty store. Do not treat that as recovery or silently replay an uncertain call.

The text allowlist controls what can become a proposal. It cannot prevent a client from placing other bytes into stdin: rejected content may transiently enter parser memory. Never send real personal information or secrets even to test rejection. Keep stderr/transcripts free of input content, and inspect provider/host logging policies before the trial.

## Stop and roll back

1. Stop at an unexpected permission, protocol mismatch, leaked input, output contamination, unapproved tool invocation or ambiguous result. No automatic restart or replay. If a proposal may have been admitted but its response was lost, preserve uncertainty. A known ID can be inspected only while the same store remains alive.
2. End the one temporary server/session using the host's documented control. This is not a promise of lossless shutdown, remote recall or secure erasure. Closing the in-memory store loses history and cannot prove an earlier operation failed.
3. Restore only the exact pilot configuration entry/file from the pre-change snapshot, under the approved rollback. Preserve unrelated entries, managed policy and settings. If no active configuration was changed, no configuration rollback is needed.
4. Remove only the separately approved disposable pilot working directory or isolated environment. Do not delete earlier archives, shared packages, unrelated data or retained evidence. There should be no newly created keys, accounts or peer grants to revoke in this stage.
5. Retain the agreed minimal result record and any unresolved outcome. Local cleanup does not erase host/provider transcripts, crash reports, swap or backups. Follow their retention/deletion controls separately if needed.

No step here authorizes live peers, relationship enrollment, signing, owner release, a listener, a relay, events or wake. The excluded additional peer-process concurrent-shutdown/descriptor-lifecycle review remains uncompleted; neither this guide nor the launcher clears it.
