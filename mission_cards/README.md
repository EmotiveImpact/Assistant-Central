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

## Signed receipts

`receipts.py` turns each owner decision or delivery in the log into an in-toto Statement v1 inside a DSSE envelope, signed with an Ed25519 key the owner holds. Any host or relay can carry the envelope, but only that owner's key verifies, so a host cannot fake anyone's yes. `matches_log` checks that a receipt names a step that is really in a given copy of the log. The encoders are written from the public in-toto and DSSE specifications; no code is copied.

## Passkey approvals

`passkey.py` lets an owner approve a step from their phone with a passkey. The WebAuthn challenge is the hash of that step's receipt statement, so the assertion approves exactly one step. `PasskeyRegistry.approve` follows the WebAuthn assertion checks for ES256: owner match, challenge, origin, RP ID, user presence and verification, signature and a forward-moving counter. `verify_receipt` re-checks a stored passkey receipt. Only `cryptography` is used.

## Mission budgets

`budget.py` lets an owner sign a spending mandate for one mission: payee, currency, total, per-charge limit, expiry and purpose, bound to the exact card version. `BudgetLedger` verifies the mandate against the owner's key and accepts a proposed charge only if it fits. No payment rail is involved, so a real one can be added behind the same check. The shape maps onto AP2 intent mandates and Verifiable Intent; no code is copied.

## Inside the assistant

`tools.py` registers MCP tools on any `MCPServer`, for example the one from `mission_approvals.server.build_server`. Adding a constraint, acknowledging a card and accepting or returning a delivery go through an elicitation round (MCP 2026-07-28), so only the owner can take those steps.

## Card view inside the assistant (MCP App)

`app.py` returns an MCP Apps extension (`io.modelcontextprotocol/ui`) with one display-only tool, `show_mission_card`, bound to `ui://assistant-central/mission-card.html` (`card_app.html`). Hosts that support MCP Apps show the card visually; others get the same content as text. The page inserts every value as text, never HTML, and has no buttons that commit anything, so acknowledging and accepting still go through the elicitation tools and their confirmation code. Use it with `MCPServer(name, extensions=[card_app(book, owner_id)])`. The browser check `tests/card_app_check.mjs` needs Playwright and runs locally; the postMessage method names follow the ext-apps draft and should be rechecked against a real host.

## Limits

- The host decides who is speaking: it must authenticate the sender before posting to a log. Elicited approvals in `tools.py` are not yet wired to receipt signing on the owner's device.
- State is in memory; there is no persistence or network transport here.

## Tests

```sh
pip install -r mission_approvals/requirements.txt cryptography==50.0.0
python -m unittest mission_cards.tests.test_cards mission_cards.tests.test_tools mission_cards.tests.test_receipts mission_cards.tests.test_budget mission_cards.tests.test_passkey mission_cards.tests.test_app
```
