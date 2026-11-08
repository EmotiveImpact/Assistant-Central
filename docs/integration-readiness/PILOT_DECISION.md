# First real integration: decision and acceptance procedure

8 November 2026. This is preparation around the unchanged r5 release, not a new demo checkpoint. No host, provider or peer was contacted; no active configuration, account, credential or installation was changed.

## The smallest useful decision

**Which already-installed assistant and computer should be the first pilot?**

Choose one existing installation, not a new account. If both are already available on a suitable machine, prefer Claude Code for the first session: its documented legacy-protocol selection, strict session MCP configuration and builtin-tool restriction fit r5. Native Codex has explicit MCP tool filtering and prompt approval, but those server settings alone do not establish restrictions on its other native tools. Do not install Claude merely to follow this conditional preference. Hermes is plausible but needs its actual release/SDK and roots policy resolved first. A native Windows-only setup cannot run the current POSIX-only launcher unchanged.

The decision is host plus machine. After selection, establish its exact build, compatible Python, configured provider label and effective permissions without reading credentials. A separate approval can then name the precise temporary configuration and synthetic host/provider interaction. Selecting a host alone does not authorize those actions or contact a model provider.

There is no verified existing user-side host installation in this evidence. The cloud workspace's tools are not evidence about the user's native machine. No further local packet parser or demo feature can settle that fact.

## What the next milestone would actually prove

One selected native host discovers and uses the reviewed three-tool server correctly, under its real approval and protocol behavior. It does **not** prove two-owner identity, inter-agent networking, a relationship directory, signing authority, peer delivery or background wake.

The server already exists: r5 `launcher.py`, SHA-256 `4df94f7f454989f864ac327da182b1054fff8952e4288915cb988fe891529571`. The full archive is `agent-network-synthetic-stdio-experimental-r5.zip`, SHA-256 `050d8d91a06f683a40d7ef7b9ab76e7f46238e2db8313b106bf6b353abef2d88`. Its 39 checks are local synthetic/SDK evidence, not native acceptance. Do not repeat or enlarge that count to imply broader integration.

## Activation gates, in order

1. **Target:** identify exact product/build, OS/machine, existing provider label and human approver. Current executable requirements are Python 3.12, POSIX, `-I -B`, no application arguments and FIFO stdin/stdout pipes. Confirm the host can launch that contract. A terminal, regular-file redirection or cloud-plugin URL is not interchangeable.
2. **Runtime:** verify archive/source integrity and the target's actual dependency set. The accompanying inventory captures the tested Linux environment; it is not a portable wheel lock or clean-install result. If dependencies are missing, stop for approval of the exact isolated environment and official package sources. Do not modify a shared environment as a shortcut.
3. **Policy/configuration review:** use an inactive draft outside watched/active configuration. Verify the proposed server alias is unused. Preserve unrelated settings. Exactly three tools must be available from this server; unrelated host tools must be disabled or withheld using controls actually supported by that build. Prompt instructions alone are not containment.
4. **Approval:** name the host agent and machine, exact executable/runtime, configuration scope, fictional prompt/tool calls and provider-visible information. The host/provider may see the prompt, schemas, arguments, results and ordinary session metadata. Unexpected authentication, installation, legal terms, persistent access or security changes are new gates.
5. **Native acceptance:** use the short procedure below. Stop on protocol, policy, logging or restart surprises. Do not weaken a control, silently change a version or auto-replay to produce a green result.
6. **Rollback:** remove or restore only the exact approved pilot entry/session configuration. An isolated disposable environment can be removed only under its approved cleanup scope. Provider history, crash reports and backups are separate. No accounts, keys or remote grants should have been created in this stage.

## Inactive profiles

The `inert-profiles` directory contains syntax-checked drafts, not installed settings. Absolute executable paths are deliberately nonexistent placeholders. The native Codex draft additionally has `enabled = false`. Claude's draft has no invented disabled flag and must stay outside active configuration until explicitly reviewed and approved.

