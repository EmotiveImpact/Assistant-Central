import test from 'node:test';
import assert from 'node:assert/strict';
import {STEPS,partStep,resultsFor,sharedName,teamsOf,teamCounts,teamLine,stepShare,planParts,partOf,partLead,
  PART,RESULT,ACCESS,readRules,partText,resultText,accessText,readTeamText,accessFor,approvalsFor,computeFor,teamCompute,checksFor,ruleList} from '../team.mjs';

const task=(id,peer,state,title,extra={})=>({id,kind:'task',direction:'outgoing',peer_id:peer,state,title,context:'c1',created_at:String(100+Number(id.slice(1))),...extra});
const result=(id,parent,state,at=500)=>({id,kind:'artifact',direction:'incoming',parent_id:parent,state,created_at:String(at)});

test('a part reads its step only from saved states',()=>{
  assert.equal(partStep(task('t1','p1','draft','M: A')).step,'Plan');
  assert.equal(partStep(task('t1','p1','draft','M: A')).needsYou,true);
  assert.equal(partStep(task('t1','p1','pending','M: A')).step,'Asked');
  assert.equal(partStep(task('t1','p1','released','M: A')).step,'Asked');
  assert.equal(partStep(task('t1','p1','accepted','M: A')).step,'Building');
  assert.equal(partStep(task('t1','p1','rejected','M: A')).step,'Stopped');
  const item=task('t1','p1','accepted','M: A');
  const waiting=partStep(item,[result('r1','t1','pending')]);
  assert.equal(waiting.step,'Result');assert.equal(waiting.needsYou,true);assert.equal(waiting.result.id,'r1');
  assert.equal(partStep(item,[result('r1','t1','accepted')]).step,'Done');
  assert.equal(partStep(item,[result('r1','t1','rejected')]).step,'Building');
  // The newest waiting result is the one to check, and results for other parts are ignored.
  assert.equal(partStep(item,[result('r1','t1','rejected',400),result('r2','t1','pending',600),result('r3','t9','accepted')]).result.id,'r2');
  assert.deepEqual(resultsFor(item,[result('r1','t1','rejected',400),result('r2','t1','pending',600),result('r3','t9','accepted')]).map(entry=>entry.id),['r2','r1']);
});

test('what can still be done is read from the state now, not from history',()=>{
  // The saved pairs the owner API returns: a withdrawn draft and an unanswered request past its time.
  const withdrawn=partStep(task('t1','p1','cancelled','M: A',{historical_state:'draft'}));
  assert.equal(withdrawn.step,'Stopped');assert.equal(withdrawn.needsYou,false);
  assert.equal(partStep(task('t1','p1','expired','M: A',{historical_state:'pending'})).step,'Stopped');
  // An expired result cannot be accepted any more, so it is not offered.
  const live=task('t1','p1','accepted','M: A',{historical_state:'accepted'});
  const stale=partStep(live,[{...result('r1','t1','expired'),historical_state:'pending'}]);
  assert.equal(stale.step,'Building');assert.equal(stale.result,undefined);
  // A signed acceptance stays done after everything expires.
  const old=task('t1','p1','expired','M: A',{historical_state:'accepted'});
  assert.equal(partStep(old).step,'Stopped');
  assert.equal(partStep(old,[{...result('r1','t1','expired'),historical_state:'accepted'}]).step,'Done');
  // A result for a part the owner withdrew is not offered either.
  assert.equal(partStep(task('t1','p1','cancelled','M: A',{historical_state:'accepted'}),[result('r1','t1','pending')]).step,'Stopped');
});

test('the mission name is the longest lead every part shares',()=>{
  assert.equal(sharedName(['Supper club app: Card deposits','Supper club app: Calendar sync']),'Supper club app');
  // A colon inside the name stays in the name.
  assert.equal(sharedName(['Launch: November: Card deposits','Launch: November: Calendar sync']),'Launch: November');
  assert.equal(sharedName(['Supper club app: Card deposits','Supper club app: Card reader']),'Supper club app');
  assert.equal(sharedName(['One: A','Two: B']),'');
  assert.equal(sharedName(['No colon here','No colon there']),'');
  assert.equal(sharedName(['M: A','']),'');assert.equal(sharedName([]),'');
  const [team]=teamsOf({items:[task('t1','p1','draft','Launch: November: Card deposits'),task('t2','p2','draft','Launch: November: Calendar sync')]});
  assert.equal(team.title,'Launch: November');
  assert.deepEqual(team.parts.map(part=>part.title),['Card deposits','Calendar sync']);
});

