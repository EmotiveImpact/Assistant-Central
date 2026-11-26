// Recents: what happened, newest first, and every piece of work with where it stands.
import React, { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useGuard } from '../lib/guard';
import { peerOf } from '../lib/home';
import { sayError, useSession } from '../lib/session';
import { stateLabel } from '../shared/web';
import type { Item, TimelineEntry } from '../lib/types';
import { Chip, Notice, Pair, T } from '../ui/parts';
import { Screen } from '../ui/Screen';
import { colour } from '../ui/theme';

const when = (seconds: number) => {
  const d = new Date(seconds * 1000), today = new Date();
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === today.toDateString() ? `Today, ${time}` : `${d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}, ${time}`;
};

const tone = (item: Item) => item.state === 'accepted' ? 'done' : item.state === 'pending' && item.direction === 'incoming' ? 'sun' : 'plain';

function summary(entry: TimelineEntry) {
  const text = entry.detail?.summary;
  if (typeof text === 'string' && text) return text;
  return entry.kind.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
}

export default function Recents() {
  const guard = useGuard();
  const { backend, state, refresh } = useSession();
  const [timeline, setTimeline] = useState<TimelineEntry[] | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => { backend?.timeline().then(setTimeline, e => setError(sayError(e))); }, [backend, state]);
  if (guard || !state) return guard;
  const items = [...state.items].sort((a, b) => b.created_at - a.created_at);
  const pull = async () => { setRefreshing(true); try { await refresh(); } catch (e) { setError(sayError(e)); } finally { setRefreshing(false); } };
  return (
    <Screen title="Recents" lead="Newest first. Only you can see this." refreshing={refreshing} onRefresh={pull}>
      <Notice text={error} tone="danger" />
      {timeline && timeline.length ? (
        <View style={{ marginBottom: 26 }}>
          <T v="label" style={{ marginBottom: 6 }}>What happened</T>
          {[...timeline].reverse().slice(0, 30).map(entry => (
            <View key={entry.seq} style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colour.line, gap: 2 }}>
              <T v="body" style={{ color: colour.text }}>{summary(entry)}</T>
              <T v="small">{when(entry.at)}</T>
            </View>
          ))}
        </View>
      ) : null}
      <T v="label" style={{ marginBottom: 6 }}>All work</T>
      {items.map(item => {
        const peer = peerOf(state, item);
        const open = () => router.push({ pathname: '/decide', params: { key: 'item:' + item.id } });
        return (
          <Pressable key={item.id} style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colour.line, opacity: pressed ? 0.7 : 1 })}
            accessibilityRole="button" accessibilityLabel={`${item.title}. ${stateLabel(item.state)}.`} onPress={open}>
            <Pair owner={peer?.owner_id ?? '?'} agent={peer?.agent_id ?? 'Assistant'} size={22} />
            <View style={{ flex: 1, gap: 2 }}>
              <T v="bodyBold" numberOfLines={2}>{item.title}</T>
              <T v="small">{item.direction === 'incoming' ? `From ${peer?.agent_id ?? 'their assistant'}` : `To ${peer?.agent_id ?? 'their assistant'}`} · {when(item.created_at)}</T>
            </View>
            <Chip label={stateLabel(item.state)} tone={tone(item)} />
          </Pressable>
        );
      })}
    </Screen>
  );
}
