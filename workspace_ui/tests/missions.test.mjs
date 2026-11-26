import test from 'node:test';
import assert from 'node:assert/strict';
import {dollars, toMicro, describeCheck, missionSummary} from '../missions.mjs';

test('budgets read as dollars, not millionths', () => {
  assert.equal(dollars(300), 'US$0.0003');
  assert.equal(dollars(500000), 'US$0.50');
  assert.equal(dollars(12_345_678), 'US$12.35');
  assert.equal(dollars(0), 'US$0.00');
});

test('typed dollars become exact millionths, and nonsense is refused', () => {
  assert.equal(toMicro('0.0003'), 300);
  assert.equal(toMicro('0.50'), 500000);
  assert.equal(toMicro('12'), 12000000);
  for (const bad of ['', '-1', '1e3', 'abc', '0.0000001', '1,5']) assert.equal(toMicro(bad), null, bad);
});

test('checks and terms are plain sentences', () => {
  assert.equal(describeCheck({kind: 'contains', value: 'plan'}), 'The result must include the words "plan".');
  assert.equal(describeCheck({kind: 'max_utf8_bytes', value: 2000}), 'The result must be no longer than 2,000 bytes.');
  assert.match(describeCheck({kind: 'sha256', value: 'a'.repeat(64)}), /exactly match/);
  assert.match(describeCheck({kind: 'human_review', value: 'Tone is friendly'}), /You decide/);
  const rows = missionSummary({goal: 'Fictional goal', deliverable: 'A note', executor: 'p1', cap_microusd: 250000,
    criteria: [{kind: 'contains', value: 'x'}]}, () => 'Bob');
  assert.deepEqual(rows.map(r => r[0]), ['What it is for', 'What comes back', 'Who does the work', 'Spending limit', 'How the result is checked']);
  assert.equal(rows[2][1], 'Bob');
  assert.match(rows[3][1], /^US\$0\.25 \(simulated/);
});
