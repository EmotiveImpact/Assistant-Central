# Agent network: integration readiness

8 November 2026. This pack turns the remaining integration and security gaps into decisions and an acceptance procedure. The frozen r5 runtime is unchanged. No native host, provider, account, credentials, live peer, installation or active configuration was used.

## What changed our understanding

**The encrypted packet is not the entire privacy boundary.** A future relay that sees both a complete signed grant and a clear receipt can verify guesses for short encrypted request text using the receipt's plaintext digest. This requires those specific objects to be visible; it is not general decryption, a cipher break or an exploit against the current trusted offline supervisor. The exact static field derivation and source lines are in [the peer security review](agent-network-peer-security-readiness.md).

Before claiming relay privacy, treat grants and evidence as potentially content-revealing. Keep them in an appropriately confidential authenticated control/evidence channel, end to end where the relay must not see them. Do not remove the receipt bindings or invent a replacement crypto scheme as a shortcut. A fully public-synthetic pilot may permit a chosen service to see everything, but cannot claim to validate private relay operation.

**Endpoint authentication is not human approval.** Signatures bind configured keys and protocol domains; they do not establish whose keys were configured, whether a human approved a disclosure, or whether a model really performed work. The two-owner pilot needs independently controlled local approval, verified complete session descriptors and explicit visibility/retention choices. Two providers or two processes alone do not supply that.

**Runtime reproduction is more specific now.** The installed declared dependency closure contains 29 distributions and 47 active requirement edges, with no missing package or version/Python constraint conflict on this Linux/Python 3.12 environment. The [exact observed pins and inventory](runtime-dependencies/README.md) are not a wheel-hash lock, clean-install result or a portable target guarantee. No dependencies were installed.

## The next useful decision

**Which already-installed assistant and computer should be the first pilot?**

If both suitable installations already exist, Claude Code offers documented legacy negotiation and session-level MCP/builtin controls that fit r5. Native Codex is also a candidate with explicit MCP tool filtering and prompt approvals. Do not install another product just to follow that conditional preference. Hermes still needs its actual release/SDK and roots behavior established. Current r5 requires Python 3.12/POSIX pipes; Windows-native acceptance is not available.

[PILOT_DECISION.md](PILOT_DECISION.md) gives the exact selection, approval, native acceptance and rollback gates. The syntax-checked drafts in `inert-profiles/` have nonexistent executable placeholders; the Codex draft is additionally disabled. None was placed in active settings. `acceptance-record.json` has every native case marked NOT RUN.

Two practical details prevent misleading success:

- Claude's legacy-negotiation setting belongs to the **host process**, not the cleared environment of the MCP server.
- An unknown proposal after a host restart does not prove a denied call was never dispatched. Require reliable same-instance/denial evidence or leave that native case unverified.

## What is ready, and what is not

- Ready for a target decision: reviewed r5 synthetic stdio artifact; concrete inactive profiles; fixed fictional payload; native acceptance record; conditional privacy finding with source evidence; current-platform dependency inventory; two-owner pilot contract in the security review.
- Still unresolved: the actual user-side host/build/machine/provider; target package artifact provenance and clean reproduction; native approval/protocol/restart/logging behavior; real owner/key provenance; authenticated local owner controls; exact transfer channel and visibility. These are actionable gates, not missing demo test counts.
- Broader network work remains separate: persistent identity/recovery, relationship and multi-task permissions, interoperable peer wire, distribution/hosting, cancellation and wake. Using two providers with the same experimental peer implementation is not A4A interoperability or arbitrary-agent networking.

The additional peer-process concurrent-shutdown/descriptor-lifecycle review remains uncompleted and excluded. This work neither repeats nor clears it. Previous source and archive hashes were checked unchanged.

## Files

- `PILOT_DECISION.md`: first-host decision, precise conditions and acceptance procedure.
- `inert-profiles/`: inactive Codex/Claude drafts; syntax checks are not host-schema or runtime validation.
- `acceptance-record.json`: future native result template, not authorization.
- `agent-network-peer-security-readiness.md`: source-based privacy, identity, consent and interop assessment plus the smallest two-owner pilot.
- `agent-network-peer-security-readiness-inputs.sha256`: 23 frozen review-input hashes.
- `runtime-dependencies/`: scoped metadata inventory and observed pins, not an installer.
- `draft-validation.json`: limited JSON/TOML/static-draft validation.
- `READINESS_MANIFEST.json`: hashes for this new pack, not a signature or execution approval.
