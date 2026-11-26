// Home's facts, worked out from saved state only. Pure, so the views and the tests agree.
// Nothing here invents a number: a budget appears only when a signed mission quote exists,
// and "done today" lists only work that someone actually agreed today.
import {amountOf} from './missions.mjs';

export function homeGreeting(hour) {
  return hour < 5 ? 'Evening' : hour < 12 ? 'Morning' : hour < 18 ? 'Afternoon' : 'Evening';
}
export function isEvening(hour) { return homeGreeting(hour) === 'Evening'; }

function startOfDay(now) { const day = new Date(now); day.setHours(0, 0, 0, 0); return day.getTime() / 1000; }

// One total per currency across every mission budget, counting each agreement once.
// Amounts stay in their own currency: nothing is converted or added across currencies.
export function budgetSummary(runs = [], items = []) {
  const contexts = new Map(items.map(item => [item.id, item.context]));
  const seen = new Set(), totals = new Map();
  for (const run of runs) {
    const balance = run?.mission_balance;
    if (!balance || typeof balance !== 'object') continue;
    const key = contexts.get(run.item_id) ?? run.run_id;
    if (seen.has(key)) continue;
    seen.add(key);
    const [cap, currency] = amountOf(balance, 'cap');
    const total = totals.get(currency) ?? {currency, cap: 0, spent: 0, held: 0, available: 0, budgets: 0};
    total.cap += Number(cap) || 0;
    total.spent += Number(amountOf(balance, 'spent')[0]) || 0;
    total.held += Number(amountOf(balance, 'held')[0]) || 0;
    total.available += Number(amountOf(balance, 'available')[0]) || 0;
    total.budgets += 1;
    totals.set(currency, total);
  }
  return [...totals.values()].sort((a, b) => b.cap - a.cap);
}

// Work agreed today: tasks either side accepted and results the owner accepted.
// Newest first. The time shown is when the work was proposed, which is what is saved.
export function doneToday(items = [], now = Date.now()) {
  const since = startOfDay(now);
  return items
    .filter(item => item.state === 'accepted' && Number(item.created_at) >= since && Number(item.created_at) <= now / 1000 + 60)
    .sort((a, b) => b.created_at - a.created_at);
}

// Who did it, in words: "You agreed", or the peer's assistant.
export function doneLine(item, peer) {
  const agent = peer?.agent_id || 'Their assistant';
  if (item.kind === 'artifact') return `${agent} delivered it and you accepted`;
  return item.direction === 'outgoing' ? `${agent} agreed to do it` : 'You agreed to it';
}

// The evening sentence: one honest line about the day.
export function eveningSummary(done, peerOf) {
  if (!done.length) return 'Nothing was agreed today.';
  const first = done[0], agent = peerOf(first)?.agent_id;
  const count = done.length === 1 ? 'One piece of work was' : `${done.length} pieces of work were`;
  return `${count} agreed today, most recently “${first.title || 'Untitled'}”` + (agent ? ` with ${agent}.` : '.');
}

export function shortKey(fingerprint) {
  const value = String(fingerprint ?? '');
  return value.length >= 8 ? value.slice(0, 4) + ' ' + value.slice(4, 8) : 'unknown';
}
