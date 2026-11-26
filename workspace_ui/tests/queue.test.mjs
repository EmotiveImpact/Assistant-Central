import test from 'node:test';
import assert from 'node:assert/strict';
import {homeQueue,CARD,askerOf,moreLine,closingLine} from '../queue.mjs';

const principal='a'.repeat(64),other='b'.repeat(64);
const approvals={note:'',count:3,drafts_available:true,
  messages:[{draft_id:'m1',assistant_id:'beacon',conversation_id:'c1',text:'Hello   there\nfriend',digest:'d'.repeat(64)}],
  questions:[{question_id:'q1',question:'Saturday or Sunday?',state:'waiting',expires_at:9e9,options:['Saturday','Sunday']}],
  drafts:[{draft_id:'s1',conversation_id:'c1',text:'Removal is booked for Friday.',revision:1,execution_authority:false}]};
const conversations={principal,actors:[{principal,owner_id:'blair',agent_id:'Beacon'},{principal:other,owner_id:'drew',agent_id:'Orbit'}],rooms:[],
  invitations:[{id:'i1',conversation_id:'supper-club',principal,admin:other},{id:'i2',conversation_id:'not-mine',principal:other,admin:principal}]};
const hostDrafts={local_only:true,execution_authority:false,connections:[{id:'claude',available:true,items:[{draftId:'h1',title:'Book the van',state:'awaiting_owner_review'},{draftId:'h2',title:'Old',state:'dismissed'}]}]};

test('one queue holds every kind of decision, proposals first', () => {
  const queue=homeQueue({proposals:[{id:'p1',title:'Explore the visual direction'}],approvals,hostDrafts,conversations});
  assert.deepEqual(queue.map(e=>e.kind),['proposal','question','message','shared-draft','invite','host-draft']);
  assert.deepEqual(queue.map(e=>e.view),[undefined,'approvals','approvals','approvals','conversations','host-drafts']);
  assert.equal(new Set(queue.map(e=>e.key)).size,queue.length,'every card has its own key');
  assert.equal(queue[2].title,'Hello there friend','text is flattened to one line');
  assert.deepEqual([queue[4].owner,queue[4].agent],['drew','Orbit'],'an invitation names who invited you');
  for(const entry of queue)assert.ok(CARD[entry.kind].action,'every card has one button');
});

test('only invitations to you and drafts still waiting are queued', () => {
  const queue=homeQueue({conversations,hostDrafts});
  assert.deepEqual(queue.map(e=>e.key),['invite:i1','host:claude:h1']);
  assert.deepEqual(homeQueue({}),[]);
});

test('long text is clipped, never dropped', () => {
  const [entry]=homeQueue({approvals:{...approvals,messages:[],drafts:[],questions:[{...approvals.questions[0],question:'x'.repeat(300)}]}});
  assert.equal(entry.title.length,90);assert.ok(entry.title.endsWith('…'));
});

test('who is asking, and the honest closing line', () => {
  assert.deepEqual(askerOf({kind:'question'},{me:'Blair',mine:'Beacon'}),{owner:'Blair',agent:'Beacon',yours:true});
  assert.deepEqual(askerOf({kind:'proposal'},{peer:{owner_id:'drew',agent_id:'Orbit'}}),{owner:'drew',agent:'Orbit',yours:false});
  assert.equal(moreLine(1),' and it needs your decision. ');
  assert.equal(moreLine(2),' and 1 more waits for you. ');
  assert.equal(moreLine(4),' and 3 more wait for you. ');
  assert.equal(closingLine([]),'Nothing else needs you.');
  assert.equal(closingLine(['Approvals']),'I couldn’t check Approvals just now.');
  assert.equal(closingLine(['Approvals','Conversations','your apps']),'I couldn’t check Approvals, Conversations and your apps just now.');
});
