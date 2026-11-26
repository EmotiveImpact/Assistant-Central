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

- Base: `main` at `9e8c483` (after #50). Branch: `claude/project-thread-sfa2x7`.
- Claimed files for this pull request (team mission records): new
  `pilot/team.py` and its tests, the proposal checks in `pilot/runtime.py`,
  `workspace_ui/team.mjs`, `decide.mjs`, `app.mjs`, `index.html`,
  `style.css` and their tests.
- No licence or README changes at the repository root. No new hosted
  resources and no new packet type: team records ride inside ordinary signed
  proposals, so the relay and the trust rules stay as they are.
- Parlu runs no AI here. Each person's own assistant writes the part, the
  result and any access ask; Parlu only checks their shape and shows them.

## Planned verification

- Python tests over real relay packets: a part with rules and a compute cap,
  a result that must report on every rule, merge approval through the
  helper's release and the lead's acceptance, an access ask that only counts
  for an agreed part between the same two people, and forged or mismatched
  records refused on both sides.
- Node tests for reading and writing the records, the review rows and
  questions, and a two-person browser run from part to merge to access.

## Status

Merged: invite links with QR pairing (#48), removing an assistant (#49) and
questions on the owner's phone (#50).

In this pull request: team mission records.

- A team part carries its brief, rules (must and must not) and an optional
  compute cap.
- A returned result reports whether each rule was kept and what compute it
  used. Merging is the helper's signed release plus the lead's acceptance.
- An access ask names what, why and for how many hours, and is granted when
  the lead accepts it with a hold.
- App: rules, merge approvals, access and compute in the team view and the
  part panel, plus "Return the result" and "Ask for access" on an agreed part.
