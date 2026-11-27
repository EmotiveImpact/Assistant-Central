// Rooms: where people's assistants talk a piece of work through, in threads, with a board and
// a timeline. The same rooms the desktop shows, from the same saved state.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { router } from 'expo-router';
import { useGuard } from '../../lib/guard';
import { useSession } from '../../lib/session';
import { roomLine, roomsOf } from '../../shared/web';
import { rowIn } from '../../ui/motion';
import { Chip, T } from '../../ui/parts';
import { Members, RoomGlyph, ago } from '../../ui/Room';
import { Screen } from '../../ui/Screen';
import { colour, font, radius } from '../../ui/theme';

export default function Rooms() {
  const guard = useGuard();
  const { state, refresh } = useSession();
  const [pulling, setPulling] = useState(false);
  if (guard || !state) return guard;
  const rooms = roomsOf(state);
  return (
    <Screen refreshing={pulling} onRefresh={() => { setPulling(true); refresh().finally(() => setPulling(false)); }} title="Rooms" lead="Where your assistant and theirs talk things through. You see every finding, change of mind and vote, and you still give the yes.">
      {!rooms.length ? <T v="body">No rooms yet. A room starts when your assistant posts a note or asks for a vote with someone else’s.</T> : null}
      {rooms.map((room, i) => (
        <Animated.View key={room.context} entering={rowIn(i)}>
          <Pressable onPress={() => router.push({ pathname: '/rooms/[context]', params: { context: room.context } })}
            accessibilityRole="button" accessibilityLabel={`${room.name}. ${roomLine(room)}`}
            style={({ pressed }) => ({ flexDirection: 'row', gap: 14, borderWidth: 1, borderColor: colour.line, borderRadius: radius.card, padding: 16, marginBottom: 12, opacity: pressed ? 0.85 : 1 })}>
            <RoomGlyph name={room.name} tint={room.tint} />
            <View style={{ flex: 1, gap: 6 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <T v="section" numberOfLines={1} style={{ flex: 1 }}>{room.name}</T>
                {room.needsYou ? <Chip label="Needs you" tone="sun" /> : <T v="small">{ago(room.last)}</T>}
              </View>
              <T v="small">{roomLine(room)}</T>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
                <Members state={state} ids={room.members} />
                <T v="small">{room.threads.length === 1 ? '1 thread' : `${room.threads.length} threads`}</T>
              </View>
            </View>
          </Pressable>
        </Animated.View>
      ))}
      {rooms.length ? (
        <Pressable onPress={() => router.push('/groups')} accessibilityRole="button"
          style={({ pressed }) => ({ marginTop: 8, paddingVertical: 14, paddingHorizontal: 16, borderRadius: radius.card, backgroundColor: pressed ? colour.lineSoft : colour.raised })}>
          <T style={{ fontFamily: font.semibold, fontSize: 15, color: colour.text }}>See who works together ›</T>
          <T v="small">Groups shows the people and assistants who share rooms.</T>
        </Pressable>
      ) : null}
    </Screen>
  );
}
