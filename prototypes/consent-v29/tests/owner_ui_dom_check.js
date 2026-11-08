/* DOM-model unit tests, not a browser, layout or visual test. No dependencies. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../owner_ui/app.js'), 'utf8');
const tick = async () => { for(let i=0;i<8;i++) await new Promise(r=>setImmediate(r)); };
const clone = x => JSON.parse(JSON.stringify(x));
function harness(options={}) {
  const nodes=[];
  class Node {
    constructor(tag,id=null) { this.tagName=tag.toUpperCase();this.id=id;this.children=[];this._text='';this.value='';this.disabled=false;this.hidden=false;this.listeners={};this.className='';this.open=false;this.parent=null;
      this.classList={add:(v)=>{this.className+=' '+v;},remove:(v)=>{this.className=this.className.replace(v,'');}}; nodes.push(this); }
    set textContent(value){this._text=String(value);this.children=[];}
    get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
    get isConnected(){return !!this.id || !!this.parent;}
    append(...items){for(const n of items){n.parent=this;this.children.push(n);}}
    replaceChildren(...items){for(const n of this.children)n.parent=null;this.children=[];this._text='';this.append(...items);}
    addEventListener(type,fn){(this.listeners[type] ||= []).push(fn);}
    async click(){if(this.disabled)return;for(const fn of this.listeners.click||[])fn({target:this});if(this.onclick)this.onclick({target:this});await tick();}
    focus(){} showModal(){this.open=true;} close(){this.open=false;}
  }
  const ids={};
  for(const id of ['owner','peer','inboxButton','nextButton','cancelButton','revokeButton','closeButton','summary','message','error','content','confirmDialog','dialogTitle','dialogBody','confirmationLabel','confirmation','dialogCancel','dialogConfirm']) {
    const tag=id.includes('Button')||id.startsWith('dialogC')?'button':id==='owner'||id==='peer'?'select':id==='confirmation'?'input':'div'; ids[id]=new Node(tag,id);
  }
  ids.owner.value='alice';ids.peer.value='bob';
  const card={request_id:'a'.repeat(32),owner:'alice',action:'send',state:options.state||'pending',stored_state:options.state||'pending',review_digest:'b'.repeat(64),revision:0,
              decision:{target:{recipient:'bob'}},envelope:{},review:'Exact fictional message. Recipient: bob.',reason:null};
  const status={delivery_id:card.request_id,state:'dispatched',label:'Outcome uncertain; check receipt before any retry',attempts:1,can_check_receipt:true,can_start_attempt:true,can_process:false,attempt_blocker:null};
  const posts=[],gets=[],events={};
  const document={getElementById:id=>ids[id],createElement:tag=>new Node(tag),body:new Node('body','body'),querySelectorAll:()=>nodes.filter(n=>n.isConnected&&['BUTTON','SELECT'].includes(n.tagName))};
  let hash='';
  const location={get hash(){return hash;},set hash(value){hash=value;for(const fn of events.hashchange||[])fn();}};
  const response=(value,ok=true)=>({ok,json:async()=>clone(value)});
  const getDefault=url=>{
    if(url.startsWith('/api/state'))return response({phase:options.phase||'ready',owner:new URL(url,'http://local').searchParams.get('owner'),owners:['alice','bob','charlie','dana'],inbox:[card],summary:{receiver_receipts:0,transitions:0,agreed:false}});
    if(url.startsWith('/api/review'))return response(card);
    if(url.startsWith('/api/delivery'))return response(status);
    throw new Error(url);
  };
  const context={document,location,window:{addEventListener:(name,fn)=>(events[name] ||= []).push(fn)},URL,Map,Promise,setTimeout,clearTimeout,console,encodeURIComponent,Date,
    fetch:async(url,init={})=>{
      if(init.method==='POST'){
        const body=JSON.parse(init.body);posts.push(body);
        if(options.post)return options.post(body,response);
        if(body.action==='check'){status.state='received';status.label='Recipient receipt verified; not processed';status.can_process=true;status.can_start_attempt=false;return response({kind:'delivery',owner:'alice',...status});}
        if(body.action==='close')return response({closed:true});
        if(body.action==='approve'){card.state=card.stored_state='authorized';return response({kind:'request',card});}
        return response({kind:'request',card});
      }
      gets.push(url);if(options.get){const custom=options.get(url,response,getDefault);if(custom)return custom;}
      return getDefault(url);
    }};
  vm.createContext(context);vm.runInContext(source,context);
  const descendants=n=>n.children.flatMap(c=>[c,...descendants(c)]);
  return {context,ids,card,status,posts,gets,response,nodes,buttons:()=>descendants(ids.content).filter(n=>n.tagName==='BUTTON'),
    find:text=>descendants(ids.content).find(n=>n.tagName==='BUTTON'&&n.textContent===text),
    view:async(route)=>{context.navigate(route);await tick();}};
}
const tests=[];function test(name,fn){tests.push([name,fn]);}
test('read-only initial render, refresh, owner switch and navigation',async()=>{
 const h=harness();await tick();await h.view('request/alice/'+h.card.request_id);await h.context.render();h.ids.owner.value='bob';await h.view('inbox/bob');
 assert.equal(h.posts.length,0);assert.match(h.ids.content.textContent,/bob’s inbox/);assert(h.gets.length>=4);
});
test('deferred review requires explicit resume and back grants nothing',async()=>{
 const h=harness({state:'deferred'});await tick();await h.view('request/alice/'+h.card.request_id);assert(!h.find('Approve exact request'));
 await h.find('Resume review').click();assert(h.find('Approve exact request'));assert.equal(h.posts.length,0);
 await h.find('Back to inbox').click();assert.equal(h.posts.length,0);
});
test('approval dialog back and wrong phrase do not mutate; exact target is retained',async()=>{
 const h=harness();await tick();await h.view('request/alice/'+h.card.request_id);await h.find('Approve exact request').click();assert(h.ids.confirmDialog.open);
 h.ids.confirmation.value='yes';h.ids.confirmation.oninput();assert(h.ids.dialogConfirm.disabled);await h.ids.dialogConfirm.click();assert.equal(h.posts.length,0);
 await h.ids.dialogCancel.click();assert(!h.ids.confirmDialog.open);assert.equal(h.posts.length,0);
 await h.find('Approve exact request').click();h.ids.confirmation.value='APPROVE alice';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.equal(h.posts.length,1);assert.deepEqual(h.posts[0],{action:'approve',owner:'alice',request_id:'a'.repeat(32),review_digest:'b'.repeat(64),confirmation:'APPROVE alice'});
});
test('double action while first response pending does not repeat mutation',async()=>{
 let release;const h=harness({post:()=>new Promise(r=>release=r)});await tick();
 const first=h.context.act({action:'next'});await tick();const second=await h.context.act({action:'next'});assert.equal(second,null);assert.equal(h.posts.length,1);
 release(h.response({kind:'stopped',reason:'test'}));await first;
});
test('network failure explicitly preserves uncertainty without retries',async()=>{
 const h=harness({post:()=>Promise.reject(new Error('lost'))});await tick();await h.context.act({action:'attempt'});
 assert.equal(h.posts.length,1);assert.match(h.ids.error.textContent,/may have committed/);assert.match(h.ids.error.textContent,/Nothing was retried automatically/);
});
test('truncated action response explicitly preserves uncertainty without retries',async()=>{
 const h=harness({post:()=>Promise.resolve({ok:true,json:async()=>{throw new SyntaxError('truncated')}})});await tick();await h.context.act({action:'submit'});
 assert.equal(h.posts.length,1);assert.match(h.ids.error.textContent,/may have committed/);assert(!h.ids.error.textContent.includes('truncated'));
});
test('stale response cannot overwrite a newer owner navigation',async()=>{
 let release;const h=harness({get:(url)=>url.startsWith('/api/review')?new Promise(r=>release=r):null});await tick();
 h.context.navigate('request/alice/'+h.card.request_id);await tick();await h.view('inbox/bob');release(h.response(h.card));await tick();
 assert.match(h.ids.content.textContent,/bob’s inbox/);assert(!h.ids.content.textContent.includes('Review for alice'));assert.equal(h.posts.length,0);
});
test('uncertain receipt check never sends or processes',async()=>{
 const h=harness();await tick();await h.view('delivery/alice/'+h.card.request_id);
 assert.match(h.ids.content.textContent,/Outcome uncertain/);assert(h.find('Process received message').disabled);
 await h.find('Check existing receipt').click();assert.deepEqual(h.posts.map(x=>x.action),['check']);assert.match(h.ids.content.textContent,/Recipient receipt verified/);
});
test('send confirmation back does not create attempt',async()=>{
 const h=harness();await tick();await h.view('delivery/alice/'+h.card.request_id);await h.find('Retry approved delivery').click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
});
test('DOM rendering treats review text as text, not HTML instructions',async()=>{
 const h=harness();h.card.review='<img src="https://evil.example" onerror="steal()">';await tick();await h.view('request/alice/'+h.card.request_id);
 assert(h.ids.content.textContent.includes('<img'));assert(!h.nodes.some(n=>n.tagName==='IMG'));assert.equal(h.posts.length,0);
});
test('expired review replacement requires an explicit typed choice and grants no approval',async()=>{
 const h=harness({state:'expired'});h.card.stored_state='pending';h.card.can_replace=true;await tick();await h.view('request/alice/'+h.card.request_id);
 assert(!h.find('Approve exact request'));await h.find('Prepare new review').click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Prepare new review').click();h.ids.confirmation.value='REVIEW alice';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.deepEqual(h.posts.map(x=>x.action),['replace_review']);assert.equal(h.posts[0].review_digest,'b'.repeat(64));assert.equal(h.posts[0].confirmation,'REVIEW alice');
});
test('superseded review links to successor without creating or approving work',async()=>{
 const h=harness({state:'superseded'});h.card.stored_state='pending';h.card.replaced_by='c'.repeat(32);h.card.can_replace=false;
 await tick();await h.view('request/alice/'+h.card.request_id);assert(!h.find('Approve exact request'));assert(!h.find('Prepare new review'));
 await h.find('Open replacement review').click();assert.equal(h.context.location.hash,'#request/alice/'+'c'.repeat(32));assert.equal(h.posts.length,0);
});
test('missing pairing is opened for its exact owner only after typed choice',async()=>{
 const h=harness({state:'stale'});h.card.stored_state='pending';h.card.pairing_reviews=[{owner:'bob',peer:'alice',state:'expired'}];
 await tick();await h.view('request/alice/'+h.card.request_id);assert(!h.find('Approve exact request'));
 await h.find('Review pairing for bob').click();assert.match(h.ids.dialogBody.textContent,/grants nothing/);await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Review pairing for bob').click();h.ids.confirmation.value='REVIEW PAIR alice';h.ids.confirmation.oninput();assert(h.ids.dialogConfirm.disabled);
 h.ids.confirmation.value='REVIEW PAIR bob';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.deepEqual(h.posts,[{action:'review_pairing',owner:'alice',request_id:'a'.repeat(32),review_digest:'b'.repeat(64),direction_owner:'bob',confirmation:'REVIEW PAIR bob'}]);
});
test('pairing review returns to source send without mutation and deferred stays paused',async()=>{
 const h=harness({state:'deferred'});h.card.action='pair';h.card.pairing_sources=[{owner:'bob',request_id:'d'.repeat(32)}];
 await tick();await h.view('request/alice/'+h.card.request_id);assert(!h.find('Approve exact request'));assert(!h.find('Return to bob’s blocked send'));
 await h.find('Resume review').click();await h.find('Return to bob’s blocked send').click();
 assert.equal(h.context.location.hash,'#request/bob/'+'d'.repeat(32));assert.equal(h.posts.length,0);
});
test('unused withdrawal needs typed owner confirmation and explains its combined action',async()=>{
 const h=harness({state:'expired'});h.card.stored_state='authorized';h.card.can_withdraw=true;
 await tick();await h.view('request/alice/'+h.card.request_id);await h.find('Withdraw unused authorization').click();
 assert.match(h.ids.dialogBody.textContent,/signs and applies/);assert.match(h.ids.dialogBody.textContent,/refused if any execution or queued delivery/);
 await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Withdraw unused authorization').click();h.ids.confirmation.value='WITHDRAW bob';h.ids.confirmation.oninput();assert(h.ids.dialogConfirm.disabled);
 h.ids.confirmation.value='WITHDRAW alice';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.deepEqual(h.posts,[{action:'withdraw_unused',owner:'alice',request_id:'a'.repeat(32),review_digest:'b'.repeat(64),confirmation:'WITHDRAW alice'}]);
});
test('withdrawn authorization has no submit or approval and fresh review is separate',async()=>{
 const h=harness({state:'withdrawn'});h.card.stored_state='authorized';h.card.can_prepare_fresh=true;
 await tick();await h.view('request/alice/'+h.card.request_id);assert(!h.find('Submit approved request'));assert(!h.find('Approve exact request'));assert(!h.find('Withdraw unused authorization'));
 assert.match(h.ids.content.textContent,/No delivery was queued/);await h.find('Prepare fresh unsigned review').click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Prepare fresh unsigned review').click();h.ids.confirmation.value='REVIEW alice';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.deepEqual(h.posts.map(x=>x.action),['fresh_after_withdrawal']);
});
test('withdrawn source opens exact successor read-only without reviving original',async()=>{
 const h=harness({state:'withdrawn'});h.card.stored_state='authorized';h.card.withdrawn_successor='e'.repeat(32);
 await tick();await h.view('request/alice/'+h.card.request_id);await h.find('Open fresh review').click();
 assert.equal(h.context.location.hash,'#request/alice/'+'e'.repeat(32));assert.equal(h.posts.length,0);
});
test('cleanup uncertainty is explicit and never falls through to an inbox',async()=>{
 const h=harness({phase:'cleanup_uncertain'});await tick();assert.match(h.ids.content.textContent,/Cleanup incomplete/);assert.match(h.ids.content.textContent,/actions are blocked/);assert(h.ids.nextButton.disabled);assert.equal(h.posts.length,0);
});
test('discard back is inert; exact confirmation ends UI without retry',async()=>{
 const h=harness();await tick();await h.ids.closeButton.click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.ids.closeButton.click();h.ids.confirmation.value='DISCARD FIXTURE';h.ids.confirmation.oninput();await h.ids.dialogConfirm.click();
 assert.equal(h.posts.length,1);assert.equal(h.posts[0].action,'close');assert.match(h.ids.content.textContent,/Fixture discarded/);assert(h.ids.nextButton.disabled);
});
(async()=>{let failed=0;for(const [name,fn] of tests){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} DOM-model checks passed. These are not browser or visual tests.`);process.exitCode=failed?1:0;})();
