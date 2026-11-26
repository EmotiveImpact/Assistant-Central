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

- Base: `main` at `dff318b` (after #49). Branch: `claude/project-thread-sfa2x7`.
- Claimed files for this pull request (questions on the owner's phone):
  new `owner_phone/runner.py`, small changes to `owner_phone/telegram.py` and
  its README, `workspace_ui/approval_service.py`,
  `workspace_ui/conversation_service.py`, `workspace_ui/server.py`, new
  `workspace_ui/phone.mjs`, `app.mjs` and `style.css`, their tests, and the
  workspace workflow's Node test list.
- No licence or README changes at the repository root. No new hosted
  resources: the host brings their own Telegram bot token, and nothing runs
  unless the host names a phone mode in its private configuration.
- The phone only answers questions an assistant has already asked. It never
  agrees to work, releases a packet or reads anything else.

## Planned verification

- Python tests over real HTTP with a fictional bot that never reaches the
  internet: pair from Parlu, the pairing message from the phone, a question
  sent once to the paired chat, a tap answering it, unpairing, a missing bot
  token reported plainly, and other local accounts refused.
- Node tests for the panel's status checks and the Telegram start link.

## Status

Merged: invite links with QR pairing (#48) and removing an assistant (#49).

In this pull request: questions on the owner's phone.

- `GET /api/approvals/phone`, `POST /api/approvals/phone/pair` and
  `POST /api/approvals/phone/unpair` for the person who runs this copy of
  Parlu.
- A background runner long-polls Telegram while Parlu is open, sends each new
  question once and takes answer taps, backing off when Telegram cannot be
  reached.
- App: "Questions on your phone" in Settings, with a QR code and an "Open
  Telegram" link for pairing, and Unpair.

Next: team mission records (per-part rules, merge approvals, access grants and
compute spend).
