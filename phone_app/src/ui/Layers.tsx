// Everything that floats, drawn above the pages: the dim, the Decide sheet rising from the
// bottom (drag it down to put it away), the + menu fanning up from its button, your menu
// dropping from your circle, search at the top, and short notes above the glass bar.
import React, { useEffect, useMemo, useState } from 'react';
import { BackHandler, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { interpolate, useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { GestureDetector, usePanGesture } from 'react-native-gesture-handler';
import Svg, { Circle, Path } from 'react-native-svg';
import { peerOf } from '../lib/home';
import { useSession } from '../lib/session';
import { stateLabel } from '../shared/web';
import { DecideContent } from './Decide';
import { BAR } from './Glass';
import { EASE, OUT, RISE_MS, riseIn, useAppear } from './motion';
import { useOverlay } from './overlay';
import { Pair, T } from './parts';
import { colour, font } from './theme';

const SHADOW = { shadowColor: '#1b1a17', shadowOpacity: 0.3, shadowRadius: 26, shadowOffset: { width: 0, height: 18 }, elevation: 16 };

function Dim({ closing }: { closing: boolean }) {
  const { close } = useOverlay();
  const p = useAppear(closing, () => undefined, 250, 220);
  const style = useAnimatedStyle(() => ({ opacity: p.value }));
  return (
    <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: colour.backdrop }, style]}>
      <Pressable style={StyleSheet.absoluteFill} onPress={() => close()} accessibilityRole="button" accessibilityLabel="Close" />
    </Animated.View>
  );
}

/** The Decide sheet: rises from the bottom, follows your finger down, and settles back or goes. */
function Sheet({ entryKey, closing }: { entryKey: string; closing: boolean }) {
  const { close, gone } = useOverlay();
  const { height } = useWindowDimensions();
  const inset = useSafeAreaInsets();
  const y = useSharedValue(height);
  useEffect(() => { y.value = withTiming(0, { duration: RISE_MS, easing: EASE }); }, [y]);
  useEffect(() => {
    if (closing) y.value = withTiming(height, { duration: 240, easing: OUT }, finished => { if (finished) scheduleOnRN(gone); });
  }, [closing, height, y, gone]);
  const drag = usePanGesture({
    onUpdate: e => { 'worklet'; y.value = e.translationY > 0 ? e.translationY : e.translationY / 6; },
    onDeactivate: e => {
      'worklet';
      if (e.translationY > 110 || e.velocityY > 900) scheduleOnRN(close);
      else y.value = withSpring(0, { damping: 22, stiffness: 240 });
    },
  });
  const style = useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));
  return (
    <Animated.View accessibilityViewIsModal style={[styles.sheet, { maxHeight: height - inset.top - 34 }, style]}>
      <GestureDetector gesture={drag}>
        <View style={{ paddingTop: 9, paddingBottom: 6, alignItems: 'center' }} accessibilityLabel="Drag down to close">
          <View style={{ width: 38, height: 5, borderRadius: 3, backgroundColor: colour.lineStrong }} />
        </View>
      </GestureDetector>
      <ScrollView bounces={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 6, paddingBottom: inset.bottom + 22 }}>
        <DecideContent entryKey={entryKey} close={close} />
      </ScrollView>
    </Animated.View>
  );
}

function Pill({ label, onPress, index }: { label: string; onPress: () => void; index: number }) {
  return (
    <Animated.View entering={riseIn(index * 38)}>
      <Pressable onPress={onPress} accessibilityRole="button" style={({ pressed }) => [styles.pill, { opacity: pressed ? 0.85 : 1 }]}>
        <Text style={{ color: '#fff', fontFamily: font.semibold, fontSize: 14.5 }}>{label}</Text>
      </Pressable>
    </Animated.View>
  );
}

/** The + menu: dark pills fanning up from the button, the button itself turned coral to close. */
function Quick({ closing }: { closing: boolean }) {
  const { close, gone, open, toast } = useOverlay();
  const inset = useSafeAreaInsets();
  const p = useAppear(closing, gone, 200, 160);
  const style = useAnimatedStyle(() => ({ opacity: p.value }));
  const x = useAnimatedStyle(() => ({ transform: [{ rotate: `${interpolate(p.value, [0, 1], [-45, 0])}deg` }, { scale: interpolate(p.value, [0, 1], [0.8, 1]) }] }));
  const go = (path: '/invite' | '/scan') => { close(); router.push(path); };
  const items: [string, () => void][] = [
    ['Start something new', () => { close(); toast('Starting something new happens on your computer for now.'); }],
    ['Search', () => open({ kind: 'search' })],
    ['Scan an invite', () => go('/scan')],
    ['Invite someone', () => go('/invite')],
  ];
  return (
    <Animated.View style={[styles.quick, { bottom: inset.bottom + 12 }, style]} pointerEvents="box-none">
      {items.map(([label, run], i) => <Pill key={label} label={label} onPress={run} index={items.length - 1 - i} />)}
      <Pressable onPress={() => close()} accessibilityRole="button" accessibilityLabel="Close">
        <Animated.View style={[styles.qx, x]}>
          <Svg width={16} height={16} viewBox="0 0 24 24"><Path d="M6 6l12 12M18 6L6 18" stroke={colour.text} strokeWidth={2.8} strokeLinecap="round" /></Svg>
        </Animated.View>
      </Pressable>
    </Animated.View>
  );
}

