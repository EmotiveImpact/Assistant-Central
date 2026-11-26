// Hold to agree, as in the mock: a small ink button inside a soft double ring, with a coral
// arc turning slowly around it. Press and hold and coral fills it over 0.85 seconds; let go
// early and it drains away and nothing happens. There is always a plain two-step button, for
// screen readers and for anyone who cannot hold.
import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Platform, Pressable, Text, View } from 'react-native';
import Animated, { cancelAnimation, Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import Svg, { Circle } from 'react-native-svg';
import * as Haptics from 'expo-haptics';
import { colour, font } from './theme';
import { Button } from './parts';

export const HOLD_MS = 850;
const INK = 62, RING = 84, ARC = 40, LENGTH = 2 * Math.PI * ARC;

const lower = (label: string) => label.charAt(0).toLowerCase() + label.slice(1);

export function HoldButton({ label, title, hint, onDone, disabled }: {
  /** What a yes does, for example "Pay £120". */
  label: string;
  /** The line beside the button, for example "Hold to pay £120 with Tom". */
  title?: string;
  hint?: string;
  onDone: () => void;
  disabled?: boolean;
}) {
  const fill = useSharedValue(0);
  const spin = useSharedValue(0);
  const fired = useRef(false);
  const [plain, setPlain] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    // People using a screen reader get the plain two-step button straight away.
    if (Platform.OS === 'web') return; // The browser preview cannot tell; the plain button is one tap away.
    AccessibilityInfo.isScreenReaderEnabled().then(on => { if (on) setPlain(true); }).catch(() => undefined);
  }, []);
  useEffect(() => {
    spin.value = withRepeat(withTiming(360, { duration: 2400, easing: Easing.linear }), -1, false);
    return () => cancelAnimation(spin);
  }, [spin]);

  const finish = () => {
    if (fired.current) return;
    fired.current = true;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
    onDone();
  };
  const start = () => {
    if (disabled || fired.current) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined);
    fill.value = withTiming(1, { duration: HOLD_MS, easing: Easing.linear }, finished => { if (finished) scheduleOnRN(finish); });
  };
  const stop = () => {
    if (fired.current) return;
    cancelAnimation(fill);
    fill.value = withTiming(0, { duration: 180 });
  };

  const fillStyle = useAnimatedStyle(() => ({ transform: [{ scale: fill.value }] }));
  const arcStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value}deg` }] }));

  const words = (
    <View style={{ flex: 1, gap: 3 }}>
      {title ? <Text style={{ fontFamily: font.bold, fontSize: 14.5, lineHeight: 19, color: colour.text }}>{title}</Text> : null}
      {hint ? <Text style={{ fontFamily: font.regular, fontSize: 12.5, lineHeight: 17, color: colour.muted }}>{hint}</Text> : null}
      {!plain ? (
        <Pressable accessibilityRole="button" onPress={() => setPlain(true)} hitSlop={8} style={{ alignSelf: 'flex-start', marginTop: 2 }}>
          <Text style={{ color: colour.accentFg, fontFamily: font.semibold, fontSize: 12.5, textDecorationLine: 'underline' }}>Use a button instead</Text>
        </Pressable>
      ) : null}
    </View>
  );

  if (plain) {
    return (
      <View style={{ gap: 10, alignSelf: 'stretch' }}>
        {title || hint ? words : null}
        {confirming
          ? <Button label={`Yes, ${lower(label)}`} disabled={disabled} onPress={finish} />
          : <Button label={label} kind="secondary" disabled={disabled} onPress={() => setConfirming(true)} />}
        {confirming ? <Button label="Not yet" kind="quiet" onPress={() => setConfirming(false)} /> : null}
      </View>
    );
  }

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
      <Pressable onPressIn={start} onPressOut={stop} disabled={disabled}
        accessibilityRole="button" accessibilityLabel={`Hold to ${lower(label)}`}
        accessibilityHint="Press and hold for about a second. Letting go early does nothing."
        accessibilityActions={[{ name: 'activate', label }]}
        onAccessibilityAction={() => setPlain(true)}
        style={{ width: RING, height: RING, alignItems: 'center', justifyContent: 'center', opacity: disabled ? 0.5 : 1 }}>
        <Animated.View style={[{ position: 'absolute', width: RING, height: RING }, arcStyle]} pointerEvents="none">
          <Svg width={RING} height={RING}>
            <Circle cx={RING / 2} cy={RING / 2} r={ARC} stroke={colour.sun} strokeWidth={3} fill="none"
              strokeDasharray={`${LENGTH / 2} ${LENGTH / 2}`} strokeLinecap="round" />
          </Svg>
        </Animated.View>
        <View style={{ width: INK + 20, height: INK + 20, borderRadius: 50, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' }}>
          <View style={{ width: INK + 14, height: INK + 14, borderRadius: 50, backgroundColor: colour.line, alignItems: 'center', justifyContent: 'center' }}>
            <View style={{ width: INK, height: INK, borderRadius: INK / 2, backgroundColor: colour.text, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
              <Animated.View style={[{ position: 'absolute', width: INK, height: INK, borderRadius: INK / 2, backgroundColor: colour.sun }, fillStyle]} />
              <Text style={{ color: '#fff', fontFamily: font.extrabold, fontSize: 12.5 }}>Hold</Text>
            </View>
          </View>
        </View>
      </Pressable>
      {words}
    </View>
  );
}
