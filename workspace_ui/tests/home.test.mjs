import test from 'node:test';
import assert from 'node:assert/strict';
import {homeGreeting, isEvening, budgetSummary, doneToday, doneLine, eveningSummary, shortKey} from '../home.mjs';

test('greeting follows the hour, and evening runs past midnight', () => {
  assert.equal(homeGreeting(4), 'Evening');
  assert.equal(homeGreeting(9), 'Morning');
  assert.equal(homeGreeting(14), 'Afternoon');
  assert.equal(homeGreeting(19), 'Evening');
  assert.equal(isEvening(18), true);
  assert.equal(isEvening(17), false);
});

test('budgets count each agreement once and never mix currencies', () => {
  const items = [{id: 'a', context: 'c1'}, {id: 'b', context: 'c1'}, {id: 'c', context: 'c2'}, {id: 'd', context: 'c3'}];
  const gbp = {cap_micro: 400e6, spent_micro: 150e6, held_micro: 55e6, available_micro: 195e6, currency: 'GBP'};
  const runs = [
    {run_id: '1', item_id: 'a', mission_balance: gbp},
    {run_id: '2', item_id: 'b', mission_balance: gbp},
    {run_id: '3', item_id: 'c', mission_balance: {cap_microusd: 2e6, spent_microusd: 1e6, held_microusd: 0, available_microusd: 1e6}},
    {run_id: '4', item_id: 'd'},
  ];
  const totals = budgetSummary(runs, items);
  assert.deepEqual(totals.map(t => [t.currency, t.cap, t.available, t.budgets]), [['GBP', 400e6, 195e6, 1], ['USD', 2e6, 1e6, 1]]);
  assert.deepEqual(budgetSummary([], items), []);
});

test('done today lists only work agreed today, newest first', () => {
  const now = new Date(2026, 10, 26, 19, 0).getTime(), today = new Date(2026, 10, 26, 9, 0).getTime() / 1000;
  const items = [
    {id: 'old', state: 'accepted', created_at: today - 86400},
    {id: 'pending', state: 'pending', created_at: today},
    {id: 'first', state: 'accepted', created_at: today},
    {id: 'second', state: 'accepted', created_at: today + 60},
    {id: 'rejected', state: 'rejected', created_at: today},
  ];
  assert.deepEqual(doneToday(items, now).map(i => i.id), ['second', 'first']);
});

test('done lines and the evening sentence say who did what', () => {
  const mira = {agent_id: 'Mira'};
  assert.equal(doneLine({kind: 'task', direction: 'outgoing'}, mira), 'Mira agreed to do it');
  assert.equal(doneLine({kind: 'task', direction: 'incoming'}, mira), 'You agreed to it');
  assert.equal(doneLine({kind: 'artifact', direction: 'incoming'}, mira), 'Mira delivered it and you accepted');
  assert.equal(eveningSummary([], () => mira), 'Nothing was agreed today.');
  assert.equal(eveningSummary([{title: 'Brief'}, {title: 'Plan'}], () => mira), '2 pieces of work were agreed today, most recently “Brief” with Mira.');
  assert.equal(shortKey('3f68d2d3aa'), '3f68 d2d3');
  assert.equal(shortKey(undefined), 'unknown');
});
