// The small pieces every screen uses: text, the person circle, the bot, the pair, buttons.
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type PressableProps, type StyleProp, type TextProps, type TextStyle, type ViewStyle } from 'react-native';
import Svg, { Circle, G, Path, Rect } from 'react-native-svg';
import { botTraits, COLOURS, SHAPES } from '../shared/web';
import { colour, font, radius, tight } from './theme';

type Variant = 'title' | 'page' | 'section' | 'body' | 'bodyBold' | 'small' | 'smallBold' | 'label' | 'say' | 'sayBold' | 'mono';

const variants: Record<Variant, TextStyle> = {
  page: { fontFamily: font.bold, fontSize: 30, lineHeight: 35, letterSpacing: tight(30), color: colour.text },
  title: { fontFamily: font.bold, fontSize: 22, lineHeight: 28, letterSpacing: -0.4, color: colour.text },
  section: { fontFamily: font.semibold, fontSize: 17, lineHeight: 23, color: colour.text },
  body: { fontFamily: font.regular, fontSize: 15, lineHeight: 22, color: colour.secondary },
  bodyBold: { fontFamily: font.semibold, fontSize: 15, lineHeight: 22, color: colour.text },
  small: { fontFamily: font.regular, fontSize: 13, lineHeight: 18, color: colour.muted },
  smallBold: { fontFamily: font.semibold, fontSize: 13, lineHeight: 18, color: colour.text },
  label: { fontFamily: font.semibold, fontSize: 11, lineHeight: 14, letterSpacing: 0.9, textTransform: 'uppercase', color: colour.muted },
  say: { fontFamily: font.semibold, fontSize: 25, lineHeight: 33, letterSpacing: -0.6, color: colour.faint },
  sayBold: { fontFamily: font.bold, fontSize: 25, lineHeight: 33, letterSpacing: -0.6, color: colour.text },
  mono: { fontFamily: font.mono, fontSize: 12, lineHeight: 16, color: colour.muted },
};

export function T({ v = 'body', style, ...rest }: TextProps & { v?: Variant }) {
  return <Text {...rest} style={[variants[v], style]} />;
}

export function initials(name: string) {
  const words = String(name || '?').trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2);
  return letters.toUpperCase();
}

/** A person: always a teal circle with their initials. */
export function Person({ name, size = 32, style }: { name: string; size?: number; style?: StyleProp<ViewStyle> }) {
  const letters = size < 30 ? initials(name).slice(0, 1) : initials(name);
  return (
    <View accessible={false} style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: size < 26 ? colour.accentFg : colour.accent, alignItems: 'center', justifyContent: 'center' }, style]}>
      <Text style={{ color: '#fff', fontFamily: font.bold, fontSize: Math.max(10, size * 0.36), letterSpacing: 0.2 }}>{letters}</Text>
    </View>
  );
}

export type Expression = 'idle' | 'busy' | 'look' | 'done' | 'sleep';

function Eyes({ e }: { e: Expression }) {
  const w = '#fff';
  if (e === 'done') return <Path d="M33 52q7-9 14 0M55 52q7-9 14 0" stroke={w} strokeWidth={5.5} fill="none" strokeLinecap="round" />;
  if (e === 'sleep') return <Path d="M33 52h13M56 52h13" stroke={w} strokeWidth={5} strokeLinecap="round" />;
  if (e === 'busy') return <G><Rect x={34} y={34} width={8} height={14} rx={4} fill={w} transform="rotate(14 38 41)" /><Rect x={52} y={32} width={8} height={14} rx={4} fill={w} transform="rotate(14 56 39)" /></G>;
  if (e === 'look') return <G><Rect x={35} y={38} width={10} height={17} rx={5} fill={w} /><Rect x={56} y={38} width={10} height={17} rx={5} fill={w} /></G>;
  return <G><Rect x={36} y={38} width={8} height={15} rx={4} fill={w} transform="rotate(10 40 45)" /><Rect x={56} y={38} width={8} height={15} rx={4} fill={w} transform="rotate(10 60 45)" /></G>;
}

/** Every few seconds, for a moment, as in the mock: assistants blink while they wait. */
function useBlink(enabled: boolean) {
  const [shut, setShut] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout>;
    const next = () => {
      timer = setTimeout(() => { setShut(true); timer = setTimeout(() => { setShut(false); next(); }, 130); }, 3200 + Math.random() * 3200);
    };
    next();
    return () => clearTimeout(timer);
  }, [enabled]);
  return shut;
}

