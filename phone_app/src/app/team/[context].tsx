// One team mission: the lead, the people, and every part with where it stands. Each part
// keeps its own exact review and receipt; sending a part or merging a result opens Decide.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { useGuard } from '../../lib/guard';
import { peerOf } from '../../lib/home';
import { useSession } from '../../lib/session';
import { STEPS, exactMoney, teamLine, teamsOf } from '../../shared/web';
import { Button, Card, Chip, Pair, T } from '../../ui/parts';
import { Progress } from '../../ui/Progress';
import { Screen } from '../../ui/Screen';
import { colour, font, radius } from '../../ui/theme';

type Tab = 'Parts' | 'People' | 'Receipts';
const STATUS: Record<string, [string, 'plain' | 'sun' | 'accent' | 'done']> = {
  Plan: ['Ready to send', 'sun'], Asked: ['Waiting for their yes', 'plain'], Building: ['Building', 'accent'],
  Result: ['Result to check', 'sun'], Done: ['Done', 'done'], Stopped: ['Stopped', 'plain'],
};

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  return (
    <View style={{ flexDirection: 'row', backgroundColor: colour.raised, borderRadius: radius.pill, padding: 4, marginVertical: 16 }} accessibilityRole="tablist">
      {(['Parts', 'People', 'Receipts'] as Tab[]).map(name => (
        <Pressable key={name} onPress={() => setTab(name)} accessibilityRole="tab" accessibilityState={{ selected: tab === name }}
          style={{ flex: 1, paddingVertical: 9, borderRadius: radius.pill, alignItems: 'center', backgroundColor: tab === name ? colour.bg : 'transparent' }}>
          <T style={{ fontFamily: font.semibold, fontSize: 15, color: tab === name ? colour.text : colour.muted }}>{name}</T>
        </Pressable>
      ))}
    </View>
  );
}

export default function Team() {
  const guard = useGuard();
  const { context } = useLocalSearchParams<{ context: string }>();
  const { state } = useSession();
  const [tab, setTab] = useState<Tab>('Parts');
  if (guard || !state) return guard;
  const team = (teamsOf(state) as any[]).find(t => t.context === context);
  if (!team) return <Screen title="Team mission"><T v="body">This team mission is no longer here.</T></Screen>;
  const me = state.identity;
  const open = (id: string) => router.push({ pathname: '/decide', params: { key: 'item:' + id } });
  return (
    <Screen>
      <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center' }}>
        <Pair owner={me.owner_id} agent={me.agent_id} size={40} e="busy" />
        <View style={{ flex: 1, gap: 4 }}>
          <View style={{ alignSelf: 'flex-start', backgroundColor: colour.text, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3 }}>
            <T style={{ color: colour.onText, fontFamily: font.bold, fontSize: 11, letterSpacing: 0.9 }}>{me.agent_id.toUpperCase()} LEADS</T>
          </View>
          <T v="page" style={{ fontSize: 28, lineHeight: 32 }}>{team.title}</T>
          <T v="small">{team.parts.length} parts · {team.people.length} assistants</T>
        </View>
      </View>
      <T v="body" style={{ fontSize: 17, lineHeight: 25, marginTop: 16, marginBottom: 12, color: colour.secondary }}>{teamLine(team)}</T>
      <Progress parts={team.parts} />
      <Tabs tab={tab} setTab={setTab} />

      {tab === 'Parts' ? team.parts.map((part: any) => {
        const peer = peerOf(state, part.item), [label, tone] = STATUS[part.step] ?? ['', 'plain'];
        const compute = part.item.team?.compute;
        return (
          <Card key={part.item.id} tone={part.needsYou ? 'sun' : undefined} style={{ gap: 12, marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
              <Pair owner={peer?.owner_id ?? '?'} agent={peer?.agent_id ?? 'Assistant'} size={30} e={part.needsYou ? 'look' : part.step === 'Building' ? 'busy' : part.step === 'Done' ? 'done' : 'idle'} />
              <View style={{ flex: 1 }}>
                <T v="section">{part.title}</T>
                <T v="small" numberOfLines={1}>{peer?.agent_id}, {peer?.owner_id}’s assistant</T>
              </View>
            </View>
            <Chip label={label} tone={tone} />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} accessible accessibilityLabel={`Step: ${part.step}`}>
              {STEPS.map((step: string) => {
                const reached = STEPS.indexOf(step) <= STEPS.indexOf(part.step), current = step === part.step;
                return <View key={step} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: current ? colour.accentBg : colour.raised }}>
                  <T style={{ fontFamily: font.semibold, fontSize: 12.5, color: current ? colour.accentOn : reached ? colour.secondary : colour.faint }}>{reached && !current ? '✓ ' : ''}{step}</T>
                </View>;
              })}
            </View>
            {part.rules ? (
              <View style={{ gap: 2 }}>
                {(part.rules.must ?? []).map((r: string) => <T key={'m' + r} v="small">Must: {r}</T>)}
                {(part.rules.must_not ?? []).map((r: string) => <T key={'n' + r} v="small">Must not: {r}</T>)}
                {compute ? <T v="small">Compute: up to {exactMoney(compute.cap_micro, compute.currency)}</T> : null}
              </View>
            ) : null}
            {part.step === 'Plan' ? <Button small label="Review and send" onPress={() => open(part.item.id)} /> : null}
            {part.step === 'Result' && part.result ? <Button small label="Check the result" onPress={() => open(part.result.id)} /> : null}
            {part.asking ? <Button small label="Answer the access ask" onPress={() => open(part.asking.item.id)} /> : null}
          </Card>
        );
      }) : null}

      {tab === 'People' ? (
        <View style={{ gap: 10 }}>
          <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <Pair owner={me.owner_id} agent={me.agent_id} size={28} />
            <View style={{ flex: 1 }}><T v="bodyBold">{me.agent_id}, your assistant</T><T v="small">Leads the mission and checks every result</T></View>
          </Card>
          {team.people.map((id: string) => {
            const peer = state.peers.find(p => p.peer_id === id);
            const parts = team.parts.filter((p: any) => p.peer_id === id).map((p: any) => p.title).join(', ');
            return (
              <Card key={id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <Pair owner={peer?.owner_id ?? '?'} agent={peer?.agent_id ?? 'Assistant'} size={28} />
                <View style={{ flex: 1 }}><T v="bodyBold">{peer?.agent_id}, {peer?.owner_id}’s assistant</T><T v="small">{parts}</T></View>
              </Card>
            );
          })}
        </View>
      ) : null}

      {tab === 'Receipts' ? (() => {
        const signed = team.parts.flatMap((p: any) => [p.item, p.result].filter(Boolean)).filter((i: any) => (i.historical_state ?? i.state) === 'accepted');
        if (!signed.length) return <T v="body">No receipts yet. Each part gets one when it is agreed, and each result when you merge it.</T>;
        return signed.map((i: any) => (
          <Card key={i.id} style={{ gap: 4, marginBottom: 10 }}>
            <T v="bodyBold">{i.title}</T>
            <T v="small">{i.kind === 'artifact' ? 'Result merged' : 'Part agreed'} · {new Date(i.created_at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</T>
            {typeof i.decision_digest === 'string' ? <T v="mono">RECEIPT {i.decision_digest.slice(0, 4)}…{i.decision_digest.slice(-2)}</T> : null}
          </Card>
        ));
      })() : null}
    </Screen>
  );
}
