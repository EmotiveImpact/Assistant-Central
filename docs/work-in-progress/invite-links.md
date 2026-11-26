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

- Base: `main` at `538f969` (after #48). Branch: `claude/project-thread-sfa2x7`.
- Claimed files for this pull request (removing an assistant):
  `pilot/server.py` (the revoke route), `pilot/runtime.py` (a rejection for a
  removed sender stays local), `pilot/relay_link.py` (closing relay tokens),
  `workspace_ui/relay_service.py`, `workspace_ui/app.mjs` and `style.css`
  (the Remove section), and their tests.
- No licence or README changes. No new hosted resources. The relay database
  schema does not change.
- The relay stays a mailbox. Removing someone never deletes history, and it
  never sends anything to the removed person.

## Planned verification

- Python unit tests over a real local relay: removing a linked person closes
  their send token; a close the relay missed, or refused, is kept and finished
  on a later sync; a removal made while Parlu ran without a relay is closed on
  the next sync; work from a removed person can still be rejected, locally.
- Workspace route tests for the revoke route with and without a relay.
- The Chromium test adds Maya through an invite link and then removes her
  assistant through the folded, two-step Remove section.

## Status

Merged: invite links with QR pairing (#48).

In this pull request: revoking an assistant from the app.

- `POST /api/peers/<fingerprint>/revoke` on the owner server. A revoked pin is
  final and cannot be added again, nor can a new key with the same owner and
  assistant names.
- With a relay, the same route also closes that person's relay token. If the
  relay cannot be reached or refuses, the close is kept and finished on the
  next sync. Each sync also closes tokens for anyone removed while the relay
  was off.
- A proposal still waiting from a removed person can be rejected; the
  rejection is recorded locally and nothing is sent.
- App: a folded Remove section on each assistant's panel, with a hold and a
  plain button.

Next: phone questions in the app, then team mission records (per-part rules,
merge approvals, access grants and compute spend).