/** An assistant: a small two-eyed blob. Shape and colour come from its name, as on desktop. */
export function Bot({ name, size = 32, e = 'idle' }: { name: string; size?: number; e?: Expression }) {
  const shut = useBlink(e === 'idle' || e === 'look' || e === 'busy');
  const t = botTraits(name) as { shape: keyof typeof SHAPES; body: string };
  const d = SHAPES[t.shape];
  const round = t.shape === 'hex' ? { stroke: t.body, strokeWidth: 12, strokeLinejoin: 'round' as const } : {};
  return (
    <Svg width={size} height={size} viewBox="-10 -10 120 120" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {e === 'look' ? <Path d={d} fill="none" stroke={COLOURS.coral} strokeWidth={5} opacity={0.55} transform="translate(50 50) scale(1.16) translate(-50 -50)" /> : null}
      <Path d={d} fill={t.body} {...round} />
      <G transform={shut ? 'translate(0 46) scale(1 0.12) translate(0 -46)' : undefined}><Eyes e={e} /></G>
    </Svg>
  );
}

/** The owner's circle, then their bot beside it, 4px apart. They never overlap or merge. */
export function Pair({ owner, agent, size = 30, e = 'idle', style }: { owner: string; agent: string; size?: number; e?: Expression; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[{ flexDirection: 'row', alignItems: 'center', gap: 4 }, style]} accessible accessibilityLabel={`${owner} and ${agent}`}>
      <Person name={owner} size={size} />
      <Bot name={agent} size={size + 4} e={e} />
    </View>
  );
}

type ButtonProps = Omit<PressableProps, 'style' | 'children'> & { label: string; kind?: 'primary' | 'secondary' | 'quiet' | 'danger'; busy?: boolean; style?: StyleProp<ViewStyle>; small?: boolean };

export function Button({ label, kind = 'primary', busy, disabled, style, small, ...rest }: ButtonProps) {
  const off = disabled || busy;
  const box: ViewStyle = kind === 'primary' ? { backgroundColor: colour.text } : kind === 'danger' ? { backgroundColor: colour.bg, borderWidth: 1, borderColor: colour.lineStrong } : kind === 'secondary' ? { backgroundColor: colour.bg, borderWidth: 1, borderColor: colour.lineStrong } : { backgroundColor: 'transparent' };
  const ink = kind === 'primary' ? colour.onText : kind === 'danger' ? colour.danger : colour.text;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!off, busy: !!busy }} disabled={off} {...rest}
      style={({ pressed }) => [styles.button, small && styles.small, box, { opacity: off ? 0.5 : pressed ? 0.82 : 1 }, style]}>
      {busy ? <ActivityIndicator color={ink} /> : <Text style={{ color: ink, fontFamily: font.semibold, fontSize: small ? 14 : 16 }}>{label}</Text>}
    </Pressable>
  );
}

export function Chip({ label, tone = 'plain' }: { label: string; tone?: 'plain' | 'sun' | 'accent' | 'ok' | 'done' }) {
  const bg = { plain: colour.raised, sun: colour.sunBg, accent: colour.accentBg, ok: colour.okBg, done: colour.accentBg }[tone];
  const ink = { plain: colour.secondary, sun: colour.sunOn, accent: colour.accentOn, ok: colour.ok, done: colour.accentOn }[tone];
  return <View style={[styles.chip, { backgroundColor: bg }]}><Text style={{ color: ink, fontFamily: font.semibold, fontSize: 12.5 }}>{label}</Text></View>;
}

export function Card({ children, style, tone }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; tone?: 'sun' }) {
  return <View style={[styles.card, tone === 'sun' && { borderColor: colour.sun, borderWidth: 1.5 }, style]}>{children}</View>;
}

/** The Parlu mark: teal person and coral assistant, an ink lens where they agree. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <Svg width={size * 1.5} height={size} viewBox="0 0 36 24" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Circle cx={12} cy={12} r={10} fill={colour.accent} />
      <Circle cx={24} cy={12} r={10} fill={colour.sun} />
      <Path d="M18 4.0a10 10 0 0 1 0 16a10 10 0 0 1 0-16z" fill={colour.text} />
    </Svg>
  );
}

export function Wordmark({ size = 22 }: { size?: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} accessible accessibilityRole="header" accessibilityLabel="Parlu">
      <Mark size={size * 0.82} />
      <Text style={{ fontFamily: font.bold, fontSize: size, letterSpacing: tight(size), color: colour.text }}>Parlu</Text>
    </View>
  );
}

export function Row({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center', gap: 10 }, style]}>{children}</View>;
}

export function Notice({ text, tone = 'plain' }: { text: string; tone?: 'plain' | 'danger' | 'ok' }) {
  if (!text) return null;
  const bg = tone === 'danger' ? colour.dangerBg : tone === 'ok' ? colour.okBg : colour.raised;
  const ink = tone === 'danger' ? colour.danger : tone === 'ok' ? colour.ok : colour.secondary;
  return <View accessibilityLiveRegion="polite" style={{ backgroundColor: bg, borderRadius: radius.md, padding: 12 }}><Text style={{ color: ink, fontFamily: font.medium, fontSize: 14, lineHeight: 20 }}>{text}</Text></View>;
}

const styles = StyleSheet.create({
  button: { minHeight: 52, paddingHorizontal: 22, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  small: { minHeight: 40, paddingHorizontal: 16 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, alignSelf: 'flex-start' },
  card: { backgroundColor: colour.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colour.line, padding: 16 },
});
