/* Independent dependency-free DOM-model review checks, not browser acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'workspace_relationship_dom_check.js'),'utf8');
const sandbox={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(sandbox);
vm.runInContext(source.slice(0,source.indexOf('\nconst tests=[];'))+'\nglobalThis.reviewHarness=harness;globalThis.reviewTick=tick;globalThis.reviewGroup=group;',sandbox);
const {reviewHarness:harness,reviewTick:tick,reviewGroup:group}=sandbox;
const tests=[];const test=(n,f)=>tests.push([n,f]);
for (const [name,change] of [
 ['other group',p=>({...p,group_id:'group-other'})],
 ['other operation',p=>({...p,operation:'attach',member:{selector:'astronomy',context:'a'.repeat(64)}})],
 ['stale revision',p=>({...p,revision:2})],
 ['wrong exact context',p=>({...p,members:[{selector:'garden',context:'x'.repeat(64)}]})],
 ['other membership',p=>({...p,members:[{selector:'astronomy',context:'a'.repeat(64)}]})],
 ['missing digest',p=>{delete p.review_digest;return p;}],
 ]) test('reject stop preview with '+name+' before review rendering',async()=>{
 const h=harness({groups:[group()],post:(body,r)=>r(change({operation:'stop',group_id:'group-fictional',revision:1,members:[{selector:'garden',context:'g'.repeat(64)}],review_digest:'d'.repeat(64)}))});
 await tick();await h.view('relationships/group-fictional');await h.find('Review stop further group work').click();
 assert(!h.find('Confirm reviewed group stop')&&!h.find('Confirm reviewed group attach'),'mismatched scope must offer no commit');
 assert(!h.ids.content.textContent.includes('Review exact fictional group scope'),'mismatched review must not render');assert.equal(h.posts.length,1);
});
for (const [name,change] of [
 ['attachment context',p=>({...p,member:{selector:'astronomy',context:'x'.repeat(64)}})],
 ['attachment selector',p=>({...p,member:{selector:'garden',context:'g'.repeat(64)}})],
 ['membership revision',p=>({...p,revision:2})],
 ]) test('reject attach preview with substituted '+name,async()=>{
 const h=harness({groups:[group()],post:(body,r)=>r(change({operation:'attach',group_id:'group-fictional',revision:1,members:[{selector:'garden',context:'g'.repeat(64)}],member:body.member,review_digest:'d'.repeat(64)}))});
 await tick();await h.view('relationships/group-fictional');await h.find('Review attach astronomy').click();assert(!h.find('Confirm reviewed group attach'));assert.equal(h.posts.length,1);
});
test('reject substituted create label before review rendering',async()=>{
 const h=harness({post:(body,r)=>r({operation:'create',registry_revision:0,...body.spec,label:'substituted',revision:1,review_digest:'d'.repeat(64)})});
 await h.preview();assert(!h.find('Confirm reviewed group create'));assert.equal(h.posts.length,1);
});
test('stopped received history remains reachable via controls',async()=>{
 const h=harness({get:(url,r)=>url.startsWith('/api/messages')?r({owner:'alice',context:'g'.repeat(64),task:'garden-task',messages:[]}):null});await tick();h.rows[0].local_work_stopped=true;await h.view('garden/alice/inbox');
 assert(!h.find('Received messages').disabled);await h.find('Received messages').click();assert.match(h.ids.content.textContent,/Received messages for alice/);assert.equal(h.posts.length,0);
});
test('stopped proposal history remains reachable without import',async()=>{
 const h=harness();await tick();h.rows[0].local_work_stopped=true;await h.view('garden/alice/inbox');assert(!h.find('Staged proposals').disabled);await h.find('Staged proposals').click();assert.match(h.ids.content.textContent,/fixture-p1/);assert(!h.find('Open proposal for owner review'));assert.equal(h.posts.length,0);
});
test('all forbidden task mutation names fail closed locally after stop',async()=>{
 const h=harness();await tick();h.rows[0].local_work_stopped=true;await h.view('garden/alice/inbox');
 for(const action of ['bind','create','next','approve','submit','attempt','process','import_proposal','preview_response','prepare_response','cancel','revoke','replace_review','fresh_after_withdrawal','review_pairing','unknown'])await vm.runInContext(`mutate(active,{action:${JSON.stringify(action)}})`,h.context);
 assert.equal(h.posts.length,0);
});
(async()=>{let failures=0;for(const[n,f]of tests){try{await f();console.log('PASS '+n);}catch(e){failures++;console.error('FAIL '+n+'\n'+e.stack);}}console.log(`${tests.length-failures}/${tests.length} independent relationship DOM-model checks passed (not browser tests).`);if(failures)process.exitCode=1;})();
