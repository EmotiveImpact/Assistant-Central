# Parlu workspace design notes

The workspace follows the Parlu brand sketch Edem chose on 26 November 2026: two overlapping circles, teal for the person, coral for the assistant and dark ink for the shared space where they agree, on warm cream grounds. This note records how `style.css` maps onto it.

## Brand

- **Mark:** two overlapping circles (teal `#14897a`, coral `#ee7b5b`) with an ink lens (`#1b1a17`) where they meet. Inline SVG in `index.html`.
- **Wordmark:** lowercase "parlu", Plus Jakarta Sans 700, tracking -0.045em. The name itself stays a placeholder in `PRODUCT` in `app.mjs`.
- **Type:** Plus Jakarta Sans (self-hosted variable font, Latin subset, SIL OFL). Page titles 36/42 bold (28/34 on phones), dialog titles 22/28 bold, section titles 17 semibold.

## Tokens

Every colour in `style.css` is a role token on `:root`. Use the role, never a raw hex.

| Role | Token | Value |
| --- | --- | --- |
| Page ground and sidebar | `--raised` | `#f3f1ec` |
| Working card | `--bg` | `#fbfaf7` |
| Inner cards | `--surface` | `#ffffff` |
| Lines | `--line`, `--line-strong` | `#e4e0d8`, `#d6d1c7` |
| Text | `--text`, `--secondary`, `--muted` | `#1b1a17`, `#3e3b35`, `#5c5850` |
| Person (teal) | `--accent`, `--accent-bg`, `--accent-on` | `#14897a`, `#e3f2ef`, `#0b5a50` |
| Assistant and "needs you" (coral) | `--sun`, `--sun-bg`, `--sun-on` | `#ee7b5b`, `#fce9e2`, `#8a3a22` |

## Rules

- **Teal is a person, coral is an assistant.** People are teal circles; assistants are warm rounded squares with a small "AI" mark, always shown with their owner.
- **Coral marks what needs you:** the count on "Needs your attention" and pending badges. The card itself stays plain white.
- **Primary actions and the active nav item are ink pills.** Secondary actions are cream pills with a line.
- **Approval screens stay plain.** Lead with the accountable person and what happens, in plain English. Money shows in the mission's own currency.
- **Shape:** cards 20 to 24px radius, dialogs 28px (a bottom sheet on phones), controls are pills.
