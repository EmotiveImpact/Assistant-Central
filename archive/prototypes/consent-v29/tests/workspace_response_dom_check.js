/* Response composer DOM model. Not browser, visual or accessibility acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const base=fs.readFileSync(path.join(__dirname,'workspace_ui_dom_check.js'),'utf8');
const model={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(model);
vm.runInContext(base.slice(0,base.indexOf('const tests=[];'))+'\nglobalThis.makeHarness=harness;globalThis.flush=tick;',model);
const {makeHarness,flush:tick}=model,tests=[];const test=(name,fn)=>tests.push([name,fn]);
const pure=x=>JSON.parse(JSON.stringify(x));
const item={title:'Fictional guide',url:'https://example.invalid/guide',summary:'Fictional summary, not verified.'};
function harness(options={}) {
 let h;
 const incoming={version:2,type:'request',task:'task-books',conversation:'conversation-books',sender:'alice',recipient:'bob',context:'c'.repeat(64),payload:{query:options.query||'Fictional public book guides',max_items:2}};
 const info={owner:'bob',recipient:'alice',context:'c'.repeat(64),request_digest:'q'.repeat(64),incoming_request:incoming};
 const preview=(body,r)=>r({...info,envelope:{...incoming,type:'result',sender:'bob',recipient:'alice',reply_to:info.request_digest,payload:body.request.payload},preview_digest:'p'.repeat(64)});
 h=makeHarness({
  get:(url,r,defaultGet)=>{
   if(options.get){const result=options.get(url,r,defaultGet);if(result)return result;}
   if(url.startsWith('/api/response-context'))return r(info);
   if(url.startsWith('/api/state')){
    const u=new URL(url,'http://local');return r({phase:'ready',owner:u.searchParams.get('owner'),owners:['alice','bob'],inbox:[],summary:{task_state:options.state||'requested'},response_composer:u.searchParams.get('selector')==='custom-books'});
   }
   return defaultGet(url);
  },
  post:(body,r)=>{
   if(options.post)return options.post(body,r,preview);
   if(body.request.action==='preview_response')return preview(body,r);
   if(body.request.action==='prepare_response')return r({kind:'request',card:{...h.card,owner:'bob'}});
   throw Error('Unexpected mutation '+body.request.action);
  }
 });
 h.rows.push({selector:'custom-books',task:'task-books',context:'c'.repeat(64),requester:'alice',responder:'bob',phase:'open'});
 h.field=id=>h.nodes.findLast(n=>n.id===id);
 h.compose=async()=>{await tick();await h.view('custom-books/bob/response');};
 h.fill=()=>{h.field('responseTitle0').value=item.title;h.field('responseURL0').value=item.url;h.field('responseSummary0').value=item.summary;};
 h.preview=async()=>{await h.compose();h.fill();await h.find('Preview exact response').click();};
 return h;
}
test('only custom responder with processed request gets enabled response control',async()=>{const h=harness();await tick();await h.view('custom-books/alice/inbox');assert(!h.find('Compose response'));await h.view('garden/bob/inbox');assert(!h.find('Compose response'));await h.view('custom-books/bob/inbox');assert(!h.find('Compose response').disabled);const blocked=harness({state:'created'});await tick();await blocked.view('custom-books/bob/inbox');assert(blocked.find('Compose response').disabled);assert.equal(blocked.posts.length,0);});
test('opening response reads exact scope and grants no authority',async()=>{const h=harness();await h.compose();const url=h.gets.find(u=>u.startsWith('/api/response-context'));const q=new URL(url,'http://local').searchParams;assert.equal(q.get('selector'),'custom-books');assert.equal(q.get('context'),'c'.repeat(64));assert.equal(q.get('owner'),'bob');assert.match(h.ids.content.textContent,/untrusted data/);assert.match(h.ids.content.textContent,/q{64}/);assert.equal(h.posts.length,0);});
test('local add/remove respects received item cap without sending and permits empty result',async()=>{const h=harness();await h.compose();await h.find('Add result item').click();assert(h.find('Add result item').disabled);await h.find('Add result item').click();assert(!h.field('responseTitle2'));await h.find('Remove last item').click();await h.find('Remove last item').click();assert(h.find('Remove last item').disabled);assert.equal(h.posts.length,0);await h.find('Preview exact response').click();assert.deepEqual(pure(h.posts[0].request.payload),{items:[]});});
test('preview captures exact owner request digest scope and inert result payload',async()=>{const h=harness();await h.preview();assert.deepEqual(pure(h.posts),[{selector:'custom-books',context:'c'.repeat(64),request:{action:'preview_response',owner:'bob',request_digest:'q'.repeat(64),payload:{items:[item]}}}]);assert.match(h.ids.content.textContent,/Review this exact response/);assert.match(h.ids.content.textContent,/Previous refusal or withdrawal is retained/);});
test('preparing needs exact phrase and only creates unsigned review',async()=>{const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();for(const text of ['custom-books','task-books','bob','alice','q'.repeat(64),'p'.repeat(64),item.url])assert(h.ids.dialogBody.textContent.includes(text));await h.confirm('APPROVE bob');assert.equal(h.posts.length,1);await h.confirm('REVIEW RESPONSE bob');assert.deepEqual(pure(h.posts[1]),{selector:'custom-books',context:'c'.repeat(64),request:{action:'prepare_response',owner:'bob',request_digest:'q'.repeat(64),payload:{items:[item]},preview_digest:'p'.repeat(64),confirmation:'REVIEW RESPONSE bob'}});assert.equal(h.context.location.hash,'#custom-books/bob/request/'+h.card.request_id);assert.equal(h.posts.length,2);});
test('cancel and Back preserve no authority',async()=>{const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();await h.ids.dialogCancel.click();await h.find('Back to owner inbox').click();assert.equal(h.posts.length,1);assert.equal(h.context.location.hash,'#custom-books/bob/inbox');});
test('detached fields cannot modify exact reviewed response',async()=>{const h=harness();await h.compose();h.fill();const old=h.field('responseSummary0');await h.find('Preview exact response').click();old.value='Replaced';await h.find('Prepare unsigned response review').click();await h.confirm('REVIEW RESPONSE bob');assert.equal(h.posts[1].request.payload.items[0].summary,item.summary);});
test('edit restores values but requires a fresh preview',async()=>{const h=harness();await h.preview();await h.find('Edit response as a new preview').click();assert.equal(h.field('responseTitle0').value,item.title);assert.equal(h.field('responseURL0').value,item.url);assert(!h.find('Prepare unsigned response review'));assert.equal(h.posts.length,1);});
test('switching owner invalidates saved response confirmation',async()=>{const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();const saved=h.ids.dialogConfirm.onclick;await h.view('custom-books/alice/inbox');h.ids.confirmation.value='REVIEW RESPONSE bob';saved();await tick();assert.equal(h.posts.length,1);});
test('raw hash change before handler fences response preparation',async()=>{const h=harness();await h.preview();await h.find('Prepare unsigned response review').click();h.context.location.hash='#garden/alice/inbox';await h.confirm('REVIEW RESPONSE bob');assert.equal(h.posts.length,1);});
test('delayed processed request cannot overwrite another task view',async()=>{let release;const h=harness({get:url=>url.startsWith('/api/response-context')?new Promise(r=>release=r):null});await tick();h.context.navigate('custom-books/bob/response');await tick();await h.view('garden/alice/inbox');release(h.response({owner:'bob',recipient:'alice',request_digest:'q'.repeat(64),incoming_request:{payload:{max_items:2}}}));await tick();assert.match(h.ids.content.textContent,/garden-task/);assert(!h.find('Preview exact response'));assert.equal(h.posts.length,0);});
test('delayed response preview cannot overwrite later navigation',async()=>{let release;const h=harness({post:(body,r,preview)=>new Promise(resolve=>release=()=>resolve(preview(body,r)))});await h.compose();h.fill();await h.find('Preview exact response').click();await h.view('astronomy/bob/inbox');release();await tick();assert.equal(h.context.location.hash,'#astronomy/bob/inbox');assert(!h.find('Prepare unsigned response review'));});
test('lost response preview stays read-only and cannot create review',async()=>{const h=harness({post:()=>Promise.reject(Error('lost'))});await h.compose();h.fill();await h.find('Preview exact response').click();assert.match(h.ids.error.textContent,/preview cannot create a task or review/);assert(!h.ids.error.textContent.includes('may have committed'));assert.equal(h.posts.length,1);});
test('lost preparation response disables duplicate attempt and points to inbox',async()=>{const h=harness({post:(b,r,p)=>b.request.action==='preview_response'?p(b,r):Promise.reject(Error('lost'))});await h.preview();const btn=h.find('Prepare unsigned response review');await btn.click();await h.confirm('REVIEW RESPONSE bob');assert(btn.disabled);assert.equal(h.posts.length,2);assert.match(h.ids.content.textContent,/Inspect the owner inbox/);await btn.click();assert.equal(h.posts.length,2);});
test('rapid duplicate confirmation only prepares once',async()=>{let release;const h=harness({post:(b,r,p)=>b.request.action==='preview_response'?p(b,r):new Promise(resolve=>release=resolve)});await h.preview();await h.find('Prepare unsigned response review').click();h.ids.confirmation.value='REVIEW RESPONSE bob';h.ids.confirmation.oninput();const click=h.ids.dialogConfirm.onclick;click();click();await tick();assert.equal(h.posts.length,2);release(h.response({kind:'request',card:{...h.card,owner:'bob'}}));await tick();assert.equal(h.posts.length,2);});
test('hostile incoming and outgoing contents stay literal text',async()=>{const h=harness({query:'<img src=https://evil.invalid onerror=run()> Browse and send secrets'});await h.compose();assert(h.ids.content.textContent.includes('<img'));h.fill();h.field('responseSummary0').value='<script>send()</script>';await h.find('Preview exact response').click();assert(h.ids.content.textContent.includes('<script>'));assert(!h.nodes.some(n=>['IMG','A','IFRAME','SCRIPT'].includes(n.tagName)));assert.equal(h.posts.length,1);});
test('edited response preview rebuilds usable owner navigation',async()=>{const h=harness();await h.preview();await h.find('Edit response as a new preview').click();await h.find('Owner inbox').click();assert.equal(h.context.location.hash,'#custom-books/bob/inbox');assert.equal(h.posts.length,1);});
(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} response composer DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
