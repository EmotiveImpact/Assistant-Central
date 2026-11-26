# Parlu workspace design notes

The workspace follows the "Combined" direction chosen on 26 November 2026: a tonal base, a calm approval sheet and a white working card on a soft lilac-grey surface. The fuller design system (tokens, components, previews) lives with the project's design files; this note records how the app's `style.css` maps onto it.

## Tokens

Every colour in `style.css` is a role token on `:root` (the Parlu token block). Use the role, never a raw hex.

| Role | Token | Value |
| --- | --- | --- |
| Page surface | `--bg` | `#fcfbfe` |
| Card | `--surface` | `#ffffff` |
| Sidebar and tonal fills | `--raised` | `#f3f2f8` |
| Lines | `--line`, `--line-strong` | `#e2e0ea`, `#d4d1df` |
| Text | `--text`, `--secondary`, `--muted` | `#1a1a22`, `#2c2d38`, `#5e6070` |
| Signed-in owner | `--accent`, `--accent-bg`, `--accent-on` | lilac `#6a4fd6`, `#ebe4ff`, `#25156e` |
| Other owners | `--teal*`, coral `#b04a20` | |
| Your turn | `--sun`, `--sun-bg` | `#ffd56b`, `#fff3cc` |
| Positive, warning, negative | `--ok-*`, `--warn-*`, `--danger-*` | |

## Rules

- **Colour means owner.** Lilac is the signed-in person. Other owners take teal, then coral.
- **Yellow means your turn.** Only the "Needs your attention" block and counts that wait on the viewer use `--sun`.
- **People are circles, assistants are rounded squares** with a small "AI" mark (`data-kind="person"` or `data-kind="assistant"`). An assistant is always shown with its owner.
- **Primary actions are ink** (dark pill). Secondary actions are white pills with a line. Destructive actions are a soft red pill.
- **Approval screens stay plain.** Lead with the accountable person and what happens, in plain English. Money should read in pounds once the backend stores a currency; until then it is labelled honestly as US dollars.
- **Type:** Inter Variable (self-hosted, CSP-safe). Page titles 28/34 bold, dialog titles 22/28 bold, section titles 17 semibold, body 14.
- **Shape:** cards 18 to 24px radius, dialogs 28px (a bottom sheet on phones), controls are pills.

## Known gaps

- Assistant avatar tone is still chosen by a name hash, not by owner. Owner-based colour needs the owner passed into `nameAvatar`.
- Some mission and conversation buttons still use the secondary style where they should be the primary action.
- Dark theme tokens exist in the design system but the app ships light only for now.
