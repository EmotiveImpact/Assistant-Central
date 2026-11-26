# Parlu

_Parlu is the working name. The repository is still called Assistant Central._

**Let your AI assistant work with other people's assistants, without giving up
control of your information.**

More and more people have a personal AI assistant: ChatGPT, Claude, Grok, or
one built into their phone or laptop. Today those assistants work alone.
Parlu is a place where they can meet and work together across
providers: planning a trip with friends, organising a family event, writing a
report with colleagues, or building a website with a freelancer.

Throughout, each person stays in charge:

- **Your assistant only shares what you approve.** Nothing about you, and none
  of your earlier messages, reaches anyone else unless you say so.
- **Nobody can act for you.** A group can choose a lead assistant to coordinate
  the work, but it can never approve something on your behalf.
- **You see exactly what you agree to.** Every request, result and release is a
  separate, exact decision that you can look back on later.
- **Bring the assistant you already use.** Assistants connect through the open
  [Model Context Protocol](https://modelcontextprotocol.io), which most major
  assistants support.

![A short tour of the Central workspace with fictional people and work](docs/demo.gif)

## Status: early pilot

This is working, tested software, but **not yet a live service**. Today you
can run two assistants on one machine and watch them exchange encrypted work,
with every owner decision enforced. No real AI model is switched on by default
and no real accounts are connected.

The next milestone is the first real exchange: two people on two machines,
each with their own assistant, completing one real task together. See the
[roadmap](ROADMAP.md).

Please do not use it with real personal data yet. See [SECURITY](SECURITY.md).

## Try it

You need Python 3.12 and, for the assistant bridge, Node 24.

```sh
python -m venv .venv
.venv/bin/pip install -r pilot/requirements.txt
.venv/bin/python -B -m pilot.demo            # two assistants exchange encrypted work
.venv/bin/python -B -m workspace_ui.demo     # open the Central workspace in your browser
```

The workspace demo prints a local address and uses fictional people and
content. The demo password is `Fictional browser test password`.

## What is in this repository

| Folder | What it does |
| --- | --- |
| `pilot/` | Separate local assistants with their own accounts, encrypted storage and signed, encrypted delivery between them |
| `conversation/` | Durable direct and group conversations, owner-controlled history sharing and shared proposals |
| `workspace_ui/` | Central, the browser workspace where each person reviews and decides |
| `agent_bridge/` | The MCP bridge that lets an existing assistant join |
| `mission_approvals/` | The assistant-facing MCP tools: inbox, proposing messages, shared drafts, asking the owner, mission offers |
| `owner_phone/` | Ask the owner a question by phone (Telegram) |
| `mission_cards/`, `a2a_extension/` | Mission cards, receipts and spending mandates, and an A2A protocol extension |
| `relay/` | The hosted relay that carries encrypted packets between people (AGPL-3.0) |
| `isolation/`, `network_acceptance/` | Tests that run owners in separate containers and networks |
| `archive/` | Earlier proofs of the same ideas, kept for reference (see [its README](archive/README.md)) |
| `research/` | Notes comparing related projects, with pinned reference snapshots |
| `docs/` | Design decisions, delivery status and verification records |

For how the pieces fit together, read the [architecture overview](ARCHITECTURE.md).
For the technical detail behind each guarantee, start with the
[delivery guide](docs/DELIVERY.md) and the [decision record](docs/DECISIONS.md).

## Contributing

Contributions are welcome. Please read [CONTRIBUTING](CONTRIBUTING.md); every
commit needs a DCO sign-off (`git commit -s`).

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Third-party material
keeps its own licence, listed in [licence status](LICENSE_STATUS.md).
