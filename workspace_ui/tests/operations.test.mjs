import test from 'node:test';
import assert from 'node:assert/strict';
import {operationGate,restoreWhenIdle,inspectionLatch,inspectSavedState,requestIsMutation} from '../operations.mjs';
import {createConversations,inspectMessageOutcome,messageRequestDigest} from '../conversations.mjs';
import {createHostDrafts} from '../host_drafts.mjs';

const principals={alice:'a'.repeat(64),bob:'b'.repeat(64)};
const unknown=message=>Object.assign(new Error(message),{unknown:true});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
class Element extends EventTarget {
  constructor(tag){super();this.tagName=tag;this.children=[];this.dataset={};this.open=false;this._text='';this.checked=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get childElementCount(){return this.children.length;}
  get textContent(){return this._text+this.children.map(c=>c.textContent||'').join('');}
  append(...nodes){this.children.push(...nodes);}
  prepend(...nodes){this.children.unshift(...nodes);}
  replaceChildren(...nodes){this._text='';this.children=[...nodes];}
  setAttribute(){}
  reportValidity(){return true;}
  close(){this.open=false;this.dispatchEvent(new Event('close'));}
  showModal(){this.open=true;}
  querySelector(selector){return find(this,e=>selector[0]==='.'?e.className?.split(' ').includes(selector.slice(1)):e.tagName===selector);}
}
function find(root,predicate){return predicate(root)?root:root.children.map(c=>find(c,predicate)).find(Boolean);}
function harness({room=false}={}){
  const original=globalThis.document,document=new EventTarget(),dialog=new Element('dialog'),root=new Element('div');
  document.hidden=false;document.body=new Element('body');document.body.append(root,dialog);
  document.createElement=tag=>new Element(tag);document.getElementById=()=>dialog;globalThis.document=document;
  const latch=inspectionLatch(),hostExpiry=Date.now()+60000;
  let pending=false,view='conversations',actor='alice',generation=1,restoreCount=0;
  const restorePanel=restoreWhenIdle({session:()=>generation,eligible:()=>!pending&&!document.hidden&&!root.childElementCount,restore:()=>{restoreCount++;mount(view);}});
  const operations=operationGate(v=>{pending=v;if(!v)restorePanel();}),writes=[],failures=[],requests=[];
  let writeResult=null,inspectionError=null,revision=0,policyGeneration=1,dismissed=false,reviewError=null,reviewDigest=null,historyFailure=false,outcome=null,outcomeError=null,outcomeWait=null,committedMessage=null;
  const request=async(path,options={})=>{
    requests.push({path,actor,options});
    if(path.endsWith('/history')&&historyFailure){historyFailure=false;throw Object.assign(new Error('History unavailable'),{unknown:requestIsMutation(path,options.method,options.readOnly)});}
    if(path==='/api/conversations/thread/history')return {messages:[{id:'message_'+revision,conversation_id:'thread',author:principals.bob,provenance_digest:'d'.repeat(64),trust:'untrusted-message',execution_authority:false,kind:'message',text:'Incoming message '+revision,sources:[]}]};
    if(path==='/api/conversations/thread')return {id:'thread',mode:'direct',admin:principals[actor],binding:{conversation_id:'thread',principal:principals[actor],member_epoch:'epoch_'+actor,policy_generation:policyGeneration},participants:[{principal:principals[actor],epoch:'epoch_'+actor}]};
    if(path.endsWith('/message-outcome')){
      if(outcomeError){const error=outcomeError;outcomeError=null;throw error;}
      if(outcomeWait){const held=outcomeWait;outcomeWait=null;return held.promise;}
      return outcome||{status:'committed',event:committedMessage};
    }
    if(path.endsWith('/message'))committedMessage={id:'sent_message',conversation_id:'thread',author:principals[actor],provenance_digest:'d'.repeat(64),trust:'untrusted-message',execution_authority:false,kind:'message',text:options.body.text,sources:[]};
    if(options.method==='POST'){
      writes.push({path,actor});const held=writeResult;writeResult=null;
      if(held)return held.promise;
      return {};
    }
    if(inspectionError){const error=inspectionError;inspectionError=null;throw error;}
    if(path==='/api/state')return {identity:actor};
    if(path==='/api/conversations')return {local_host_only:true,audience:'local-owner-only',execution_authority:false,principal:principals[actor],actors:[{principal:principals[actor],owner_id:actor,agent_id:actor+'_assistant'}],rooms:room?[{id:'thread',admin:principals[actor],mode:'direct'}]:[],invitations:[]};
    if(path==='/api/host-drafts')return {local_only:true,execution_authority:false,connections:[{id:actor,available:true,items:[{draftId:actor+'_draft',title:actor+' private draft title',state:'awaiting_owner_review'}]}]};
    if(path.endsWith('/review')&&reviewError)throw reviewError;
    if(path.endsWith('/review'))return {draft:{requestId:'request',title:actor+' private draft title',instruction:actor+' private draft content'},status:{draftId:actor+'_draft',state:dismissed?'dismissed':'awaiting_owner_review',ownerConsent:'not_requested',transportReceipt:'none',execution:'not_started'},binding:{ownerId:principals[actor],hostId:'host',sessionId:'host_session',conversationId:'room',recipientId:'fixed_recipient',expiresAt:hostExpiry},digest:reviewDigest||'c'.repeat(64),reviewToken:'token',reviewExpiresAt:Date.now()+30000,decision:dismissed?{decisionId:'decision',decision:'dismissed',digest:reviewDigest||'c'.repeat(64)}:null};
    throw new Error('Unexpected request '+path);
  };
  const failed=source=>(error,operation)=>{failures.push(error);if(error.unknown)latch.require(source,operation);};
  const common={request,busy:()=>pending,uncertain:()=>latch.pending(),session:()=>generation,unknownFailure:unknown};
  const restore=()=>{restoreCount++;mount(view);};
  const conversations=createConversations({...common,failed:failed('conversations'),gate:operations.scope(),restore,active:()=>view==='conversations'&&!document.hidden});
  const hostDrafts=createHostDrafts({...common,failed:failed('host-drafts'),gate:operations.scope(),restore,owner:()=>principals[actor],active:()=>view==='host-drafts'&&!document.hidden});
  function mount(next){view=next;conversations.reset();hostDrafts.reset();(next==='conversations'?conversations:hostDrafts).mount(root,true);}
  function click(label){const item=find(document.body,e=>e.tagName==='button'&&e.textContent===label);assert.ok(item,'Missing button '+label);item.dispatchEvent(new Event('click'));return item;}
  async function inspect(){click('Inspect draft');await flush();}
  function dismiss(){find(document.body,e=>e.id==='host-draft-dismiss-confirm').checked=true;return click('Dismiss exact draft');}
  return {root,document,writes,failures,requests,latch,mount,click,inspect,dismiss,
    message:()=>committedMessage,
    outcome(value){outcome=value;},failOutcome(error=Object.assign(new Error('Outcome read unavailable'),{unknown:false})){outcomeError=error;},holdOutcome(){outcomeWait=deferred();return outcomeWait;},
    async compose(text='One exact fictional message'){const input=find(root,e=>e.tagName==='textarea');assert.ok(input);input.value=text;input.dispatchEvent(new Event('input'));return click('Send to current members');},
    failHistory(){historyFailure=true;},markDismissed(){dismissed=true;},failHostInspection(){reviewError=new Error('Host unavailable');},wrongHostDigest(){reviewDigest='e'.repeat(64);},
    updateHistory(){revision++;},updatePolicy(){policyGeneration++;},
    busy:()=>pending,uncertain:()=>latch.pending(),restores:()=>restoreCount,
    hold(){writeResult=deferred();return writeResult;},
    inspectionFails(){inspectionError=new Error('Saved-state inspection lost');},
    newSession(next){conversations.reset({sessionEnded:true});hostDrafts.reset({sessionEnded:true});operations.reset();generation++;actor=next;latch.reset();},
    async inspectSavedState(){await inspectSavedState({latch,session:()=>generation,readState:()=>request('/api/state'),inspectHost:()=>hostDrafts.inspectUncertain(),inspectConversation:operation=>inspectMessageOutcome({request,session:()=>generation,operation})});mount(view);},
    close(){conversations.reset({sessionEnded:true});hostDrafts.reset({sessionEnded:true});operations.reset();generation++;globalThis.document=original;}
  };
}

test('scoped resets and completions cannot release another panel or shell lease',()=>{
  let busy=false;const gate=operationGate(v=>{busy=v;}),conversation=gate.scope(),host=gate.scope();
  const a=conversation.acquire(),b=host.acquire(),shell=gate.acquire();
  conversation.reset();a();assert.equal(busy,true);b();assert.equal(busy,true);shell();assert.equal(busy,false);
});
test('an old session completion cannot release the new session lease',()=>{
  let busy=false;const gate=operationGate(v=>{busy=v;}),old=gate.scope(),current=gate.scope();
  const releaseOld=old.acquire();gate.reset();const releaseCurrent=current.acquire();
  old.reset();releaseOld();assert.equal(busy,true);releaseCurrent();assert.equal(busy,false);
});
for(const first of ['conversations','host-drafts'])test(first+' pending write fences the other panel through navigation and visibility cleanup',async()=>{
  const h=harness();
  try{
    h.mount(first);await flush();if(first==='host-drafts')await h.inspect();const held=h.hold();
    first==='conversations'?h.click('New conversation'):h.dismiss();await flush();assert.equal(h.busy(),true);
    const second=first==='conversations'?'host-drafts':'conversations';h.mount(second);await flush();
    h.click(second==='conversations'?'New conversation':'Inspect draft');await flush();assert.equal(h.writes.length,1);
    h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));assert.equal(h.root.textContent,'');assert.equal(h.busy(),true);
    held.resolve({});await flush();await flush();assert.equal(h.busy(),false);assert.equal(h.uncertain(),true);assert.equal(h.restores(),0);assert.equal(h.root.textContent,'');
    h.document.hidden=false;h.mount(second);await flush();h.click(second==='conversations'?'New conversation':'Inspect draft');await flush();assert.equal(h.writes.length,1);
    assert.equal(h.failures.length,1);assert.equal(h.failures[0].unknown,true);
  }finally{h.close();}
});
test('same-session visible completion restores a cleared panel but keeps inspection required',async()=>{
  const h=harness();try{
    h.mount('conversations');await flush();const held=h.hold();h.click('New conversation');
    h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));h.document.hidden=false;
    held.resolve({});await flush();await flush();assert.equal(h.restores(),1);assert.match(h.root.textContent,/New conversation/);assert.equal(h.uncertain(),true);
    h.click('New conversation');await flush();assert.equal(h.writes.length,1);
    await h.inspectSavedState();await flush();h.click('New conversation');await flush();assert.equal(h.writes.length,1);assert.equal(h.uncertain(),true);
  }finally{h.close();}
});
test('old actor completion cannot clear a newer host write or restore old plaintext',async()=>{
  const h=harness();try{
    h.mount('host-drafts');await flush();await h.inspect();assert.match(h.document.body.textContent,/alice private draft content/);
    const old=h.hold();h.dismiss();h.newSession('bob');h.mount('host-drafts');await flush();await h.inspect();
    const fresh=h.hold();h.dismiss();assert.equal(h.busy(),true);old.resolve({});await flush();await flush();
    assert.equal(h.busy(),true);assert.equal(h.uncertain(),false);assert.equal(h.failures.length,0);assert.equal(h.restores(),0);
    assert.doesNotMatch(h.document.body.textContent,/alice private/);assert.match(h.document.body.textContent,/bob private draft content/);
    fresh.resolve({});await flush();await flush();assert.equal(h.busy(),false);assert.doesNotMatch(h.document.body.textContent,/alice private/);
    assert.deepEqual(h.writes.map(w=>w.actor),['alice','bob']);
  }finally{h.close();}
});
for(const panel of ['conversations','host-drafts'])test(panel+' committed write with lost inspection stays blocked without retry',async()=>{
  const h=harness();try{
    h.mount(panel);await flush();if(panel==='host-drafts')await h.inspect();const held=h.hold();
    const button=panel==='conversations'?h.click('New conversation'):h.dismiss();h.inspectionFails();held.resolve({});await flush();await flush();
    assert.equal(h.uncertain(),true);assert.equal(h.failures[0].unknown,true);assert.equal(h.busy(),false);assert.doesNotMatch(h.document.body.textContent,/alice private draft content/);
    button.dispatchEvent(new Event('click'));await flush();assert.equal(h.writes.length,1);
  }finally{h.close();}
});
for(const panel of ['conversations','host-drafts'])test(panel+' lost mutation response stays blocked without retry',async()=>{
  const h=harness();try{
    h.mount(panel);await flush();if(panel==='host-drafts')await h.inspect();const held=h.hold();
    const button=panel==='conversations'?h.click('New conversation'):h.dismiss();held.reject(unknown('Committed response lost'));await flush();await flush();
    button.dispatchEvent(new Event('click'));await flush();assert.equal(h.writes.length,1);assert.equal(h.uncertain(),true);assert.equal(h.busy(),false);
  }finally{h.close();}
});

