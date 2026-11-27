import test from 'node:test';
import assert from 'node:assert/strict';
import {teamsOf} from '../team.mjs';
import {roomsOf,buildRoom,tally,answerOf,columnOf,timelineOf,filterTimeline,groupsOf,roomLine,eventLine,noteText,voteText,recordTitle,NOTE,VOTE,canvasLayout} from '../rooms.mjs';

const C1='a'.repeat(64),C2='b'.repeat(64);
let n=0;
const item=(direction,peer,state,room,extra={})=>({id:'i'+(++n),kind:'task',direction,peer_id:peer,state,title:'T'+n,context:C1,task_id:'task-'+n,created_at:1000+n,room,...extra});
const note=(fields={})=>({record:'note',room:'Nana',thread:'Food',note:'finding',stage:'researching',summary:'S'+(++n),replaces:null,why:null,...fields});
const vote=(fields={})=>({record:'vote',room:'Nana',thread:'Food',question:'Lunch at 1?',rule:'most',stance:'yes',vote_id:'v1',why:null,...fields});
const state=(items,history=[])=>({identity:{owner_id:'blair',agent_id:'Beacon'},peers:[],items,history});

test('a context becomes a room only when it carries a room record or a team mission',()=>{
  const plain=item('incoming','p1','pending',undefined,{context:C2});
  const s=state([item('incoming','p1','pending',note()),plain]);
  const rooms=roomsOf(s);
  assert.equal(rooms.length,1);
  assert.equal(rooms[0].name,'Nana');
  assert.deepEqual(rooms[0].members,['p1']);
});

test('the rule decides a vote, and it closes as soon as the outcome cannot change',()=>{
  assert.equal(tally('most','yes',['yes','waiting','waiting']).outcome,'open');
  assert.equal(tally('most','yes',['yes','no','waiting']).outcome,'open');
  assert.equal(tally('most','yes',['yes','yes','no']).outcome,'passed');
  assert.equal(tally('most','no',['no','waiting']).outcome,'failed');
  assert.equal(tally('all','yes',['yes','yes']).outcome,'passed');
  assert.equal(tally('all','yes',['yes','no']).outcome,'failed');
  assert.equal(tally('all','abstain',['yes']).outcome,'failed');
  assert.equal(tally('all','yes',['yes','none']).outcome,'failed');
  assert.equal(tally('all','yes',['waiting']).outcome,'open');
});

test('each answer is read only from that copy’s own signed decision',()=>{
  assert.equal(answerOf({state:'expired',historical_state:'accepted'}),'yes');
  assert.equal(answerOf({state:'rejected',historical_state:'rejected'}),'no');
  assert.equal(answerOf({state:'released'}),'waiting');
  assert.equal(answerOf({state:'expired',historical_state:'released'}),'none');
  assert.equal(answerOf({state:'draft'}),'unsent');
});

test('your copies of one vote are one entry with a tally; a copy sent to you is yours to answer',()=>{
  const v=vote();
  const s=state([item('outgoing','p1','accepted',v,{historical_state:'accepted'}),item('outgoing','p2','rejected',v,{historical_state:'rejected'}),
    item('incoming','p1','pending',vote({vote_id:'v2',question:'Cottages?'}))]);
  const room=buildRoom(s,C1,'Nana');
  const votes=room.entries.filter(entry=>entry.type==='vote');
  assert.equal(votes.length,2);
  const mine=votes.find(entry=>!entry.incoming);
  assert.equal(mine.result.yes,2);assert.equal(mine.result.total,3);assert.equal(mine.result.outcome,'passed');
  assert.equal(columnOf(mine),'done');
  const theirs=votes.find(entry=>entry.incoming);
  assert.equal(columnOf(theirs),'yes');
  assert.equal(room.needsYou,1);
});

test('a change of mind replaces the earlier note on the board and shows on the timeline',()=>{
  const first=item('incoming','p1','expired',note({note:'idea'}),{task_id:'note-hotel'});
  const change=item('incoming','p1','pending',note({note:'change',stage:'doing',replaces:'note-hotel',why:'Cheaper'}));
  const room=buildRoom(state([first,change]),C1,'Nana');
  const [a,b]=room.entries;
  assert.equal(columnOf(a),null);
  assert.equal(columnOf(b),'doing');
  assert.equal(b.replaces,a);
  assert.deepEqual(room.timeline.map(e=>e.kind),['note','change']);
  assert.equal(filterTimeline(room.timeline,'change').length,1);
  assert.equal(room.changes,1);
});

