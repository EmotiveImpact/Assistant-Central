// The evening story: one tap per thing that was agreed today, each with its proof.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import { Redirect, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';
import { useGuard } from '../lib/guard';
import { peerOf } from '../lib/home';
import { useSession } from '../lib/session';
import { doneLine, doneToday, exactMoney } from '../shared/web';
import type { Item } from '../lib/types';
import { Button, Pair, T } from '../ui/parts';
import { colour, font } from '../ui/theme';

export default function Story() {
  const guard = useGuard();
  const { state } = useSession();
  const inset = useSafeAreaInsets();
  const [index, setIndex] = useState(0);
  if (guard || !state) return guard;
  const done = doneToday(state.items) as Item[];
  if (!done.length) return <Redirect href="/" />;
  const item = done[Math.min(index, done.length - 1)], peer = peerOf(state, item);
  const next = () => (index + 1 < done.length ? setIndex(index + 1) : router.back());
  const proof = [doneLine(item, peer) + '.', item.mission_cap ? `Limit ${exactMoney(item.mission_cap.cap_micro, item.mission_cap.currency)}, signed.` : 'No money involved.',
    typeof item.decision_digest === 'string' ? `Receipt ${item.decision_digest.slice(0, 4)}…${item.decision_digest.slice(-2)}` : 'Signed by both sides.'];
  return (
    <View style={{ flex: 1, backgroundColor: colour.bg, paddingTop: inset.top + 10, paddingHorizontal: 20, paddingBottom: inset.bottom + 20 }}>
      <View style={{ flexDirection: 'row', gap: 4 }}>
        {done.map((_, i) => <View key={i} style={{ flex: 1, height: 3, borderRadius: 2, backgroundColor: i <= index ? colour.sun : colour.line }} />)}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 14 }}>
        <Pair owner={state.identity.owner_id} agent={state.identity.agent_id} size={26} e="done" />
        <View style={{ flex: 1 }}><T v="smallBold">{state.identity.agent_id}’s day</T><T v="small">{index + 1} of {done.length}</T></View>
        <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Close" hitSlop={10}>
          <Svg width={22} height={22} viewBox="0 0 24 24"><Path d="M6 6l12 12M18 6L6 18" stroke={colour.text} strokeWidth={1.8} strokeLinecap="round" /></Svg>
        </Pressable>
      </View>
      <Pressable onPress={next} style={{ flex: 1, justifyContent: 'flex-end', gap: 16, paddingBottom: 20 }} accessibilityRole="button" accessibilityHint="Shows the next one">
        <T style={{ fontFamily: font.bold, fontSize: 36, lineHeight: 40, letterSpacing: -1.4, color: colour.text }}>{item.title}.</T>
        <View style={{ backgroundColor: colour.raised, borderRadius: 18, padding: 14, gap: 6 }}>
          {proof.map(line => <T key={line} v="body" style={{ color: colour.secondary }}>✓ {line}</T>)}
        </View>
      </Pressable>
      <Button label={index + 1 < done.length ? 'Good, next' : 'Good'} onPress={next} />
    </View>
  );
}
