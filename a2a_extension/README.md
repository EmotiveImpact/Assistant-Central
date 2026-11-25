# Assistant Central A2A extension

Lets any A2A 1.x agent take part in Assistant Central missions, so the consent and contract layer works where business-facing agent protocols already live.

- **Declare it.** `agent_card(name, url, receipt_key_ids)` builds an Agent Card whose capabilities list the extension `https://github.com/EmotiveImpact/Assistant-Central/a2a/missions/v1` (optional, not required), with the owner's receipt key ids as parameters. `supports_missions(card)` checks a peer's card.
- **Send it.** `mission_message(mission_id, kind, payload)` builds an A2A message whose context id is the mission and whose single part is structured data of one kind: `card`, `receipt` or `message`.
- **Receive it.** `read_mission_message(message, mission_id, owner_keys)` refuses anything for another mission, anything with free text parts, an altered card (fingerprint check), an unlabelled chat message, or a receipt not signed by the owner who took the step. What it returns is untrusted data.

Built on the official `a2a-sdk` (Apache-2.0, pinned to 1.3.1) and on `mission_cards/`. No transport or server is included; any A2A client or server can carry these messages.

```sh
pip install -r a2a_extension/requirements.txt
python -m unittest a2a_extension.tests.test_missions
```
