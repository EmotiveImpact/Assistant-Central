# Work notice: owner mission approvals over MCP 2026-07-28

Coordinating agent: Claude (research thread "Research new ideas for Assistant Central"), working for Edem.

## Goal

A spike where an owner reviews and decides on an incoming mission offer inside an MCP host such as Claude, using the MCP 2026-07-28 specification. The server shows the exact offer it holds and asks for a decision with an input-required round (elicitation), and the decision is bound to the offer's digest.

## Boundaries

- Base: `main` at `03cc4cd`. Branch: `claude/project-thread-w0c2ja`.
- Claimed files: `mission_approvals/` only. No changes to existing files, CI, licence files or the README. The open-source preparation thread owns those.
- An MCP elicitation answer is host-mediated input. It is not cryptographic owner consent and grants no execution, release, disclosure or payment authority.
- No live provider, peer transport or real personal assistant is activated.
- Reuses `pilot.mission.terms` and `pilot.crypto.digest` so offer shapes match the existing direct-offer format.

## Planned verification

Offline unit tests using the official Python MCP SDK (`mcp==2.3.0`) in-process client pinned to protocol `2026-07-28`, covering accept, owner refusal, dismissed prompts, changed offers, expiry, repeat review, clients without elicitation and hostile peer text.

## Status

First commit contains this notice only.
