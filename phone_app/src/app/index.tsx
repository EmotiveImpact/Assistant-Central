// Home. A short honest paragraph with people and their assistants inline, then one decision
// at a time. Swipe right (or tap the button) to open it, left to see the next. A swipe never
// agrees to anything on its own: it only opens the decision.
import React, { useMemo, useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';
import { useGuard } from '../lib/guard';
import { cardStack, failedParts, paragraph, peerOf, queueOf, type Card as HomeCard, type Segment } from '../lib/home';
import { sayError, useSession } from '../lib/session';
import { doneLine, doneToday, isEvening, teamLine, teamsOf } from '../shared/web';
import type { Item, State } from '../lib/types';
import { Chip, Notice, Pair, Person, T, Wordmark } from '../ui/parts';
import { colour, font, radius } from '../ui/theme';

const SWIPE = 110;

function Paragraph({ segments }: { segments: Segment[] }) {
  return (
    <Text accessibilityRole="header" style={{ fontFamily: font.semibold, fontSize: 27, lineHeight: 36, letterSpacing: -0.7, color: colour.faint }}>
      {segments.map((s, i) => 'pair' in s
        ? <View key={i} style={{ transform: [{ translateY: 5 }], paddingHorizontal: 2 }}><Pair owner={s.pair.owner} agent={s.pair.agent} size={22} e="look" /></View>
        : <Text key={i} style={s.bold ? { color: colour.text, fontFamily: font.bold } : undefined}>{s.text}</Text>)}
    </Text>
  );
}

function TopCard({ card, index, total, onOpen, onLater }: { card: HomeCard; index: number; total: number; onOpen: () => void; onLater: () => void }) {
  const pan = useRef(new Animated.ValueXY()).current;
  const responder = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy),
    onPanResponderMove: Animated.event([null, { dx: pan.x }], { useNativeDriver: false }),
    onPanResponderRelease: (_, g) => {
      const reset = () => Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
      if (g.dx > SWIPE) { reset(); onOpen(); }
      else if (g.dx < -SWIPE && total > 1) { Animated.timing(pan, { toValue: { x: -500, y: 0 }, duration: 160, useNativeDriver: false }).start(() => { pan.setValue({ x: 0, y: 0 }); onLater(); }); }
      else reset();
    },
    onPanResponderTerminate: () => Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start(),
  }), [pan, onOpen, onLater, total]);
  const rotate = pan.x.interpolate({ inputRange: [-300, 0, 300], outputRange: ['-8deg', '0deg', '8deg'] });
  return (
    <Animated.View {...responder.panHandlers}
      accessible accessibilityRole="button" accessibilityLabel={`${card.who}. ${card.lead ? card.lead + '. ' : ''}${card.entry.title}`}
      accessibilityHint={`Opens it. ${index + 1} of ${total}.`}
      accessibilityActions={[{ name: 'activate' }, ...(total > 1 ? [{ name: 'decrement', label: 'Not now' }] : [])]}
      onAccessibilityAction={e => (e.nativeEvent.actionName === 'decrement' ? onLater() : onOpen())}
      style={{ transform: [{ translateX: pan.x }, { rotate }], backgroundColor: colour.text, borderRadius: radius.lg, padding: 18, gap: 12, minHeight: 196 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Pair owner={card.owner} agent={card.agent} size={26} e="look" />
        <View style={{ flex: 1 }}>
          <Text style={{ color: colour.onText, fontFamily: font.semibold, fontSize: 14 }} numberOfLines={1}>{card.who}</Text>
          <Text style={{ color: '#b9b5ad', fontFamily: font.regular, fontSize: 12 }} numberOfLines={1}>{card.team || card.lead || 'Needs your decision'} · {index + 1} of {total}</Text>
        </View>
      </View>
      <Text style={{ color: colour.onText, fontFamily: font.semibold, fontSize: 21, lineHeight: 28, letterSpacing: -0.3, flex: 1 }} numberOfLines={4}>{card.entry.title}</Text>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        {total > 1 ? (
          <Pressable onPress={onLater} hitSlop={10} accessibilityRole="button" accessibilityLabel="Not now, show the next one">
            <Text style={{ color: '#d6d2ca', fontFamily: font.semibold, fontSize: 14 }}>← Not now</Text>
          </Pressable>
        ) : <View />}
        <Pressable onPress={onOpen} hitSlop={10} accessibilityRole="button" accessibilityLabel={card.action}>
          <Text style={{ color: colour.sun, fontFamily: font.bold, fontSize: 15 }}>{card.action} →</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

function Stack({ cards, total, offset, setOffset }: { cards: HomeCard[]; total: number; offset: number; setOffset: (n: number) => void }) {
  if (!cards.length) return null;
  const open = () => router.push({ pathname: '/decide', params: { key: cards[0].entry.key } });
  return (
    <View style={{ marginTop: 28, paddingTop: cards.length > 1 ? 18 : 0 }}>
      {cards.length > 2 ? <View style={{ position: 'absolute', top: 0, left: 28, right: 28, height: 60, borderRadius: radius.lg, backgroundColor: colour.lineStrong }} /> : null}
      {cards.length > 1 ? <View style={{ position: 'absolute', top: 9, left: 14, right: 14, height: 60, borderRadius: radius.lg, backgroundColor: colour.accent }} /> : null}
      <TopCard key={cards[0].entry.key} card={cards[0]} index={offset % total} total={total} onOpen={open} onLater={() => setOffset(offset + 1)} />
    </View>
  );
}

function DoneToday({ state }: { state: State }) {
  const done = doneToday(state.items) as Item[];
  if (!done.length) return null;
  const first = done[0], peer = peerOf(state, first);
  return (
    <Pressable onPress={() => router.push('/recents')} accessibilityRole="button" accessibilityLabel={`Done today: ${first.title}. See all.`}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 22 }}>
      <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: colour.accentBg, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={12} height={12} viewBox="0 0 24 24"><Path d="M5 12.5l4.5 4.5L19 7.5" stroke={colour.accentFg} strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" /></Svg>
      </View>
      <Text style={{ flex: 1, fontFamily: font.regular, fontSize: 14, color: colour.muted }} numberOfLines={2}>
        <Text style={{ fontFamily: font.semibold, color: colour.secondary }}>Done today: </Text>{first.title}, {doneLine(first, peer).toLowerCase()}{done.length > 1 ? `, and ${done.length - 1} more` : ''}. <Text style={{ color: colour.accentFg, fontFamily: font.semibold }}>See all</Text>
      </Text>
    </Pressable>
  );
}

function Teams({ state }: { state: State }) {
  const teams = teamsOf(state) as ReturnType<typeof teamsOf>;
  if (!teams.length) return null;
  const team = teams[0];
  return (
    <Pressable onPress={() => router.push({ pathname: '/team/[context]', params: { context: team.context } })} accessibilityRole="button"
      accessibilityLabel={`Team mission ${team.title}. ${teamLine(team)}`}
      style={({ pressed }) => ({ marginTop: 18, borderWidth: 1, borderColor: colour.line, borderRadius: radius.card, padding: 14, gap: 8, opacity: pressed ? 0.85 : 1 })}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <T v="label">Team mission</T>
        {team.parts.some((p: { needsYou: boolean }) => p.needsYou) ? <Chip label="Needs you" tone="sun" /> : null}
      </View>
      <T v="section">{team.title}</T>
      <T v="small" numberOfLines={2}>{teamLine(team)}</T>
    </Pressable>
  );
}

function Bar() {
  const inset = useSafeAreaInsets();
  const glass = { backgroundColor: 'rgba(255,255,255,0.94)', borderWidth: 1, borderColor: colour.line, shadowColor: '#1b1a17', shadowOpacity: 0.1, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 4 };
  return (
    <View style={{ position: 'absolute', left: 16, right: 16, bottom: inset.bottom + 10, flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      <View accessibilityRole="button" accessibilityLabel="Home" accessibilityState={{ selected: true }} style={{ width: 54, height: 54, borderRadius: 27, backgroundColor: colour.text, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={22} height={22} viewBox="0 0 24 24"><Path d="M4 11l8-6.5 8 6.5V20h-5.5v-5h-5v5H4z" stroke={colour.onText} strokeWidth={1.7} fill="none" strokeLinejoin="round" /></Svg>
      </View>
      <Pressable onPress={() => router.push('/recents')} accessibilityRole="button" accessibilityLabel="Recents"
        style={[{ flex: 1, height: 54, borderRadius: 27, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }, glass]}>
        <Svg width={18} height={18} viewBox="0 0 24 24"><Circle cx={12} cy={12} r={8.5} stroke={colour.text} strokeWidth={1.7} fill="none" /><Path d="M12 7.5V12l3 2" stroke={colour.text} strokeWidth={1.7} fill="none" strokeLinecap="round" /></Svg>
        <Text style={{ fontFamily: font.semibold, fontSize: 16, color: colour.text }}>Recents</Text>
      </Pressable>
      <Pressable onPress={() => router.push('/invite')} accessibilityRole="button" accessibilityLabel="Invite someone or join"
        style={[{ width: 54, height: 54, borderRadius: 27, alignItems: 'center', justifyContent: 'center' }, glass]}>
        <Svg width={20} height={20} viewBox="0 0 24 24"><Path d="M12 5v14M5 12h14" stroke={colour.text} strokeWidth={1.8} strokeLinecap="round" /></Svg>
      </Pressable>
    </View>
  );
}

export default function Home() {
  const guard = useGuard();
  const { state, approvals, approvalsFailed, backend, refresh, uncertain } = useSession();
  const inset = useSafeAreaInsets();
  const [offset, setOffset] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  if (guard || !state || !backend) return guard;

  const now = new Date(), hour = now.getHours();
  const queue = queueOf(state, approvals);
  const failed = failedParts(approvals, approvalsFailed);
  const segments = paragraph(state, queue, failed, hour, offset);
  const cards = cardStack(state, queue, offset);
  const evening = isEvening(hour) && (doneToday(state.items) as Item[]).length > 0;
  const when = now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }) + ' · ' + now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const pull = async () => { setRefreshing(true); setError(''); try { await refresh(); } catch (e) { setError(sayError(e)); } finally { setRefreshing(false); } };

  return (
    <View style={{ flex: 1, backgroundColor: colour.bg }}>
      <ScrollView contentContainerStyle={{ paddingTop: inset.top + 10, paddingHorizontal: 20, paddingBottom: inset.bottom + 110 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={pull} tintColor={colour.accent} />}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Wordmark size={21} />
            {backend.mode === 'demo' ? <Chip label="Demo" /> : null}
          </View>
          <Pressable onPress={() => router.push('/menu')} accessibilityRole="button" accessibilityLabel={`Menu for ${state.identity.owner_id}`} hitSlop={8}>
            <Person name={state.identity.owner_id} size={38} />
          </Pressable>
        </View>
        <T v="label" style={{ marginBottom: 10 }}>{when}</T>
        <Paragraph segments={segments} />
        {uncertain ? <View style={{ marginTop: 16 }}><Notice text="An earlier step could not be confirmed. Pull down to refresh before deciding anything else." tone="danger" /></View> : null}
        {error ? <View style={{ marginTop: 16 }}><Notice text={error} tone="danger" /></View> : null}
        <Stack cards={cards} total={queue.length} offset={offset} setOffset={setOffset} />
        {evening && !queue.length ? (
          <Pressable onPress={() => router.push('/story')} accessibilityRole="button" style={{ marginTop: 24, backgroundColor: colour.raised, borderRadius: radius.card, padding: 16 }}>
            <T v="bodyBold">See today’s story</T>
            <T v="small">One tap per thing your assistant did, each with proof.</T>
          </Pressable>
        ) : null}
        <DoneToday state={state} />
        <Teams state={state} />
      </ScrollView>
      <Bar />
    </View>
  );
}
