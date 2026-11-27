// The small pieces the room screens share: the room's glyph, who said something, the tally of a
// vote and the segmented tabs. Every word and number comes from workspace_ui/rooms.mjs.
import React from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import Animated, { LinearTransition } from 'react-native-reanimated';
import type { State } from '../lib/types';
import { EASE } from './motion';
import { Pair, T } from './parts';
import { colour, font, radius } from './theme';

/** Who an entry or event belongs to, as a pair of names. "you" is your own assistant. */
export function whoOf(state: State, who: string) {
  if (who === 'you') return { owner: state.identity.owner_id, agent: state.identity.agent_id, yours: true };
  const peer = state.peers.find(p => p.peer_id === who);
  return { owner: peer?.owner_id ?? 'Someone', agent: peer?.agent_id ?? 'Assistant', yours: false };
}

/** A short spoken name: "You" for your own side, otherwise the assistant's name. */
export const speaker = (state: State) => (who: string) => who === 'room' ? 'The room' : who === 'you' ? 'You' : whoOf(state, who).agent;

/** The room's mark: a rounded square in the room's tint with its first letter. */
export function RoomGlyph({ name, tint, size = 40 }: { name: string; tint: string; size?: number }) {
  const letter = [...String(name || '?').replace(/^[^\p{L}\p{N}]+/u, '')][0] ?? '?';
  return (
    <View style={{ width: size, height: size, borderRadius: size * 0.3, backgroundColor: tint, alignItems: 'center', justifyContent: 'center' }} accessibilityElementsHidden importantForAccessibility="no">
      <T style={{ color: '#fff', fontFamily: font.bold, fontSize: size * 0.44, lineHeight: size * 0.56 }}>{letter.toUpperCase()}</T>
    </View>
  );
}

/** The assistants in a room, each beside its person, never overlapping. */
export function Members({ state, ids, size = 22 }: { state: State; ids: string[]; size?: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      {ids.slice(0, 5).map(id => {
        const w = whoOf(state, id);
        return <Pair key={id} owner={w.owner} agent={w.agent} size={size} />;
      })}
      {ids.length > 5 ? <T v="small">+{ids.length - 5}</T> : null}
    </View>
  );
}

/** A vote's tally: yes in teal, no in coral, waiting in grey, with the rule written out. */
export function Tally({ result, rule }: { result: { yes: number; no: number; open: number; total: number; outcome: string }; rule: string }) {
  const share = (n: number) => `${result.total ? (n / result.total) * 100 : 0}%` as const;
  const word = result.outcome === 'passed' ? 'Passed' : result.outcome === 'failed' ? 'Did not pass' : 'Open';
  return (
    <View style={{ gap: 6 }} accessible accessibilityLabel={`${word}. ${result.yes} yes, ${result.no} no, ${result.open} waiting, of ${result.total}. ${rule}.`}>
      <View style={{ flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', backgroundColor: colour.raised }}>
        <Animated.View layout={LinearTransition.duration(260).easing(EASE)} style={{ width: share(result.yes), backgroundColor: colour.accent }} />
        <Animated.View layout={LinearTransition.duration(260).easing(EASE)} style={{ width: share(result.no), backgroundColor: colour.sun }} />
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <T v="small"><T v="smallBold" style={{ color: result.outcome === 'passed' ? colour.accentFg : result.outcome === 'failed' ? colour.sunOn : colour.text }}>{word}</T>, {result.yes} of {result.total} yes</T>
        <T v="small">{rule}</T>
      </View>
    </View>
  );
}

/** Segmented tabs on a raised pill, the same as the team mission screen. */
export function Segments<K extends string>({ tabs, tab, setTab }: { tabs: readonly K[]; tab: K; setTab: (t: K) => void }) {
  return (
    <View style={{ flexDirection: 'row', backgroundColor: colour.raised, borderRadius: radius.pill, padding: 4, marginVertical: 16 }} accessibilityRole="tablist">
      {tabs.map(name => (
        <Pressable key={name} onPress={() => setTab(name)} accessibilityRole="tab" accessibilityState={{ selected: tab === name }}
          style={{ flex: 1, paddingVertical: 9, borderRadius: radius.pill, alignItems: 'center', backgroundColor: tab === name ? colour.bg : 'transparent' }}>
          <T style={{ fontFamily: font.semibold, fontSize: 15, color: tab === name ? colour.text : colour.muted }}>{name}</T>
        </Pressable>
      ))}
    </View>
  );
}

/** A row of small filter chips that scrolls sideways when it runs out of room. */
export function Filters({ options, value, onChange }: { options: readonly (readonly [string, string])[]; value: string; onChange: (v: string) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingBottom: 12 }} style={{ marginHorizontal: -20 }}>
      <View style={{ width: 14 }} />
      {options.map(([id, label]) => {
        const on = id === value;
        return (
          <Pressable key={id} onPress={() => onChange(id)} accessibilityRole="button" accessibilityState={{ selected: on }}
            style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.pill, borderWidth: 1, borderColor: on ? colour.text : colour.line, backgroundColor: on ? colour.text : colour.bg }}>
            <T style={{ fontFamily: font.semibold, fontSize: 13, color: on ? colour.onText : colour.secondary }}>{label}</T>
          </Pressable>
        );
      })}
      <View style={{ width: 14 }} />
    </ScrollView>
  );
}

/** When something happened, in plain words. */
export function ago(at: number | null | undefined, now = Date.now() / 1000) {
  if (!at) return '';
  const minutes = Math.max(0, Math.round((now - at) / 60));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
