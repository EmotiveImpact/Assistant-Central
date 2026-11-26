// Hold to agree. Money and consent need a deliberate press: the ring fills over about a
// second, and letting go early does nothing. There is always a plain button alternative,
// for screen readers and for anyone who cannot hold.
import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform, Pressable, Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import * as Haptics from 'expo-haptics';
import { colour, font } from './theme';
import { Button } from './parts';

export const HOLD_MS = 1000;
const SIZE = 132, STROKE = 6, R = (SIZE - STROKE) / 2, LENGTH = 2 * Math.PI * R;
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const tap = (style: Haptics.ImpactFeedbackStyle) => { Haptics.impactAsync(style).catch(() => undefined); };

export function HoldButton({ label, onDone, disabled, hint }: { label: string; onDone: () => void; disabled?: boolean; hint?: string }) {
  const progress = useRef(new Animated.Value(0)).current;
  const fired = useRef(false);
  const [plain, setPlain] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    // People using a screen reader get the plain two-step button straight away.
    if (Platform.OS === 'web') return; // The browser preview cannot tell; the plain button is one tap away.
    AccessibilityInfo.isScreenReaderEnabled().then(on => { if (on) setPlain(true); }).catch(() => undefined);
  }, []);

  const start = () => {
    if (disabled || fired.current) return;
    tap(Haptics.ImpactFeedbackStyle.Light);
    Animated.timing(progress, { toValue: 1, duration: HOLD_MS, easing: Easing.linear, useNativeDriver: false }).start(({ finished }) => {
      if (!finished || fired.current) return;
      fired.current = true;
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
      onDone();
    });
  };
  const stop = () => {
    if (fired.current) return;
    progress.stopAnimation();
    Animated.timing(progress, { toValue: 0, duration: 180, useNativeDriver: false }).start();
  };

  if (plain) {
    return (
      <View style={{ gap: 10, alignSelf: 'stretch' }}>
        {confirming
          ? <Button label={`Yes, ${label.charAt(0).toLowerCase() + label.slice(1)}`} disabled={disabled} onPress={() => { if (!fired.current) { fired.current = true; onDone(); } }} />
          : <Button label={label} kind="secondary" disabled={disabled} onPress={() => setConfirming(true)} />}
        {confirming ? <Button label="Not yet" kind="quiet" onPress={() => setConfirming(false)} /> : null}
      </View>
    );
  }

  const offset = progress.interpolate({ inputRange: [0, 1], outputRange: [LENGTH, 0] });
  return (
    <View style={{ alignItems: 'center', gap: 10 }}>
      <Pressable onPressIn={start} onPressOut={stop} disabled={disabled}
        accessibilityRole="button" accessibilityLabel={`Hold to ${label.charAt(0).toLowerCase() + label.slice(1)}`}
        accessibilityHint="Press and hold for about a second. Letting go early does nothing."
        accessibilityActions={[{ name: 'activate', label }]}
        onAccessibilityAction={() => setPlain(true)}
        style={{ width: SIZE, height: SIZE, alignItems: 'center', justifyContent: 'center', opacity: disabled ? 0.5 : 1 }}>
        <Svg width={SIZE} height={SIZE} style={{ position: 'absolute' }}>
          <Circle cx={SIZE / 2} cy={SIZE / 2} r={R} stroke={colour.sunBg} strokeWidth={STROKE} fill="none" />
          <AnimatedCircle cx={SIZE / 2} cy={SIZE / 2} r={R} stroke={colour.sun} strokeWidth={STROKE} fill="none"
            strokeDasharray={`${LENGTH} ${LENGTH}`} strokeDashoffset={offset} strokeLinecap="round" transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`} />
        </Svg>
        <View style={{ width: SIZE - 30, height: SIZE - 30, borderRadius: SIZE, backgroundColor: colour.text, alignItems: 'center', justifyContent: 'center', padding: 8 }}>
          <Text style={{ color: colour.onText, fontFamily: font.bold, fontSize: 16 }}>Hold</Text>
        </View>
      </Pressable>
      {hint ? <Text style={{ color: colour.muted, fontFamily: font.regular, fontSize: 13, textAlign: 'center' }}>{hint}</Text> : null}
      <Pressable accessibilityRole="button" onPress={() => setPlain(true)} hitSlop={8}>
        <Text style={{ color: colour.accentFg, fontFamily: font.semibold, fontSize: 13.5, textDecorationLine: 'underline' }}>Use a button instead</Text>
      </Pressable>
    </View>
  );
}
