import test from 'node:test';
import assert from 'node:assert/strict';
import {validateCatalogue,validateRoom,validateMessages,validateHistoryReview} from '../conversations.mjs';
const alice='a'.repeat(64),bob='b'.repeat(64),hash='c'.repeat(64);
const room={id:'thread',mode:'direct',admin:alice,binding:{conversation_id:'thread',principal:alice,member_epoch:'epoch_a',policy_generation:3},participants:[{principal:alice,epoch:'epoch_a'},{principal:bob,epoch:'epoch_b'}]};
const message={id:'event',conversation_id:'thread',author:alice,provenance_digest:hash,trust:'untrusted-message',execution_authority:false,kind:'message',text:'<script>inert</script>',sources:[]};
const catalogue={local_host_only:true,audience:'local-owner-only',execution_authority:false,principal:alice,actors:[{principal:alice,owner_id:'alice',agent_id:'assistant'}],rooms:[{id:'thread',admin:alice,mode:'direct'}],invitations:[]};
test('local catalogue never accepts provider audience or forged current identity',()=>{assert.equal(validateCatalogue(catalogue),catalogue);for(const bad of [{audience:'provider'},{principal:bob},{execution_authority:true},{actors:Array(33).fill(catalogue.actors[0])}])assert.throws(()=>validateCatalogue({...catalogue,...bad}));});
test('room binds current owner epoch and exact generation',()=>{assert.equal(validateRoom(room,'thread',alice),room);assert.throws(()=>validateRoom(room,'other',alice));assert.throws(()=>validateRoom(room,'thread',bob));assert.throws(()=>validateRoom({...room,binding:{...room.binding,policy_generation:1.5}},'thread',alice));});
test('message text stays inert with bounded exact provenance',()=>{assert.deepEqual(validateMessages([message],'thread'),[message]);for(const bad of [{conversation_id:'other'},{execution_authority:true},{text:'x'.repeat(16385)},{sources:[{id:'source',digest:'not a digest'}]}])assert.throws(()=>validateMessages([{...message,...bad}],'thread'));assert.throws(()=>validateMessages([message,message],'thread'));});
test('history review matches exact selection author recipient and member epoch',()=>{const review={statement:{domain:'assistant-central-conversation/1/history-grant',id:'grant',conversation_id:'thread',issuer:alice,recipient:bob,audience:'local-owner-only',policy_generation:3,member_epoch:'epoch_b',events:[{id:'event',digest:hash}],purpose:'Review context',expires_at:2000000100},review_digest:hash,execution_authority:false,recipient:{principal:bob},messages:[message]};assert.equal(validateHistoryReview(review,room,alice,bob,['event']),review);for(const bad of [{recipient:alice},{member_epoch:'old_epoch'},{policy_generation:2},{issuer:bob},{audience:'model'},{events:[{id:'event',digest:'d'.repeat(64)}]}])assert.throws(()=>validateHistoryReview({...review,statement:{...review.statement,...bad}},room,alice,bob,['event']));assert.throws(()=>validateHistoryReview(review,room,alice,bob,['other']));});

test('late old mount completion cannot unlock a newer operation',async()=>{
  const {operationGate}=await import('../conversations.mjs');let busy=false;const gate=operationGate(value=>{busy=value;});
  const old=gate.acquire();assert.equal(busy,true);gate.reset();assert.equal(busy,false);
  const current=gate.acquire();assert.equal(busy,true);old();assert.equal(busy,true);current();assert.equal(busy,false);
});
test('successful mutation with failed saved-state inspection remains uncertain',async()=>{
  const {inspectMutation}=await import('../conversations.mjs');const unknown=message=>Object.assign(new Error(message),{unknown:true});let writes=0;
  await assert.rejects(inspectMutation(async()=>{writes++;},async()=>{throw new Error('GET failed');},unknown),error=>error.unknown===true&&error.message.includes('operation returned'));
  assert.equal(writes,1);
  const expired=Object.assign(new Error('expired'),{unauthorised:true});await assert.rejects(inspectMutation(async()=>{},async()=>{throw expired;},unknown),error=>error===expired);
});

