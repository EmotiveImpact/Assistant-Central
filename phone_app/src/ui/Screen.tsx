// The frame for a full screen: white ground, safe areas, an optional back row and title.
import React from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Svg, { Path } from 'react-native-svg';
import { colour, font } from './theme';
import { T } from './parts';

export function Back({ label = 'Back' }: { label?: string }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} hitSlop={10}
      onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', paddingVertical: 6 }}>
      <Svg width={20} height={20} viewBox="0 0 24 24"><Path d="M15 5l-7 7 7 7" stroke={colour.text} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></Svg>
      <Text style={{ fontFamily: font.semibold, fontSize: 15, color: colour.text }}>{label}</Text>
    </Pressable>
  );
}

export function Screen({ children, title, lead, back = true, scroll = true, refreshing, onRefresh, footer, style }: {
  children: React.ReactNode; title?: string; lead?: string; back?: boolean | string; scroll?: boolean;
  refreshing?: boolean; onRefresh?: () => void; footer?: React.ReactNode; style?: StyleProp<ViewStyle>;
}) {
  const inset = useSafeAreaInsets();
  const head = (
    <View style={{ gap: 6, marginBottom: 18 }}>
      {back ? <Back label={typeof back === 'string' ? back : 'Back'} /> : null}
      {title ? <T v="page" accessibilityRole="header" style={{ marginTop: back ? 8 : 0 }}>{title}</T> : null}
      {lead ? <T v="body" style={{ fontSize: 16, lineHeight: 23, color: colour.muted }}>{lead}</T> : null}
    </View>
  );
  const pad = { paddingTop: inset.top + 12, paddingHorizontal: 20, paddingBottom: inset.bottom + (footer ? 110 : 32) };
  return (
    <View style={{ flex: 1, backgroundColor: colour.bg }}>
      {scroll ? (
        <ScrollView contentContainerStyle={[pad, style]} keyboardShouldPersistTaps="handled"
          refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={colour.accent} /> : undefined}>
          {head}{children}
        </ScrollView>
      ) : <View style={[{ flex: 1 }, pad, style]}>{head}{children}</View>}
      {footer}
    </View>
  );
}

/** Content for a sheet: no back row, the grabber is the way out. */
export function Sheet({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const inset = useSafeAreaInsets();
  return (
    <ScrollView style={{ backgroundColor: colour.bg }} contentContainerStyle={[{ padding: 22, paddingTop: 30, paddingBottom: inset.bottom + 28, gap: 16 }, style]} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  );
}
