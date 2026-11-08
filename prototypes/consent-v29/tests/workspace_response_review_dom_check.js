/* Independent interruption review. DOM model only, no real browser acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
// Reuse only fixture construction, not implementation test assertions.
const base=fs.readFileSync(path.join(__dirname,'workspace_response_dom_check.js'),'utf8');
const model={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(model);
vm.runInContext(base.slice(0,base.indexOf("test('only custom responder"))+'\nglobalThis.makeResponse=harness;globalThis.flush=tick;',model);
const {makeResponse:harness,flush:tick}=model,tests=[];
const test=(name,fn)=>tests.push([name,fn]);
test('late prepare success never navigates away from newer task',async()=>{
 let release;const h=harness({post:(b,r,p)=>b.request.action==='preview_response'?p(b,r):new Promise(resolve=>release=()=>resolve(r({kind:'request',card:{...h.card,owner:'bob'}})))});
 await h.preview();await h.find('Prepare unsigned response review').click();await h.confirm('REVIEW RESPONSE bob');
 await h.view('garden/alice/inbox');release();await tick();
 assert.equal(h.context.location.hash,'#garden/alice/inbox');assert.match(h.ids.content.textContent,/garden-task/);assert.equal(h.posts.length,2);
});
test('late prepare rejection cannot contaminate a new response session',async()=>{
 let reject;const h=harness({post:(b,r,p)=>b.request.action==='preview_response'?p(b,r):new Promise((_,j)=>reject=j)});
 await h.preview();await h.find('Prepare unsigned response review').click();await h.confirm('REVIEW RESPONSE bob');
 await h.view('custom-books/bob/response');reject(Error('lost preparation'));await tick();
 assert(h.find('Preview exact response'));assert(h.ids.error.hidden);assert(!h.ids.content.textContent.includes('attempted once'));assert.equal(h.posts.length,2);
});
test('same route navigation invalidates previous exact confirmation',async()=>{
 const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();const saved=h.ids.dialogConfirm.onclick;
 await h.view('custom-books/bob/response');h.ids.confirmation.value='REVIEW RESPONSE bob';saved();await tick();
 assert.equal(h.posts.length,1);assert(!h.ids.confirmDialog.open);assert(h.find('Preview exact response'));
});
test('preview in flight freezes captured values even when editable DOM changes',async()=>{
 let release;const h=harness({post:(b,r,p)=>new Promise(resolve=>release=()=>resolve(p(b,r)))});
 await h.compose();h.fill();await h.find('Preview exact response').click();h.field('responseTitle0').value='Later text';release();await tick();
 assert.equal(h.posts[0].request.payload.items[0].title,'Fictional guide');assert(!h.ids.content.textContent.includes('Later text'));
});
test('empty response survives edit and explicit repreview without restored default item',async()=>{
 const h=harness();await h.compose();await h.find('Remove last item').click();await h.find('Preview exact response').click();
 await h.find('Edit response as a new preview').click();assert(h.find('Remove last item').disabled);await h.find('Preview exact response').click();
 assert.equal(h.posts.length,2);assert.equal(h.posts[1].request.payload.items.length,0);
});
test('raw hash change fences old preview click before hash event',async()=>{
 const h=harness();await h.compose();h.fill();const old=h.find('Preview exact response');h.context.location.hash='#garden/alice/inbox';await old.click();assert.equal(h.posts.length,0);
});
test('modal blocks editing and preview resubmission until cancellation',async()=>{
 const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();await h.find('Edit response as a new preview').click();
 assert(h.ids.confirmDialog.open);assert(h.find('Prepare unsigned response review'));await h.ids.dialogCancel.click();await h.find('Edit response as a new preview').click();
 assert(h.find('Preview exact response'));assert.equal(h.posts.length,1);
});
(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} independent response DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
