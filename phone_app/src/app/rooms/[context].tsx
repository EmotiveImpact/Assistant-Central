// One room. Threads holds the talk, one topic each. Board shows where each piece of work
// stands. Timeline lists every finding, change of mind, vote and yes in the order it happened.
// Every answer is still your own signed decision: Vote and Review open Decide.
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import Animated from 'react-native-reanimated';
import { useLocalSearchParams } from 'expo-router';
import { useGuard } from '../../lib/guard';
import { useSession } from '../../lib/session';
import type { Item, State } from '../../lib/types';
import { COLUMNS, NOTE_WORDS, RULE_WORDS, TIMELINE_FILTERS, columnOf, eventLine, filterTimeline, roomLine, roomsOf } from '../../shared/web';
import { rowIn } from '../../ui/motion';
import { Button, Card, Chip, Pair, T } from '../../ui/parts';
import { Filters, Members, RoomGlyph, Segments, Tally, ago, speaker, whoOf } from '../../ui/Room';
import { Screen } from '../../ui/Screen';
import { useOverlay } from '../../ui/overlay';
import { colour, font, radius } from '../../ui/theme';

type Tab = 'Threads' | 'Board' | 'Timeline';
const TABS = ['Threads', 'Board', 'Timeline'] as const;
const COLUMN_HINT: Record<string, string> = {
  researching: 'Being looked into', doing: 'Under way', yes: 'Waiting for you', done: 'Agreed or finished',
};

// The words shown for one entry, without the room's name repeated in front of a part's title.
const titleOf = (room: any) => (entry: any) => {
  const raw = entry.type === 'note' ? entry.note.summary : entry.type === 'vote' ? entry.vote.question : String(entry.title ?? '');
  const prefix = `${room.name}: `;
  return raw.startsWith(prefix) ? raw.slice(prefix.length) : raw;
};

// The one thing you can do with an entry, if anything: vote, send your drafts, or review.
function actionOf(entry: any): { label: string; item: Item } | null {
  if (entry.type === 'vote' && entry.incoming) return entry.items[0].state === 'pending' ? { label: 'Vote', item: entry.items[0] } : null;
  const draft = entry.items.find((item: Item) => item.direction === 'outgoing' && item.state === 'draft');
  if (draft) {
    const left = entry.items.filter((item: Item) => item.state === 'draft').length;
    return { label: left > 1 ? `Review and send, ${left} copies` : 'Review and send', item: draft };
  }
  if (entry.type === 'task') {
    const result = entry.results.find((r: Item) => r.direction === 'incoming' && r.state === 'pending');
    if (result) return { label: 'Check the result', item: result };
    if (entry.item.direction === 'incoming' && entry.item.state === 'pending') return { label: 'Review', item: entry.item };
  }
  return null;
}

function kindLabel(entry: any) {
  if (entry.type === 'note') return NOTE_WORDS[entry.note.note] ?? 'Note';
  if (entry.type === 'vote') return 'Vote';
  return entry.thread === 'Parts' ? 'Part' : 'Ask';
}

function Who({ state, who, at, size = 26 }: { state: State; who: string; at?: number; size?: number }) {
  const w = whoOf(state, who);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <Pair owner={w.owner} agent={w.agent} size={size} />
      <View style={{ flex: 1 }}>
        <T v="bodyBold" numberOfLines={1}>{w.agent}<T v="small">{w.yours ? ', your assistant' : `, ${w.owner}’s assistant`}</T></T>
      </View>
      {at ? <T v="small">{ago(at)}</T> : null}
    </View>
  );
}

function Voters({ state, entry }: { state: State; entry: any }) {
  const tone = (a: string) => a === 'yes' ? colour.accentBg : a === 'no' ? colour.sunBg : colour.raised;
  const ink = (a: string) => a === 'yes' ? colour.accentOn : a === 'no' ? colour.sunOn : colour.muted;
  const words: Record<string, string> = { yes: 'yes', no: 'no', waiting: 'waiting', none: 'no answer', unsent: 'not sent yet' };
  const list = entry.incoming ? entry.answers : [{ who: 'you', answer: entry.vote.stance }, ...entry.answers];
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      {list.map((a: any, i: number) => (
        <View key={a.who + i} style={{ paddingHorizontal: 9, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: tone(a.answer) }}>
          <T style={{ fontFamily: font.semibold, fontSize: 12, color: ink(a.answer) }}>{speaker(state)(a.who)}: {words[a.answer] ?? a.answer}</T>
        </View>
      ))}
    </View>
  );
}

