# Mission approvals (spike)

An MCP server that lets an owner review an incoming mission offer from inside their own assistant, using the MCP 2026-07-28 multi round-trip elicitation flow.

## What it does

- `list_mission_offers` lists offers with sender, goal and status. Sender and goal are marked as written by the other person.
- `review_mission_offer` shows the owner the exact stored offer, with peer text fenced between markers and control characters removed, then asks them to accept or decline and to type an eight-character confirmation code taken from the offer's digest.
- The decision is recorded once, bound to that digest. If the offer changes or expires while the owner is looking at it, nothing is recorded.

## What it does not do

- The decision is host-elicited input, not a cryptographic owner signature.
- Accepting grants no authority to run the mission, release a result, disclose a provider or spend money. Each of those needs its own approval.
- There is no live provider and no persistence yet; the inbox is in memory.

## Running the tests

```sh
python -m venv .venv && .venv/bin/pip install -r mission_approvals/requirements.txt
.venv/bin/python -m unittest mission_approvals.tests.test_review
```

The tests drive the server with the official MCP Python client pinned to protocol `2026-07-28` and a scripted owner, entirely offline.