test('a team is outgoing tasks sharing one context across two or more assistants',()=>{
  const items=[
    task('t1','p1','accepted','Supper club app: Card deposits'),
    task('t2','p2','draft','Supper club app: Calendar sync'),
    task('t3','p3','pending','Supper club app: Menu page'),
    result('r1','t1','pending'),
    // One assistant only: not a team.
    task('t4','p1','draft','Solo: A',{context:'c2'}),task('t5','p1','draft','Solo: B',{context:'c2'}),
    // Incoming work never forms a team.
    {...task('t6','p2','pending','Theirs: A',{context:'c3'}),direction:'incoming'},{...task('t7','p3','pending','Theirs: B',{context:'c3'}),direction:'incoming'},
  ];
  const teams=teamsOf({items});
  assert.equal(teams.length,1);
  const [team]=teams;
  assert.equal(team.title,'Supper club app');
  assert.deepEqual(team.parts.map(part=>part.title),['Card deposits','Calendar sync','Menu page']);
  assert.deepEqual(team.parts.map(part=>part.step),['Result','Plan','Asked']);
  assert.deepEqual(team.people,['p1','p2','p3']);
  assert.deepEqual(teamCounts(team),{Plan:1,Asked:1,Building:0,Result:1,Done:0,Stopped:0});
  assert.equal(teamLine(team),'0 of 3 parts are done. One result needs your check. One part is ready for you to send. One assistant is still deciding.');
});

test('mixed mission names fall back to full titles',()=>{
  const [team]=teamsOf({items:[task('t1','p1','draft','One: A'),task('t2','p2','draft','Two: B')]});
  assert.equal(team.title,'Team mission');
  assert.deepEqual(team.parts.map(part=>part.title),['One: A','Two: B']);
});

test('the line is honest when everything is done or stopped',()=>{
  const items=[task('t1','p1','accepted','M: A'),task('t2','p2','accepted','M: B'),result('r1','t1','accepted'),result('r2','t2','accepted')];
  assert.equal(teamLine(teamsOf({items})[0]),'All 2 parts are done.');
  const stopped=[task('t1','p1','accepted','M: A'),task('t2','p2','rejected','M: B'),result('r1','t1','accepted')];
  assert.equal(teamLine(teamsOf({items:stopped})[0]),'1 of 2 parts is done. One part stopped.');
});

test('progress share follows the five steps',()=>{
  assert.deepEqual(STEPS,['Plan','Asked','Building','Result','Done']);
  assert.equal(stepShare('Plan'),0.2);assert.equal(stepShare('Done'),1);assert.equal(stepShare('Stopped'),0);
});

test('planning a team mission checks every part before anything is created',()=>{
  const rows=[{title:'Card deposits',peer_id:'p1',text:'Build it'},{title:'Calendar sync',peer_id:'p2',text:'Sync it'},{title:'',peer_id:'p1',text:''}];
  const parts=planParts('Supper club app',rows);
  assert.deepEqual(parts.map(part=>part.title),['Supper club app: Card deposits','Supper club app: Calendar sync']);
  assert.throws(()=>planParts('',rows),/short name/);
  assert.throws(()=>planParts('x'.repeat(61),rows),/short name/);
  assert.throws(()=>planParts('M',[rows[0]]),/at least two parts/);
  assert.throws(()=>planParts('M',[rows[0],{title:'B',peer_id:'p1',text:'t'}]),/two different assistants/);
  assert.throws(()=>planParts('M',[rows[0],{title:'B',peer_id:'p2',text:''}]),/name, an assistant and a brief/);
  assert.throws(()=>planParts('M',Array.from({length:7},(_,i)=>({title:'P'+i,peer_id:'p'+i,text:'t'}))),/six parts/);
  assert.throws(()=>planParts('M',[rows[0],{title:'x'.repeat(120),peer_id:'p2',text:'t'}]),/part name short/);
  // The saved limits count bytes: 45 Japanese characters fit the form but not the 128 byte title.
  assert.throws(()=>planParts('Fictional',[rows[0],{title:'あ'.repeat(45),peer_id:'p2',text:'t'}]),/too long with the mission name/);
  assert.throws(()=>planParts('M',[rows[0],{title:'B',peer_id:'p2',text:'あ'.repeat(3000)}]),/brief for “B” is too long/);
  assert.equal(planParts('M',[rows[0],{title:'あ'.repeat(30),peer_id:'p2',text:'あ'.repeat(2000)}]).length,2);
});

test('an item knows which team mission it belongs to',()=>{
  const items=[task('t1','p1','accepted','Supper club app: Card deposits'),task('t2','p2','draft','Supper club app: Calendar sync'),
    result('r1','t1','pending'),task('t9','p1','draft','Alone: A',{context:'c9'}),result('r9','t9','pending')];
  const state={items};
  const part=partOf(state,items[1]);
  assert.equal(part.team.title,'Supper club app');assert.equal(part.part.title,'Calendar sync');assert.equal(part.result,false);
  assert.equal(partLead(part),'Calendar sync, part of Supper club app');
  const returned=partOf(state,items[2]);
  assert.equal(returned.result,true);
  assert.equal(partLead(returned),'Result for Card deposits, part of Supper club app');
  // Work outside any team mission says nothing.
  assert.equal(partOf(state,items[3]),null);assert.equal(partOf(state,items[4]),null);assert.equal(partOf(state,undefined),null);
  assert.equal(partLead(null),'');
});

