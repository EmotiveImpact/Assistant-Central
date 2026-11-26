import test from 'node:test';
import assert from 'node:assert/strict';
import {botTraits, BODIES, SHAPES, COLOURS} from '../bots.mjs';

test('each assistant keeps the same bot everywhere', () => {
  assert.deepEqual(botTraits('Otto'), botTraits('otto'));
  assert.ok(BODIES.includes(botTraits('Juniper').body));
  assert.ok(Object.hasOwn(SHAPES, botTraits('Juniper').shape));
});

test('bot colours stay warm: no lilac or yellow', () => {
  assert.deepEqual(Object.keys(COLOURS), ['coral', 'rust', 'rose', 'amber', 'clay', 'berry']);
});

test('different assistants usually look different', () => {
  const names = ['Beacon', 'Atlas', 'Orbit', 'Mira', 'Juniper', 'Otto', 'Sage', 'Pip'];
  const looks = new Set(names.map(n => JSON.stringify(botTraits(n))));
  assert.ok(looks.size >= 7, `only ${looks.size} distinct looks`);
});
