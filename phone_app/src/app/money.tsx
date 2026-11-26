// Money: one big number per currency from the signed budgets. Nothing is converted or
// guessed. The people you work with have their own page, Assistants.
import React from 'react';
import { useGuard } from '../lib/guard';
import { useSession } from '../lib/session';
import { budgetSummary, money } from '../shared/web';
import { Card, T } from '../ui/parts';
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
  const { state } = useSession();
  if (guard || !state) return guard;
  const runs = ((state.workflow as { runs?: unknown[] } | undefined)?.runs ?? []) as unknown[];
  const totals = budgetSummary(runs, state.items) as Total[];
  return (
    <Screen title="Money">
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
    </Screen>
  );
}
