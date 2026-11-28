import { FONTS } from "./lib/snap-cn-ui/fonts";

/** Parlu tokens, as literal values (a Remotion render has no app CSS). */
export const PARLU = {
  bg: "#ffffff",
  raised: "#f5f5f4",
  line: "#ebebe9",
  ink: "#1b1a17",
  faint: "#8e897f",
  accent: "#14897a",
  sun: "#ee7b5b",
  coral: "#c4522f",
  font: FONTS["Plus Jakarta Sans"],
} as const;

/** Bot pebble from the design system, in a 0 0 100 100 box. */
export const BOT_PEBBLE = "M50 7C77 7 94 23 94 51S77 94 49 94 6 79 6 51 23 7 50 7Z";

/** The Parlu mark (teal person, coral assistant, ink lens) as an image URL. */
export const MARK_SVG =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="480" height="480"><circle cx="18" cy="24" r="12" fill="#14897a"/><circle cx="30" cy="24" r="12" fill="#ee7b5b"/><path d="M24 13.61 A12 12 0 0 1 24 34.39 A12 12 0 0 1 24 13.61 Z" fill="#1b1a17"/></svg>',
  );
