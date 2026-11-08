/* Dependency-free DOM MODEL checks. NOT a real browser, visual or accessibility test. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../workspace_ui/app.js'),'utf8');
const tick=async()=>{for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));};
const clone=x=>JSON.parse(JSON.stringify(x));
function harness(options={}) {
 const nodes=[];
 class Node {
  constructor(tag,id=null){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.parent=null;this._text='';this.value='';this.disabled=false;this.hidden=false;this.listeners={};this.className='';this.open=false;this.classList={add:v=>{this.className+=' '+v;},remove:()=>{}};nodes.push(this);}
  set textContent(v){this._text=String(v);this.replaceChildren();} get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  get isConnected(){return !!this.id || !!(this.parent&&this.parent.isConnected);}
  append(...items){for(const n of items){n.parent=this;this.children.push(n);}}
  replaceChildren(...items){for(const n of this.children)n.parent=null;this.children=[];this.append(...items);}
  addEventListener(t,f){(this.listeners[t]||=[]).push(f);}
  async click(){if(this.disabled)return;for(const f of this.listeners.click||[])f({target:this});if(this.onclick)this.onclick({target:this});await tick();}
  focus(){}showModal(){this.open=true;}close(){this.open=false;}
 }
 const ids={};for(const id of ['tasks','controls','content','message','error','confirmDialog','dialogTitle','dialogBody','confirmationLabel','confirmation','dialogCancel','dialogConfirm'])ids[id]=new Node(id.startsWith('dialogC')?'button':id==='confirmation'?'input':'div',id);
 const rows=[{selector:'garden',task:'garden-task',context:'g'.repeat(64),requester:'alice',responder:'bob',phase:options.phase||'open'}, {selector:'astronomy',task:'astronomy-task',context:'a'.repeat(64),requester:'bob',responder:'alice',phase:options.phase||'open'}];
 const card={request_id:'1'.repeat(32),owner:'alice',action:'send',state:options.state||'pending',stored_state:options.state||'pending',review_digest:'r'.repeat(64),decision:{target:{recipient:'bob',task:'garden-task'}},review:'Exact inert payload for bob.',envelope:{},reason:null};
 const status={delivery_id:card.request_id,state:'dispatched',label:'Outcome uncertain; check receipt before any retry',attempts:1,can_check_receipt:true,can_start_attempt:true,can_process:false};
 const proposals=[{proposal_id:'fixture-p1',envelope_digest:'e'.repeat(64),state:'staged',type:'request',recipient:'bob'}];
 const posts=[],gets=[],events={};let hash=options.hash||'';
 const location={get hash(){return hash;},set hash(v){hash=v;}};
 const response=(v,ok=true)=>({ok,json:async()=>clone(v)});
 const getDefault=url=>{
  if(url==='/api/tasks')return response(rows);
  const u=new URL(url,'http://local'),owner=u.searchParams.get('owner'),row=rows.find(r=>r.selector===u.searchParams.get('selector'));
  if(!row||u.searchParams.get('context')!==row.context)throw Error('Missing/wrong scope');
  if(u.pathname==='/api/state')return response({phase:options.servicePhase||'ready',owner,owners:['alice','bob'],inbox:[{...card,owner}],summary:{transitions:0},bindings:[{owner:options.bindingOwner||'alice',digest:'binding-token',approved:false,receive_from:['bob'],transport_pubkey:'fixture-key'}]});
  if(u.pathname==='/api/review')return response({...card,owner});
  if(u.pathname==='/api/delivery')return response(status);
  if(u.pathname==='/api/proposals')return response(proposals);
  throw Error(url);
 };
 const document={getElementById:id=>ids[id],createElement:t=>new Node(t),querySelectorAll:()=>nodes.filter(n=>n.isConnected&&['BUTTON','SELECT'].includes(n.tagName))};
 const context={document,location,window:{addEventListener:(k,f)=>(events[k]||=[]).push(f)},URL,URLSearchParams,Promise,Map,console,encodeURIComponent,decodeURIComponent,Date,
  fetch:async(url,init={})=>{
   if(init.method==='POST'){
    const body=JSON.parse(init.body);posts.push(body);if(options.post)return options.post(body,response);
    const req=body.request,row=rows.find(r=>r.selector===body.selector);
    if(req.action==='create'){row.phase='open';return response(row);}
    if(req.action==='close'){row.phase='closed';return response({task_closed:true});}
    if(req.action==='approve')card.state=card.stored_state='authorized';
    if(req.action==='check'){status.state='received';status.label='Recipient receipt verified; not processed';status.can_process=true;status.can_start_attempt=false;return response({kind:'delivery',owner:req.owner,...status});}
    return response({kind:'request',card});
   }
   gets.push(url);if(options.get){const result=options.get(url,response,getDefault);if(result)return result;}return getDefault(url);
  }};
 vm.createContext(context);vm.runInContext(source,context);
 const descendants=n=>n.children.flatMap(c=>[c,...descendants(c)]);
 return {context,ids,rows,card,status,posts,gets,nodes,proposals,response,
  find:text=>[...descendants(ids.content),...descendants(ids.controls),...descendants(ids.tasks)].find(n=>n.tagName==='BUTTON'&&n.textContent===text),
  view:async(route)=>{context.navigate(route);await tick();},
  confirm:async phrase=>{ids.confirmation.value=phrase;ids.confirmation.oninput();await ids.dialogConfirm.click();},
  hash:async route=>{location.hash='#'+route;for(const f of events.hashchange||[])f();await tick();}};
}
const tests=[];function test(name,f){tests.push([name,f]);}
const review=h=>'garden/alice/request/'+h.card.request_id;
test('initial catalog and task navigation never create services or mutate',async()=>{
 const h=harness({phase:'not_created'});await tick();assert.deepEqual(h.gets,['/api/tasks']);await h.view('garden/alice/inbox');assert(h.find('Create selected temporary task'));assert.equal(h.posts.length,0);assert(!h.gets.some(u=>u.startsWith('/api/state')));
 await h.view('astronomy/bob/inbox');assert.equal(h.posts.length,0);
});
test('explicit create targets only captured task/context and does not bind',async()=>{
 const h=harness({phase:'not_created'});await tick();await h.view('astronomy/bob/inbox');await h.find('Create selected temporary task').click();
 assert.deepEqual(h.posts,[{selector:'astronomy',context:'a'.repeat(64),request:{action:'create'}}]);assert.equal(h.rows[0].phase,'not_created');
});
test('all task-specific reads carry exact selector context and owner',async()=>{
 const h=harness();await tick();await h.view(review(h));await h.view('astronomy/bob/delivery/'+h.card.request_id);await h.view('astronomy/alice/proposals');
 for(const url of h.gets.filter(u=>u!=='/api/tasks')){const q=new URL(url,'http://local').searchParams;const row=h.rows.find(r=>r.selector===q.get('selector'));assert.equal(q.get('context'),row.context);assert(['alice','bob'].includes(q.get('owner')));}assert.equal(h.posts.length,0);
});
test('binding typed exact digest and owner; cancellation mutates nothing',async()=>{
 const h=harness({servicePhase:'bindings'});await tick();await h.view('garden/alice/inbox');await h.find('Review binding for alice').click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Review binding for alice').click();await h.confirm('BIND alice');assert.equal(h.posts[0].request.binding_digest,'binding-token');assert.equal(h.posts[0].selector,'garden');
});
test('Bob binding from Alice view consistently identifies Bob in confirmation',async()=>{
 const h=harness({servicePhase:'bindings',bindingOwner:'bob'});await tick();await h.view('garden/alice/inbox');await h.find('Review binding for bob').click();assert.match(h.ids.dialogBody.textContent,/Owner: bob/);assert(!h.ids.dialogBody.textContent.includes('Owner: alice'));await h.confirm('BIND bob');assert.equal(h.posts[0].request.owner,'bob');assert.equal(h.posts[0].request.confirmation,'BIND bob');assert.equal(h.posts[0].selector,'garden');
});
test('approval shows exact task recipient review token; wrong phrase and Back do nothing',async()=>{
 const h=harness();await tick();await h.view(review(h));await h.find('Approve exact request').click();assert.match(h.ids.dialogBody.textContent,/garden-task/);assert.match(h.ids.dialogBody.textContent,/bob/);assert(h.ids.dialogBody.textContent.includes(h.card.review_digest));
 await h.confirm('yes');assert.equal(h.posts.length,0);await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);
 await h.find('Approve exact request').click();await h.confirm('APPROVE alice');assert.deepEqual(h.posts[0],{selector:'garden',context:'g'.repeat(64),request:{action:'approve',owner:'alice',request_id:h.card.request_id,review_digest:h.card.review_digest,confirmation:'APPROVE alice'}});
});
test('navigation cancels pending confirmation and saved confirm callback cannot approve',async()=>{
 const h=harness();await tick();await h.view(review(h));await h.find('Approve exact request').click();const stale=h.ids.dialogConfirm.onclick;
 await h.view('astronomy/bob/inbox');assert(!h.ids.confirmDialog.open);h.ids.confirmation.value='APPROVE alice';stale();await tick();assert.equal(h.posts.length,0);
});
test('raw hash changed before hashchange event also prevents stale confirmation',async()=>{
 const h=harness();await tick();await h.view(review(h));await h.find('Approve exact request').click();h.context.location.hash='#astronomy/bob/inbox';await h.confirm('APPROVE alice');assert.equal(h.posts.length,0);
});
test('detached old task button cannot act after switching',async()=>{
 const h=harness();await tick();await h.view('garden/alice/inbox');const old=h.find('Prepare next review');await h.view('astronomy/bob/inbox');await old.click();assert.equal(h.posts.length,0);
});
test('rapid duplicate confirmation and action clicks produce one mutation',async()=>{
 let release;const h=harness({post:()=>new Promise(r=>release=r)});await tick();await h.view(review(h));await h.find('Approve exact request').click();h.ids.confirmation.value='APPROVE alice';h.ids.confirmation.oninput();const confirm=h.ids.dialogConfirm.onclick;confirm();confirm();await tick();assert.equal(h.posts.length,1);release(h.response({kind:'request',card:h.card}));await tick();
});
test('rapid prepare clicks while response pending cannot duplicate',async()=>{
 let release;const h=harness({post:()=>new Promise(r=>release=r)});await tick();await h.view('garden/alice/inbox');const btn=h.find('Prepare next review');await btn.click();await btn.click();assert.equal(h.posts.length,1);release(h.response({kind:'request',card:h.card}));await tick();
});
test('delayed old-task read cannot overwrite new task view',async()=>{
 let release;const h=harness({get:url=>url.startsWith('/api/review')?new Promise(r=>release=r):null});await tick();h.context.navigate(review(h));await tick();await h.view('astronomy/bob/inbox');release(h.response(h.card));await tick();assert.match(h.ids.content.textContent,/astronomy-task/);assert(!h.ids.content.textContent.includes('Review for alice'));
});
test('delayed mutation response cannot navigate new task or render old result',async()=>{
 let release;const h=harness({post:()=>new Promise(r=>release=r)});await tick();await h.view('garden/alice/inbox');await h.find('Prepare next review').click();await h.hash('astronomy/bob/inbox');release(h.response({kind:'request',card:h.card}));await tick();assert.equal(h.context.location.hash,'#astronomy/bob/inbox');assert.match(h.ids.content.textContent,/astronomy-task/);assert.equal(h.posts.length,1);
});
test('old-task error cannot overwrite current task',async()=>{
 let reject;const h=harness({post:()=>new Promise((_,r)=>reject=r)});await tick();await h.view('garden/alice/inbox');await h.find('Prepare next review').click();await h.hash('astronomy/bob/inbox');reject(Error('lost'));await tick();assert(h.ids.error.hidden);assert.match(h.ids.content.textContent,/astronomy-task/);
});
test('lost action response explicitly uncertain with no automatic retry',async()=>{
 const h=harness({post:()=>Promise.reject(Error('lost'))});await tick();await h.view('garden/alice/inbox');await h.find('Prepare next review').click();assert.equal(h.posts.length,1);assert.match(h.ids.error.textContent,/may have committed/);assert.match(h.ids.error.textContent,/Nothing was retried automatically/);
});
test('truncated response is uncertain, not failed or safe to resend',async()=>{
 const h=harness({post:()=>Promise.resolve({ok:true,json:async()=>{throw Error('truncated');}})});await tick();await h.view('garden/alice/inbox');await h.find('Prepare next review').click();assert.equal(h.posts.length,1);assert.match(h.ids.error.textContent,/may have committed/);
});
test('hostile review and proposal URLs are text only, no image or hyperlink',async()=>{
 const h=harness();h.card.review='<img src="https://evil.invalid" onerror="approve()">';h.proposals[0].proposal_id='<a href="https://evil.invalid">run</a>';await tick();await h.view(review(h));assert(h.ids.content.textContent.includes('<img'));await h.view('garden/alice/proposals');assert(h.ids.content.textContent.includes('<a href'));assert(!h.nodes.some(n=>['IMG','A','IFRAME'].includes(n.tagName)));assert.equal(h.posts.length,0);
});
test('proposal import explicit and unsigned, exact ID scope and history wording',async()=>{
 const h=harness();await tick();await h.view('garden/alice/proposals');assert.equal(h.posts.length,0);await h.find('Open proposal for owner review').click();assert.match(h.ids.dialogBody.textContent,/Original review history/);await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);await h.find('Open proposal for owner review').click();await h.confirm('REVIEW alice');assert.deepEqual(h.posts[0],{selector:'garden',context:'g'.repeat(64),request:{action:'import_proposal',owner:'alice',proposal_id:'fixture-p1'}});assert.equal(h.context.location.hash,'#'+review(h));assert.match(h.ids.content.textContent,/Review for alice/);
});
test('close only selected task requires phrase, leaves other task available',async()=>{
 const h=harness();await tick();await h.view('garden/alice/inbox');await h.find('Close only this task').click();await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);await h.find('Close only this task').click();await h.confirm('DISCARD FIXTURE');assert.equal(h.rows[0].phase,'closed');assert.equal(h.rows[1].phase,'open');assert(!h.find('Prepare next review'));await h.view('astronomy/bob/inbox');assert(h.find('Prepare next review'));assert.equal(h.posts.length,1);
});
test('cleanup and startup uncertainty block every affected mutation control',async()=>{
 for(const phase of ['cleanup_uncertain','startup_failed_cleanup_uncertain']){const h=harness({phase});await tick();await h.view('garden/alice/inbox');assert.match(h.ids.content.textContent,/Some temporary resources may remain/);assert(!h.find('Create selected temporary task'));assert(!h.find('Close only this task'));assert(!h.find('Prepare next review'));assert.equal(h.posts.length,0);}
});
test('failed startup refreshes metadata and blocks recreation without retry',async()=>{
 let h;h=harness({phase:'not_created',post:(_,response)=>{h.rows[0].phase='startup_failed_cleanup_uncertain';return response({error:'Startup cleanup uncertain'},false);}});await tick();await h.view('garden/alice/inbox');await h.find('Create selected temporary task').click();assert.match(h.ids.content.textContent,/cleanup uncertain/);assert(!h.find('Create selected temporary task'));assert.equal(h.posts.length,1);
});
test('close cleanup failure refreshes metadata to blocked state without retry',async()=>{
 let h;h=harness({post:(_,response)=>{h.rows[0].phase='cleanup_uncertain';return response({error:'Cleanup incomplete'},false);}});await tick();await h.view('garden/alice/inbox');await h.find('Close only this task').click();await h.confirm('DISCARD FIXTURE');assert.match(h.ids.content.textContent,/cleanup uncertain/);assert(!h.find('Prepare next review'));assert.equal(h.posts.length,1);
});
test('deferred stays paused until explicit local resume, no permission granted',async()=>{
 const h=harness({state:'deferred'});await tick();await h.view(review(h));assert(!h.find('Approve exact request'));await h.find('Resume review').click();assert(h.find('Approve exact request'));assert.equal(h.posts.length,0);await h.find('Back to inbox').click();assert.equal(h.posts.length,0);
});
test('replacement and withdrawal preserve exact review tokens and typed actions',async()=>{
 for(const [flag,label,action,phrase] of [['can_replace','Prepare new review','replace_review','REVIEW alice'],['can_withdraw','Withdraw unused authorization','withdraw_unused','WITHDRAW alice'],['can_prepare_fresh','Prepare fresh unsigned review','fresh_after_withdrawal','REVIEW alice']]){const h=harness({state:'stale'});h.card[flag]=true;await tick();await h.view(review(h));await h.find(label).click();await h.confirm(phrase);assert.equal(h.posts[0].request.action,action);assert.equal(h.posts[0].request.review_digest,h.card.review_digest);assert.equal(h.posts[0].selector,'garden');}
});
test('pairing direction remains exact and separate from source send',async()=>{
 const h=harness({state:'stale'});h.card.pairing_reviews=[{owner:'bob',peer:'alice',state:'expired'}];await tick();await h.view(review(h));await h.find('Review pairing for bob').click();await h.confirm('REVIEW PAIR alice');assert.equal(h.posts.length,0);await h.confirm('REVIEW PAIR bob');assert.equal(h.posts[0].request.direction_owner,'bob');assert.equal(h.posts[0].request.owner,'alice');assert.equal(h.posts[0].request.action,'review_pairing');
});
test('delivery uncertainty and receipt-only action distinct from send and process',async()=>{
 const h=harness();await tick();await h.view('garden/alice/delivery/'+h.card.request_id);assert.match(h.ids.content.textContent,/Outcome uncertain/);assert(h.find('Process received message').disabled);await h.find('Check existing receipt').click();assert.deepEqual(h.posts.map(p=>p.request.action),['check']);assert.match(h.ids.content.textContent,/Recipient receipt verified/);
});
test('send exact recipient task and cancellation followed by typed confirmation',async()=>{
 const h=harness();await tick();await h.view('garden/alice/delivery/'+h.card.request_id);await h.find('Retry approved delivery').click();assert.match(h.ids.dialogBody.textContent,/bob/);assert.match(h.ids.dialogBody.textContent,/garden-task/);await h.ids.dialogCancel.click();assert.equal(h.posts.length,0);await h.find('Retry approved delivery').click();await h.confirm('SEND alice');assert.equal(h.posts[0].request.action,'attempt');assert.equal(h.posts.length,1);
});
test('back/hash navigation is read-only and task controls contain no meeting assumptions',async()=>{
 const h=harness();await tick();await h.hash('garden/alice/inbox');await h.hash('astronomy/bob/inbox');await h.hash('garden/alice/inbox');assert.equal(h.posts.length,0);assert(!h.ids.content.textContent.includes('Meeting'));assert(h.find('Review revocation of bob'));
});
test('model-testable responsive and focus controls have explicit labels and CSS rules',async()=>{
 const html=fs.readFileSync(path.join(__dirname,'../workspace_ui/index.html'),'utf8'),css=fs.readFileSync(path.join(__dirname,'../workspace_ui/style.css'),'utf8');assert.match(html,/name="viewport"/);assert.match(html,/aria-labelledby="dialogTitle"/);assert.match(html,/for="confirmation"/);assert.match(css,/@media\(max-width:620px\)/);assert.match(css,/focus-visible/);assert.match(css,/overflow-wrap:anywhere/);
});
(async()=>{let failed=0;for(const [name,f]of tests){try{await f();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+'\n'+e.stack);}}console.log(`${tests.length-failed}/${tests.length} workspace DOM-model checks passed (not browser tests).`);if(failed)process.exitCode=1;})();
