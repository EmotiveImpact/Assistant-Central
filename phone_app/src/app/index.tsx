// Home. A short honest paragraph with people and their assistants inline, then one decision
// at a time. Swipe right (or tap the button) to open it, left to see the next. A swipe never
// agrees to anything on its own: it only opens the decision.
import React, { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn, interpolate, useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { GestureDetector, usePanGesture, useTapGesture } from 'react-native-gesture-handler';
import Svg, { Path } from 'react-native-svg';
import * as Haptics from 'expo-haptics';
import { useGuard } from '../lib/guard';
import { cardStack, failedParts, paragraph, peerOf, queueOf, type Card as HomeCard, type Segment } from '../lib/home';
import { sayError, useSession } from '../lib/session';
import { doneLine, doneToday, isEvening, teamLine, teamsOf } from '../shared/web';
import type { Item, State } from '../lib/types';
import { cardForward, rowIn } from '../ui/motion';
import { useOverlay } from '../ui/overlay';
import { Bot, Chip, Notice, Pair, Person, T, Wordmark } from '../ui/parts';
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

const KIND: Record<string, string> = {
  question: 'A question for you', message: 'A message to send', joiner: 'Wants to connect', 'shared-draft': 'Shared draft', invite: 'An invitation', 'host-draft': 'A draft to check',
};

function kindOf(card: HomeCard) {
  const item = card.entry.item;
  if (card.entry.kind !== 'proposal' || !item) return KIND[card.entry.kind] ?? 'Needs you';
  if (item.team?.record === 'result') return 'Result to check';
  if (item.team?.record === 'access') return 'Access ask';
  if (item.team) return 'Team mission part';
  if (item.mission_cap) return 'Mission approval';
  return item.kind === 'artifact' ? 'Something to check' : 'Proposal';
}

function Arrow({ left }: { left?: boolean }) {
  return <Svg width={15} height={15} viewBox="0 0 24 24"><Path d={left ? 'M19 12H5m6-6l-6 6 6 6' : 'M5 12h14m-6-6l6 6-6 6'} stroke="#d6d2ca" strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" /></Svg>;
}

/** The live card. Drag it: right opens the decision, left puts it to the back. Never agrees. */
function TopCard({ card, index, total, onOpen, onLater, onEarlier }: { card: HomeCard; index: number; total: number; onOpen: () => void; onLater: () => void; onEarlier: () => void }) {
  const x = useSharedValue(0);
  const many = total > 1;
  const pan = usePanGesture({
    activeOffsetX: [-12, 12],
    failOffsetY: [-14, 14],
    onUpdate: e => { 'worklet'; x.value = e.translationX; },
    onDeactivate: e => {
      'worklet';
      if (e.translationX > SWIPE || e.velocityX > 900) { x.value = withSpring(0, { damping: 18, stiffness: 200 }); scheduleOnRN(onOpen); }
      else if ((e.translationX < -SWIPE || e.velocityX < -900) && many) x.value = withTiming(-560, { duration: 210 }, done => { if (done) scheduleOnRN(onLater); });
      else x.value = withSpring(0, { damping: 18, stiffness: 200 });
    },
  });
  // A tap on the card's words opens it too. It waits for the drag to fail, so the end of a
  // drag is never read as a tap, and the buttons along the bottom keep their own taps.
  const tap = useTapGesture({ maxDistance: 10, requireToFail: pan, onActivate: () => { 'worklet'; scheduleOnRN(onOpen); } });
  const style = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }, { rotate: `${interpolate(x.value, [-300, 0, 300], [-7, 0, 7])}deg` }] }));
  const openHint = useAnimatedStyle(() => ({ opacity: interpolate(x.value, [0, SWIPE], [0, 1], 'clamp') }));
  const laterHint = useAnimatedStyle(() => ({ opacity: interpolate(x.value, [-SWIPE, 0], [1, 0], 'clamp') }));
  return (
    <Animated.View entering={cardForward}>
    <GestureDetector gesture={pan}>
      <Animated.View
        accessible accessibilityRole="button" accessibilityLabel={`${kindOf(card)}. ${card.who}. ${card.entry.title}`}
        accessibilityHint={`Opens it. ${index + 1} of ${total}.`}
        accessibilityActions={[{ name: 'activate' }, ...(many ? [{ name: 'decrement', label: 'Not now' }] : [])]}
        onAccessibilityAction={e => (e.nativeEvent.actionName === 'decrement' ? onLater() : onOpen())}
        style={[styles.card, style]}>
        <GestureDetector gesture={tap}>
        <View style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Pair owner={card.owner} agent={card.agent} size={24} e="look" />
            <View style={{ flex: 1 }}>
              <Text style={{ color: colour.onText, fontFamily: font.bold, fontSize: 14 }} numberOfLines={1}>{kindOf(card)}</Text>
              <Text style={{ color: '#b9b5ad', fontFamily: font.regular, fontSize: 12 }} numberOfLines={1}>{card.team ? `${card.agent} · ${card.team}` : card.who}</Text>
            </View>
            <Text style={{ color: '#b9b5ad', fontFamily: font.semibold, fontSize: 12 }}>{index + 1} of {total}</Text>
          </View>
          <Text style={{ color: colour.onText, fontFamily: font.semibold, fontSize: 19, lineHeight: 25, letterSpacing: -0.3 }} numberOfLines={4}>{card.entry.title}</Text>
        </View>
        </GestureDetector>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16, marginTop: 4 }}>
          {many ? (
            <>
              <Pressable onPress={onLater} hitSlop={10} accessibilityRole="button" accessibilityLabel="Not now, show the next one">
                <Text style={{ color: '#d6d2ca', fontFamily: font.semibold, fontSize: 13.5 }}>Not now</Text>
              </Pressable>
              <Pressable onPress={onEarlier} hitSlop={10} accessibilityRole="button" accessibilityLabel="Previous"><Arrow left /></Pressable>
              <Pressable onPress={onLater} hitSlop={10} accessibilityRole="button" accessibilityLabel="Next"><Arrow /></Pressable>
            </>
          ) : null}
          <View style={{ flex: 1 }} />
          <Pressable onPress={onOpen} hitSlop={10} accessibilityRole="button" accessibilityLabel={card.action}>
            <Text style={{ color: colour.sun, fontFamily: font.bold, fontSize: 14.5 }}>Open ›</Text>
          </Pressable>
        </View>
        <Animated.View pointerEvents="none" style={[styles.hint, { left: 16 }, openHint]}><Text style={styles.hintText}>Open</Text></Animated.View>
        <Animated.View pointerEvents="none" style={[styles.hint, { right: 16 }, laterHint]}><Text style={styles.hintText}>Not now</Text></Animated.View>
      </Animated.View>
    </GestureDetector>
    </Animated.View>
  );
}

