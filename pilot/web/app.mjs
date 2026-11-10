import {plain,finiteDate,stateLabel,statusClass,isPending,isTerminal,isPeerActive,filteredItems,validateState,validateReview,proposalBody,peerBody,workflowEnabled,workflowStateLabel,workflowSummary,canPrepareWorkflow,validateWorkflowStatus,validateWorkflowReview,validateWorkflowResult} from './model.mjs';

const $ = id => document.getElementById(id);
let token = null, generation = 0, busy = false, currentView = 'inbox', currentFilter = 'all';
let state = null, selected = null, selectedWorkflow = null, uncertain = false;
const viewCopy = {
  inbox:['Inbox','INCOMING WORK','The next move is yours.','Review each request before your assistant takes it on.','Your inbox','Exact requests, explicit decisions'],
  outbox:['Outbox','OUTGOING WORK','Share with intention.','Prepare the exact content, then choose whether to release it.','Your outbox','Prepared and released proposals'],
  peers:['Trusted peers','YOUR NETWORK','Trust starts with identity.','Verify each owner’s fingerprint before exchanging work.','Enrolled peers','A named peer is not an approval'],
  activity:['Activity','DURABLE HISTORY','Every decision has a record.','Inspect what was received, decided and withdrawn.','Recent activity','Saved events from this assistant']
};
class RequestFailure extends Error { constructor(message,{unknown=false,unauthorised=false}={}) { super(message); this.unknown=unknown;this.unauthorised=unauthorised; } }
function text(tag,value,className) { const node=document.createElement(tag);node.textContent=String(value??'');if(className)node.className=className;return node; }
function button(label,className,handler) { const node=text('button',label,className);node.type='button';node.addEventListener('click',handler);return node; }
function detail(list,label,value) { list.append(text('dt',label),text('dd',plain(value)||'Unavailable')); }
function badge(value) { return text('span',stateLabel(value),'badge '+statusClass(value)); }
function datetime(value) { const time=finiteDate(value); return time===null?'Time not supplied':new Date(time*1000).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); }
function peerName(peerId) { const peer=state?.peers.find(peer=>peer.peer_id===peerId); return peer ? `${plain(peer.agent_id,'Assistant')} · ${plain(peer.owner_id,'Owner')}` : plain(peerId,'Unknown peer'); }
function identityText(identity) { if(typeof identity==='string')return identity;return `${plain(identity?.agent_id,'Assistant')} · ${plain(identity?.owner_id,'Owner')}`; }
function notice(message,success=false) { $('notice').textContent=message;$('notice').hidden=!message;$('notice').classList.toggle('success',success); }
function setBusy(value) { busy=value; document.querySelectorAll('button').forEach(node=>{ if(!node.classList.contains('close-dialog'))node.disabled=value; }); }
function resetSession(message='') {
  generation++;token=null;state=null;selected=null;selectedWorkflow=null;uncertain=false;
  document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
  $('workspace').hidden=true;$('login-screen').hidden=false;$('password').value='';
  $('item-list').replaceChildren();$('review-content').textContent='';$('review-details').replaceChildren();$('review-commitments').replaceChildren();$('review-actions').replaceChildren();
  $('compose-form').reset();$('peer-form').reset();$('login-message').textContent=message;
  setBusy(false);
}
async function request(path,{method='GET',body,sessionToken=token}={}) {
  const mutation=method!=='GET';
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
  try {
    const headers={Accept:'application/json'};if(body!==undefined)headers['Content-Type']='application/json';if(sessionToken)headers.Authorization=`Bearer ${sessionToken}`;
    const response=await fetch(path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer'});
    if(response.status===401)throw new RequestFailure('Your session has ended. Unlock the workspace again.',{unauthorised:true});
    if(!response.ok)throw new RequestFailure(response.status>=500?'The operation could not be confirmed. Inspect the saved state before doing anything else.':'The request was refused. Refresh and review the exact current proposal.',{unknown:mutation&&response.status>=500});
    const raw=await response.text();if(raw.length>2097152)throw new Error('Response bound');
    try { return raw?JSON.parse(raw):{}; } catch { throw new Error('Response unavailable'); }
  } catch(error) {
    if(error instanceof RequestFailure)throw error;
    throw new RequestFailure(mutation?'The operation could not be confirmed. Inspect the saved state before doing anything else.':'The workspace could not be reached. Your saved decisions have not been changed.',{unknown:mutation});
  } finally { clearTimeout(timeout); }
}
function handleFailure(error,target='notice') {
  if(error.unauthorised) { resetSession(error.message);return; }
  const message=error instanceof RequestFailure?error.message:'The returned state could not be verified. Refresh before deciding.';
  if(error.unknown){uncertain=true;notice(message);$('connection-status').textContent='Inspection required';$('refresh').setAttribute('aria-label','Inspect saved state after an uncertain outcome');}
  if(target==='notice')notice(message);else $(target).textContent=message;
}
async function refresh({clearNotice=false}={}) {
  const epoch=generation;
  const data=validateState(await request('/api/state'));
  if(epoch!==generation||!token)return;
  state=data;uncertain=false;render();$('connection-status').textContent='Saved state checked';$('refresh').setAttribute('aria-label','Refresh saved state');
  if(clearNotice)notice('Saved state inspected. Review any pending item before acting.',true);
}
async function performWrite(path,body,{target='notice',onSuccess}={}) {
  if(busy||uncertain)return;
  const epoch=generation;let returned=false;setBusy(true);
  try {
    const result=await request(path,{method:'POST',body});
    returned=true;
    if(epoch!==generation)return;
    await refresh();
    if(epoch!==generation)return;
    if(onSuccess)onSuccess(result);
  } catch(error) { if(epoch===generation)handleFailure(returned&&!error.unauthorised?new RequestFailure('The operation returned, but its saved state could not be inspected. Refresh before acting again.',{unknown:true}):error,target); }
  finally { if(epoch===generation)setBusy(false); }
}
function render() {
  if(!state)return;
  const owner=state.identity;$('owner-name').textContent=owner.owner_id;$('agent-name').textContent=owner.agent_id;$('owner-avatar').textContent=owner.owner_id.slice(0,2).toUpperCase();
  $('inbox-count').textContent=state.items.filter(item=>item.direction==='incoming'&&isPending(item)).length;
  $('outbox-count').textContent=state.items.filter(item=>item.direction==='outgoing'&&!isTerminal(item)).length;
  $('pending-total').textContent=state.items.filter(item=>item.direction==='incoming'&&isPending(item)).length;
  $('accepted-total').textContent=state.items.filter(item=>item.state==='accepted').length;$('peer-total').textContent=state.peers.filter(isPeerActive).length;
  const copy=viewCopy[currentView];['view-name','page-eyebrow','page-title','page-description','list-title','list-description'].forEach((id,index)=>$(id).textContent=copy[index]);
  document.querySelectorAll('[data-view]').forEach(node=>{node.classList.toggle('active',node.dataset.view===currentView);node.setAttribute('aria-current',node.dataset.view===currentView?'page':'false');});
  document.querySelectorAll('[data-filter]').forEach(node=>{node.classList.toggle('selected',node.dataset.filter===currentFilter);node.setAttribute('aria-pressed',String(node.dataset.filter===currentFilter));});
  $('summary').hidden=['peers','activity'].includes(currentView);$('filters').hidden=['peers','activity'].includes(currentView);$('add-peer').hidden=currentView!=='peers';
  const provider=state.provider;
  $('provider-status').textContent=workflowEnabled(state)?'Local synthetic rehearsal available · Live calls disabled':provider?.live_enabled===true?'Provider activation reported by server':'Live provider calls disabled';
  $('item-list').replaceChildren();
  if(currentView==='peers')renderPeers();else if(currentView==='activity')renderHistory();else renderItems();
}
function empty(symbol,title,description,action) {
  const box=text('div','','empty-state');box.append(text('div',symbol,'empty-symbol'),text('h3',title),text('p',description));if(action)box.append(button(action.label,'button secondary',action.run));$('item-list').append(box);
}
function renderItems() {
  const items=filteredItems(state.items,currentView,currentFilter);
  if(!items.length){empty(currentView==='inbox'?'↙':'↗',currentFilter==='all'?(currentView==='inbox'?'Your inbox is clear.':'Nothing released without you.'):'No matching proposals.',currentView==='inbox'?'New proposals will appear here after you sync the exchange. Every incoming item needs its own decision.':'Prepare a fictional task or artifact, then review the exact proposal before releasing it.');return;}
  for(const item of [...items].reverse()) {
    const row=text('article','','item-row');const main=text('div','','item-main');main.append(text('h3',plain(item.title,'Untitled proposal'),'item-title'));
    const meta=text('div','','item-meta');meta.append(text('span',item.kind==='task'?'TASK REQUEST':'ARTIFACT','item-type'),text('span','·'),text('span',peerName(item.peer_id)));main.append(meta);
    const right=text('div','','row-right');right.append(badge(item.state),button(isTerminal(item)?'Inspect':'Review exact item','button secondary',()=>openReview(item)));
    const run=state.workflow?.runs.find(run=>run.item_id===item.id);
    if(run){main.append(text('p',workflowSummary(run),'workflow-note'));right.append(button('Inspect synthetic run','button secondary',()=>openWorkflow(item,run.run_id)));}
    row.append(text('div',item.kind==='task'?'↗':'▤','item-icon '+item.kind),main,right);$('item-list').append(row);
  }
}
function renderPeers() {
  const own=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3','Your public identity','item-title'),text('div',identityText(state.identity),'item-meta'),text('p',state.identity.fingerprint,'peer-fingerprint'));
  const identity=state.identity.public||Object.fromEntries(Object.entries(state.identity).filter(([key])=>['owner_id','agent_id','signing_key','exchange_key','version'].includes(key)));
  const right=text('div','','row-right');right.append(button('View public identity','button secondary',()=>showPublicIdentity(identity,state.identity.fingerprint)));
  own.append(text('div','◇','item-icon'),main,right);$('item-list').append(own);
  if(!state.peers.length){empty('⊞','Start with one trusted peer.','Exchange public identities with the other owner and compare the complete fingerprint.',{label:'Enrol a peer',run:()=>openDialog('peer-dialog')});return;}
  for(const peer of state.peers) {
    const row=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',plain(peer.agent_id,'Assistant'),'item-title'),text('div',plain(peer.owner_id,'Owner'),'item-meta'),text('p',peer.fingerprint,'peer-fingerprint'));
    const right=text('div','','row-right');right.append(text('span',isPeerActive(peer)?'Enrolled':peer.state==='revoked'?'Revoked':'Status unavailable',isPeerActive(peer)?'badge accepted':'badge revoked'));
    row.append(text('div','⊞','item-icon'),main,right);$('item-list').append(row);
  }
}
function showPublicIdentity(identity,fingerprint) {
  selected=null;$('review-title').textContent='Your public identity';$('review-eyebrow').textContent='SHARE AND VERIFY';$('review-state').replaceChildren();$('review-details').replaceChildren();detail($('review-details'),'Fingerprint',fingerprint);
  $('review-content').textContent=JSON.stringify(identity,null,2);$('review-commitments').replaceChildren();$('review-message').textContent='';$('review-scope').textContent='Only public identity fields are shown. The other owner must verify the full fingerprint before enrolment.';$('review-actions').replaceChildren(button('Close','button secondary',()=> $('review-dialog').close()));openDialog('review-dialog');
}
function renderHistory() {
  if(!state.history.length){empty('≋','A clear record from the start.','Saved decisions and exchange events will appear here. An uncertain outcome stays uncertain until saved evidence resolves it.');return;}
  for(const item of [...state.history].reverse()) {
    const row=text('article','','item-row activity-row');const main=text('div','','item-main');main.append(text('h3',plain(item.label)||plain(item.event).replaceAll('_',' ')||'Saved event','item-title'));
    const id=plain(item.item_id)||plain(item.id);if(id)main.append(text('p',id,'peer-fingerprint'));
    const when=finiteDate(item.created_at??item.time);row.append(text('span','·','item-icon'),main,text('time',when===null?`Event ${item.sequence??'recorded'}`:datetime(when),'activity-time'));$('item-list').append(row);
  }
}
async function openReview(item) {
  if(busy||uncertain)return;
  const epoch=generation;setBusy(true);
  try {
    const review=validateReview(await request(`/api/items/${encodeURIComponent(item.id)}/review`),item);
    if(epoch!==generation)return;
    selected={item:{...item},review};selectedWorkflow=null;$('review-title').textContent=plain(item.title,'Exact proposal');$('review-eyebrow').textContent=item.direction==='outgoing'?'OUTGOING RELEASE REVIEW':'RECIPIENT DECISION';$('review-state').replaceChildren(badge(item.state));
    $('review-details').replaceChildren();detail($('review-details'),'Type',item.kind==='task'?'Task request':'Artifact');detail($('review-details'),'Peer',peerName(item.peer_id));detail($('review-details'),'Recipient',identityText(review.recipient));detail($('review-details'),'Task reference',item.task_id);detail($('review-details'),'Valid until',datetime(item.expires));
    if(item.historical_state&&item.historical_state!==item.state)detail($('review-details'),'Historical state',stateLabel(item.historical_state));
    const permissions=review.source_permissions;
    if(permissions?.return_policy==='origin-only')detail($('review-details'),'Sharing scope','Reviewed artifact return to task originator only');
    const provider=permissions?.provider_disclosure;detail($('review-details'),'Provider permission',provider?`${plain(provider.provider)} · ${plain(provider.model)} · ${Number(provider.max_output_tokens)} output tokens`:'No provider disclosure approved');
    $('review-content').textContent=review.content===null?'Content is no longer available for review. This record preserves the original commitments and decision.':review.content;$('review-commitments').replaceChildren();detail($('review-commitments'),'Proposal ID',item.id);detail($('review-commitments'),'Review digest',review.review_digest);detail($('review-commitments'),'Artifact digest',review.artifact_digest);detail($('review-commitments'),'Context',review.context);
    $('review-scope').textContent=item.direction==='outgoing'?'Release shares only this exact proposal with its named recipient. The recipient makes a separate decision.':'Acceptance records this exact proposal. It does not start work or run a model. Any artifact return needs its own review and can go only to the task originator.';
    $('review-message').textContent='';$('review-actions').replaceChildren();
    const captions={accept:'Accept exact proposal',reject:'Reject proposal',release:'Approve & release',cancel:'Withdraw proposal'};
    for(const action of ['cancel','reject','release','accept'])if(review.allowed_actions.includes(action))$('review-actions').append(button(captions[action],`button ${['accept','release'].includes(action)?'primary':'danger'}`,()=>decideSelected(action)));
    if(canPrepareWorkflow(state,item,review))$('review-actions').append(button('Prepare synthetic run','button secondary',()=>prepareWorkflow(item)));
    if(!review.allowed_actions.length)$('review-actions').append(button('Close','button secondary',()=> $('review-dialog').close()));
    $('review-dialog').showModal();
  } catch(error) { if(epoch===generation)handleFailure(error); }
  finally { if(epoch===generation)setBusy(false); }
}
async function decideSelected(action) {
  if(!selected||busy||uncertain||!selected.review.allowed_actions.includes(action))return;
  const snapshot=selected;const suffix=['accept','reject'].includes(action)?'decision':action;
  const body={review_digest:snapshot.review.review_digest};if(suffix==='decision')body.decision=action;
  await performWrite(`/api/items/${encodeURIComponent(snapshot.item.id)}/${suffix}`,body,{target:'review-message',onSuccess:()=>{selected=null;$('review-dialog').close();notice(action==='release'?'Exact proposal released. Use Sync exchange to deliver queued messages.':'Your decision has been saved.',true);}});
}
async function prepareWorkflow(item) {
  if(!selected||selected.item.id!==item.id||!canPrepareWorkflow(state,item,selected.review))return;
  await performWrite(`/api/items/${encodeURIComponent(item.id)}/workflow`,{}, {target:'review-message',onSuccess:()=>{selected=null;$('review-dialog').close();notice('Synthetic run prepared. Inspect its exact request and approve it separately. Nothing has run.',true);}});
}
function workflowDetailHeader(item,run,heading) {
  selected=null;$('review-title').textContent=heading;$('review-eyebrow').textContent='LOCAL SYNTHETIC REHEARSAL';$('review-state').replaceChildren(text('span',workflowStateLabel(run.state),'badge '+statusClass(run.state)));
  $('review-details').replaceChildren();detail($('review-details'),'Task',plain(item.title,item.task_id));detail($('review-details'),'Return recipient',peerName(item.peer_id));detail($('review-details'),'Provider calls','None. Fixed local fixture only.');
  $('review-commitments').replaceChildren();detail($('review-commitments'),'Run ID',run.run_id);detail($('review-commitments'),'Task proposal',item.id);detail($('review-commitments'),'Context',item.context);detail($('review-commitments'),'Provider review',run.review_digest);
  $('review-message').textContent='';$('review-actions').replaceChildren();
}
async function openWorkflow(item,runId) {
  if(busy||uncertain)return;
  const epoch=generation;setBusy(true);
  try {
    const run=validateWorkflowStatus(await request(`/api/workflows/${encodeURIComponent(runId)}`),item);
    if(epoch!==generation)return;
    workflowDetailHeader(item,run,'Inspect synthetic run');
    selectedWorkflow={item:{...item},run,review:null,mode:'status'};
    $('review-content').textContent='No automatic retry is permitted. Inspect the retained status and original operation.';
    $('review-scope').textContent='This is a local fixture, not completed research or a live model response. A run never releases an artifact automatically.';
    if(run.allowed_actions.includes('review')) {
      const value=validateWorkflowReview(await request(`/api/workflows/${encodeURIComponent(runId)}/review`),run,item,state.identity);
      if(epoch!==generation)return;
      selectedWorkflow={item:{...item},run,review:value,mode:'provider'};
      $('review-title').textContent='Review synthetic request';$('review-content').textContent=JSON.stringify(value.review.request,null,2);
      detail($('review-details'),'Fixture route',`${value.review.binding.provider} · ${value.review.binding.model}`);detail($('review-details'),'Output limit',`${value.review.binding.max_output_tokens} tokens`);detail($('review-details'),'Input commitment',item.artifact_digest);
      $('review-scope').textContent='Approve only this exact request for the local synthetic fixture. Approval does not run it. Running is a separate one-shot action and does not publish or release the result.';
      if(run.allowed_actions.includes('approve'))$('review-actions').append(button('Approve synthetic request','button primary',()=>workflowAction('approve')));
      if(run.allowed_actions.includes('run'))$('review-actions').append(button('Run synthetic fixture once','button primary',()=>workflowAction('run')));
    } else if(run.allowed_actions.includes('review_result')) {
      const peer=state.peers.find(peer=>peer.peer_id===item.peer_id);
      const value=validateWorkflowResult(await request(`/api/workflows/${encodeURIComponent(runId)}/result`),run,item,peer);
      if(epoch!==generation)return;
      selectedWorkflow={item:{...item},run,review:value,mode:'result'};
      $('review-title').textContent='Review original synthetic result';$('review-content').textContent=value.content;
      detail($('review-details'),'Artifact title',value.review.title);detail($('review-details'),'Valid until',datetime(value.review.expires));
      detail($('review-commitments'),'Result digest',value.review.result_digest);detail($('review-commitments'),'Result review',value.review_digest);detail($('review-commitments'),'Source permissions',value.review.source_permissions_digest);
      $('review-scope').textContent='Stage only this exact original fixture result as an artifact draft for the originating task owner. Staging does not release it. Review and release the resulting outbox item separately.';
      if(run.allowed_actions.includes('stage'))$('review-actions').append(button('Stage exact artifact','button primary',()=>workflowAction('stage')));
    }
    if(run.artifact_id){detail($('review-commitments'),'Retained artifact',run.artifact_id);detail($('review-details'),'Artifact state',stateLabel(run.artifact_state));}
    if(run.allowed_actions.includes('cancel'))$('review-actions').prepend(button('Cancel synthetic run','button danger',()=>workflowAction('cancel')));
    $('review-actions').append(button('Close','button secondary',()=>{$('review-dialog').close();selectedWorkflow=null;}));
    $('review-dialog').showModal();
  } catch(error) { if(epoch===generation)handleFailure(error); }
  finally { if(epoch===generation)setBusy(false); }
}
async function workflowAction(action) {
  if(!selectedWorkflow||busy||uncertain||!selectedWorkflow.run.allowed_actions.includes(action)||!workflowEnabled(state))return;
  const snapshot=selectedWorkflow,body={};
  if(['approve','run','stage'].includes(action))body.review_digest=snapshot.review.review_digest;
  if(action==='approve')body.expires=Math.min(Math.floor(Date.now()/1000)+300,Math.floor(snapshot.item.expires));
  await performWrite(`/api/workflows/${encodeURIComponent(snapshot.run.run_id)}/${action}`,body,{target:'review-message',onSuccess:()=>{
    selectedWorkflow=null;$('review-dialog').close();
    if(action==='stage'){currentView='outbox';currentFilter='all';render();}
    const messages={approve:'Exact synthetic request approved. Inspect the run to perform the separate one-shot fixture action.',run:'Original synthetic result retained. Inspect it before staging an artifact.',stage:'Exact artifact staged as a draft. Review and release it separately from your outbox.',cancel:'Synthetic run cancelled locally. No remote cancellation or recall is claimed.'};notice(messages[action],true);
  }});
}
function openDialog(id) { if(busy||uncertain)return;$(id).showModal(); }
function newContext(){return Array.from(crypto.getRandomValues(new Uint8Array(32)),byte=>byte.toString(16).padStart(2,'0')).join('');}
function prepareCompose(){
  if(busy||uncertain)return;
  if(!state.peers.some(isPeerActive)){currentView='peers';render();notice('Enrol an active trusted peer before preparing a proposal.');return;}
  $('compose-form').reset();$('compose-message').textContent='';$('proposal-peer').replaceChildren();
  for(const peer of state.peers.filter(isPeerActive)){const option=text('option',`${plain(peer.agent_id,'Assistant')} · ${plain(peer.owner_id,'Owner')}`);option.value=peer.peer_id;$('proposal-peer').append(option);}
  const form=$('compose-form');form.elements.context.value=newContext();form.elements.task_id.value='task-'+crypto.randomUUID();form.elements.text.value='SYNTHETIC ONLY: ';
  configureKind();openDialog('compose-dialog');
}
function configureKind(){
  const form=$('compose-form'),artifact=form.elements.kind.value==='artifact';$('parent-field').hidden=!artifact;$('proposal-parent').required=artifact;
  $('workflow-permission-field').hidden=artifact||!workflowEnabled(state);if(artifact||!workflowEnabled(state))form.elements.synthetic_run.checked=false;
  form.elements.context.readOnly=artifact;form.elements.task_id.readOnly=artifact;form.elements.peer_id.disabled=artifact;
  $('compose-message').textContent='';
  if(artifact){
    $('proposal-parent').replaceChildren();
    for(const item of state.items.filter(item=>item.direction==='incoming'&&item.kind==='task'&&item.state==='accepted')){const option=text('option',plain(item.title,item.task_id));option.value=item.id;$('proposal-parent').append(option);}
    if(!$('proposal-parent').options.length)$('compose-message').textContent='Accept an incoming task before preparing an artifact in reply.';
    selectParent();
  }
}
function selectParent(){
  const item=state.items.find(item=>item.id===$('proposal-parent').value);if(!item)return;
  const form=$('compose-form');form.elements.peer_id.value=item.peer_id;form.elements.task_id.value=item.task_id;form.elements.context.value=item.context;
}

$('login-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;setBusy(true);$('login-message').textContent='';const password=$('password').value;$('password').value='';const epoch=generation;
  try {
    const result=await request('/api/session',{method:'POST',body:{password},sessionToken:null});
    if(epoch!==generation)return;
    if(typeof result.token!=='string'||result.token.length<16||!result.identity)throw new Error('Invalid login response');
    token=result.token;generation++;await refresh();$('login-screen').hidden=true;$('workspace').hidden=false;$('main').focus();
  } catch(error) { resetSession(error.unauthorised?'The password was not accepted.':error instanceof RequestFailure?error.message:'The session could not be verified.'); }
  finally {setBusy(false);}
});
async function logout(){
  if(busy)return;const original=token;resetSession();
  try {await request('/api/session',{method:'DELETE',body:{},sessionToken:original});}catch{$('login-message').textContent='Locked here. Server sign-out could not be confirmed; the session will expire.';}
}
$('logout').addEventListener('click',logout);$('mobile-logout').addEventListener('click',logout);
$('refresh').addEventListener('click',async()=>{if(busy)return;const epoch=generation;setBusy(true);try{await refresh({clearNotice:true});selected=null;selectedWorkflow=null;$('review-dialog').close();}catch(error){if(epoch===generation)handleFailure(error);}finally{if(epoch===generation)setBusy(false);}});
$('sync').addEventListener('click',()=>performWrite('/api/exchange',{}, {onSuccess:()=>notice('Exchange checked. Review new items and saved delivery outcomes below.',true)}));
$('new-proposal').addEventListener('click',prepareCompose);$('add-peer').addEventListener('click',()=>openDialog('peer-dialog'));
document.querySelectorAll('[data-view]').forEach(node=>node.addEventListener('click',()=>{if(busy)return;currentView=node.dataset.view;currentFilter='all';render();}));
document.querySelectorAll('[data-filter]').forEach(node=>node.addEventListener('click',()=>{if(busy)return;currentFilter=node.dataset.filter;render();}));
document.querySelectorAll('.close-dialog').forEach(node=>node.addEventListener('click',()=>{if(busy)return;node.closest('dialog').close();selected=null;selectedWorkflow=null;}));
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();else{selected=null;selectedWorkflow=null;}}));
$('proposal-kind').addEventListener('change',configureKind);$('proposal-parent').addEventListener('change',selectParent);
$('compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertain)return;const form=event.currentTarget;const fields=Object.fromEntries(new FormData(form));fields.peer_id=form.elements.peer_id.value;
  if(fields.kind==='artifact')fields.parent_expires=state.items.find(item=>item.id===fields.parent_id)?.expires;
  try {await performWrite('/api/proposals',proposalBody(fields),{target:'compose-message',onSuccess:()=>{$('compose-dialog').close();currentView='outbox';currentFilter='all';render();notice('Proposal prepared. Open it to review the exact content before release.',true);}});}catch(error){$('compose-message').textContent=error.message;}
});
$('peer-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertain)return;
  try {const body=peerBody(Object.fromEntries(new FormData(event.currentTarget)));await performWrite('/api/peers',body,{target:'peer-message',onSuccess:()=>{$('peer-dialog').close();$('peer-form').reset();notice('Exact peer enrolled. Each proposal still needs separate approval.',true);}});}catch(error){$('peer-message').textContent=error.message;}
});
document.addEventListener('visibilitychange',()=>{if(document.hidden){$('password').value='';}});
