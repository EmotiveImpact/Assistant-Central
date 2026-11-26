// Assistants: the people you work with, each beside their assistant. Big cards as on the
// live web app, in the mock's plain words, with the same labels as the web app. A short key
// sits on each card; the shared work opens underneath when you tap it.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import Animated, { FadeIn, LinearTransition } from 'react-native-reanimated';
import { router } from 'expo-router';
import { useGuard } from '../lib/guard';
import { queueOf } from '../lib/home';
import { useSession } from '../lib/session';
import type { Item, Peer } from '../lib/types';
import { shortKey, stateLabel } from '../shared/web';
import { rowIn } from '../ui/motion';
import { useOverlay } from '../ui/overlay';
import { Button, Chip, Pair, T, type Expression } from '../ui/parts';
import { Screen } from '../ui/Screen';
import { colour, font } from '../ui/theme';

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** The status chip, worded as on the web app. Autonomy settings can let an assistant act
 * without asking for some things, so the chip never promises that it always asks. */
function ruleOf(peer: Peer | 'yours'): { label: string; tone: 'plain' | 'accent' | 'sun' } {
  if (peer === 'yours') return { label: 'Your assistant', tone: 'accent' };
  if (peer.state === 'active') return { label: 'Connected', tone: 'plain' };
  if (peer.state === 'revoked') return { label: 'Removed', tone: 'plain' };
  return { label: 'Not checked yet', tone: 'sun' };
}

const keyOf = (fingerprint?: string) => fingerprint && fingerprint.length >= 8 ? (shortKey(fingerprint) as string).toUpperCase() : undefined;

function Big({ owner, agent, title, line, rule, e, waiting, dim, fullKey, work, onOpenWork }: {
  owner: string; agent: string; title: string; line: string; rule: ReturnType<typeof ruleOf>; e: Expression;
  waiting: number; dim?: boolean; fullKey?: string; work: Item[]; onOpenWork: (id: string) => void;
}) {
  const keyText = keyOf(fullKey);
  const [open, setOpen] = useState(false);
  return (
    <Animated.View layout={LinearTransition.duration(220)}
      style={{ borderWidth: 1, borderColor: waiting ? colour.sun : colour.line, borderRadius: 22, backgroundColor: colour.surface, opacity: dim ? 0.6 : 1, overflow: 'hidden' }}>
      <Pressable onPress={() => setOpen(v => !v)} accessibilityRole="button" accessibilityState={{ expanded: open }}
        accessibilityLabel={`${title}. ${line}. ${rule.label}.${waiting ? ` ${waiting} waiting for you.` : ''}`}
        style={({ pressed }) => ({ padding: 18, gap: 14, backgroundColor: pressed ? colour.raised : 'transparent' })}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <Pair owner={owner} agent={agent} size={44} e={e} />
          <View style={{ flex: 1, gap: 2 }}>
            <T style={{ fontFamily: font.extrabold, fontSize: 21, lineHeight: 26, letterSpacing: -0.4, color: colour.text }}>{title}</T>
            <T v="small">{line}</T>
          </View>
          {keyText ? (
            <View style={{ alignSelf: 'flex-start', backgroundColor: colour.raised, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 3 }}>
              <T v="mono" numberOfLines={1} style={{ fontSize: 11, color: colour.muted }} accessibilityLabel={`Key ${keyText}`}>{keyText}</T>
            </View>
          ) : null}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 12, borderTopWidth: 1, borderTopColor: colour.lineSoft }}>
          <Chip label={rule.label} tone={rule.tone} />
          {waiting ? <Chip label={`${waiting} waiting for you`} tone="sun" /> : null}
          <View style={{ flex: 1 }} />
          <T style={{ fontFamily: font.semibold, fontSize: 13, color: colour.accentFg }}>{open ? 'Less' : 'More'}</T>
        </View>
      </Pressable>
      {open ? (
        <Animated.View entering={FadeIn.duration(200)} style={{ paddingHorizontal: 18, paddingBottom: 18, gap: 10 }}>
          {fullKey ? (
            <View style={{ backgroundColor: colour.raised, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 10, gap: 2 }}>
              <T v="small">Full key</T>
              <T v="mono" style={{ fontSize: 11.5 }} selectable>{fullKey}</T>
            </View>
          ) : null}
          {work.length ? work.slice(0, 4).map(item => (
            <Pressable key={item.id} onPress={() => onOpenWork(item.id)} accessibilityRole="button"
              style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, opacity: pressed ? 0.6 : 1 })}>
              <T v="bodyBold" style={{ flex: 1 }} numberOfLines={1}>{item.title}</T>
              <T v="small">{stateLabel(item.state)}</T>
            </Pressable>
          )) : <T v="small">No shared work yet.</T>}
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

export default function Assistants() {
  const guard = useGuard();
  const { state, approvals } = useSession();
  const { decide } = useOverlay();
  if (guard || !state) return guard;
  const waitingBy = new Map<string, number>();
  for (const entry of queueOf(state, approvals)) {
    const id = entry.item?.peer_id;
    if (id) waitingBy.set(id, (waitingBy.get(id) ?? 0) + 1);
  }
  const peers = [...state.peers].sort((a, b) => Number(b.state === 'active') - Number(a.state === 'active'));
  const active = peers.filter(p => p.state === 'active').length;
  const me = state.identity;
  const myKey = (me as { fingerprint?: string }).fingerprint;
  const open = (id: string) => decide('item:' + id);
  return (
    <Screen title="Assistants" lead="The people you work with, beside their assistants.">
      <View style={{ gap: 12 }}>
        <Animated.View entering={rowIn(0)}>
          <Big owner={me.owner_id} agent={me.agent_id} title={me.agent_id} line={`Yours · ${cap(me.owner_id)}`}
            rule={ruleOf('yours')} e="idle" waiting={0} fullKey={myKey}
            work={[]} onOpenWork={open} />
        </Animated.View>
        {peers.map((p, i) => (
          <Animated.View key={p.peer_id} entering={rowIn(i + 1)}>
            <Big owner={p.owner_id} agent={p.agent_id} title={p.agent_id} line={`${cap(p.owner_id)}’s assistant`}
              rule={ruleOf(p)} e={p.state !== 'active' ? 'sleep' : waitingBy.has(p.peer_id) ? 'look' : 'idle'}
              waiting={waitingBy.get(p.peer_id) ?? 0} dim={p.state === 'revoked'}
              fullKey={p.fingerprint ?? p.peer_id}
              work={state.items.filter(item => item.peer_id === p.peer_id).sort((a, b) => b.created_at - a.created_at)}
              onOpenWork={open} />
          </Animated.View>
        ))}
      </View>
      <T v="small" style={{ marginTop: 14, textAlign: 'center' }}>
        {active === 1 ? '1 assistant connected' : `${active} assistants connected`}
      </T>
      <View style={{ marginTop: 16 }}>
        <Button label="Invite someone" kind="secondary" onPress={() => router.push('/invite')} />
      </View>
    </Screen>
  );
}
