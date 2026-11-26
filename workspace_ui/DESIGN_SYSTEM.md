# Parlu workspace design notes

The workspace follows the Parlu brand sketch Edem chose on 26 November 2026: two overlapping circles, teal for the person, coral for the assistant and dark ink for the shared space where they agree, on white grounds (Edem asked for white over cream on 26 November). This note records how `style.css` maps onto it.

## Brand

- **Mark:** two overlapping circles (teal `#14897a`, coral `#ee7b5b`) with an ink lens (`#1b1a17`) where they meet. Inline SVG in `index.html`.
- **Wordmark:** "Parlu" with a capital P, Plus Jakarta Sans 700, tracking -0.045em. The name itself stays a placeholder in `PRODUCT` in `app.mjs`.
- **Pairs in text:** a person and assistant pair inside a sentence sits centred on the line (`vertical-align:middle` with a .09em lift), never dropped low like a subscript.
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

### Money, Done today, Ask bar and the evening story

- **Money and keys** sits at the top of the right rail. Budgets come from accepted mission terms (the signed spending limit). Where this workspace runs the work, the figure is the amount left; where it cannot see the spending, it shows the amount agreed and says so. One currency at a time, never converted. With no mission budget it says "No budgets yet" and offers to set one up. The Keys tab lists who holds which signing key (short fingerprint) beside each owner and bot.
- **Done today** lists work someone agreed today, newest first, with a Receipt badge when a signed decision exists. It shows four and links to the rest in All work. The time is the proposal's, which is what is saved.
- **Ask bar** drafts a proposal from what you typed. Nothing is sent until you review it.
- **Evening story** (from 18:00, when nothing is waiting) sums up the day; while decisions wait, Home stays on the decisions in one line and shows one finished piece of work at a time. "Good" moves on. "Don't do that again" reopens what was agreed, where it can be cancelled; it does not change a permission by itself, because nothing runs here without the owner's yes. Wiring it to the autonomy dial needs a per-assistant setting and comes next.

### Your menu and Settings

- **Your menu** opens from the owner card at the foot of the sidebar: your keys and identity, workspace status, search, settings, and lock and sign out. It sits above the card on a white ground with a 20px radius. Focus goes to the first line, the arrow keys move through it, and Escape closes it and returns focus to the card.
- **Settings** is a side panel, never a separate page. It gathers what is already yours to change and holds no switch of its own: every line opens the place where that thing really lives. A setting the workspace does not have is left out, never shown as a dead control.
