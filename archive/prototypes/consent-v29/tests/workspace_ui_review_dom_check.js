/* Independent supplemental DOM MODEL checks. No browser/visual/a11y claims. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
// Reuse only the model harness, not the original test runner or test cases.
const base = fs.readFileSync(path.join(__dirname,'workspace_ui_dom_check.js'),'utf8');
const model = {require,__dirname,console,setImmediate,URL,URLSearchParams};
vm.createContext(model);
vm.runInContext(base.slice(0,base.indexOf('const tests=[];')) + '\nglobalThis.makeHarness=harness;globalThis.flush=tick;',model);
const {makeHarness:harness,flush:tick} = model;
const tests=[];
function test(name,fn){tests.push([name,fn]);}
test('same task leave-and-return fences old approval callback by generation',async()=>{
 const h=harness();await tick();const route='garden/alice/request/'+h.card.request_id;
 await h.view(route);await h.find('Approve exact request').click();const saved=h.ids.dialogConfirm.onclick;
 await h.view('astronomy/bob/inbox');await h.view(route);
 h.ids.confirmation.value='APPROVE alice';saved();await tick();assert.equal(h.posts.length,0);
});
test('same task leave-and-return fences old mutation response by generation',async()=>{
 let release;const h=harness({post:()=>new Promise(r=>release=r)});await tick();
 await h.view('garden/alice/inbox');await h.find('Prepare next review').click();
 await h.hash('astronomy/bob/inbox');await h.hash('garden/alice/inbox');
 release(h.response({kind:'request',card:h.card}));await tick();
 assert.equal(h.context.location.hash,'#garden/alice/inbox');assert(!h.ids.content.textContent.includes('Review for alice'));
 assert(h.find('Prepare next review'));assert.equal(h.posts.length,1);
});
test('malformed navigation stays inert rather than silently selecting or creating',async()=>{
 const h=harness({phase:'not_created'});await tick();await h.hash('garden/%E0%A4%A/inbox');
 assert(!h.ids.error.hidden);assert(!h.find('Create selected temporary task'));assert.equal(h.posts.length,0);
 assert(!h.gets.some(u=>u.startsWith('/api/state')));
});
test('owner switch invalidates prior owner buttons even within same task',async()=>{
 const h=harness();await tick();await h.view('garden/alice/inbox');const saved=h.find('Review cancellation');
 await h.view('garden/bob/inbox');await saved.click();assert.equal(h.posts.length,0);
 await h.find('Review cancellation').click();assert.equal(h.posts.length,1);
 assert.equal(h.posts[0].request.owner,'bob');assert.equal(h.posts[0].selector,'garden');
});
test('binding confirmation title body phrase and action all name target owner',async()=>{
 const h=harness({servicePhase:'bindings',bindingOwner:'bob'});await tick();await h.view('garden/alice/inbox');
 await h.find('Review binding for bob').click();assert.equal(h.ids.dialogTitle.textContent,'Bind bob');
 assert(h.ids.dialogBody.textContent.includes('Owner: bob'));assert(!h.ids.dialogBody.textContent.includes('Owner: alice'));
 assert.equal(h.ids.confirmation.placeholder,'BIND bob');assert.equal(h.ids.confirmationLabel.textContent,'Type BIND bob to continue');
 await h.confirm('BIND bob');assert.equal(h.posts[0].request.owner,'bob');
});
test('HTTP error body without usable JSON is uncertainty, never automatic retry',async()=>{
 const h=harness({post:()=>Promise.resolve({ok:false,json:async()=>{throw Error('bad response');}})});await tick();
 await h.view('garden/alice/inbox');await h.find('Prepare next review').click();
 assert.equal(h.posts.length,1);assert.match(h.ids.error.textContent,/may have committed/);
 assert.match(h.ids.error.textContent,/Nothing was retried automatically/);
});
(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} independent DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
