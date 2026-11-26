// Agreed. Both assistants light up side by side, each still beside its owner, with a teal
// tick between them. Then the receipt: what was agreed, by whom, and its signed reference.
import React from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import Svg, { Path } from 'react-native-svg';
import { useSession } from '../lib/session';
import { Bot, Button, Card, Person, T } from '../ui/parts';
import { Sheet } from '../ui/Screen';
import { colour } from '../ui/theme';

export default function Agreed() {
  const { receipt, state, setReceipt } = useSession();
  if (!receipt || !state) return <Sheet><T v="title">Nothing to show</T><Button label="Back to Home" onPress={() => router.back()} /></Sheet>;
  const me = state.identity.owner_id, mine = state.identity.agent_id;
  const done = () => { setReceipt(null); router.back(); };
  const ref = receipt.digest ? `${receipt.digest.slice(0, 4)}…${receipt.digest.slice(-2)}` : '';
  return (
    <Sheet style={{ alignItems: 'center', gap: 18 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 10 }} accessible accessibilityLabel={`You and ${receipt.owner} agreed`}>
        <Person name={me} size={36} />
        <Bot name={mine} size={56} e="done" />
        <View style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: colour.accentBg, alignItems: 'center', justifyContent: 'center', marginHorizontal: 10 }}>
          <Svg width={14} height={14} viewBox="0 0 24 24"><Path d="M5 12.5l4.5 4.5L19 7.5" stroke={colour.accentFg} strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" /></Svg>
        </View>
        <Person name={receipt.owner ?? 'Them'} size={36} />
        <Bot name={receipt.agent ?? 'Assistant'} size={56} e="done" />
      </View>
      <T v="page" accessibilityRole="header" style={{ textAlign: 'center' }}>You and {receipt.owner} agreed.</T>
      <T v="body" style={{ textAlign: 'center', color: colour.muted }}>{receipt.line}</T>
      <Card style={{ alignSelf: 'stretch', gap: 12 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <View style={{ gap: 2, flex: 1 }}>
            <T v="small">{receipt.amount ? 'Up to' : 'Agreed'}</T>
            <T v="section" numberOfLines={2}>{receipt.amount || receipt.title}</T>
          </View>
          <View style={{ gap: 4, alignItems: 'flex-end' }}>
            <T v="small">Signed by</T>
            <View style={{ flexDirection: 'row', gap: 4 }}><Person name={me} size={24} /><Person name={receipt.owner ?? 'Them'} size={24} /></View>
          </View>
        </View>
        {receipt.amount ? <T v="small">{receipt.title}</T> : null}
        {ref ? <T v="mono">RECEIPT {ref}</T> : null}
      </Card>
      <Button label="Done" onPress={done} style={{ paddingHorizontal: 40 }} />
    </Sheet>
  );
}
