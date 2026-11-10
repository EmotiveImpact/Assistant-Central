import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { fixture, draft } from './helpers.mjs';
import { DraftStore } from '../src/store.ts';
const principal = 'a'.repeat(64);
const owner = {principal, sessionDigest:'b'.repeat(64), sessionExpiresAt:Date.now()+600_000};
const setup = () => fixture('review',{ownerId:principal});
const create = f => f.store.dispatch(f.binding,'create_task_draft',draft).draftId;
const review = (f,id,who=owner) => f.store.reviewForOwner(f.binding,who,id);
const dismiss = (f,r,who=owner) => f.store.dismissForOwner(f.binding,who,r.status.draftId,r.digest,r.reviewToken);
const denied = fn => assert.throws(fn);

test('owner list and exact review bind complete immutable content and real fingerprint',()=>{
 const f=setup();try{ const id=create(f);const r=review(f,id);
 assert.deepEqual(r.draft,draft);assert.deepEqual(r.binding,f.binding);
 assert.deepEqual(f.store.listForOwner(f.binding,owner),[{draftId:id,title:draft.title,state:'awaiting_owner_review'}]);
 assert.equal(r.status.ownerConsent,'not_requested');assert.equal(r.status.transportReceipt,'none');assert.equal(r.status.execution,'not_started');
 assert.equal(r.digest.length,64);assert.ok(r.reviewExpiresAt<=f.binding.expiresAt);
 }finally{f.cleanup();}
});
test('dismiss is exact, terminal, encrypted, idempotent after response loss and restart',()=>{
 const f=setup();let reopened;try{ const id=create(f),r=review(f,id);const one=dismiss(f,r),two=dismiss(f,r);
 assert.deepEqual(one,two);assert.equal(one.status.state,'dismissed');
 assert.equal(f.store.dispatch(f.binding,'task_draft_status',{draftId:id}).state,'dismissed');
 assert.equal(f.store.dispatch(f.binding,'create_task_draft',draft).state,'dismissed');
 reopened=new DraftStore(f.launch.storePath,f.key);
 assert.deepEqual(reopened.dismissForOwner(f.binding,owner,id,r.digest,r.reviewToken),one);
 const current=reopened.reviewForOwner(f.binding,owner,id);assert.deepEqual(current.decision,one.decision);
 const db=new DatabaseSync(f.launch.storePath);assert.equal(db.prepare('SELECT count(*) AS n FROM owner_dismissals').get().n,1);db.close();
 const bytes=readFileSync(f.launch.storePath); for(const value of [draft.title,draft.instruction,owner.sessionDigest,r.reviewToken,one.decision.decisionId]) assert.equal(bytes.includes(Buffer.from(value)),false);
 }finally{reopened?.close();f.cleanup();}
});
test('other authenticated owners, sessions, binding fields, altered digest/token and IDs fail',()=>{
 const f=setup();try{const id=create(f),r=review(f,id);
 denied(()=>review(f,id,{...owner,principal:'c'.repeat(64)}));
 denied(()=>dismiss(f,r,{...owner,sessionDigest:'c'.repeat(64)}));
 denied(()=>dismiss(f,r,{...owner,sessionExpiresAt:owner.sessionExpiresAt+1}));
 denied(()=>dismiss(f,{...r,digest:'0'.repeat(64)}));
 denied(()=>dismiss(f,{...r,reviewToken:r.reviewToken+'x'}));
 denied(()=>dismiss(f,{...r,status:{draftId:'missing'}}));
 for(const field of ['ownerId','hostId','sessionId','conversationId','recipientId','expiresAt']) {
 const binding={...f.binding,[field]:field==='expiresAt'?f.binding.expiresAt+1:'changed'};
 denied(()=>f.store.dismissForOwner(binding,owner,id,r.digest,r.reviewToken));
 }
 assert.equal(review(f,id).status.state,'awaiting_owner_review');
 }finally{f.cleanup();}
});
test('same owner with a new authenticated session must inspect again; saved decision remains stable',()=>{
 const f=setup();try{const id=create(f),r=review(f,id),one=dismiss(f,r);const current={...owner,sessionDigest:'d'.repeat(64)};
 denied(()=>dismiss(f,r,current));const newReview=review(f,id,current);assert.deepEqual(dismiss(f,newReview,current),one);
 }finally{f.cleanup();}
});
test('revoked and expired scopes refuse all owner facade operations, including repeated dismiss',()=>{
 for(const mode of ['revoke','expire','rollback']) { const f=setup();let other;
 try{const id=create(f),r=review(f,id);dismiss(f,r);
 if(mode==='revoke')f.store.revoke(f.binding);
 other=new DraftStore(f.launch.storePath,f.key,()=>mode==='expire'?f.binding.expiresAt:mode==='rollback'?1:Date.now());
 denied(()=>other.listForOwner(f.binding,owner));denied(()=>other.reviewForOwner(f.binding,owner,id));
 denied(()=>other.dismissForOwner(f.binding,owner,id,r.digest,r.reviewToken));
 }finally{other?.close();f.cleanup();}}
});
test('review lease and owner session deadline are enforced separately from host lease',()=>{
 for(const mode of ['review','owner']) {const f=setup();let other;try{
 const id=create(f),r=review(f,id);const now=mode==='review'?r.reviewExpiresAt:owner.sessionExpiresAt;
 other=new DraftStore(f.launch.storePath,f.key,()=>now);
 denied(()=>other.dismissForOwner(f.binding,owner,id,r.digest,r.reviewToken));
 assert.equal(f.store.inspectForOwner(f.binding,id).status.state,'awaiting_owner_review');
 }finally{other?.close();f.cleanup();}}
});
test('review/host/session expiry crossing final commit rolls back dismissal and keeps the fence',()=>{
 for(const mode of ['review','host','session','rollback']) {const f=setup();let other;try{
 const id=create(f),r=review(f,id);const initial=Date.now();let calls=0;
 other=new DraftStore(f.launch.storePath,f.key,()=>++calls===1?initial:mode==='host'?f.binding.expiresAt:mode==='session'?owner.sessionExpiresAt:mode==='rollback'?1:r.reviewExpiresAt);
 denied(()=>other.dismissForOwner(f.binding,owner,id,r.digest,r.reviewToken));
 assert.equal(f.store.inspectForOwner(f.binding,id).status.state,'awaiting_owner_review');
 const db=new DatabaseSync(f.launch.storePath);assert.equal(db.prepare('SELECT count(*) AS n FROM owner_dismissals').get().n,0);db.close();
 }finally{other?.close();f.cleanup();}}
});
test('old review cannot cross current host conversation or recipient scope replacement',()=>{
 const f=setup();try{const id=create(f),r=review(f,id);for(const key of ['conversationId','recipientId']){
 const b={...f.binding,[key]:'different'};f.store.provision(b);const second=f.store.dispatch(b,'create_task_draft',draft);
 denied(()=>f.store.dismissForOwner(b,owner,second.draftId,r.digest,r.reviewToken));
 assert.equal(f.store.listForOwner(b,owner).length,1);
 }}finally{f.cleanup();}
});
test('exact authenticated v1 store migration preserves original drafts and rejects partial/unknown variants',()=>{
 for(const mode of ['valid','wrong-key','partial','wrong-version']) {const f=setup();let reopened;try{
 const id=create(f);const db=new DatabaseSync(f.launch.storePath);db.exec('DROP TABLE owner_dismissals; UPDATE bridge_meta SET version=1');
 if(mode==='partial')db.exec('CREATE TABLE owner_dismissals (scope TEXT)');
 if(mode==='wrong-version')db.exec('UPDATE bridge_meta SET version=99');db.close();
 if(mode!=='valid')denied(()=>new DraftStore(f.launch.storePath,mode==='wrong-key'?Buffer.alloc(32):f.key));
 else{denied(()=>new DraftStore(f.launch.storePath,f.key));reopened=new DraftStore(f.launch.storePath,f.key,Date.now,{allowOfflineV1Upgrade:true});assert.deepEqual(reopened.reviewForOwner(f.binding,owner,id).draft,draft);}
 }finally{reopened?.close();f.cleanup();}}
});
test('ciphertext swaps or a corrupted dismissal cannot give successful reviewed state',()=>{
 const f=setup();try{const id=create(f),r=review(f,id);dismiss(f,r);const db=new DatabaseSync(f.launch.storePath);
 db.exec("UPDATE owner_dismissals SET sealed='invalid'");db.close();
 denied(()=>f.store.listForOwner(f.binding,owner));denied(()=>review(f,id));denied(()=>dismiss(f,r));
 denied(()=>f.store.dispatch(f.binding,'task_draft_status',{draftId:id}));
 }finally{f.cleanup();}
});