test('shell restores the selected panel after a previous panel finishes, retaining uncertainty',async()=>{
  const h=harness();try{
    h.mount('host-drafts');await flush();await h.inspect();const held=h.hold();h.dismiss();
    h.mount('conversations');await flush();h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));h.document.hidden=false;
    assert.equal(h.root.textContent,'');held.resolve({});await flush();await flush();
    assert.equal(h.busy(),false);assert.equal(h.uncertain(),true);assert.match(h.root.textContent,/New conversation/);assert.equal(h.restores(),1);
    h.click('New conversation');await flush();assert.equal(h.writes.length,1);assert.doesNotMatch(h.document.body.textContent,/alice private draft/);
  }finally{h.close();}
});
test('queued shell restoration refuses a changed session',async()=>{
  let session=1,restored=0;const restore=restoreWhenIdle({session:()=>session,eligible:()=>true,restore:()=>restored++});
  restore();session++;await flush();assert.equal(restored,0);restore();await flush();assert.equal(restored,1);
});

test('actual passive conversation poll preserves unsent text but clears a changed audience and hidden view',async()=>{
  const timeout=globalThis.setTimeout,clear=globalThis.clearTimeout,timers=new Map();
  globalThis.setTimeout=(fn,delay,...args)=>{if(delay!==15000)return timeout(fn,delay,...args);const id={};timers.set(id,fn);return id;};
  globalThis.clearTimeout=id=>timers.has(id)?timers.delete(id):clear(id);
  const h=harness({room:true}),textarea=()=>find(h.root,e=>e.tagName==='textarea');
  const poll=async()=>{assert.equal(timers.size,1);const [id,fn]=[...timers][0];timers.delete(id);fn();await flush();await flush();};
  try{
    h.mount('conversations');await flush();h.click('Conversation · thread');await flush();
    const old=textarea();old.value='Keep this unsent plan';old.dispatchEvent(new Event('input'));
    h.updateHistory();await poll();assert.notEqual(textarea(),old);assert.equal(textarea().value,'Keep this unsent plan');assert.match(h.root.textContent,/Incoming message 1/);
    h.updatePolicy();await poll();assert.equal(textarea().value,'');
    textarea().value='Private unsent plan';textarea().dispatchEvent(new Event('input'));
    h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));assert.equal(h.root.textContent,'');
    h.document.hidden=false;h.mount('conversations');await flush();h.click('Conversation · thread');await flush();assert.equal(textarea().value,'');
  }finally{h.close();globalThis.setTimeout=timeout;globalThis.clearTimeout=clear;}
});