/** Your menu: a white card that drops from your circle in the top corner. */
function Avatar({ closing }: { closing: boolean }) {
  const { close, gone, open } = useOverlay();
  const { state, backend, lock, leave } = useSession();
  const inset = useSafeAreaInsets();
  const p = useAppear(closing, gone, 200, 150);
  const style = useAnimatedStyle(() => ({ opacity: p.value, transform: [{ translateY: interpolate(p.value, [0, 1], [-8, 0]) }, { scale: interpolate(p.value, [0, 1], [0.96, 1]) }] }));
  if (!state || !backend) return null;
  const go = (path: '/team' | '/money' | '/invite' | '/settings' | '/recents') => { close(); router.push(path); };
  const lines: [string, () => void, ('danger' | undefined)?][] = [
    ['Team missions', () => go('/team')],
    ['Money and assistants', () => go('/money')],
    ['Recents', () => go('/recents')],
    ['Search', () => open({ kind: 'search' })],
    ['Invite someone', () => go('/invite')],
    ['Settings', () => go('/settings')],
    backend.mode === 'demo'
      ? ['Leave the demo', async () => { close(); await leave(); router.replace('/welcome'); }]
      : ['Lock Parlu', () => { close(); lock('Locked. Type your password to carry on.'); router.replace('/unlock'); }],
  ];
  return (
    <Animated.View style={[styles.amenu, { top: inset.top + 54 }, style]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 10, paddingTop: 8, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: colour.lineSoft, marginBottom: 4 }}>
        <Pair owner={state.identity.owner_id} agent={state.identity.agent_id} size={26} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: font.bold, fontSize: 14, color: colour.text, textTransform: 'capitalize' }}>{state.identity.owner_id}</Text>
          <Text style={{ fontFamily: font.regular, fontSize: 12, color: colour.muted }}>{state.identity.agent_id} is ready</Text>
        </View>
      </View>
      {lines.map(([label, run]) => (
        <Pressable key={label} onPress={run} accessibilityRole="button" style={({ pressed }) => ({ paddingHorizontal: 10, paddingVertical: 10, borderRadius: 12, backgroundColor: pressed ? colour.raised : 'transparent' })}>
          <Text style={{ fontFamily: font.semibold, fontSize: 14.5, color: colour.text }}>{label}</Text>
        </Pressable>
      ))}
    </Animated.View>
  );
}

type Hit = { key: string; title: string; note: string; run: () => void; owner?: string; agent?: string };