function Post({ state, room, entry, open, index }: { state: State; room: any; entry: any; open: (id: string) => void; index: number }) {
  const action = actionOf(entry), column = columnOf(entry);
  const words = titleOf(room)(entry);
  const replaced = entry.type === 'note' && entry.replacedBy;
  return (
    <Animated.View entering={rowIn(index)}>
      <Card tone={column === 'yes' ? 'sun' : undefined} style={{ gap: 10, marginBottom: 12, opacity: replaced ? 0.6 : 1 }}>
        <Who state={state} who={entry.who} at={entry.at} />
        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
          <Chip label={kindLabel(entry)} tone={entry.type === 'note' && entry.note.note === 'change' ? 'sun' : entry.type === 'vote' ? 'accent' : 'plain'} />
          {replaced ? <Chip label="Replaced by a change of mind" /> : null}
          {column && !replaced ? <Chip label={(COLUMNS.find(([id]) => id === column) ?? ['', ''])[1]} tone={column === 'done' ? 'done' : column === 'yes' ? 'sun' : 'plain'} /> : null}
        </View>
        {entry.type === 'vote'
          ? <T v="section">{words}</T>
          : <T v="body" style={{ color: colour.text, textDecorationLine: replaced ? 'line-through' : 'none' }}>{words}</T>}
        {entry.type === 'note' && entry.note.note === 'change' ? (
          <View style={{ gap: 4, borderLeftWidth: 2, borderLeftColor: colour.sun, paddingLeft: 10 }}>
            {entry.replaces ? <T v="small">Was: {entry.replaces.note.summary}</T> : null}
            {entry.note.why ? <T v="small" style={{ color: colour.secondary }}>Why: {entry.note.why}</T> : null}
          </View>
        ) : null}
        {entry.type === 'vote' ? (
          <View style={{ gap: 10 }}>
            {entry.incoming
              ? <T v="small">{RULE_WORDS[entry.vote.rule]} must agree. {whoOf(state, entry.who).agent} counts the answers.</T>
              : <Tally result={entry.result} rule={`${RULE_WORDS[entry.vote.rule]} must agree`} />}
            <Voters state={state} entry={entry} />
          </View>
        ) : null}
        {entry.type === 'task' && entry.step ? <T v="small">Step: {entry.step}</T> : null}
        {action ? <Button small label={action.label} onPress={() => open(action.item.id)} /> : null}
      </Card>
    </Animated.View>
  );
}

function Threads({ state, room, open }: { state: State; room: any; open: (id: string) => void }) {
  const [thread, setThread] = useState('all');
  const options = useMemo(() => [['all', 'All threads'] as const, ...room.threads.map((t: string) => [t, `# ${t}`] as const)], [room.threads]);
  const entries = room.entries.filter((e: any) => thread === 'all' || e.thread === thread).slice().reverse();
  return (
    <View>
      {room.threads.length > 1 ? <Filters options={options} value={thread} onChange={setThread} /> : null}
      {!entries.length ? <T v="body">Nothing in this thread yet.</T> : null}
      {entries.map((entry: any, i: number) => <Post key={entry.items[0].id} state={state} room={room} entry={entry} open={open} index={i} />)}
    </View>
  );
}

