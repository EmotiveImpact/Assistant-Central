import { colour, font, radius } from './theme';

export const fieldStyle = {
  borderWidth: 1, borderColor: colour.lineStrong, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 13,
  fontFamily: font.regular, fontSize: 16, color: colour.text, backgroundColor: colour.bg,
} as const;