/** Search: a floating card at the top. Work, people and places, as you type. */
function Search({ closing }: { closing: boolean }) {
  const { close, gone, decide } = useOverlay();
  const { state } = useSession();
  const inset = useSafeAreaInsets();
  const [text, setText] = useState('');
  const p = useAppear(closing, gone, 220, 150);
  const style = useAnimatedStyle(() => ({ opacity: p.value, transform: [{ translateY: interpolate(p.value, [0, 1], [-10, 0]) }] }));
  const hits = useMemo<Hit[]>(() => {
    if (!state) return [];
    const q = text.trim().toLowerCase();
    const has = (...words: (string | undefined)[]) => !q || words.some(w => (w ?? '').toLowerCase().includes(q));
    const go = (path: '/recents' | '/team' | '/money' | '/invite' | '/settings') => () => { close(); router.push(path); };
    const work = [...state.items].sort((a, b) => b.created_at - a.created_at).filter(i => has(i.title, i.context)).slice(0, q ? 6 : 4).map(i => {
      const peer = peerOf(state, i);
      return { key: 'i' + i.id, title: i.title, note: stateLabel(i.state) as string, owner: peer?.owner_id, agent: peer?.agent_id, run: () => decide('item:' + i.id) };
    });
    const people = q ? state.peers.filter(x => has(x.owner_id, x.agent_id)).slice(0, 4).map(x => ({ key: 'p' + x.peer_id, title: `${x.agent_id}, ${x.owner_id}’s assistant`, note: 'Connected', owner: x.owner_id, agent: x.agent_id, run: go('/money') })) : [];
    const places = ([['Recents', '/recents'], ['Team missions', '/team'], ['Money and assistants', '/money'], ['Invite someone', '/invite'], ['Settings', '/settings']] as const)
      .filter(([label]) => has(label)).map(([label, path]) => ({ key: 'g' + path, title: label, note: 'Go to', run: go(path) }));
    return [...work, ...people, ...places];
  }, [state, text, close, decide]);
  return (
    <Animated.View style={[styles.search, { top: inset.top + 46 }, style]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colour.line }}>
        <Svg width={18} height={18} viewBox="0 0 24 24"><Circle cx={11} cy={11} r={6.5} stroke={colour.muted} strokeWidth={2} fill="none" /><Path d="M16 16l4 4" stroke={colour.muted} strokeWidth={2} strokeLinecap="round" /></Svg>
        <TextInput value={text} onChangeText={setText} autoFocus placeholder="Search work, people and places" placeholderTextColor={colour.faint}
          accessibilityLabel="Search" returnKeyType="search" autoCorrect={false}
          style={{ flex: 1, fontFamily: font.medium, fontSize: 16, color: colour.text, paddingVertical: 2 }} />
      </View>
      <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 380 }} contentContainerStyle={{ padding: 6 }}>
        {hits.length ? hits.map(hit => (
          <Pressable key={hit.key} onPress={hit.run} accessibilityRole="button" style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 12, backgroundColor: pressed ? colour.raised : 'transparent' })}>
            {hit.owner && hit.agent ? <Pair owner={hit.owner} agent={hit.agent} size={20} /> : <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colour.raised }} />}
            <Text style={{ flex: 1, fontFamily: font.semibold, fontSize: 14.5, color: colour.text }} numberOfLines={1}>{hit.title}</Text>
            <Text style={{ fontFamily: font.regular, fontSize: 12, color: colour.muted }}>{hit.note}</Text>
          </Pressable>
        )) : <T v="small" style={{ padding: 12 }}>Nothing matches “{text.trim()}”.</T>}
      </ScrollView>
    </Animated.View>
  );
}

/** A short note above the glass bar, gone after a few seconds. */
function Toast() {
  const { note, clearNote } = useOverlay();
  if (!note) return null;
  return <ToastLine key={note.id} id={note.id} text={note.text} clear={clearNote} />;
}

function ToastLine({ id, text, clear }: { id: number; text: string; clear: (id: number) => void }) {
  const inset = useSafeAreaInsets();
  const [closing, setClosing] = useState(false);
  useEffect(() => { const t = setTimeout(() => setClosing(true), 2600); return () => clearTimeout(t); }, []);
  const p = useAppear(closing, () => clear(id), 250, 200);
  const style = useAnimatedStyle(() => ({ opacity: p.value, transform: [{ translateY: interpolate(p.value, [0, 1], [10, 0]) }] }));
  return (
    <Animated.View pointerEvents="none" accessibilityLiveRegion="polite" accessibilityRole="alert" style={[styles.toastWrap, { bottom: inset.bottom + BAR + 26 }, style]}>
      <View style={styles.toast}><Text style={{ color: '#fff', fontFamily: font.semibold, fontSize: 13.5, textAlign: 'center' }}>{text}</Text></View>
    </Animated.View>
  );
}

export function Layers() {
  const { layer, closing, close } = useOverlay();
  useEffect(() => {
    if (!layer) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => { close(); return true; });
    return () => sub.remove();
  }, [layer, close]);
  return (
    <>
      {layer ? <Dim closing={closing} /> : null}
      {layer?.kind === 'decide' ? <Sheet key={layer.key} entryKey={layer.key} closing={closing} /> : null}
      {layer?.kind === 'plus' ? <Quick closing={closing} /> : null}
      {layer?.kind === 'avatar' ? <Avatar closing={closing} /> : null}
      {layer?.kind === 'search' ? <Search closing={closing} /> : null}
      <Toast />
    </>
  );
}

const styles = StyleSheet.create({
  sheet: { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: colour.bg, borderTopLeftRadius: 28, borderTopRightRadius: 28, ...SHADOW },
  quick: { position: 'absolute', right: 14, alignItems: 'flex-end', gap: 9 },
  pill: { backgroundColor: colour.text, borderWidth: 1, borderColor: colour.secondary, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 12 },
  qx: { width: BAR, height: BAR, borderRadius: BAR / 2, backgroundColor: colour.sun, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  amenu: { position: 'absolute', right: 12, width: 250, backgroundColor: colour.bg, borderRadius: 20, padding: 8, ...SHADOW, shadowOpacity: 0.22 },
  search: { position: 'absolute', left: 10, right: 10, backgroundColor: colour.bg, borderRadius: 20, ...SHADOW },
  toastWrap: { position: 'absolute', left: 20, right: 20, alignItems: 'center' },
  toast: { backgroundColor: colour.text, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 10, maxWidth: 360 },
});