const rules={must:['Tests pass'],must_not:['Store card numbers']},compute={cap_micro:500000,currency:'GBP'};

test('a part carries its rules and compute limit in the exact text both sides sign',()=>{
  assert.deepEqual(readRules('Tests pass\n\n  Use the design system  \n'),['Tests pass','Use the design system']);
  assert.throws(()=>readRules(Array.from({length:9},(_,i)=>'Rule '+i).join('\n')),/Up to 8/);
  const text=partText({brief:' SYNTHETIC ONLY: build deposits ',must:rules.must,mustNot:rules.must_not,compute});
  assert.ok(text.startsWith(PART));
  assert.deepEqual(JSON.parse(text.slice(PART.length)),{brief:'SYNTHETIC ONLY: build deposits',compute,rules});
  assert.throws(()=>partText({brief:'B',must:['A'],mustNot:['A']}),/once/);
  assert.throws(()=>partText({brief:'B',compute:{cap_micro:0,currency:'GBP'}}),/compute limit/);
  assert.throws(()=>partText({brief:'  '}),/brief/);
  assert.deepEqual(readTeamText(text),{record:'part',value:{brief:'SYNTHETIC ONLY: build deposits',compute,rules}});
  assert.equal(readTeamText('SYNTHETIC ONLY: an ordinary request'),null);
  assert.equal(readTeamText(PART+'{broken'),null);
});

test('a result reports on every rule, in order, and compute only in the part\'s currency',()=>{
  const team={record:'part',rules,compute};
  const text=resultText('SYNTHETIC ONLY: done',team,{kept:[true,true],computeMicro:12000});
  assert.deepEqual(JSON.parse(text.slice(RESULT.length)),{checks:[{rule:'Tests pass',side:'must',kept:true},{rule:'Store card numbers',side:'must_not',kept:true}],compute_used:{micro:12000,currency:'GBP'},summary:'SYNTHETIC ONLY: done'});
  assert.throws(()=>resultText('Done',team,{kept:[true]}),/every rule/);
  assert.throws(()=>resultText('Done',{rules,compute:null},{kept:[true,true],computeMicro:5}),/no compute limit/);
  assert.deepEqual(ruleList(rules).map(entry=>entry.side),['must','must_not']);
});

test('access is asked for one part, for a bounded time',()=>{
  const text=accessText({partTaskId:'team-1',what:'Read the calendar',why:'Deposits follow bookings',hours:24});
  assert.deepEqual(JSON.parse(text.slice(ACCESS.length)),{hours:24,part_task_id:'team-1',what:'Read the calendar',why:'Deposits follow bookings'});
  assert.throws(()=>accessText({partTaskId:'team-1',what:'Read',why:'Because',hours:200}),/7 days/);
});

test('a team part shows its rules, access asks, merge approvals and reported compute',()=>{
  const items=[
    task('t1','p1','accepted','M: Cards',{task_id:'team-1',team:{record:'part',rules,compute}}),
    task('t2','p2','accepted','M: Calendar',{task_id:'team-2',team:{record:'part',rules:{must:[],must_not:[]},compute:{cap_micro:250000,currency:'GBP'}}}),
    {...result('r1','t1','pending'),team:{record:'result',checks:[{rule:'Tests pass',side:'must',kept:true},{rule:'Store card numbers',side:'must_not',kept:false}],compute_used:{micro:600000,currency:'GBP'}}},
    {id:'a1',kind:'task',direction:'incoming',peer_id:'p2',state:'pending',context:'c1',created_at:'1000',team:{record:'access',part_task_id:'team-2',what:'Read the calendar',hours:2}},
    {id:'a2',kind:'task',direction:'incoming',peer_id:'p1',state:'pending',context:'c1',created_at:'1000',team:{record:'access',part_task_id:'team-2',what:'Not this helper\'s part',hours:2}},
  ];
  const [team]=teamsOf({items});
  const [cards,calendar]=team.parts;
  assert.deepEqual(cards.rules,rules);
  assert.equal(calendar.needsYou,true);assert.equal(calendar.asking.item.id,'a1');
  assert.deepEqual(accessFor(calendar.item,items).map(ask=>[ask.item.id,ask.until,ask.granted]),[['a1',1000+7200,false]]);
  assert.deepEqual(approvalsFor(cards).map(entry=>[entry.who,entry.signed]),[['helper',true],['you',false]]);
  assert.deepEqual(checksFor(cards.result).map(entry=>entry.kept),[true,false]);
  assert.deepEqual(computeFor(cards.item,items),{limit:compute,used:{micro:600000,currency:'GBP'},over:true});
  assert.deepEqual(teamCompute(team,items),[{currency:'GBP',limit:750000,used:600000}]);
  assert.match(teamLine(team),/One assistant asks for access\./);
  assert.equal(partLead(partOf({items},items[3])),'Access for Calendar, part of M');
});