test('shell runtime refresh and unrelated host inspection preserve conversation operation hold',async()=>{
  const h=harness();try{
    h.mount('conversations');await flush();const held=h.hold();h.click('New conversation');held.reject(unknown('Response lost'));await flush();await flush();
    const ticket=h.latch.capture('conversations');assert.equal(ticket.operation.path,'/api/conversations');assert.ok(ticket.operation.id);
    h.mount('host-drafts');await flush();await h.inspect();assert.match(h.document.body.textContent,/alice private draft content/);
    await h.inspectSavedState();await flush();assert.equal(h.latch.capture('conversations'),ticket);assert.equal(h.uncertain(),true);
    await h.inspect();h.dismiss();await flush();assert.equal(h.writes.length,1,'unrelated inspection never permits another write');
    h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));assert.equal(h.document.body.textContent,'');assert.equal(h.latch.capture('conversations'),ticket);
    h.newSession('bob');assert.equal(h.uncertain(),false);assert.equal(h.latch.capture('conversations'),undefined);
  }finally{h.close();}
});
test('shell clears a host hold only after the original exact dismissal is observed',async()=>{
  const h=harness();try{
    h.mount('host-drafts');await flush();await h.inspect();const held=h.hold();h.dismiss();held.reject(unknown('Response lost'));await flush();await flush();
    const ticket=h.latch.capture('host-drafts');assert.equal(ticket.operation.draftId,'alice_draft');assert.equal(ticket.operation.digest,'c'.repeat(64));
    h.mount('conversations');await flush();h.click('Refresh conversations');await flush();assert.equal(h.latch.capture('host-drafts'),ticket);
    await h.inspectSavedState();await flush();assert.equal(h.uncertain(),true,'pending draft is inconclusive, not a negative receipt');assert.equal(h.writes.length,1);
    h.markDismissed();await h.inspectSavedState();await flush();assert.equal(h.uncertain(),false);assert.equal(h.writes.length,1);
    assert.equal(h.requests.filter(r=>r.path==='/api/host-drafts/alice/alice_draft/review').length,3);
  }finally{h.close();}
});
for(const failure of ['failHostInspection','wrongHostDigest'])test('shell host reconciliation remains held for '+failure,async()=>{
  const h=harness();try{
    h.mount('host-drafts');await flush();await h.inspect();const held=h.hold();h.dismiss();held.reject(unknown('Response lost'));await flush();await flush();
    h.markDismissed();h[failure]();const ticket=h.latch.capture('host-drafts');await assert.rejects(h.inspectSavedState());
    assert.equal(h.latch.capture('host-drafts'),ticket);assert.equal(h.uncertain(),true);assert.equal(h.writes.length,1);
  }finally{h.close();}
});
test('successful runtime state cannot clear optional sources or a newer inspection ticket',async()=>{
  const latch=inspectionLatch();let session=1,calls=0;
  latch.require('runtime');const conversation=latch.require('conversations',{path:'message',requestId:'exact'});
  const oldHost=latch.require('host-drafts',{draftId:'old'}),held=deferred();
  const inspecting=inspectSavedState({latch,session:()=>session,readState:async()=>{calls++;return {state:true};},inspectHost:()=>held.promise});
  await flush();assert.equal(latch.capture('runtime'),undefined);assert.equal(latch.capture('conversations'),conversation);assert.equal(latch.capture('host-drafts'),oldHost);
  const newer=latch.require('host-drafts',{draftId:'new'});held.resolve(true);await inspecting;
  assert.equal(latch.capture('host-drafts'),newer);assert.equal(latch.capture('conversations'),conversation);assert.equal(calls,1);
});
test('failed runtime inspection and old-session completion never clear current holds',async()=>{
  const latch=inspectionLatch();let session=1,attempts=0;const old=latch.require('host-drafts',{draftId:'old'});
  await assert.rejects(inspectSavedState({latch,session:()=>session,readState:async()=>{attempts++;throw Error('State lost');},inspectHost:async()=>true}));
  assert.equal(latch.capture('host-drafts'),old);assert.equal(attempts,1);
  const held=deferred(),inspecting=inspectSavedState({latch,session:()=>session,readState:async()=>({}),inspectHost:()=>held.promise});await flush();
  session++;latch.reset();const current=latch.require('conversations',{requestId:'new'});held.resolve(true);
  assert.equal(await inspecting,null);assert.equal(latch.capture('conversations'),current);
});