function Stack({ cards, total, offset, setOffset }: { cards: HomeCard[]; total: number; offset: number; setOffset: (n: number) => void }) {
  const { decide, toast } = useOverlay();
  if (!cards.length) return null;
  const open = () => { Haptics.selectionAsync().catch(() => undefined); decide(cards[0].entry.key); };
  const later = () => { setOffset(offset + 1); toast('Saved for later. It stays in the queue.'); };
  const earlier = () => setOffset(offset - 1 + total);
  return (
    <View style={{ marginTop: 26, paddingTop: cards.length > 1 ? 20 : 0 }}>
      {cards.length > 2 ? <Animated.View key={'b2' + offset} entering={FadeIn.duration(300)} style={[styles.behind, { top: 0, left: 26, right: 26, backgroundColor: colour.lineStrong }]} /> : null}
      {cards.length > 1 ? <Animated.View key={'b1' + offset} entering={FadeIn.duration(260)} style={[styles.behind, { top: 10, left: 12, right: 12, backgroundColor: colour.accent }]} /> : null}
      <TopCard key={cards[0].entry.key + offset} card={cards[0]} index={offset % total} total={total} onOpen={open} onLater={later} onEarlier={earlier} />
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

/** "Ask your assistant to start something": new work starts on the computer for now. */
function Ask({ agent }: { agent: string }) {
  const { toast } = useOverlay();
  return (
    <Pressable onPress={() => toast('Starting something new happens on your computer for now.')} accessibilityRole="button"
      accessibilityLabel={`Ask ${agent} to start something`}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 16, borderWidth: 1, borderColor: colour.line, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 10, opacity: pressed ? 0.8 : 1 })}>
      <Bot name={agent} size={24} />
      <Text style={{ flex: 1, fontFamily: font.regular, fontSize: 14.5, color: colour.muted }} numberOfLines={1}>Ask {agent} to start something…</Text>
    </Pressable>
  );
}

export default function Home() {
  const guard = useGuard();
  const { state, approvals, approvalsFailed, backend, refresh, uncertain } = useSession();
  const overlay = useOverlay();
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
          <Pressable onPress={() => overlay.toggle('avatar')} accessibilityRole="button" accessibilityLabel={`Menu for ${state.identity.owner_id}`} hitSlop={8}>
            <Person name={state.identity.owner_id} size={38} />
          </Pressable>
        </View>
        <T v="label" style={{ marginBottom: 10 }}>{when}</T>
        <Animated.View key={'p' + offset} entering={FadeIn.duration(280)}><Paragraph segments={segments} /></Animated.View>
        {uncertain ? <View style={{ marginTop: 16 }}><Notice text="An earlier step could not be confirmed. Pull down to refresh before deciding anything else." tone="danger" /></View> : null}
        {error ? <View style={{ marginTop: 16 }}><Notice text={error} tone="danger" /></View> : null}
        <Stack cards={cards} total={queue.length} offset={offset} setOffset={setOffset} />
        {evening && !queue.length ? (
          <Pressable onPress={() => router.push('/story')} accessibilityRole="button" style={{ marginTop: 24, backgroundColor: colour.raised, borderRadius: radius.card, padding: 16 }}>
            <T v="bodyBold">See today’s story</T>
            <T v="small">One tap per thing your assistant did, each with proof.</T>
          </Pressable>
        ) : null}
        <Animated.View entering={rowIn(2)}><DoneToday state={state} /></Animated.View>
        <Animated.View entering={rowIn(3)}><Ask agent={state.identity.agent_id} /></Animated.View>
        <Animated.View entering={rowIn(4)}><Teams state={state} /></Animated.View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colour.text, borderRadius: radius.lg, paddingHorizontal: 18, paddingTop: 16, paddingBottom: 14, gap: 8, minHeight: 168,
    shadowColor: '#1b1a17', shadowOpacity: 0.45, shadowRadius: 22, shadowOffset: { width: 0, height: 18 }, elevation: 10,
  },
  behind: { position: 'absolute', height: 70, borderRadius: radius.lg },
  hint: { position: 'absolute', top: 14, backgroundColor: 'rgba(255,255,255,0.14)', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  hintText: { color: '#fff', fontFamily: font.bold, fontSize: 12 },
});