function Board({ state, room, open }: { state: State; room: any; open: (id: string) => void }) {
  const { width } = useWindowDimensions();
  const column = Math.min(320, width - 72);
  const words = titleOf(room);
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} snapToInterval={column + 12} decelerationRate="fast"
      style={{ marginHorizontal: -20 }} contentContainerStyle={{ paddingHorizontal: 20, gap: 12, alignItems: 'flex-start' }}>
      {COLUMNS.map(([id, label]) => {
        const cards = room.board[id] as any[];
        return (
          <View key={id} style={{ width: column, backgroundColor: id === 'yes' && cards.length ? colour.sunBg : colour.raised, borderRadius: radius.card, padding: 12, gap: 10 }}
            accessibilityLabel={`${label}, ${cards.length}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', paddingHorizontal: 4 }}>
              <T v="smallBold" style={{ fontSize: 14 }}>{label}</T>
              <T v="small">{cards.length}</T>
            </View>
            <T v="small" style={{ paddingHorizontal: 4, marginTop: -8 }}>{COLUMN_HINT[id]}</T>
            {!cards.length ? <T v="small" style={{ paddingHorizontal: 4, paddingVertical: 12 }}>Nothing here.</T> : null}
            {cards.map(entry => {
              const w = whoOf(state, entry.who), action = actionOf(entry);
              return (
                <Pressable key={entry.items[0].id} onPress={() => open((action?.item ?? entry.items[0]).id)} accessibilityRole="button"
                  accessibilityLabel={`${kindLabel(entry)} from ${w.agent}: ${words(entry)}`}
                  style={({ pressed }) => ({ backgroundColor: colour.bg, borderRadius: radius.md, padding: 12, gap: 8, borderWidth: 1, borderColor: colour.line, opacity: pressed ? 0.85 : 1 })}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Pair owner={w.owner} agent={w.agent} size={18} />
                    <T v="small" style={{ flex: 1 }} numberOfLines={1}>{w.agent} · # {entry.thread}</T>
                    <T style={{ fontFamily: font.semibold, fontSize: 11, color: entry.type === 'note' && entry.note.note === 'change' ? colour.sunOn : colour.muted }}>{kindLabel(entry)}</T>
                  </View>
                  <T v="body" numberOfLines={4} style={{ color: colour.text, fontSize: 14, lineHeight: 20 }}>{words(entry)}</T>
                  {entry.type === 'vote' && !entry.incoming ? <Tally result={entry.result} rule={RULE_WORDS[entry.vote.rule]} /> : null}
                  {action ? <T style={{ fontFamily: font.semibold, fontSize: 13, color: colour.accentFg }}>{action.label} ›</T> : null}
                </Pressable>
              );
            })}
          </View>
        );
      })}
    </ScrollView>
  );
}

function Timeline({ state, room }: { state: State; room: any }) {
  const [filter, setFilter] = useState('all');
  const events = filterTimeline(room.timeline, filter).slice().reverse();
  const name = speaker(state), words = titleOf(room);
  const dot = (kind: string) => kind === 'change' ? colour.sun : ['vote', 'answer', 'outcome'].includes(kind) ? colour.accent : ['agree', 'merge'].includes(kind) ? colour.ok : colour.lineStrong;
  return (
    <View>
      <Filters options={TIMELINE_FILTERS} value={filter} onChange={setFilter} />
      {!events.length ? <T v="body">Nothing like that has happened in this room yet.</T> : null}
      {events.map((event: any, i: number) => {
        const quote = event.kind === 'note' || event.kind === 'change' || event.kind === 'vote' ? words(event.entry) : '';
        const w = event.who === 'room' ? null : whoOf(state, event.who);
        return (
          <Animated.View key={`${event.kind}-${event.seq}-${i}`} entering={rowIn(i)} style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ alignItems: 'center', width: 14 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: dot(event.kind), marginTop: 6 }} />
              {i < events.length - 1 ? <View style={{ flex: 1, width: 2, backgroundColor: colour.lineSoft, marginTop: 4 }} /> : null}
            </View>
            <View style={{ flex: 1, paddingBottom: 18, gap: 4 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                {w ? <Pair owner={w.owner} agent={w.agent} size={18} /> : null}
                <T v="bodyBold" style={{ flex: 1, fontSize: 14, lineHeight: 20 }}>{eventLine(event, name, words)}</T>
              </View>
              {quote ? <T v="small" style={{ color: colour.secondary }}>“{quote}”</T> : null}
              {event.kind === 'change' && event.entry.note.why ? <T v="small">Why: {event.entry.note.why}</T> : null}
              <T v="small" style={{ fontSize: 12 }}># {event.entry.thread}{event.at ? ` · ${ago(event.at)}` : ''}</T>
            </View>
          </Animated.View>
        );
      })}
    </View>
  );
}

export default function Room() {
  const guard = useGuard();
  const { context } = useLocalSearchParams<{ context: string }>();
  const { state } = useSession();
  const { decide } = useOverlay();
  const [tab, setTab] = useState<Tab>('Threads');
  if (guard || !state) return guard;
  const room = roomsOf(state).find((r: any) => r.context === context);
  if (!room) return <Screen title="Room"><T v="body">This room is no longer here.</T></Screen>;
  const open = (id: string) => decide('item:' + id);
  return (
    <Screen>
      <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center' }}>
        <RoomGlyph name={room.name} tint={room.tint} size={48} />
        <View style={{ flex: 1, gap: 4 }}>
          <T v="page" style={{ fontSize: 27, lineHeight: 32 }} accessibilityRole="header">{room.name}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Members state={state} ids={room.members} size={20} />
            <T v="small">{room.members.length + 1} assistants</T>
          </View>
        </View>
      </View>
      <T v="body" style={{ fontSize: 16, lineHeight: 23, marginTop: 14, color: colour.secondary }}>{roomLine(room)}</T>
      <Segments tabs={TABS} tab={tab} setTab={setTab} />
      {tab === 'Threads' ? <Threads state={state} room={room} open={open} /> : null}
      {tab === 'Board' ? <Board state={state} room={room} open={open} /> : null}
      {tab === 'Timeline' ? <Timeline state={state} room={room} /> : null}
    </Screen>
  );
}
