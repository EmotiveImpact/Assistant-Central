# Supported agent bridge work notice

Coordination only. No working integration is claimed by this first commit.

- Coordinator: Assistant Central supported-agent-bridge worker.
- Base: main at 30627d80619a58c55622af23a0b46fbfc7b5e7ac.
- Goal: a narrow, authenticated host-bound MCP adapter with deterministic
  integration evidence from two official agent-host SDKs, not raw model wrappers.
- Claimed scope: new `agent_bridge/**` and
  `.github/workflows/agent-bridge.yml` only. No active pilot, server, UI, runtime,
  provider, transport or frozen-prototype changes.
- Dependencies: independent of current signed-grant, receipt-recovery,
  owner-interface and network-harness PRs. Future composition requires a separate
  reviewed owner-authorisation integration.
- Verification planned: strict schema, trusted identity/routing, idempotency,
  isolation/revocation, audit limits, actual MCP transport and official host SDK
  execution using explicitly labelled deterministic model doubles.
- Limits: no credentials, paid/live calls, public endpoints, existing personal
  assistant activation, or automatic owner consent. This worker will not merge.