test('read-only POST classification is explicit and cannot downgrade conversation writes',()=>{
  for(const path of ['/api/conversations/thread/history','/api/conversations/thread/context','/api/conversations/thread/read','/api/conversations/thread/grant-review','/api/conversations/thread/message-outcome','/api/conversations/grants/list']){
    assert.equal(requestIsMutation(path,'POST'),true);assert.equal(requestIsMutation(path,'POST',true),false);
  }
  for(const path of ['/api/conversations','/api/conversations/thread/message','/api/conversations/thread/invite','/api/conversations/thread/remove','/api/conversations/invitations/invite/accept','/api/conversations/grants/grant/approve','/api/conversations/grants/grant/revoke','/api/host-drafts/host/draft/dismiss'])assert.equal(requestIsMutation(path,'POST',true),true);
});
test('failed actual history POST stays retryable without an uncertain-write hold',async()=>{
  const h=harness({room:true});try{
    h.mount('conversations');await flush();h.failHistory();h.click('Conversation · thread');await flush();
    assert.equal(h.failures.length,1);assert.equal(h.failures[0].unknown,false);assert.equal(h.uncertain(),false);assert.equal(h.writes.length,0);
    await h.inspectSavedState();await flush();h.click('Conversation · thread');await flush();assert.match(h.root.textContent,/Incoming message 0/);
    assert.equal(h.uncertain(),false);assert.equal(h.requests.filter(r=>r.path.endsWith('/history')).length,2);
  }finally{h.close();}
});

