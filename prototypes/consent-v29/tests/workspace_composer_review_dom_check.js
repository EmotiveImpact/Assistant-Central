/* Independent composer race checks. DOM model only, not browser acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'workspace_composer_dom_check.js'),'utf8');
const context={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(context);
vm.runInContext(source.slice(0,source.indexOf("test('opening composer"))+'\nglobalThis.reviewHarness=harness;globalThis.flush=tick;',context);
const hmake=context.reviewHarness,tick=context.flush;
const tests=[];
function preview(body,response){return response({spec:body.spec,selector:body.spec.selector,task:body.spec.task_id,requester:body.spec.requester,responder:'alice',context:'c'.repeat(64),review_digest:'d'.repeat(64)});}
tests.push(['late successful creation does not navigate away from a different task',async()=>{
 let release;const h=hmake({post:(b,r)=>!b.action?preview(b,r):new Promise(resolve=>release=resolve)});
 await h.preview();await h.find('Create this reviewed task').click();await h.confirm('CREATE TASK');
 await h.view('astronomy/bob/inbox');
 release(h.response({selector:'custom-books',task:'task-books',context:'c'.repeat(64),requester:'bob',responder:'alice',phase:'open'}));await tick();
 assert.equal(h.context.location.hash,'#astronomy/bob/inbox');assert.equal(h.posts.length,2);
 assert(!h.find('Create this reviewed task'));
}]);
tests.push(['saved confirmation after editing cannot create an earlier review',async()=>{
 const h=hmake();await h.preview();await h.find('Create this reviewed task').click();
 const stale=h.ids.dialogConfirm.onclick;await h.ids.dialogCancel.click();await h.find('Edit as a new review').click();
 h.field('composeName').value='new-books';h.field('composeQuery').value='New fictional examples';
 await h.find('Preview exact task').click();h.ids.confirmation.value='CREATE TASK';stale();await tick();
 assert.equal(h.posts.length,2);assert(h.ids.content.textContent.includes('custom-new-books'));
}]);
tests.push(['late rejected creation cannot paint an error over another task',async()=>{
 let reject;const h=hmake({post:(b,r)=>!b.action?preview(b,r):new Promise((_,rj)=>reject=rj)});
 await h.preview();await h.find('Create this reviewed task').click();await h.confirm('CREATE TASK');await h.view('garden/alice/inbox');
 reject(Error('lost'));await tick();assert.equal(h.context.location.hash,'#garden/alice/inbox');
 assert(h.ids.error.hidden);assert.equal(h.posts.length,2);assert(!h.find('Inspect task catalog'));
}]);
(async()=>{let failures=0;for(const [name,run] of tests){try{await run();console.log('PASS '+name);}catch(e){failures++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failures}/${tests.length} independent composer DOM-model checks passed.`);if(failures)process.exitCode=1;})();