test('component privacy cleanup preserves an unresolved mutation request fence',async()=>{
  // A minimal inert DOM exercises controller events and request ordering, not
  // layout. Actual layout/browser acceptance remains the hosted test's job.
  class Element extends EventTarget{
    constructor(tag){super();this.tagName=tag;this.children=[];this.dataset={};this.open=false;this._text='';}
    set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent||'').join('');}
    append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this._text='';this.children=[...nodes];}
    setAttribute(){}close(){this.open=false;this.dispatchEvent(new Event('close'));}showModal(){this.open=true;}
  }
  const original=globalThis.document,doc=new EventTarget(),dialog=new Element('dialog');doc.hidden=false;doc.createElement=t=>new Element(t);doc.getElementById=()=>dialog;globalThis.document=doc;
  const {createConversations}=await import('../conversations.mjs');const root=new Element('div');let isBusy=false,settle,writes=0,ownerSession=1;const failures=[];
  const unknownFailure=message=>Object.assign(new Error(message),{unknown:true});let controller;
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  const request=async(path,options={})=>{if(options.method==='POST'){writes++;return new Promise(resolve=>{settle=resolve;});}return {...catalogue,rooms:[]};};
  const find=(element,label)=>element.textContent===label?element:element.children.map(c=>find(c,label)).find(Boolean);
  try{
    controller=createConversations({request,busy:()=>isBusy,setBusy:v=>{isBusy=v;},failed:e=>failures.push(e),active:()=>true,unknownFailure,session:()=>ownerSession,restore:()=>controller.mount(root,true)});
    controller.mount(root,true);await flush();find(root,'New conversation').dispatchEvent(new Event('click'));await flush();assert.equal(writes,1);assert.equal(isBusy,true);
    doc.hidden=true;doc.dispatchEvent(new Event('visibilitychange'));assert.equal(root.textContent,'');assert.equal(isBusy,true,'clearing plaintext is not cancellation');
    settle({binding:{}});await flush();await flush();assert.equal(isBusy,false);assert.equal(failures.length,1);assert.equal(failures[0].unknown,true);assert.equal(writes,1);
  }finally{controller?.reset({sessionEnded:true});globalThis.document=original;}
});

test('passive new messages preserve only an unsent draft for the exact current audience',async()=>{
  const {nextComposer}=await import('../conversations.mjs');
  const context={session:1,principal:alice,conversationId:'thread',memberEpoch:'epoch_a',policyGeneration:3};
  const original=nextComposer(null,context);original.text='An unsent plan';
  const same=nextComposer(original,{...context},{passive:true});assert.equal(same,original);assert.equal(same.requestId,original.requestId);assert.equal(same.text,'An unsent plan');
  for(const change of [{session:2},{principal:bob},{conversationId:'other'},{memberEpoch:'new_epoch'},{policyGeneration:4}]){
    const fresh=nextComposer(original,{...context,...change},{passive:true});assert.equal(fresh.text,'');assert.notEqual(fresh.requestId,original.requestId);
  }
  const explicit=nextComposer(original,context);assert.equal(explicit.text,'');assert.notEqual(explicit.requestId,original.requestId);
  assert.equal(nextComposer(null,context,{passive:true}).text,'','privacy reset leaves no draft to retain');
});
test('passive refresh cannot turn a submitted or uncertain draft into a new request',async()=>{
  const {nextComposer}=await import('../conversations.mjs');
  const context={session:1,principal:alice,conversationId:'thread',memberEpoch:'epoch_a',policyGeneration:3};
  const draft=nextComposer(null,context);draft.text='Already submitted';draft.submitted=true;
  assert.equal(nextComposer(draft,context,{passive:true}),null);
  assert.equal(nextComposer(draft,{...context,policyGeneration:4},{passive:true}),null);
});

