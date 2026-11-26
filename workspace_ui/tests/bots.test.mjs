import test from 'node:test';
import assert from 'node:assert/strict';
import {botTraits, BODIES} from '../bots.mjs';

test('each assistant keeps the same bot everywhere', () => {
  assert.deepEqual(botTraits('Otto'), botTraits('otto'));
  assert.ok(BODIES.includes(botTraits('Juniper').body));
});

test('different assistants usually look different', () => {
  const names = ['Beacon', 'Atlas', 'Orbit', 'Mira', 'Juniper', 'Otto', 'Sage', 'Pip'];
  const looks = new Set(names.map(n => JSON.stringify(botTraits(n))));
  assert.equal(looks.size, names.length);
});
