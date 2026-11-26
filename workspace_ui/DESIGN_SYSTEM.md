# Parlu workspace design notes

The workspace follows the Parlu brand sketch Edem chose on 26 November 2026: two overlapping circles, teal for the person, coral for the assistant and dark ink for the shared space where they agree, on white grounds (Edem asked for white over cream on 26 November). This note records how `style.css` maps onto it.

## Brand

- **Mark:** two overlapping circles (teal `#14897a`, coral `#ee7b5b`) with an ink lens (`#1b1a17`) where they meet. Inline SVG in `index.html`.
- **Wordmark:** lowercase "parlu", Plus Jakarta Sans 700, tracking -0.045em. The name itself stays a placeholder in `PRODUCT` in `app.mjs`.
- **Type:** Plus Jakarta Sans (self-hosted variable font, Latin subset, SIL OFL). Page titles 36/42 bold (28/34 on phones), dialog titles 22/28 bold, section titles 17 semibold.

## Tokens

Every colour in `style.css` is a role token on `:root`. Use the role, never a raw hex.

| Role | Token | Value |
| --- | --- | --- |
| Raised cells | `--raised` | `#f5f5f4` |
| Page ground and working card | `--bg` | `#ffffff` |
| Inner cards | `--surface` | `#ffffff` |
| Lines | `--line`, `--line-strong` | `#e4e0d8`, `#d6d1c7` |
| Text | `--text`, `--secondary`, `--muted` | `#1b1a17`, `#3e3b35`, `#5c5850` |
| Person (teal) | `--accent`, `--accent-bg`, `--accent-on` | `#14897a`, `#e3f2ef`, `#0b5a50` |
| Assistant and "needs you" (coral) | `--sun`, `--sun-bg`, `--sun-on` | `#ee7b5b`, `#fce9e2`, `#8a3a22` |

## Rules

- **Teal is a person, coral is an assistant.** People are teal circles; assistants are two-eyed blobs (a blob is only ever an assistant, so the shape itself says AI, and every label names it, as in "Otto, Tom's assistant"), always shown beside their owner.
- **Coral marks what needs you:** the count on "Needs your attention" and pending badges. The card itself stays plain white.
- **Primary actions and the active nav item are ink pills.** Secondary actions are white pills with a line.
- **Approval screens stay plain.** Lead with the accountable person and what happens, in plain English. Money shows in the mission's own currency.
- **Shape:** cards 20 to 24px radius, dialogs 28px (a bottom sheet on phones), controls are pills.

- **People and assistants sit side by side, never overlapping.** The owner's teal circle and the assistant's bot keep a small gap; only the logo mark overlaps.

## The Parlu direction (chosen by Edem, 26 November 2026)

One app whose screens are states, not separate apps. Source: `/mnt/project-files/design-system/direction/` in the project files.

- **Home is a paragraph.** At most three sentences with people and bots inline, ending with a true line about whether anything else needs you. Under it, one decision per card. A card never decides on its own: "Review and agree" opens the exact review.
- **Every assistant has a face.** A two-eyed blob from `bots.mjs` (six shapes, six warm colours, five expressions that carry state), always beside its owner's teal circle with a 4px gap. Nothing overlaps or merges.
- **Money and consent need a hold.** `hold.mjs` fills a coral ring over about a second; letting go early does nothing. The plain button stays as the alternative.
- **Desktop speaks the phone's language.** White cards with 24px radii, rows at 16 to 20px, heavy tight headings (800, -0.035em), pill controls and a glass top bar. Home uses the narrated paragraph as its headline, a centre column for decisions and a right rail for numbers, people and activity. Main places first in the sidebar (Home, Inbox, Approvals, Assistants, Recents), everything else quieter under More.
- **Phone frame.** A floating glass pill bar with Home, Recents and a plus button that opens a short dark menu. The desktop keeps its white sidebar.
- **Still to come:** the money view (one budget number and who holds which key) and the evening story with "Good" and "Don't do that again".