- **Native Codex:** the draft uses the documented exact three-name `enabled_tools` list and prompt approval mode. Local desktop/CLI/IDE configuration can be shared. No documented protocol-version override was verified for this host; actual legacy negotiation must pass before any tool call. Do not invent a switch to make it pass.
- **Claude Code:** the server entry points to the Python interpreter with `-I -B` and the launcher path as an argument. A separate permissions draft asks for each of the three names under the selected alias. Strict MCP configuration and builtin-tool restriction are host-side controls to verify at activation. `--allowedTools` auto-approves and is not a filter. **`MCP_PROTOCOL_NEGOTIATION=legacy` belongs to the Claude host process, not the server's environment.** r5 clears its own environment; putting the option only inside the server entry would not select the host's negotiation behavior.
- **Hermes:** no activation profile is supplied yet because roots policy/release pairing remains unresolved. Do not convert that uncertainty into a guessed setting. Its startup/test/reload/watch behavior may execute or reconnect a server, so a draft must not be placed in an active profile.

These fields come from the official documentation review performed on 8 November 2026, not a newly tested host. References: [native Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Claude MCP](https://code.claude.com/docs/en/mcp), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Claude permissions](https://code.claude.com/docs/en/permissions), [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp). Exact effective syntax and policy must be reconciled with the selected build before activation. No new public-web or host call was made to create these drafts.

## One short native acceptance session

Use only the exact public fixture text:

> SYNTHETIC ONLY: Count three paper moons in the fictional garden. Do not send anything.

1. Observe a single server start and record the host build, runtime and negotiated legacy protocol. Discovery must show exactly `propose`, `proposal_status`, `processed_inbox`, without extra resource/prompt/event wrappers. Unexpected callbacks or capabilities fail this gate.
2. Read `processed_inbox({})`: require `publication: 0`, `items: []` and `No trusted local snapshot published.` This is an unpublished inbox, not evidence that a peer was checked.
3. With the human approval prompt visible, call `propose` with the exact text above once. Require `pending`, `local unsigned proposal`, and null operation/command/message/packet fields. Do not call this a send, approval or delivery.
4. Read `proposal_status` for the returned ID. Its exact pending view must agree. A separately approved same-text call with a fresh JSON-RPC ID should return that same proposal, only while the same store is alive.
5. Attempt one harmless text variant and one unavailable owner operation through the reviewed test procedure. Require rejection without authority access. Never use real personal data or a secret as a rejection test.
6. Separately verify a human-denied proposal call is not dispatched. Host UI text or an unknown status alone may be insufficient: if the server restarted, fresh empty state cannot prove nonexecution. Require reliable host/operator evidence that the call was denied before dispatch and the same server instance remained live; otherwise record this case as **unverified**, not passed. Do not add a privileged debug tool merely to manufacture evidence.
7. End before idle/record budgets become relevant. Record whether the host attempted reconnection/restart. Never infer recovery from a new empty store. Stop at an ambiguous result; inspect a known proposal ID only if the same store is still live, and never automatically replay an uncertain operation.

The attached `acceptance-record.json` is an empty result template. Every case is NOT RUN. It contains no approval and must not be filled with inferred successes.

## Stop conditions that need a decision, not more offline demonstrations

- No compatible existing host/runtime: choose a different existing target or approve a specific isolated installation.
- Host requires unsupported MCP negotiation or its native transport is incompatible: record the exact build/response; decide on a narrowly scoped adapter change rather than relabeling r5.
- Native permission/logging/restart behavior cannot establish the required boundary: keep the result unverified and review that behavior before expanding scope.
- Proposed next step includes real owners, keys, transport or wake: use a separate two-owner design and authorization. Local tool approval is not owner identity or permission to send information to another agent.

The additional peer-process concurrent-shutdown/descriptor-lifecycle review remains uncompleted and excluded. This procedure does not retry it or claim it is cleared.
