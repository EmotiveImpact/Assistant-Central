/* Independent offline model regressions; no browser or visual acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'workspace_text_exchange_dom_check.js'),'utf8');
const ctx={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(ctx);
vm.runInContext(source.slice(0,source.indexOf("test('default capability"))+'\nglobalThis.helpers={composer,responseHarness,choose,tick};',ctx);
const {composer,responseHarness,choose,tick}=ctx.helpers;
const tests=[];const test=(name,fn)=>tests.push([name,fn]);
test('unknown composer capability cannot fall back to shortlist',async()=>{
 const h=composer.make();await h.compose();await choose(h,'unregistered-text-v2');await h.find('Preview exact task').click();assert.equal(h.posts.length,0);assert.match(h.ids.error.textContent,/Unknown capability/);
});
test('delayed text preview freezes capability and bound at click time',async()=>{
 let release;const h=composer.make({post:(body,r)=>new Promise(resolve=>{release=()=>resolve(r({spec:body.spec,selector:body.spec.selector,task:body.spec.task_id,requester:body.spec.requester,responder:'alice',context:'c'.repeat(64),review_digest:'d'.repeat(64)}));})});
 await h.compose();await choose(h);h.field('composeReplyChars').value='2';await h.find('Preview exact task').click();
 await choose(h,'public-resource-shortlist-v1');h.field('composeReplyChars').value='512';release();await tick();
 await h.find('Create this reviewed task').click();assert.match(h.ids.dialogBody.textContent,/bounded-text-exchange-v1/);assert.match(h.ids.dialogBody.textContent,/"max_reply_chars":\s*2/);assert.equal(h.posts.length,1);
});
test('response edit changes text and needs a new preview before preparation',async()=>{
 const h=responseHarness({limit:2});await h.preview('😀a');await h.find('Edit response as a new preview').click();
 assert.equal(h.field('responseText').value,'😀a');assert(!h.find('Prepare unsigned response review'));
 h.field('responseText').value='e\u0301x';await h.find('Preview exact response').click();assert.equal(h.posts.length,1);
 h.field('responseText').value='e\u0301';await h.find('Preview exact response').click();assert.equal(h.posts.length,2);assert.equal(h.posts[1].request.payload.text,'e\u0301');
});
test('raw hash change fences text preparation before navigation event',async()=>{
 const h=responseHarness();await h.preview('<svg onload=run()>');await h.find('Prepare unsigned response review').click();
 assert(h.ids.dialogBody.textContent.includes('<svg onload=run()>'));assert(!h.nodes.some(n=>['SVG','SCRIPT','IMG','A'].includes(n.tagName)));
 h.context.location.hash='#garden/alice/inbox';await h.confirm('REVIEW RESPONSE bob');assert.equal(h.posts.length,1);
});
(async()=>{let failed=0;for(const [name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} independent text review DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
