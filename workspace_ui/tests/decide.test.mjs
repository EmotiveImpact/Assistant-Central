import test from 'node:test';
import assert from 'node:assert/strict';
import {decisionQuestion,decisionRows,needsHold} from '../decide.mjs';

const names={agent:'Orbit',owner:'Drew'};
const task={kind:'task',direction:'incoming',title:'Explore the visual direction'};

test('the question names the decision in plain words', () => {
  assert.equal(decisionQuestion(task,names),'Agree to “Explore the visual direction” for Drew?');
  assert.equal(decisionQuestion({...task,kind:'artifact'},names),'Accept “Explore the visual direction” from Orbit?');
  assert.equal(decisionQuestion({...task,direction:'outgoing'},names),'Send “Explore the visual direction” to Drew?');
});

test('rows are always Spends, Shares and Keeps, and spending appears only with a signed limit', () => {
  const plain=decisionRows(task,{...names,actions:['accept','reject']});
  assert.deepEqual(plain.map(([key])=>key),['Spends','Shares','Keeps']);
  assert.match(plain[0][1],/^Nothing\./);
  assert.match(plain[1][1],/signed receipt Orbit can check/);
  assert.match(plain[2][1],/does not start work/);
  const mission=decisionRows({...task,mission_cap:{cap_micro:276,currency:'USD'}},{...names,actions:['accept']});
  assert.match(mission[0][1],/^Up to .+ from this mission's limit\. Simulated, no real payment\.$/);
  const outgoing=decisionRows({...task,direction:'outgoing',kind:'artifact'},{...names,actions:['release']});
  assert.match(outgoing[1][1],/^This exact result with Orbit, Drew's assistant\. Nobody else\.$/);
});

test('only money needs a hold', () => {
  assert.equal(needsHold({mission_cap:{cap_micro:1,currency:'GBP'}},'accept'),true);
  assert.equal(needsHold({},'accept'),false);
  assert.equal(needsHold({mission_cap:{cap_micro:1,currency:'GBP'}},'reject'),false);
});
