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

test('a limit is shown exactly, never rounded', () => {
  const row=cap=>decisionRows({...task,mission_cap:cap},{...names,actions:['accept']})[0][1];
  // 14,999 millionths of a pound is not "£0.01".
  assert.match(row({cap_micro:14999,currency:'GBP'}),/^Up to £0\.014999 from this mission's limit\./);
  assert.match(row({cap_micro:500000,currency:'GBP'}),/^Up to £0\.50 from /);
  assert.match(row({cap_micro:276,currency:'USD'}),/^Up to US\$0\.000276 from /);
  assert.match(row({cap_micro:12345678,currency:'EUR'}),/^Up to €12\.345678 from /);
  const outgoing=decisionRows({...task,direction:'outgoing',mission_cap:{cap_micro:1999999,currency:'GBP'}},{...names,actions:['release']})[0][1];
  assert.match(outgoing,/^Up to £1\.999999 from this mission's limit if Orbit agrees\./);
});

test('only money needs a hold', () => {
  assert.equal(needsHold({mission_cap:{cap_micro:1,currency:'GBP'}},'accept'),true);
  assert.equal(needsHold({},'accept'),false);
  assert.equal(needsHold({mission_cap:{cap_micro:1,currency:'GBP'}},'reject'),false);
});

test('team records get their own question, rows and hold',async()=>{
  const {decisionQuestion,decisionRows,needsHold}=await import('../decide.mjs');
  const names={agent:'Otto',owner:'Maya',actions:['accept','reject']};
  const access={id:'a',kind:'task',direction:'incoming',title:'Access',team:{record:'access',what:'Read the calendar',hours:48}};
  assert.equal(decisionQuestion(access,names),'Let Otto read the calendar?');
  assert.deepEqual(decisionRows(access,names).map(([key])=>key),['Shares','For','Keeps']);
  assert.match(decisionRows(access,names)[1][1],/^2 days/);
  assert.equal(needsHold(access,'accept'),true);
  const result={id:'r',kind:'artifact',direction:'incoming',title:'Cards',team:{record:'result',checks:[{rule:'A',side:'must',kept:false}],compute_used:{micro:12000,currency:'GBP'}}};
  assert.equal(decisionQuestion(result,names),'Merge “Cards” from Otto?');
  assert.match(decisionRows(result,names)[0][1],/reports £0\.012 of compute/);
  assert.match(decisionRows(result,names)[1][1],/1 rule not kept/);
  assert.equal(needsHold(result,'accept'),false);
  const part={id:'p',kind:'task',direction:'incoming',title:'Cards',team:{record:'part',rules:{must:['A'],must_not:['B']},compute:{cap_micro:500000,currency:'GBP'}}};
  assert.match(decisionRows(part,names)[1][1],/2 rules/);
  assert.equal(needsHold(part,'accept'),true);
  assert.equal(needsHold({...part,team:{...part.team,compute:null}},'accept'),false);
});
