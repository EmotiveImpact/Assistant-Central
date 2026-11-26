# Work notice: invite links, then the remaining backend features

Coordinating agent: Claude (project thread "Build the backend for the remaining
features"), working for Edem. No other agents are assigned.

## Goal

Build the backend that the rebuilt app is waiting for, then wire each piece into
the app. In order:

1. **Invite links with QR pairing** (this pull request). One person makes a link
   in Parlu, the other opens it in their own Parlu, and both copies end up
   enrolled with each other and able to pass packets through the relay, without
   pasting fingerprints or using the command line.
2. Revoking an assistant, and pairing a phone for questions, from the app.
3. Team missions: per-part rules, merge approvals, access grants and compute
   spend.

Items 2 and 3 follow in their own pull requests from this same branch name.

## Boundaries

- Base: `main` at `b9221d8`. Branch: `claude/project-thread-sfa2x7`.
- Claimed files for this pull request: `relay/acrelay/protocol.py` (invite link
  version 2), `relay/acrelay/service.py` (invite page only), new
  `pilot/relay_link.py`, new `workspace_ui/relay_service.py`, new
  `workspace_ui/qr.mjs` and `workspace_ui/invites.mjs`, small additions to
  `workspace_ui/server.py`, `app.mjs`, `index.html` and `style.css`, their
  tests, and `docs/TWO_PEOPLE.md`.
- No licence or README changes. No new hosted resources. The relay database
  schema does not change.
- The relay stays a mailbox. It never sees an identity key, a join secret or a
  message, and nothing a relay says is treated as delivery or as a decision.
- Joining never accepts work. Each proposal still needs its own exact owner
  decision.

## Planned verification

- Python unit tests over a real local relay: make, open and accept an invite,
  the join packet, approval on the inviting side, a task carried there and a
  receipt carried back, a forged join, a reused link, an expired link and a
  revoked link.
- Node tests for the QR encoder against known-good symbols.
- The Chromium test drives two real copies of Parlu and one local relay.

## Status

First commit contains this notice only.
