import { Platform } from 'react-native';

// Parlu's tokens, matching design-system/tokens.json and the desktop app's CSS roles.
export const colour = {
  raised: '#f5f5f4',
  bg: '#ffffff',
  surface: '#ffffff',
  sidebar: '#fafafa',
  line: '#ebebe9',
  lineSoft: '#f0f0ee',
  lineStrong: '#d9d9d6',
  text: '#1b1a17',
  secondary: '#3e3b35',
  muted: '#5c5850',
  faint: '#8e897f',
  onText: '#fbfaf7',
  accent: '#14897a',
  accentFg: '#0f6e61',
  accentBg: '#e3f2ef',
  accentOn: '#0b5a50',
  sun: '#ee7b5b',
  sunBg: '#fce9e2',
  sunOn: '#8a3a22',
  ok: '#1b7a52',
  okBg: '#d7f3e6',
  danger: '#b23a30',
  dangerBg: '#fdeceb',
  backdrop: 'rgba(27,26,23,0.36)',
} as const;

export const radius = { sm: 6, av: 9, md: 14, card: 20, lg: 24, sheet: 28, pill: 999 } as const;
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 10: 40 } as const;

export const font = {
  regular: 'PlusJakartaSans_400Regular',
  medium: 'PlusJakartaSans_500Medium',
  semibold: 'PlusJakartaSans_600SemiBold',
  bold: 'PlusJakartaSans_700Bold',
  extrabold: 'PlusJakartaSans_800ExtraBold',
  mono: Platform.select({ ios: 'Menlo', default: 'monospace' }),
} as const;

/** The wordmark's tracking, -0.045em, at a given size. */
export const tight = (size: number) => -0.045 * size;