test('request canonicalisation matches Python UTF-8 bytes and SHA-256 for Unicode, escaping and source order',async()=>{
  const {execFileSync}=await import('node:child_process');
  const {canonicalMessageRequest,messageRequestDigest}=await import('../conversations.mjs');
  const vectors=[{text:'Fictional café ☕'},{text:'Quotes " / \\ \b\f\n\r\t\u0000\u001f'},{text:'𝄞🧑‍🚀\u2028\u2029 café cafe\u0301'},{kind:'quote',text:'Original source order',source_ids:['source_b','source_a']},{kind:'summary',text:'Reversed source order',source_ids:['source_a','source_b']}];
  for(const value of vectors){
    const request={kind:'message',source_ids:[],...value},actual=canonicalMessageRequest(request);
    const expected=JSON.parse(execFileSync('python',['-c','import json,sys; from pilot.crypto import canonical,digest; value=json.load(sys.stdin); print(json.dumps({"bytes": canonical(value).hex(), "digest": digest(value)}))'],{input:JSON.stringify(request),encoding:'utf8'}));
    assert.equal(Buffer.from(actual,'utf8').toString('hex'),expected.bytes);assert.equal(await messageRequestDigest(request),expected.digest);
  }
  assert.equal(await messageRequestDigest(vectors[0]),'6a83aee7ede93131aebfe490a00513769eb432d2f24013856c57b630fed65bc8');
  assert.notEqual(await messageRequestDigest({text:'café'}),await messageRequestDigest({text:'cafe\u0301'}),'never normalise owner text');
  assert.notEqual(await messageRequestDigest({kind:'quote',text:'same',source_ids:['a','b']}),await messageRequestDigest({kind:'quote',text:'same',source_ids:['b','a']}));
});
test('ill-formed surrogates, oversized text and invalid sources fail before hashing',async()=>{
  const {canonicalMessageRequest}=await import('../conversations.mjs');
  for(const text of ['\ud800','\udc00','a\ud800b','\udc00\ud800','x'.repeat(16385),'☕'.repeat(5462),''])assert.throws(()=>canonicalMessageRequest({text}));
  for(const value of [{kind:'quote',text:'word'},{text:'word',source_ids:['same','same']},{text:'word',source_ids:['invalid.id']},{text:'word',source_ids:Array(33).fill('source')},{kind:'proposal',text:'word'}])assert.throws(()=>canonicalMessageRequest(value));
});
test('exact message inspector requires current session, original owner room and recomputed content commitment',async()=>{
  const {prepareMessageOperation,inspectMessageOutcome}=await import('../conversations.mjs');let session=3,calls=0;
  const operation=await prepareMessageOperation({session,principal:alice,conversationId:'thread',memberEpoch:'epoch_a',policyGeneration:3},'original_request',message.text);
  const inspect=result=>inspectMessageOutcome({session:()=>session,operation,request:async()=>{calls++;return result;}});
  assert.equal(await inspect({status:'committed',event:message}),true);
  assert.notEqual(operation.requestDigest,message.provenance_digest,'request hash is not provenance hash');
  for(const changed of [{author:bob},{conversation_id:'other'},{text:'Different content'},{kind:'quote',sources:[{id:'source',digest:hash}]},{execution_authority:true}])await assert.rejects(inspect({status:'committed',event:{...message,...changed}}));
  for(const malformed of [{status:'pending'},{status:'inconclusive',event:message},{status:'committed'},{status:'committed',event:message,extra:'data'}])await assert.rejects(inspect(malformed));
  assert.equal(await inspect({status:'inconclusive'}),false);
  const before=calls;session++;assert.equal(await inspect({status:'committed',event:message}),false);assert.equal(calls,before,'old session never makes an inspection request');
  assert.equal(await inspectMessageOutcome({session:()=>session,operation:{path:'invite'},request:async()=>{throw Error('Unsupported mutation must not be inspected');}}),false);
});