async function sendHeldMessage(h,text){
  h.mount('conversations');await flush();h.click('Conversation · thread');await flush();
  const held=h.hold(),button=await h.compose(text);while(!h.writes.length)await flush();
  return {held,button};
}
test('committed lost message response clears only after exact read, with one send and no retained plaintext',async()=>{
  const h=harness({room:true});try{
    const text='Private café ☕\n"exact" message', {held,button}=await sendHeldMessage(h,text);
    button.dispatchEvent(new Event('click'));held.reject(unknown('Committed response lost'));await flush();await flush();
    const ticket=h.latch.capture('conversations'),op=ticket.operation;
    assert.ok(Object.isFrozen(op));assert.deepEqual(Object.keys(op).sort(),['conversationId','memberEpoch','policyGeneration','principal','requestDigest','requestId','session','type']);
    assert.equal(op.requestDigest,await messageRequestDigest({text}));assert.equal(op.principal,principals.alice);
    const send=h.requests.find(r=>r.path.endsWith('/message'));assert.equal(op.requestId,send.options.body.request_id);
    assert.doesNotMatch(JSON.stringify(op),/Private|café|"text"/);
    h.mount('host-drafts');await flush();await h.inspect();assert.equal(h.latch.capture('conversations'),ticket);
    assert.equal(h.requests.filter(r=>r.path.endsWith('/message-outcome')).length,0,'no automatic inspection or send retry');
    await h.inspectSavedState();await flush();assert.equal(h.uncertain(),false);assert.equal(h.writes.length,1);
    const read=h.requests.find(r=>r.path.endsWith('/message-outcome'));assert.equal(read.options.readOnly,true);
    assert.deepEqual(read.options.body,{binding:{member_epoch:op.memberEpoch,policy_generation:op.policyGeneration},request_id:op.requestId,expected_request_digest:op.requestDigest});
    assert.doesNotMatch(h.document.body.textContent,/Private café/,'recovered words never enter an unrelated panel');
    button.dispatchEvent(new Event('click'));await flush();assert.equal(h.writes.length,1,'stale original composer cannot resend');
  }finally{h.close();}
});
test('message absence is inconclusive and repeated reads never replay the original request',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h);held.reject(unknown('Request response lost'));await flush();await flush();
    const ticket=h.latch.capture('conversations');h.outcome({status:'inconclusive'});
    for(let i=0;i<2;i++){await h.inspectSavedState();await flush();h.click('New conversation');assert.equal(h.latch.capture('conversations'),ticket);}
    assert.equal(h.writes.length,1);assert.equal(h.requests.filter(r=>r.path.endsWith('/message-outcome')).length,2);
  }finally{h.close();}
});
test('failed read-only message inspection stays retryable and cannot replace the original hold',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h);held.reject(unknown('Response lost'));await flush();await flush();
    const ticket=h.latch.capture('conversations');h.failOutcome();await assert.rejects(h.inspectSavedState(),error=>error.unknown===false);
    assert.equal(h.latch.capture('conversations'),ticket);assert.equal(h.uncertain(),true);assert.equal(h.writes.length,1);
    await h.inspectSavedState();await flush();assert.equal(h.uncertain(),false);assert.equal(h.writes.length,1);
  }finally{h.close();}
});
test('navigation and hidden-view cleanup retain only message metadata and restore without replay',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h,'A private message hidden during dispatch');
    h.mount('host-drafts');await flush();h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(h.document.body.textContent,'');assert.equal(h.busy(),true);
    held.reject(unknown('Response lost'));await flush();await flush();assert.equal(h.uncertain(),true);assert.equal(h.document.body.textContent,'');
    await h.inspectSavedState();await flush();assert.equal(h.uncertain(),false);assert.equal(h.document.body.textContent,'');
    h.document.hidden=false;h.mount('conversations');await flush();assert.equal(h.writes.length,1);assert.doesNotMatch(h.document.body.textContent,/private message/);
  }finally{h.close();}
});
test('old exact inspection cannot clear a replacement same-session message ticket',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h);held.reject(unknown('Response lost'));await flush();await flush();
    const old=h.latch.capture('conversations'),read=h.holdOutcome(),pending=h.inspectSavedState();await flush();
    const newer=h.latch.require('conversations',Object.freeze({...old.operation,requestId:'new_request'}));
    read.resolve({status:'committed',event:h.message()});await pending;assert.equal(h.latch.capture('conversations'),newer);assert.equal(h.uncertain(),true);assert.equal(h.writes.length,1);
  }finally{h.close();}
});
test('logout and new-session inspection completion cannot restore old message data or clear a new hold',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h,'Alice old private message');held.reject(unknown('Response lost'));await flush();await flush();
    const read=h.holdOutcome(),pending=h.inspectSavedState();await flush();h.newSession('bob');
    const newer=h.latch.require('conversations',Object.freeze({type:'message-outcome',session:2,principal:principals.bob,conversationId:'thread',memberEpoch:'epoch_bob',policyGeneration:1,requestId:'new',requestDigest:'c'.repeat(64)}));
    read.resolve({status:'committed',event:h.message()});await pending;await flush();
    assert.equal(h.latch.capture('conversations'),newer);assert.doesNotMatch(h.document.body.textContent,/Alice old private/);assert.equal(h.writes.length,1);
  }finally{h.close();}
});
test('hash preparation failure makes no send and creates no recoverable uncertainty ticket',async()=>{
  const h=harness({room:true}),original=crypto.subtle.digest;try{
    h.mount('conversations');await flush();h.click('Conversation · thread');await flush();
    crypto.subtle.digest=async()=>{throw Error('Digest unavailable');};await h.compose('Must never be sent');await flush();await flush();
    assert.equal(h.writes.length,0);assert.equal(h.latch.capture('conversations'),undefined);assert.equal(h.busy(),false);assert.equal(h.failures.length,1);
  }finally{crypto.subtle.digest=original;h.close();}
});
test('privacy cleanup during hashing cancels dispatch without pretending a write occurred',async()=>{
  const h=harness({room:true}),original=crypto.subtle.digest,hash=deferred();try{
    h.mount('conversations');await flush();h.click('Conversation · thread');await flush();
    crypto.subtle.digest=()=>hash.promise;await h.compose('Never dispatched');assert.equal(h.busy(),true);
    h.document.hidden=true;h.document.dispatchEvent(new Event('visibilitychange'));hash.resolve(new Uint8Array(32).buffer);await flush();await flush();
    assert.equal(h.writes.length,0);assert.equal(h.uncertain(),false);assert.equal(h.failures.length,0);assert.equal(h.document.body.textContent,'');
  }finally{crypto.subtle.digest=original;h.close();}
});
test('ordinary successful message send keeps its exact request and requires no recovery read',async()=>{
  const h=harness({room:true});try{
    const {held}=await sendHeldMessage(h,'A normal message');held.resolve(h.message());await flush();await flush();
    assert.equal(h.writes.length,1);assert.equal(h.uncertain(),false);assert.equal(h.failures.length,0);assert.equal(h.requests.filter(r=>r.path.endsWith('/message-outcome')).length,0);
    assert.equal(find(h.root,e=>e.tagName==='textarea').value,'');assert.equal(h.busy(),false);
  }finally{h.close();}
});
