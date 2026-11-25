# Mission cards

Keeps every owner's written requirements in view from the first draft to the final acceptance, so separate assistants working on one job cannot quietly drop one person's constraints.

## How a card moves

1. **Drafting.** Each owner adds their own constraints, as "must" or "must not" (`card.py`).
2. **Agreed.** Every owner acknowledges the exact card by its fingerprint. Adding a constraint clears all acknowledgements, so nobody is held to text they have not seen.
3. **Delivered.** The delivery must list every constraint by id as met or not met, with a note. A delivery that skips one is refused.
4. **Accepted.** Every other owner accepts. If one of your own constraints was reported as not met, you must waive it explicitly or return the delivery for changes.

## Activity log

Each step is written to an append-only, hash-chained log anchored to the mission (`log.py`). Events naming any other mission are refused, which closes the route where a peer's assistant slips instructions for some other task into a conversation. `verify_chain` checks a copy is complete, in order and unaltered. `list_activity(after)` is the plain read API for other views such as the workspace timeline; records marked `untrusted` were written by other people.

## AI label

Every message an assistant sends is wrapped by `label.py` with a human-readable disclosure ("Written by Sam's AI assistant") and a machine-readable `ai_generated` marker, as EU AI Act Article 50 expects. The log refuses unlabelled messages and messages labelled for a different owner.

## Inside the assistant

`tools.py` registers MCP tools on any `MCPServer`, for example the one from `mission_approvals.server.build_server`. Adding a constraint, acknowledging a card and accepting or returning a delivery go through an elicitation round (MCP 2026-07-28), so only the owner can take those steps.

## Limits

- The host decides who is speaking: it must authenticate the sender before posting to a log. Approvals are host-elicited, not signed by an owner-held key yet.
- State is in memory; there is no persistence or network transport here.

## Tests

```sh
pip install -r mission_approvals/requirements.txt cryptography==50.0.0
python -m unittest mission_cards.tests.test_cards mission_cards.tests.test_tools
```
