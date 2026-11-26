// The floating glass bar from the mock: Home, Recents, and + for something new. It floats
// over every main screen, frosted, and stays put while pages change underneath it.
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';
import { router, usePathname } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { useAnimatedStyle, withSpring, withTiming } from 'react-native-reanimated';
import Svg, { Circle, Path } from 'react-native-svg';
import * as Haptics from 'expo-haptics';
import { useSession } from '../lib/session';
import { useOverlay } from './overlay';
import { colour, font } from './theme';

export const BAR = 52;
const HIDDEN = new Set(['/welcome', '/connect', '/unlock', '/scan']);

/** A frosted round surface: blurred where the platform blurs well, near-white elsewhere. */
export function Frost({ style, children, on }: { style?: StyleProp<ViewStyle>; children?: React.ReactNode; on?: boolean }) {
  const shape = StyleSheet.flatten(style) ?? {};
  // The content sits in its own view so it always paints above the blur, on the web too.
  const inside = <View style={styles.inside}>{children}</View>;
  if (on) return <View style={[styles.lift, shape, { backgroundColor: colour.text, borderColor: colour.text }]}>{inside}</View>;
  return (
    <View style={[styles.lift, shape, { backgroundColor: Platform.OS === 'android' ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.72)' }]}>
      {Platform.OS !== 'android' ? (
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, { borderRadius: 999, overflow: 'hidden' }]}>
          <BlurView intensity={40} tint="light" style={StyleSheet.absoluteFill} />
        </View>
      ) : null}
      {inside}
    </View>
  );
}

export function useBarVisible() {
  const path = usePathname();
  const { state, backend } = useSession();
  return !!state && !!backend && !HIDDEN.has(path);
}

const tap = () => { Haptics.selectionAsync().catch(() => undefined); };

export function GlassBar() {
  const path = usePathname();
  const inset = useSafeAreaInsets();
  const overlay = useOverlay();
  const visible = useBarVisible();
  const plusOpen = overlay.layer?.kind === 'plus' && !overlay.closing;
  const plusStyle = useAnimatedStyle(() => ({ transform: [{ rotate: withSpring(plusOpen ? '45deg' : '0deg', { damping: 14, stiffness: 180 }) }] }), [plusOpen]);
  const barStyle = useAnimatedStyle(() => ({ opacity: withTiming(visible ? 1 : 0, { duration: 180 }), transform: [{ translateY: withTiming(visible ? 0 : 30, { duration: 220 }) }] }), [visible]);
  const home = path === '/', recents = path === '/recents';
  // Home and Recents sit at the bottom of the stack, like tabs: going to either one first
  // returns to Home, so pages never pile up behind the bar.
  const go = (to: '/' | '/recents') => {
    tap();
    if (overlay.layer) overlay.close();
    if (path === to) return;
    if (path !== '/') { if (router.canDismiss()) router.dismissAll(); else router.replace('/'); }
    if (to === '/recents') router.push('/recents');
  };
  return (
    <Animated.View pointerEvents={visible ? 'box-none' : 'none'} style={[styles.bar, { bottom: inset.bottom + 12 }, barStyle]}>
      <Pressable onPress={() => go('/')} accessibilityRole="button" accessibilityLabel="Home" accessibilityState={{ selected: home }}>
        <Frost on={home} style={styles.square}>
          <Svg width={21} height={21} viewBox="0 0 24 24"><Path d="M4 11l8-6.5 8 6.5V20h-5.5v-5h-5v5H4z" stroke={home ? colour.onText : colour.text} strokeWidth={1.8} fill="none" strokeLinejoin="round" /></Svg>
        </Frost>
      </Pressable>
      <Pressable onPress={() => go('/recents')} accessibilityRole="button" accessibilityLabel="Recents" accessibilityState={{ selected: recents }} style={{ flex: 1 }}>
        <Frost on={recents} style={styles.mid}>
          <Svg width={17} height={17} viewBox="0 0 24 24"><Circle cx={12} cy={12} r={8.5} stroke={recents ? colour.onText : colour.text} strokeWidth={1.9} fill="none" /><Path d="M12 7.5V12l3 2" stroke={recents ? colour.onText : colour.text} strokeWidth={1.9} fill="none" strokeLinecap="round" /></Svg>
          <Text style={{ fontFamily: font.bold, fontSize: 15, color: recents ? colour.onText : colour.text }}>Recents</Text>
        </Frost>
      </Pressable>
      <Pressable onPress={() => { tap(); overlay.toggle('plus'); }} accessibilityRole="button" accessibilityLabel={plusOpen ? 'Close' : 'Something new'} accessibilityState={{ expanded: plusOpen }}>
        <Frost style={styles.square}>
          <Animated.View style={plusStyle}>
            <Svg width={20} height={20} viewBox="0 0 24 24"><Path d="M12 5v14M5 12h14" stroke={colour.text} strokeWidth={2} strokeLinecap="round" /></Svg>
          </Animated.View>
        </Frost>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  bar: { position: 'absolute', left: 14, right: 14, flexDirection: 'row', gap: 9, alignItems: 'center' },
  lift: {
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.9)', borderRadius: 999,
    shadowColor: '#1b1a17', shadowOpacity: 0.22, shadowRadius: 16, shadowOffset: { width: 0, height: 8 }, elevation: 6,
  },
  square: { width: BAR, height: BAR },
  mid: { height: BAR },
  inside: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7 },
});
