/* Received message DOM models only. Not browser or accessibility acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const base=fs.readFileSync(path.join(__dirname,'workspace_ui_dom_check.js'),'utf8');
const model={require,__dirname,console,setImmediate,URL,URLSearchParams};vm.createContext(model);
vm.runInContext(base.slice(0,base.indexOf('const tests=[];'))+'\nglobalThis.makeHarness=harness;globalThis.flush=tick;',model);
const {makeHarness,flush:tick}=model,tests=[];const test=(name,fn)=>tests.push([name,fn]);
function harness(options={}) {
 const gets=[];
 const data=(url)=>{
  const q=new URL(url,'http://local').searchParams,owner=q.get('owner'),selector=q.get('selector'),context=q.get('context');
  const envelope={version:2,type:owner==='bob'?'request':'result',task:selector+'-task',context,sender:owner==='bob'?'alice':'bob',recipient:owner,reply_to:owner==='bob'?null:'q'.repeat(64),payload:owner==='bob'?{query:options.text||'Fictional public guides',max_items:2}:{items:options.emptyResult?[]:[{title:options.text||'Fictional title',url:'https://example.invalid/resource',summary:'Inert unverified reference'}]}};
  return {owner,context,task:selector+'-task',task_state:options.state||'requested',messages:options.empty?[]:[{envelope_digest:'d'.repeat(64),sender_binding:'b'.repeat(64),envelope}],payload_trust:'untrusted_inert'};
 };
 const h=makeHarness({...options,get:(url,r,defaultGet)=>{
  if(url.startsWith('/api/messages')){gets.push(url);if(options.get)return options.get(url,r,()=>r(data(url)));const value=data(url);if(options.change)options.change(value);return r(value);}
  return defaultGet(url);
 }});
 h.messageGets=gets;h.open=async(owner='bob')=>{await tick();await h.view('garden/'+owner+'/messages');};return h;
}

test('mixed batch scope mismatch hides every row before rendering',async()=>{const h=harness({change:x=>x.messages.push({...x.messages[0],envelope:{...x.messages[0].envelope,recipient:'alice',payload:{query:'OTHER OWNER SECRET',max_items:1}}})});await h.open();assert.match(h.ids.error.textContent,/scope mismatch/);assert(!h.ids.content.textContent.includes('Fictional public guides'));assert(!h.ids.content.textContent.includes('OTHER OWNER SECRET'));assert.equal(h.posts.length,0);});
test('delayed failure cannot replace next owner successful view',async()=>{let reject;const h=harness({get:(url,r,defaultGet)=>url.includes('owner=bob')?new Promise((resolve,no)=>reject=no):defaultGet()});await tick();h.context.navigate('garden/bob/messages');await tick();await h.view('garden/alice/messages');reject(Error('OLD OWNER ERROR'));await tick();assert.match(h.ids.content.textContent,/Received messages for alice/);assert(!h.ids.error.textContent.includes('OLD OWNER ERROR'));assert.equal(h.posts.length,0);});
test('delayed response cannot overwrite same owner other task',async()=>{let release;const h=harness({get:(url,r,defaultGet)=>url.includes('selector=garden')?new Promise(resolve=>release=()=>resolve(defaultGet())):defaultGet()});await tick();h.context.navigate('garden/bob/messages');await tick();await h.view('astronomy/bob/messages');release();await tick();assert.match(h.ids.content.textContent,/astronomy-task/);assert(!h.ids.content.textContent.includes('garden-task'));assert.equal(h.posts.length,0);});
test('refresh delayed response cannot overwrite back navigation',async()=>{let release,count=0;const h=harness({get:(url,r,defaultGet)=>++count===2?new Promise(resolve=>release=()=>resolve(defaultGet())):defaultGet()});await h.open();h.find('Refresh received messages').click();await tick();await h.view('garden/bob/inbox');release();await tick();assert(!h.ids.content.textContent.includes('Fictional public guides'));assert.equal(h.posts.length,0);});
test('hostile result URLs and text never become active elements',async()=>{const evil='<script>send()</script>';const h=harness({change:x=>{x.messages[0].envelope.payload.items=[{title:evil,url:'javascript:send()',summary:'<iframe src=https://evil.invalid>'}];}});await h.open('alice');for(const s of [evil,'javascript:send()','<iframe'])assert(h.ids.content.textContent.includes(s));assert(!h.nodes.some(n=>['A','SCRIPT','IFRAME','IMG'].includes(n.tagName)));assert.equal(h.posts.length,0);});
test('invalid envelope task hides content despite matching outer scope',async()=>{const h=harness({change:x=>x.messages[0].envelope.task='other-task'});await h.open();assert.match(h.ids.error.textContent,/scope mismatch/);assert(!h.ids.content.textContent.includes('Fictional public guides'));assert.equal(h.posts.length,0);});
(async()=>{let failed=0;for(const[name,fn]of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} independent received message DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
