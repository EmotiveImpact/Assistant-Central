# Linear style reference

Observed on 10 November 2026 at <https://linear.app/> using rendered computed
styles from the public website and its embedded interactive workspace. This is
a direct style mapping, not a visual guess. Central keeps its own branding,
content, functionality and responsive information layout.

## Font

Linear's HTML preloads
`https://static.linear.app/fonts/InterVariable.woff2?v=4.1`.
Central bundles the unmodified `web/InterVariable.woff2` from the official
[Inter v4.1 release](https://github.com/rsms/inter/releases/tag/v4.1).
It has the same advertised family and version. The CDN download was unavailable
in this environment, so byte identity with Linear's CDN asset is not claimed.

- Family: `Inter Variable`.
- Weight axis: 100 to 900, with 400 normal, 510 medium and 590 semibold.
- Optical sizing: `auto`.
- Body and heading features: `"cv01", "ss03"`.
- Navigation button features: `normal`, matching Linear's computed button style.
- File: 352,240 bytes.
- SHA-256: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`.
- Licence: SIL Open Font Licence 1.1, included in `INTER-LICENSE.txt`.

The font is preloaded and served only from the narrow same-origin static route.
No font CDN, analytics or other new external request is needed at runtime.
Browser regression tests require the successful WOFF2 response, its pinned
SHA-256, an actually loaded FontFace, and the rendered family and weights.
A font-family declaration with a missing asset does not pass.

## Direct mappings

| Central component | Observed Linear element | Measured values |
| --- | --- | --- |
| Base surface and text | Root tokens | `#08090a`, `#f7f8f8` |
| Secondary and muted text | Root tokens | `#d0d6e0`, `#8a8f98`, `#62666d` |
| Panel and raised surfaces | Root tokens | `#0f1011`, `#141516` |
| Main border and separator | Root tokens | `#23252a`, `#202122` |
| Accent | Root tokens | `#7170ff`, hover `#828fff` |
| Workspace frame | `.WS84WW_frame` | Background `#090a0b`, padding 8px |
| Sidebar | `.Mmx1Wq_sidebar` | Width 232px, padding 8px 16px 16px 8px |
| Navigation | `.Mmx1Wq_navItem` | 13px, weight 510, normal line height, height 28px, padding 0 7px, gap 8px, radius 8px, colour `#d0d6e0` |
| Active navigation | `.Mmx1Wq_navItem` | White at 4% opacity |
| Navigation section | `.Mmx1Wq_collapsible` | 12px/14px, weight 510 |
| Page and review headings | `.KFZpfa_titleText` | 20px/26.6px, weight 590, tracking -0.24px, colour `#d0d6e0` |
| Section headings | App Activity `h4` | 16px/28px, weight 590 |
| Description | `.KFZpfa_description` | 14px/21px, weight 400, tracking -0.182px, colour `#8a8f98` |
| Primary button | `.S36ykG_size-small.S36ykG_variant-invert` | 13px, weight 510, height 32px, padding 0 12px, gap 8px, radius 9999px, background `#e5e5e6`, text `#08090a` |
| Status chip | `._1uFtza_labelButton` | 12px/14px, weight 400, height 24px, radius 16px, border `#2e2e32`, padding 0 11px 0 7px |
| Board card | `._5k-xcq_card.qM9FAa_issue` | Background `#0f1011`, 1px white border at 8%, radius 9px, padding 8px 10px 12px 12px |
| Board card title | `._5k-xcq_titleText` | 16px/24px, weight 400 |
| Board column heading | `.qM9FAa_colHeader` | 16px/24px, padding 0 12px 28px, gap 8px |
| Board spacing | `.qM9FAa_row` and card stack | Columns 12px, cards 8px |
| Entrance headline | Website `h1` | 64px/64px, weight 510, tracking -1.408px |
| Responsive headline | Website title tokens | At 1024px: 56px/56px, tracking -1.232px; at 640px: 40px/40px, tracking -0.88px |

The source page is responsive and can change later. These values document the
specific observed reference. Central-specific overview metrics, decision forms,
mobile navigation and content arrangements are adaptations using these tokens;
this is not a claim that every screen is a pixel-identical copy of Linear.

## Verification

The browser test checks exact navigation and heading computed values, successful
font decoding, same-origin requests, real owner API workflows, and mobile
horizontal overflow. It captures the entrance, overview, board, review and mobile
screens. All approvals remain synthetic and the UI does not enable providers.
