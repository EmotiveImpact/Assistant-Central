// Real cross-process owner-read/model-write contention, not a mocked SQLite lock.
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {DatabaseSync} from 'node:sqlite';
import {fixture,draft} from './helpers.mjs';
import {DraftStore} from '../src/store.ts';
const principal='a'.repeat(64);
const storeURL=new URL('../src/store.ts',import.meta.url).href;
async function ownerHoldingLock(f){
 const program=`import {readFileSync,readSync} from 'node:fs';import {DraftStore} from ${JSON.stringify(storeURL)};
 const f=JSON.parse(readFileSync(0,'utf8'));let first=true;
 const store=new DraftStore(f.storePath,Buffer.from(f.keyHex,'hex'),()=>{if(first){first=false;process.stdout.write('locked\\n');if(readSync(3,Buffer.alloc(1),0,1,null)!==1)throw Error('Missing fixture gate');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,250);}return Date.now();});
 try{store.listForOwner(f.binding,{principal:f.binding.ownerId,sessionDigest:'b'.repeat(64),sessionExpiresAt:f.binding.expiresAt});}finally{store.close();}`;
 const child=spawn(process.execPath,['--input-type=module','-e',program],{env:{NODE_NO_WARNINGS:'1'},stdio:['pipe','pipe','pipe','pipe']});
 const done=once(child,'exit');child.stdin.end(JSON.stringify(f.launch));
 await Promise.race([once(child.stdout,'data'),done.then(()=>{throw Error('Fictional owner fixture failed before lock');})]);
 return {child,done,release(){child.stdio[3].end(Buffer.from([1]));}};
}
test('waiting model dispatch samples time after the actual owner transaction, without revocation or duplicate effect',{timeout:5000},async()=>{
 const f=fixture('contention',{ownerId:principal});let held;
 try{
  const before=f.store.dispatch(f.binding,'create_task_draft',draft);held=await ownerHoldingLock(f);
  held.release();const repeat=f.store.dispatch(f.binding,'create_task_draft',draft);
  assert.deepEqual(repeat,before);assert.equal((await held.done)[0],0);
  const db=new DatabaseSync(f.launch.storePath);try{
   assert.equal(db.prepare('SELECT count(*) AS n FROM drafts').get().n,1);
   const scope=db.prepare('SELECT revoked,expires,operations FROM scopes').get();
   assert.equal(scope.revoked,0);assert.equal(scope.expires,f.binding.expiresAt);assert.equal(scope.operations,2);
  }finally{db.close();}
  assert.equal(f.store.dispatch(f.binding,'task_draft_status',{draftId:before.draftId}).state,'awaiting_owner_review');
 }finally{held?.child.kill();f.cleanup();}
});
test('provision cannot admit a new lease which expires while waiting for the owner write lock',{timeout:5000},async()=>{
 const f=fixture('provision_contention',{ownerId:principal});let held;
 try{
  held=await ownerHoldingLock(f);const binding={...f.binding,sessionId:'expires_while_waiting',expiresAt:Date.now()+50};held.release();
  assert.throws(()=>f.store.provision(binding));assert.equal((await held.done)[0],0);
  const db=new DatabaseSync(f.launch.storePath);try{
   assert.equal(db.prepare('SELECT count(*) AS n FROM scopes').get().n,1);
   assert.equal(db.prepare('SELECT expires FROM scopes').get().expires,f.binding.expiresAt);
  }finally{db.close();}
  assert.throws(()=>f.store.dispatch(binding,'create_task_draft',draft));
 }finally{held?.child.kill();f.cleanup();}
});
test('provision checks final expiry and genuine backwards time without installing or reviving scopes',()=>{
 for(const existing of [false,true])for(const backwards of [false,true]){
  const f=fixture('provision_final',{ownerId:principal});let current;
  try{
   const start=Date.now();const binding=existing?f.binding:{...f.binding,sessionId:'new_scope'};let ticks=0;
   current=new DraftStore(f.launch.storePath,f.key,()=>++ticks===1?start:backwards?start-1000:binding.expiresAt);
   assert.throws(()=>current.provision(binding));
   const db=new DatabaseSync(f.launch.storePath);try{
    assert.equal(db.prepare('SELECT count(*) AS n FROM scopes').get().n,1);
    assert.equal(db.prepare('SELECT revoked FROM scopes').get().revoked,existing?1:0);
    assert.equal(db.prepare('SELECT expires FROM scopes').get().expires,f.binding.expiresAt);
   }finally{db.close();}
   if(existing)assert.throws(()=>f.store.dispatch(f.binding,'create_task_draft',draft));
  }finally{current?.close();f.cleanup();}
 }
});
