import test from 'node:test';
import assert from 'node:assert/strict';
import {SECTIONS,WORK_VIEWS,WORK_FILTERS,sectionOf,tabOf,receiptsOf,shortDigest} from '../depth.mjs';
import {readFile} from 'node:fs/promises';

// projections.mjs imports the pilot model that the launcher serves at /model.mjs.
const modelURL=new URL('../../pilot/web/model.mjs',import.meta.url).href;
const source=(await readFile(new URL('../projections.mjs',import.meta.url),'utf8')).replace("from './model.mjs'",`from ${JSON.stringify(modelURL)}`);
const {VIEWS}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

test('every existing screen lives in exactly one place', () => {
  assert.deepEqual(Object.values(SECTIONS).map(section=>section.label),['Home','Rooms','Groups','Recents','Assistants','Money']);
  const placed=Object.values(SECTIONS).flatMap(section=>section.views);
  assert.equal(new Set(placed).size,placed.length,'no screen sits in two places');
  for(const view of VIEWS)assert.ok(placed.includes(view),`${view} has a place`);
  assert.equal(sectionOf('inbox'),'recents');assert.equal(sectionOf('transfers'),'assistants');
  assert.equal(sectionOf('approvals'),'home');assert.equal(sectionOf('unknown'),'home');
  assert.equal(sectionOf('room'),'rooms');assert.equal(sectionOf('groups'),'groups');
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

test('a decision signed today sits above older receipts, whenever its proposal was made', () => {
  // The old proposal "a" was decided last, so its receipt is the newest record.
  const state={items:[{id:'a',title:'Old proposal',created_at:100,decision_digest:'d'.repeat(64)},
    {id:'b',title:'New proposal',created_at:900,decision_digest:'e'.repeat(64)}],
    history:[{sequence:1,event:'proposal_received',item_id:'a'},{sequence:2,event:'proposal_received',item_id:'b'},
      {sequence:3,event:'recipient_decided',item_id:'b'},{sequence:4,event:'peer_decision_observed',item_id:'a'}],
    workflow:{runs:[{item_id:'b',run_id:'r1',result_digest:'f'.repeat(64)}]}};
  assert.deepEqual(receiptsOf(state).map(r=>[r.kind,r.item.id]),[['decision','a'],['decision','b'],['result','b']]);
  // A run event moves that result to the top.
  state.history.push({sequence:5,event:'workflow_result_staged',item_id:'b',data:{run_id:'r1'}});
  assert.deepEqual(receiptsOf(state).map(r=>[r.kind,r.item.id]),[['result','b'],['decision','a'],['decision','b']]);
});

test('short digests keep both ends', () => {
  assert.equal(shortDigest('0123456789abcdef'),'0123…cdef');
  assert.equal(shortDigest('short'),'short');
  assert.equal(shortDigest(undefined),'');
});
