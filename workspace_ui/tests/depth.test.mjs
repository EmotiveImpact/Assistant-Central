import test from 'node:test';
import assert from 'node:assert/strict';
import {SECTIONS,WORK_VIEWS,WORK_FILTERS,sectionOf,tabOf,receiptsOf,shortDigest} from '../depth.mjs';
import {readFile} from 'node:fs/promises';

// projections.mjs imports the pilot model that the launcher serves at /model.mjs.
const modelURL=new URL('../../pilot/web/model.mjs',import.meta.url).href;
const source=(await readFile(new URL('../projections.mjs',import.meta.url),'utf8')).replace("from './model.mjs'",`from ${JSON.stringify(modelURL)}`);
const {VIEWS}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

test('every existing screen lives in exactly one of the four places', () => {
  assert.deepEqual(Object.values(SECTIONS).map(section=>section.label),['Home','Recents','Assistants','Money']);
  const placed=Object.values(SECTIONS).flatMap(section=>section.views);
  assert.equal(new Set(placed).size,placed.length,'no screen sits in two places');
  for(const view of VIEWS)assert.ok(placed.includes(view),`${view} has a place`);
  assert.equal(sectionOf('inbox'),'recents');assert.equal(sectionOf('transfers'),'assistants');
  assert.equal(sectionOf('approvals'),'home');assert.equal(sectionOf('unknown'),'home');
});

test('All work is one tab whose filters are the existing work screens', () => {
  assert.deepEqual(WORK_FILTERS.map(([view])=>view),WORK_VIEWS);
  for(const view of WORK_VIEWS)assert.equal(tabOf(view),'tasks');
  assert.equal(tabOf('receipts'),'receipts');
});

test('receipts list only digests that exist in saved state, newest first', () => {
  const state={items:[
    {id:'a',title:'Old',created_at:100,decision_digest:'d'.repeat(64)},
    {id:'b',title:'New',created_at:300,decision_digest:'e'.repeat(64)},
    {id:'c',title:'Unsigned',created_at:400},
  ],workflow:{runs:[{item_id:'a',result_digest:'f'.repeat(64)},{item_id:'c'}]}};
  const receipts=receiptsOf(state);
  assert.deepEqual(receipts.map(r=>[r.kind,r.item.id]),[['decision','b'],['decision','a'],['result','a']]);
  assert.deepEqual(receiptsOf({}),[]);
});

test('short digests keep both ends', () => {
  assert.equal(shortDigest('0123456789abcdef'),'0123…cdef');
  assert.equal(shortDigest('short'),'short');
  assert.equal(shortDigest(undefined),'');
});