test('a note you send to several members is one post, and a draft waits for your send',()=>{
  const shared=note({summary:'Train at 10:12'});
  const room=buildRoom(state([item('outgoing','p1','draft',shared),item('outgoing','p2','draft',shared)]),C1,'Nana');
  assert.equal(room.entries.length,1);
  assert.equal(room.entries[0].items.length,2);
  assert.equal(columnOf(room.entries[0]),'yes');
});

test('the timeline follows the saved history, not the clock',()=>{
  const v=vote();const a=item('outgoing','p1','accepted',v,{historical_state:'accepted'}),b=item('outgoing','p2','accepted',v,{historical_state:'accepted'});
  const history=[{sequence:1,event:'proposal_created',item_id:a.id},{sequence:2,event:'proposal_created',item_id:b.id},
    {sequence:9,event:'peer_decision_observed',item_id:b.id},{sequence:12,event:'peer_decision_observed',item_id:a.id}];
  const room=buildRoom(state([a,b],history),C1,'Nana');
  const kinds=room.timeline.map(e=>[e.kind,e.who]);
  assert.deepEqual(kinds,[['vote','you'],['answer','p2'],['answer','p1'],['outcome','room']]);
  const line=eventLine(room.timeline[3],who=>who==='room'?'The room':who);
  assert.match(line,/passed, 3 of 3 yes/);
});

test('groups join assistants who share a room, through anyone',()=>{
  const r1={members:['p1','p2'],votes:[],timeline:[],entries:[1],changes:0,needsYou:0,last:1,context:C1};
  const r2={members:['p2','p3'],votes:[],timeline:[],entries:[1],changes:0,needsYou:1,last:2,context:C2};
  const r3={members:['p9'],votes:[],timeline:[],entries:[],changes:0,needsYou:0,last:3,context:'c'.repeat(64)};
  const groups=groupsOf(state([]),[r1,r2,r3]);
  assert.equal(groups.length,2);
  const big=groups.find(group=>group.peers.length===3);
  assert.deepEqual(big.peers.sort(),['p1','p2','p3']);
  assert.equal(big.needsYou,1);
});

test('room records are written exactly as the runtime checks them',()=>{
  const text=noteText({room:"Nana's 80th",thread:'Food',summary:'Soft menu'});
  assert.ok(text.startsWith(NOTE));
  assert.deepEqual(Object.keys(JSON.parse(text.slice(NOTE.length))),['note','replaces','room','stage','summary','thread','why']);
  assert.throws(()=>noteText({room:'A',thread:'B',summary:'S',note:'change'}),/replaces and why/);
  assert.throws(()=>noteText({room:'',thread:'B',summary:'S'}),/room/);
  const ballot=voteText({room:'A',thread:'B',question:'Q?',voteId:'vote-1',rule:'all'});
  assert.ok(ballot.startsWith(VOTE));
  assert.equal(JSON.parse(ballot.slice(VOTE.length)).rule,'all');
  assert.throws(()=>voteText({room:'A',thread:'B',question:'Q?',voteId:'bad id'}),/id/);
  assert.ok(new TextEncoder().encode(recordTitle('Food','x'.repeat(300))).length<=120);
});

test('one honest line per room, and the canvas gives each assistant its own column',()=>{
  const room=buildRoom(state([item('incoming','p1','pending',note()),item('incoming','p2','pending',note({stage:'done'}))]),C1,'Nana');
  assert.equal(roomLine(room),'1 of 2 done.');
  const layout=canvasLayout(room);
  assert.deepEqual(layout.lanes,['p1','p2']);
  const [a,b]=[...layout.positions.values()];
  assert.notEqual(a.x,b.x);
});

test('a note or vote sent to several members never turns a room into a team mission',()=>{
  const v=vote();
  const s=state([item('outgoing','p1','pending',v),item('outgoing','p2','pending',v),item('outgoing','p1','draft',note()),item('outgoing','p2','draft',note())]);
  assert.equal(teamsOf(s).length,0);
  assert.equal(roomsOf(s).length,1);
});
