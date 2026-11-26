// Money and assistants: one big number per currency from the signed budgets, then everyone
// you are connected to, each assistant beside its owner. Nothing is converted or guessed.
import React from 'react';
import { View } from 'react-native';
import { useGuard } from '../lib/guard';
import { queueOf } from '../lib/home';
import { useSession } from '../lib/session';
import { budgetSummary, money, shortKey } from '../shared/web';
import { Bot, Card, Pair, T } from '../ui/parts';
import { Screen } from '../ui/Screen';
import { colour, font } from '../ui/theme';

type Total = { currency: string; cap: number; spent: number; held: number; available: number; budgets: number; unknown: number };

function Big({ amount }: { amount: string }) {
  const [whole, pence] = amount.split('.');
  return (
    <T style={{ fontFamily: font.extrabold, fontSize: 52, lineHeight: 58, letterSpacing: -2, color: colour.text }}>
      {whole}<T style={{ fontFamily: font.extrabold, fontSize: 52, color: colour.faint, letterSpacing: -2 }}>{pence ? '.' + pence : ''}</T>
    </T>
  );
}

export default function Money() {
  const guard = useGuard();
  const { state, approvals } = useSession();
  if (guard || !state) return guard;
  const runs = ((state.workflow as { runs?: unknown[] } | undefined)?.runs ?? []) as unknown[];
  const totals = budgetSummary(runs, state.items) as Total[];
  const waiting = new Set(queueOf(state, approvals).map(e => e.item?.peer_id).filter(Boolean));
  const peers = state.peers.filter(p => p.state === 'active');
  return (
    <Screen title="Money and assistants">
      {totals.length ? totals.map(total => {
        const known = total.budgets - total.unknown;
        return (
          <Card key={total.currency} style={{ gap: 6, marginBottom: 12 }}>
            <Big amount={money(known ? total.available : total.cap, total.currency) as string} />
            <T v="small">{known ? 'Left across your shared budgets' : `Agreed across ${total.budgets} shared budget${total.budgets === 1 ? '' : 's'}`}</T>
            {total.unknown ? <T v="small">Spending shows here once an assistant reports it. Parlu never guesses it.</T> : null}
          </Card>
        );
      }) : (
        <Card style={{ gap: 6, marginBottom: 12 }}>
          <Big amount="£0.00" />
          <T v="small">No shared budgets yet. When you agree to spend, the limit appears here in its own currency.</T>
        </Card>
      )}
      <Card style={{ gap: 12, marginTop: 6 }}>
        <View>
          <T v="section">Assistants</T>
          <T v="small">{peers.length} connected{waiting.size ? ` · ${waiting.size} need${waiting.size === 1 ? 's' : ''} you` : ''}</T>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {peers.map(p => <Bot key={p.peer_id} name={p.agent_id} size={48} e={waiting.has(p.peer_id) ? 'look' : 'idle'} />)}
        </View>
      </Card>
      <View style={{ marginTop: 14, gap: 8 }}>
        <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 }}>
          <Pair owner={state.identity.owner_id} agent={state.identity.agent_id} size={24} />
          <T v="bodyBold" style={{ flex: 1 }}>{state.identity.agent_id}, yours</T>
        </Card>
        {peers.map(p => (
          <Card key={p.peer_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 }}>
            <Pair owner={p.owner_id} agent={p.agent_id} size={24} e={waiting.has(p.peer_id) ? 'look' : 'idle'} />
            <T v="bodyBold" style={{ flex: 1 }}>{p.agent_id} · {p.owner_id}’s</T>
            <T v="mono" accessibilityLabel={`Key ${shortKey(p.fingerprint ?? p.peer_id)}`}>{shortKey(p.fingerprint ?? p.peer_id)}</T>
          </Card>
        ))}
      </View>
    </Screen>
  );
}
