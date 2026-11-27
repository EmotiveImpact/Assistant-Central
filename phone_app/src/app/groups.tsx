// Groups: the small societies of people and assistants who work together. Two assistants are
// in one group when they share a room, directly or through someone else. You are in every group,
// and every assistant always sits beside its person.
import React from 'react';
import { Pressable, View, useWindowDimensions } from 'react-native';
import Animated from 'react-native-reanimated';
import { router } from 'expo-router';
import Svg, { Line } from 'react-native-svg';
import { useGuard } from '../lib/guard';
import { useSession } from '../lib/session';
import type { State } from '../lib/types';
import { RULE_WORDS, groupsOf, roomLine, roomsOf } from '../shared/web';
import { rowIn } from '../ui/motion';
import { Card, Chip, Pair, T } from '../ui/parts';
import { RoomGlyph, whoOf } from '../ui/Room';
import { Screen } from '../ui/Screen';
import { colour, font, radius } from '../ui/theme';


// Where each assistant sits: you in the middle, the others on a ring around you.
function Constellation({ state, group, width }: { state: State; group: any; width: number }) {
  const height = 200, cx = width / 2, cy = height / 2, r = Math.min(width / 2 - 44, 70);
  const spots = new Map<string, { x: number; y: number }>([['you', { x: cx, y: cy }]]);
  group.peers.forEach((id: string, i: number) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(group.peers.length, 1);
    spots.set(id, { x: cx + Math.cos(angle) * r * 1.6, y: cy + Math.sin(angle) * r });
  });
  const heaviest = Math.max(1, ...group.ties.map((t: any) => t.weight));
  return (
    <View style={{ width, height }} accessible accessibilityLabel={`You and ${group.peers.map((id: string) => whoOf(state, id).agent).join(', ')}`}>
      <Svg width={width} height={height} style={{ position: 'absolute' }}>
        {group.peers.map((id: string) => {
          const a = spots.get('you')!, b = spots.get(id)!;
          return <Line key={'y' + id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={colour.accent} strokeOpacity={0.35} strokeWidth={2} />;
        })}
        {group.ties.map((t: any) => {
          const a = spots.get(t.a), b = spots.get(t.b);
          if (!a || !b) return null;
          return <Line key={t.a + t.b} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={colour.lineStrong} strokeWidth={1 + (2 * t.weight) / heaviest} strokeDasharray="4 4" />;
        })}
      </Svg>
      {[...spots].map(([id, spot]) => {
        const w = whoOf(state, id);
        return (
          <View key={id} style={{ position: 'absolute', left: spot.x - 40, top: spot.y - 16, width: 80, alignItems: 'center', gap: 2 }}>
            <Pair owner={w.owner} agent={w.agent} size={id === 'you' ? 28 : 24} e={id === 'you' ? 'busy' : 'idle'} />
            <T numberOfLines={1} style={{ fontFamily: font.semibold, fontSize: 11, color: id === 'you' ? colour.accentOn : colour.secondary }}>{id === 'you' ? 'You' : w.owner}</T>
          </View>
        );
      })}
    </View>
  );
}

function Stat({ value, label, warm }: { value: number; label: string; warm?: boolean }) {
  return (
    <View style={{ flex: 1, minWidth: '45%', backgroundColor: warm && value ? colour.sunBg : colour.raised, borderRadius: radius.md, padding: 10 }}>
      <T style={{ fontFamily: font.bold, fontSize: 20, color: warm && value ? colour.sunOn : colour.text }}>{value}</T>
      <T v="small">{label}</T>
    </View>
  );
}

export default function Groups() {
  const guard = useGuard();
  const { state } = useSession();
  const { width } = useWindowDimensions();
  if (guard || !state) return guard;
  const groups = groupsOf(state, roomsOf(state));
  const inner = Math.min(width, 520) - 40 - 34;
  return (
    <Screen title="Groups" lead="Who works together. Each group is the people whose assistants share rooms with yours.">
      {!groups.length ? <T v="body">No groups yet. One forms when your assistant shares a room with someone else’s.</T> : null}
      {groups.map((group, i) => {
        const names = group.peers.map((id: string) => whoOf(state, id).owner);
        const rules = group.rules.map((rule: string) => RULE_WORDS[rule]?.toLowerCase()).filter(Boolean);
        return (
          <Animated.View key={group.peers.join()} entering={rowIn(i)}>
            <Card style={{ gap: 12, marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <T v="section" style={{ flex: 1 }}>You, {names.join(', ')}</T>
                {group.needsYou ? <Chip label="Needs you" tone="sun" /> : null}
              </View>
              <Constellation state={state} group={group} width={inner} />
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <Stat value={group.decided} label="Agreed" />
                <Stat value={group.passed} label="Votes passed" />
                <Stat value={group.changes} label="Changes of mind" />
                <Stat value={group.needsYou} label="Needs you" warm />
              </View>
              {rules.length ? <T v="small">Votes here are decided by {rules.join(' or ')}. Each answer is that person’s own signed yes or no.</T> : null}
              <View style={{ gap: 6 }}>
                {group.rooms.map((room: any) => (
                  <Pressable key={room.context} onPress={() => router.push({ pathname: '/rooms/[context]', params: { context: room.context } })} accessibilityRole="button"
                    style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 8, borderRadius: radius.md, backgroundColor: pressed ? colour.raised : 'transparent' })}>
                    <RoomGlyph name={room.name} tint={room.tint} size={28} />
                    <View style={{ flex: 1 }}>
                      <T v="bodyBold" numberOfLines={1}>{room.name}</T>
                      <T v="small" numberOfLines={1}>{roomLine(room)}</T>
                    </View>
                    <T v="small">›</T>
                  </Pressable>
                ))}
              </View>
            </Card>
          </Animated.View>
        );
      })}
    </Screen>
  );
}
