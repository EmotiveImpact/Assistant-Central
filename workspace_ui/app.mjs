import {operationGate,restoreWhenIdle,inspectionLatch,inspectSavedState,requestIsMutation} from './operations.mjs';
import {createConversations,inspectMessageOutcome} from './conversations.mjs';
import {createHostDrafts} from './host_drafts.mjs';
import {validateTransferReview,transferPath} from './transfers.mjs';
import {VIEWS,viewFromHash,matchesQuery,projectItems,boardGroups,workspaceTotals,activeTasks,attentionItems} from './projections.mjs';
import {plain,finiteDate,stateLabel,statusClass,isTerminal,isPeerActive,validateState,validateReview,proposalBody,peerBody,workflowEnabled,workflowStateLabel,validateWorkflowStatus,validateWorkflowReview,validateWorkflowResult,workflowSummary,canPrepareWorkflow} from './model.mjs';

const $ = id => document.getElementById(id);
const mobileNavigation=matchMedia('(max-width:700px)'), sidebar=document.querySelector('.sidebar');
function setNavigation(open,{restoreFocus=false}={}){
  const wasOpen=document.body.classList.contains('sidebar-open');open=Boolean(open&&mobileNavigation.matches);
  document.body.classList.toggle('sidebar-open',open);sidebar.inert=mobileNavigation.matches&&!open;
  sidebar.setAttribute('aria-hidden',String(sidebar.inert));$('menu-toggle').setAttribute('aria-expanded',String(open));$('menu-toggle').setAttribute('aria-label',open?'Close navigation':'Open navigation');
  if(open&&!wasOpen)sidebar.querySelector('[data-view]')?.focus();
  else if(wasOpen&&!open){if(restoreFocus&&mobileNavigation.matches)$('menu-toggle').focus();else if(sidebar.contains(document.activeElement))$('main').focus();}
}
mobileNavigation.addEventListener('change',()=>setNavigation(false));
let token = null, generation = 0, busy = false, currentView = viewFromHash(location.hash), currentFilter = 'all', currentLayout = 'list', searchQuery = '';
let state = null, selected = null, selectedWorkflow = null, selectedTransfer = null;
const uncertainty=inspectionLatch();
const viewCopy = {
  overview:['Overview','WORKSPACE OVERVIEW','Your workspace, in motion.','People, assistants and the work you share.','Workspace results','Search your saved work'],
  inbox:['Inbox','INCOMING WORK','Inbox','Review the requests and artifacts shared with your assistant.','All incoming','Every proposal has its own decision'],
  tasks:['Work','SHARED WORK','All work','Follow every task from its first proposal to the exact result.','All tasks','Incoming and outgoing task requests'],
  artifacts:['Artifacts','SHARED ARTIFACTS','Artifacts','Find the exact artifacts prepared and shared across your network.','All artifacts','Drafts, received artifacts and saved decisions'],
  outbox:['Outbox','OUTGOING WORK','Outbox','Prepare the exact content. Review it before you release it.','All outgoing','Prepared and released proposals'],
  peers:['Assistants','YOUR NETWORK','Your assistants','A network of people and the assistants they choose to trust.','Assistant network','Enrolment is separate from approval'],
  conversations:['Conversations','SCOPED LOCAL HISTORY','Room for a conversation.','Persistent conversations with explicit membership and exact history consent.','Your conversations','Local coordinating host only'],
  transfers:['Transfers','EXPLICIT DELIVERY','Every handoff, deliberate.','Review an exact packet before each send or import.','Connections & transfers','No automatic delivery or retries'],
  'host-drafts':['Host drafts','INERT LOCAL DRAFTS','Inspect before anything moves.','Review exact drafts from a configured supported host.','Host task drafts','Inspection and dismissal only'],
  activity:['Activity','WORKSPACE ACTIVITY','Activity','The saved history of work moving through your workspace.','Recent activity','Recorded events from this assistant']
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
function setBusy(value) { busy=value; document.querySelectorAll('button').forEach(node=>{ if(!node.classList.contains('close-dialog'))node.disabled=value; });if(!value)restorePanel(); }
const restorePanel=restoreWhenIdle({session:()=>generation,eligible:()=>Boolean(token&&state&&!busy&&!document.hidden&&['conversations','host-drafts'].includes(currentView)&&!$('item-list').childElementCount),restore:()=>render()});
const operations=operationGate(setBusy);
const conversations=createConversations({request,gate:operations.scope(),session:()=>generation,restore:()=>{if(token&&currentView==='conversations')render();},unknownFailure:message=>new RequestFailure(message,{unknown:true}),busy:()=>busy,uncertain:()=>uncertainty.pending(),failed:(error,operation)=>handleFailure(error,'notice','conversations',operation),active:()=>Boolean(token&&currentView==='conversations'&&!document.hidden)});
const hostDrafts=createHostDrafts({request,gate:operations.scope(),restore:()=>{if(token&&currentView==='host-drafts')render();},session:()=>generation,owner:()=>state?.identity.fingerprint,unknownFailure:message=>new RequestFailure(message,{unknown:true}),busy:()=>busy,uncertain:()=>uncertainty.pending(),failed:(error,operation)=>handleFailure(error,'notice','host-drafts',operation),active:()=>Boolean(token&&currentView==='host-drafts'&&!document.hidden)});
function resetSession(message='') {
  conversations.reset({sessionEnded:true});
  hostDrafts.reset({sessionEnded:true});
  generation++;token=null;state=null;selected=null;selectedWorkflow=null;selectedTransfer=null;uncertainty.reset();searchQuery='';
  $('search-input').value='';setNavigation(false);
  for(const id of ['overview-attention','overview-work','overview-network','overview-events','overview-stats'])$(id).replaceChildren();
  document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
  $('account').value='';$('workspace').hidden=true;$('login-screen').hidden=false;$('password').value='';
  $('item-list').replaceChildren();$('review-content').textContent='';$('review-details').replaceChildren();$('review-commitments').replaceChildren();$('review-actions').replaceChildren();
  for(const id of ['review-title','review-eyebrow','review-state','review-scope','review-message','compose-message','peer-message','peer-connection-note','owner-name','agent-name','owner-avatar','connection-status','provider-status'])$(id).replaceChildren();
  for(const id of ['proposal-peer','proposal-parent','peer-connection'])$(id).replaceChildren();
  for(const id of ['inbox-count','outbox-count','pending-total','accepted-total','peer-total'])$(id).textContent='0';
  $('review-dialog').querySelector('.commitment-details').open=false;notice('');
  $('compose-form').reset();$('peer-form').reset();$('login-message').textContent=message;
  operations.reset();
}
async function request(path,{method='GET',body,sessionToken=token,readOnly=false}={}) {
  const mutation=requestIsMutation(path,method,readOnly);
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
    throw new RequestFailure(mutation?'The operation could not be confirmed. Inspect the saved state before doing anything else.':'The workspace could not be reached. This inspection made no changes.',{unknown:mutation});
  } finally { clearTimeout(timeout); }
}
function handleFailure(error,target='notice',source='runtime',operation=null) {
  if(error.unauthorised) { resetSession(error.message);return; }
  const message=(error instanceof RequestFailure?error.message:'The returned state could not be verified. Refresh before deciding.')+(error.unknown&&source==='conversations'?(operation?.type==='message-outcome'?' Use Refresh saved state to inspect this exact message without sending it again.':' Read-only inspection remains available; this operation has no exact recovery and writes stay blocked in this session.'):'');
  if(error.unknown){uncertainty.require(source,operation);notice(message);$('connection-status').textContent='Inspection required';$('refresh').setAttribute('aria-label','Inspect saved state after an uncertain outcome');}
  if(target==='notice')notice(message);else $(target).textContent=message;
}
async function refresh({clearNotice=false}={}) {
  const epoch=generation;
  const data=await inspectSavedState({latch:uncertainty,session:()=>generation,readState:async()=>validateState(await request('/api/state')),inspectHost:()=>hostDrafts.inspectUncertain(),inspectConversation:operation=>inspectMessageOutcome({request,session:()=>generation,operation})});
  if(epoch!==generation||!token||!data)return;
  state=data;render();$('connection-status').textContent=uncertainty.pending()?'Inspection required':'Saved state checked';$('refresh').setAttribute('aria-label',uncertainty.pending()?'Inspect saved state after an uncertain outcome':'Refresh saved state');
  if(clearNotice)notice(uncertainty.pending()?'An earlier operation is still unconfirmed. A missing or unavailable result is not proof it failed. Read-only inspection is available; writes stay blocked.':'Saved state inspected. Review any pending item before acting.',!uncertainty.pending());
}
async function performWrite(path,body,{target='notice',onSuccess}={}) {
  if(busy||uncertainty.pending())return;
  const epoch=generation;let returned=false;const release=operations.acquire();
  try {
    const result=await request(path,{method:'POST',body});
    returned=true;
    if(epoch!==generation)return;
    await refresh();
    if(epoch!==generation)return;
    if(onSuccess)onSuccess(result);
  } catch(error) { if(epoch===generation)handleFailure(returned&&!error.unauthorised?new RequestFailure('The operation returned, but its saved state could not be inspected. Refresh before acting again.',{unknown:true}):error,target); }
  finally { release(); }
}
function navigate(view,{filter='all'}={}) {
  if(busy||!VIEWS.includes(view))return;
  currentView=view;currentFilter=filter;searchQuery='';$('search-input').value='';
  if(location.hash!=='#'+view)history.pushState(null,'','#'+view);
  setNavigation(false);render();
}
function render() {
  if(!state)return;
  conversations.reset();
  hostDrafts.reset();
  const owner=state.identity;$('owner-name').textContent=owner.owner_id;$('agent-name').textContent=owner.agent_id;$('owner-avatar').textContent=owner.owner_id.slice(0,2).toUpperCase();
  const totals=workspaceTotals(state);
  $('inbox-count').textContent=totals.pending;
  $('outbox-count').textContent=state.items.filter(item=>item.direction==='outgoing'&&!isTerminal(item)).length;
  $('pending-total').textContent=totals.pending;
  $('accepted-total').textContent=state.items.filter(item=>item.state==='accepted').length;$('peer-total').textContent=totals.peers;
  const copy=viewCopy[currentView];['view-name','page-eyebrow','page-title','page-description','list-title','list-description'].forEach((id,index)=>$(id).textContent=copy[index]);
  let acceptedFilter=$('accepted-filter');
  if(currentFilter==='accepted'&&!acceptedFilter){acceptedFilter=button('Accepted','selected',()=>{if(busy)return;currentFilter='accepted';render();});acceptedFilter.id='accepted-filter';acceptedFilter.dataset.filter='accepted';$('filters').append(acceptedFilter);}
  if(acceptedFilter)acceptedFilter.hidden=currentFilter!=='accepted';
  if(currentFilter==='accepted')$('list-title').textContent=currentView==='tasks'?'Accepted tasks':'Accepted proposals';
  document.querySelectorAll('[data-view]').forEach(node=>{node.classList.toggle('active',node.dataset.view===currentView);node.setAttribute('aria-current',node.dataset.view===currentView?'page':'false');});
  document.querySelectorAll('[data-filter]').forEach(node=>{node.classList.toggle('selected',node.dataset.filter===currentFilter);node.setAttribute('aria-pressed',String(node.dataset.filter===currentFilter));});
  document.querySelectorAll('[data-layout]').forEach(node=>{node.classList.toggle('selected',node.dataset.layout===currentLayout);node.setAttribute('aria-pressed',String(node.dataset.layout===currentLayout));});
  const overview=currentView==='overview'&&!searchQuery, structural=['peers','activity','transfers','conversations','host-drafts'].includes(currentView);
  $('overview-panel').hidden=!overview;$('work-panel').hidden=overview;
  $('summary').hidden=true;$('filters').hidden=structural||overview;$('view-toggle').hidden=structural||overview;$('add-peer').hidden=currentView!=='peers';
  $('search-clear').hidden=!searchQuery;
  $('search-input').disabled=['transfers','conversations','host-drafts'].includes(currentView);
  $('new-proposal').hidden=['conversations','host-drafts'].includes(currentView);
  $('search-input').setAttribute('placeholder',currentView==='transfers'?'Exact transfer selection below':currentView==='peers'?'Search assistants…':currentView==='activity'?'Search activity…':'Search work…');
  const provider=state.provider;
  $('provider-status').textContent=workflowEnabled(state)?'Synthetic workspace · Live calls disabled':provider?.live_enabled===true?'Provider activation reported by server':'Live provider calls disabled';
  $('item-list').replaceChildren();$('item-list').classList.toggle('board',currentLayout==='board'&&!structural);
  if(overview)renderOverview(totals);else if(currentView==='peers')renderPeers();else if(currentView==='activity')renderHistory();else if(currentView==='transfers')renderTransfers();else if(currentView==='conversations')conversations.mount($('item-list'),state.conversations?.enabled===true);else if(currentView==='host-drafts')hostDrafts.mount($('item-list'),state.host_drafts?.enabled===true);else renderItems();
  const date=$('overview-date');if(date)date.textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
}
function empty(symbol,title,description,action,target=$('item-list')) {
  const box=text('div','','empty-state');box.append(text('div',symbol,'empty-symbol'),text('h3',title),text('p',description));if(action)box.append(button(action.label,'button secondary',action.run));target.append(box);
}
function peerAvatar(peerId,className='peer-avatar') {
  const peer=state.peers.find(peer=>peer.peer_id===peerId),name=plain(peer?.agent_id,'?');
  const avatar=text('span',name.slice(0,1).toUpperCase(),className);avatar.setAttribute('aria-hidden','true');return avatar;
}
function itemRow(item) {
  const row=text('article','','item-row');row.dataset.itemId=item.id;
  const main=text('div','','item-main');
  const heading=button(plain(item.title,'Untitled proposal'),'item-title item-open',()=>openReview(item));heading.setAttribute('aria-label','Review '+plain(item.title,'proposal'));const title=text('h3','','item-heading');title.append(heading);main.append(title);
  const meta=text('div','','item-meta');meta.append(text('span',plain(item.task_id,plain(item.id)).slice(0,28),'task-ref'),text('span','·'),text('span',item.direction==='incoming'?'Incoming':'Outgoing'),text('span','·'),text('span',peerName(item.peer_id)));main.append(meta);
  const right=text('div','','row-right');right.append(badge(item.state),peerAvatar(item.peer_id),button(isTerminal(item)?'Inspect':'Review exact item','button secondary row-action',()=>openReview(item)));
  const run=state.workflow?.runs.find(run=>run.item_id===item.id);
  if(run){main.append(text('p',workflowSummary(run),'workflow-note'));right.append(button('Inspect synthetic run','button secondary workflow-action',()=>openWorkflow(item,run.run_id)));}
  const symbol=text('span',item.kind==='task'?'◌':'▤','item-icon '+item.kind+' '+statusClass(item.state));symbol.setAttribute('aria-hidden','true');
  row.append(symbol,main,right);return row;
}
function renderItems() {
  const items=projectItems(state,currentView,currentFilter,searchQuery);
  if(searchQuery)$('list-description').textContent=`${items.length} ${items.length===1?'result':'results'} for “${searchQuery}”`;
  else $('list-description').textContent=`${items.length} ${currentView==='artifacts'?'artifacts':currentView==='tasks'?'tasks':'proposals'} · ${viewCopy[currentView][5]}`;
  if(!items.length){empty('⌕',searchQuery?'No matching work.':currentFilter!=='all'?'No matching proposals.':currentView==='artifacts'?'Your artifacts will live here.':'A little room for what comes next.',searchQuery?'Try a title, task reference, assistant or status.':'Create a proposal, or sync the exchange to inspect incoming work.',searchQuery?{label:'Clear search',run:clearSearch}:undefined);return;}
  if(currentLayout==='board'){
    const board=text('div','','board-columns');
    for(const group of boardGroups(items)){
      const column=text('section','','board-column '+group.id),heading=text('div','','board-heading');heading.append(text('h3',group.label),text('span',group.items.length,'group-count'));
      const rows=text('div','','board-items');for(const item of group.items)rows.append(itemRow(item));
      if(!group.items.length)rows.append(text('p','No items','board-empty'));
      column.append(heading,rows);board.append(column);
    }
    $('item-list').append(board);
  }else for(const item of items)$('item-list').append(itemRow(item));
}
function overviewItem(item) {
  const row=button('','overview-row',()=>openReview(item));
  row.append(text('span',item.kind==='artifact'?'▤':'◌','overview-item-icon '+statusClass(item.state)));
  const main=text('span','','overview-row-main');main.append(text('strong',plain(item.title,'Untitled proposal')),text('span',peerName(item.peer_id)+' · '+plain(item.task_id).slice(0,28),'overview-row-meta'));
  row.append(main,badge(item.state),text('span','↗','overview-arrow'));return row;
}
function renderOverview(totals) {
  for(const id of ['overview-stats','overview-attention','overview-work','overview-network','overview-events'])$(id).replaceChildren();
  const stats=[['Needs your review',totals.pending,'Incoming proposals','inbox','pending'],['Accepted tasks',totals.acceptedTasks,'Work agreed by its recipient','tasks','accepted'],['Artifacts',totals.artifacts,'Drafts and received work','artifacts','all'],['Trusted assistants',totals.peers,'Individually enrolled','peers','all']];
  for(const [label,value,note,view,filter] of stats){const tile=button('','overview-metric',()=>navigate(view,{filter}));tile.append(text('span',label,'metric-label'),text('strong',value,'metric-value'),text('span',note,'metric-note'));$('overview-stats').append(tile);}
  const attention=attentionItems(state).slice(0,3);
  if(attention.length)for(const item of attention)$('overview-attention').append(overviewItem(item));
  else empty('✓','You’re all caught up.','New requests will appear here after you sync the exchange.',undefined,$('overview-attention'));
  const work=activeTasks(state).slice(0,5);
  if(work.length)for(const item of work)$('overview-work').append(overviewItem(item));
  else empty('◌','Room for your next idea.','Prepare a task to start a new piece of work.',{label:'New proposal',run:prepareCompose},$('overview-work'));
  const people=[{...state.identity,local:true},...state.peers.slice(0,3)];
  for(const peer of people){
    const row=button('','overview-person',()=>navigate('peers'));row.append(text('span',plain(peer.agent_id,'?').slice(0,1).toUpperCase(),'peer-avatar '+(peer.local?'local':'')));
    const main=text('span','','overview-person-main');main.append(text('strong',plain(peer.agent_id,'Assistant')),text('span',plain(peer.owner_id,'Owner')));
    row.append(main,text('span',peer.local?'Your assistant':isPeerActive(peer)?'Enrolled':peer.state==='revoked'?'Revoked':'Status unavailable','person-status'));$('overview-network').append(row);
  }
  const events=state.history.slice(-4).reverse();
  for(const event of events){const row=text('div','','overview-event');row.append(text('span','','event-dot'));const main=text('div','','event-main');main.append(text('strong',eventLabel(event)),text('time',eventWhen(event)));row.append(main);$('overview-events').append(row);}
  if(!events.length)$('overview-events').append(text('p','Your saved activity will appear here.','overview-empty-note'));
}
function renderPeers() {
  const own=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',plain(state.identity.agent_id,'Your assistant'),'item-title'),text('div',plain(state.identity.owner_id)+' · Your assistant','item-meta'),text('p',state.identity.fingerprint,'peer-fingerprint'));
  const identity=state.identity.public||Object.fromEntries(Object.entries(state.identity).filter(([key])=>['owner_id','agent_id','signing_key','exchange_key','version'].includes(key)));
  const right=text('div','','row-right');right.append(text('span','Your assistant','badge local'),button('View public identity','button secondary',()=>showPublicIdentity(identity,state.identity.fingerprint)));
  own.append(text('div',plain(state.identity.agent_id,'?').slice(0,1).toUpperCase(),'peer-avatar local'),main,right);
  if(matchesQuery([state.identity.agent_id,state.identity.owner_id,'your assistant'],searchQuery))$('item-list').append(own);
  const peers=state.peers.filter(peer=>matchesQuery([peer.agent_id,peer.owner_id,peer.peer_id,peer.fingerprint,peer.state],searchQuery));
  if(!state.peers.length&&!searchQuery){empty('⊞','Good work is connected.','Exchange public identities with another owner and verify their full fingerprint.',{label:'Enrol a peer',run:openPeerDialog});return;}
  for(const peer of peers) {
    const row=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',plain(peer.agent_id,'Assistant'),'item-title'),text('div',plain(peer.owner_id,'Owner'),'item-meta'),text('p',peer.fingerprint,'peer-fingerprint'));
    const right=text('div','','row-right');right.append(text('span',isPeerActive(peer)?'Enrolled':peer.state==='revoked'?'Revoked':'Status unavailable',isPeerActive(peer)?'badge accepted':'badge revoked'));
    row.append(peerAvatar(peer.peer_id),main,right);$('item-list').append(row);
  }
  if(!$('item-list').childElementCount)empty('⌕','No matching assistants.','Try an assistant name, owner or fingerprint.',{label:'Clear search',run:clearSearch});
}

function showPublicIdentity(identity,fingerprint) {
  selected=null;selectedWorkflow=null;selectedTransfer=null;$('review-title').textContent='Your public identity';$('review-eyebrow').textContent='SHARE AND VERIFY';$('review-state').replaceChildren();$('review-details').replaceChildren();detail($('review-details'),'Fingerprint',fingerprint);
  $('review-content').textContent=JSON.stringify(identity,null,2);$('review-commitments').replaceChildren();$('review-message').textContent='';$('review-scope').textContent='Only public identity fields are shown. The other owner must verify the full fingerprint before enrolment.';$('review-actions').replaceChildren(button('Close','button secondary',()=> $('review-dialog').close()));openDialog('review-dialog');
}
function eventLabel(item){const label=plain(item.label)||plain(item.event).replaceAll('_',' ')||'Saved event';return label.charAt(0).toUpperCase()+label.slice(1);}
function eventWhen(item){const when=finiteDate(item.created_at??item.time);return when===null?(Number.isSafeInteger(item.sequence)&&item.sequence>0?`Event #${item.sequence}`:'Event recorded'):datetime(when);}
function renderHistory() {
  const events=state.history.filter(item=>matchesQuery([eventLabel(item),item.item_id,item.id],searchQuery)).slice().reverse();
  if(!events.length){empty('≋',searchQuery?'No matching activity.':'A clear record from the start.',searchQuery?'Try an event name or proposal identifier.':'Saved decisions and exchange events will appear here. An uncertain outcome stays uncertain until saved evidence resolves it.');return;}
  for(const item of events) {
    const row=text('article','','item-row activity-row');const main=text('div','','item-main');main.append(text('h3',eventLabel(item),'item-title'));
    const id=plain(item.item_id)||plain(item.id);if(id)main.append(text('p',id,'peer-fingerprint'));
    row.append(text('span','','event-dot'),main,text('time',eventWhen(item),'activity-time'));$('item-list').append(row);
  }
}
async function openReview(item) {
  if(busy||uncertainty.pending())return;
  const epoch=generation;const release=operations.acquire();
  try {
    const review=validateReview(await request(`/api/items/${encodeURIComponent(item.id)}/review`),item);
    if(epoch!==generation)return;
    selected={item:{...item},review};selectedWorkflow=null;selectedTransfer=null;$('review-title').textContent=plain(item.title,'Exact proposal');$('review-eyebrow').textContent=item.direction==='outgoing'?'OUTGOING RELEASE REVIEW':'RECIPIENT DECISION';$('review-state').replaceChildren(badge(item.state));
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
  finally { release(); }
}
async function decideSelected(action) {
  if(!selected||busy||uncertainty.pending()||!selected.review.allowed_actions.includes(action))return;
  const snapshot=selected;const suffix=['accept','reject'].includes(action)?'decision':action;
  const body={review_digest:snapshot.review.review_digest};if(suffix==='decision')body.decision=action;
  await performWrite(`/api/items/${encodeURIComponent(snapshot.item.id)}/${suffix}`,body,{target:'review-message',onSuccess:()=>{selected=null;$('review-dialog').close();notice(action==='release'?'Exact proposal released. Choose a configured transfer for HTTPS delivery, or Sync exchange for local loopback only.':action==='cancel'?'Proposal withdrawn locally. In-flight bytes cannot be recalled; recipient handling remains separate.':'Your decision has been saved.',true);}});
}
async function prepareWorkflow(item) {
  if(!selected||selected.item.id!==item.id||!canPrepareWorkflow(state,item,selected.review))return;
  await performWrite(`/api/items/${encodeURIComponent(item.id)}/workflow`,{}, {target:'review-message',onSuccess:()=>{selected=null;$('review-dialog').close();notice('Synthetic run prepared. Inspect its exact request and approve it separately. Nothing has run.',true);}});
}
function workflowDetailHeader(item,run,heading) {
  selected=null;selectedTransfer=null;$('review-title').textContent=heading;$('review-eyebrow').textContent='LOCAL SYNTHETIC REHEARSAL';$('review-state').replaceChildren(text('span',workflowStateLabel(run.state),'badge '+statusClass(run.state)));
  $('review-details').replaceChildren();detail($('review-details'),'Task',plain(item.title,item.task_id));detail($('review-details'),'Return recipient',peerName(item.peer_id));detail($('review-details'),'Provider calls','None. Fixed local fixture only.');
  $('review-commitments').replaceChildren();detail($('review-commitments'),'Run ID',run.run_id);detail($('review-commitments'),'Task proposal',item.id);detail($('review-commitments'),'Context',item.context);detail($('review-commitments'),'Provider review',run.review_digest);
  $('review-message').textContent='';$('review-actions').replaceChildren();
}
async function openWorkflow(item,runId) {
  if(busy||uncertainty.pending())return;
  const epoch=generation;const release=operations.acquire();
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
  finally { release(); }
}
async function workflowAction(action) {
  if(!selectedWorkflow||busy||uncertainty.pending()||!selectedWorkflow.run.allowed_actions.includes(action)||!workflowEnabled(state))return;
  const snapshot=selectedWorkflow,body={};
  if(['approve','run','stage'].includes(action))body.review_digest=snapshot.review.review_digest;
  if(action==='approve')body.expires=Math.min(Math.floor(Date.now()/1000)+300,Math.floor(snapshot.item.expires));
  await performWrite(`/api/workflows/${encodeURIComponent(snapshot.run.run_id)}/${action}`,body,{target:'review-message',onSuccess:()=>{
    selectedWorkflow=null;$('review-dialog').close();
    if(action==='stage'){currentView='outbox';currentFilter='all';searchQuery='';$('search-input').value='';history.replaceState(null,'','#outbox');render();}
    const messages={approve:'Exact synthetic request approved. Inspect the run to perform the separate one-shot fixture action.',run:'Original synthetic result retained. Inspect it before staging an artifact.',stage:'Exact artifact staged as a draft. Review and release it separately from your outbox.',cancel:'Synthetic run cancelled locally. No remote cancellation or recall is claimed.'};notice(messages[action],true);
  }});
}
function openDialog(id) { if(busy||uncertainty.pending())return;$(id).showModal(); }
function newContext(){return Array.from(crypto.getRandomValues(new Uint8Array(32)),byte=>byte.toString(16).padStart(2,'0')).join('');}
function prepareCompose(){
  if(busy||uncertainty.pending())return;
  if(!state.peers.some(isPeerActive)){navigate('peers');notice('Enrol an active trusted peer before preparing a proposal.');return;}
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
  event.preventDefault();if(busy)return;const release=operations.acquire();$('login-message').textContent='';const password=$('password').value;$('password').value='';let epoch=generation;
  try {
    const result=await request('/api/session',{method:'POST',body:{password,...($('account').value.trim()?{account:$('account').value.trim()}:{})},sessionToken:null});
    if(epoch!==generation)return;
    if(typeof result.token!=='string'||result.token.length<16||!result.identity)throw new Error('Invalid login response');
    token=result.token;epoch=++generation;await refresh();if(epoch!==generation||!token)return;$('login-screen').hidden=true;$('workspace').hidden=false;$('main').focus();
  } catch(error) { if(epoch===generation)resetSession(error.unauthorised?'The password was not accepted.':error instanceof RequestFailure?error.message:'The session could not be verified.'); }
  finally {release();}
});
async function logout(){
  if(busy)return;const original=token;resetSession();const epoch=generation;
  try {await request('/api/session',{method:'DELETE',body:{},sessionToken:original});}catch{if(epoch===generation)$('login-message').textContent='Locked here. Server sign-out could not be confirmed; the session will expire.';}
}
$('logout').addEventListener('click',logout);$('mobile-logout').addEventListener('click',logout);
$('refresh').addEventListener('click',async()=>{if(busy)return;const epoch=generation;const release=operations.acquire();try{await refresh({clearNotice:true});if(epoch!==generation)return;selected=null;selectedWorkflow=null;selectedTransfer=null;$('review-dialog').close();}catch(error){if(epoch===generation)handleFailure(error);}finally{release();}});
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();setNavigation(false);(token?$('main'):$('password')).focus();});
$('sync').addEventListener('click',()=>performWrite('/api/exchange',{}, {onSuccess:()=>notice('Exchange checked. Review new items and saved delivery outcomes below.',true)}));
$('new-proposal').addEventListener('click',prepareCompose);$('add-peer').addEventListener('click',openPeerDialog);
document.querySelectorAll('[data-view]').forEach(node=>node.addEventListener('click',()=>navigate(node.dataset.view)));
document.querySelectorAll('[data-filter]').forEach(node=>node.addEventListener('click',()=>{if(busy)return;currentFilter=node.dataset.filter;render();}));
document.querySelectorAll('.close-dialog').forEach(node=>node.addEventListener('click',()=>{if(busy)return;node.closest('dialog').close();selected=null;selectedWorkflow=null;selectedTransfer=null;}));
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();else{selected=null;selectedWorkflow=null;selectedTransfer=null;}}));
$('proposal-kind').addEventListener('change',configureKind);$('proposal-parent').addEventListener('change',selectParent);
$('compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending())return;const form=event.currentTarget;const fields=Object.fromEntries(new FormData(form));fields.peer_id=form.elements.peer_id.value;
  if(fields.kind==='artifact')fields.parent_expires=state.items.find(item=>item.id===fields.parent_id)?.expires;
  try {await performWrite('/api/proposals',proposalBody(fields),{target:'compose-message',onSuccess:()=>{$('compose-dialog').close();currentView='outbox';currentFilter='all';searchQuery='';$('search-input').value='';history.replaceState(null,'','#outbox');render();notice('Proposal prepared. Open it to review the exact content before release.',true);}});}catch(error){$('compose-message').textContent=error.message;}
});
$('peer-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending())return;
  try {const body=peerBody(Object.fromEntries(new FormData(event.currentTarget)),state.transfers?.connections||[]);await performWrite('/api/peers',body,{target:'peer-message',onSuccess:()=>{$('peer-dialog').close();$('peer-form').reset();notice('Exact peer enrolled. Each proposal still needs separate approval.',true);}});}catch(error){$('peer-message').textContent=error.message;}
});
document.addEventListener('visibilitychange',()=>{if(document.hidden){$('password').value='';}});

function clearSearch(){searchQuery='';$('search-input').value='';render();$('search-input').focus();}
$('search-input').addEventListener('input',event=>{searchQuery=event.target.value.trim().slice(0,200);render();});
$('search-clear').addEventListener('click',clearSearch);
document.querySelectorAll('[data-layout]').forEach(node=>node.addEventListener('click',()=>{if(!['list','board'].includes(node.dataset.layout))return;currentLayout=node.dataset.layout;render();}));
$('menu-toggle').addEventListener('click',()=>setNavigation(!document.body.classList.contains('sidebar-open'),{restoreFocus:true}));
$('sidebar-scrim')?.addEventListener('click',()=>setNavigation(false,{restoreFocus:true}));
function restoreLocation(){
  currentView=viewFromHash(location.hash);currentFilter='all';searchQuery='';$('search-input').value='';
  setNavigation(false);render();
}
window.addEventListener('popstate',restoreLocation);
window.addEventListener('hashchange',restoreLocation);
window.addEventListener('focus',()=>{if(token&&['conversations','host-drafts'].includes(currentView)&&!document.hidden&&!busy)render();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&token&&['conversations','host-drafts'].includes(currentView)&&!busy)render();});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){setNavigation(false,{restoreFocus:true});return;}
  if(event.key==='Tab'&&document.body.classList.contains('sidebar-open')){
    const focusable=[...sidebar.querySelectorAll('a[href],button:not([disabled]),[tabindex="0"]'),$('sidebar-scrim'),$('menu-toggle')].filter(node=>node&&node.getClientRects().length);
    const first=focusable[0],last=focusable.at(-1);
    if(!focusable.includes(document.activeElement)||(event.shiftKey&&document.activeElement===first)){event.preventDefault();(event.shiftKey?last:first)?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    return;
  }
  if(!token||busy||document.body.classList.contains('sidebar-open')||document.querySelector('dialog[open]'))return;
  const editing=event.target.closest('input,textarea,select,[contenteditable="true"]');
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('search-input').focus();$('search-input').select();}
  else if(!editing&&!event.metaKey&&!event.ctrlKey&&!event.altKey&&event.key.toLowerCase()==='n'){event.preventDefault();prepareCompose();}
});

setNavigation(false);

function openPeerDialog(){
  if(busy||uncertainty.pending())return;
  $('peer-form').reset();$('peer-message').textContent='';
  $('peer-connection').replaceChildren();const local=text('option','Local loopback pilot');local.value='';$('peer-connection').append(local);
  for(const c of state.transfers?.connections||[]){const option=text('option',c.label);option.value=c.id;$('peer-connection').append(option);}
  $('peer-transport-field').hidden=!(state.transfers?.connections.length);configurePeerConnection();openDialog('peer-dialog');
}
function configurePeerConnection(){
  const c=state?.transfers?.connections.find(c=>c.id===$('peer-connection').value);
  $('peer-endpoint-field').hidden=Boolean(c);$('peer-form').elements.endpoint.required=!c;
  $('peer-connection-note').hidden=!c;$('peer-connection-note').textContent=c?`Host-configured destination: ${c.destination}. Expected fingerprint: ${c.peer_fingerprint}. Independently compare it with the owner; this is not proof of their identity.`:'';
}
$('peer-connection').addEventListener('change',configurePeerConnection);
function renderTransfers(){
  const transfers=state.transfers;
  if(!transfers){empty('⇄','Transfer controls unavailable.','This host does not expose the transfer workspace.');return;}
  const intro=text('div','','transfer-intro');intro.append(text('p','Sending, importing a signed receipt, accepting a proposal and approving execution are separate decisions. Nothing here starts work.','scope-note'));
  if(!transfers.enabled)intro.append(text('p','HTTPS delivery is not configured. A host administrator must supply private connection configuration and restart the service. No network call is made by opening this page.'));
  const d=transfers.dispatch;
  if(d)intro.append(text('p',d.state==='in_flight'?'One transfer is in flight. You can inspect, withdraw or sign out; already handed-off bytes cannot be recalled. Refresh saved state to inspect its outcome.':d.transport_acknowledged?'The mailbox returned an untrusted quarantine acknowledgement. Delivery remains uncertain until a signed receipt is imported.':'The last network outcome is unknown. Inspect the immutable attempts before choosing a retry.','scope-note'));
  $('item-list').append(intro);
  if(transfers.connections.length)$('item-list').append(text('h3','Configured connections','transfer-heading'));
  for(const c of transfers.connections){const row=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',c.label,'item-title'),text('p',c.destination,'peer-fingerprint'),text('p',c.peer_fingerprint,'peer-fingerprint'),text('p',state.peers.some(p=>p.peer_id===c.peer_fingerprint&&isPeerActive(p))?'Peer is enrolled. This destination is host configuration, not proof of owner identity.':'Peer is not enrolled. Independently verify and enrol it under Assistants.','workflow-note'));row.append(text('div','⊞','item-icon'),main);$('item-list').append(row);}
  $('item-list').append(text('h3','Retained outbox','transfer-heading'));
  if(!transfers.outbox.length)$('item-list').append(text('p','No released packets. Creating a draft does not queue it for delivery.','transfer-intro'));
  for(const item of transfers.outbox)renderTransferRow('outbox',item.message_id,item.peer,`${item.state==='received'?'Signed receipt observed':item.state==='cancelled'?'Locally stopped':item.state==='uncertain'?'Delivery uncertain':'Queued'} · ${item.attempts} of 5 transport attempts`,item.message_id);
  $('item-list').append(text('h3','Original cached receipts','transfer-heading'));
  if(!transfers.receipts.length)$('item-list').append(text('p','No cached receipts. Importing does not automatically send a receipt.','transfer-intro'));
  for(const item of transfers.receipts)renderTransferRow('receipt',item.incoming_id,item.peer,'Transport receipt only. Not recipient acceptance.',item.message_id);
  $('item-list').append(text('h3','Quarantine: choose one exact file','transfer-heading'));
  if(!transfers.quarantine.length)$('item-list').append(text('p','No digest-named entries available. Quarantine is untrusted and is never automatically imported.','transfer-intro'));
  else {
    const form=text('form','','transfer-import');const peerLabel=text('label','Expected sender connection');const peerSelect=text('select','');peerSelect.required=true;const blank=text('option','Choose the independently verified sender');blank.value='';peerSelect.append(blank);for(const c of transfers.connections){const option=text('option',c.label);option.value=c.id;peerSelect.append(option);}peerLabel.append(peerSelect);
    const fileLabel=text('label','Exact quarantine file digest');const fileSelect=text('select','');fileSelect.required=true;for(const id of transfers.quarantine){const option=text('option',id);option.value=id;fileSelect.append(option);}fileLabel.append(fileSelect);
    const inspect=button('Inspect selected import','button secondary',()=>{if(!form.reportValidity())return;const connection=transfers.connections.find(c=>c.id===peerSelect.value);openTransfer({connection,kind:'quarantine',identifier:fileSelect.value});});form.append(peerLabel,fileLabel,inspect);form.addEventListener('submit',e=>e.preventDefault());$('item-list').append(form);
  }
}
function renderTransferRow(kind,identifier,peer,summary,messageId){
  const row=text('article','','item-row transfer-row');const main=text('div','','item-main');main.append(text('h3',kind==='receipt'?'Return original receipt':peerName(peer),'item-title'),text('p',summary,'workflow-note'),text('p',messageId,'peer-fingerprint'));
  const actions=text('div','','row-right');for(const c of state.transfers.connections.filter(c=>c.peer_fingerprint===peer))actions.append(button(`Inspect via ${c.label}`,'button secondary',()=>openTransfer({connection:c,kind,identifier})));
  if(!actions.children.length)actions.append(text('span','No configured connection','workflow-note'));row.append(text('div',kind==='receipt'?'↩':'↗','item-icon'),main,actions);$('item-list').append(row);
}
async function openTransfer(selection){
  if(busy||uncertainty.pending())return;const epoch=generation;const release=operations.acquire();
  try{
    const review=validateTransferReview(await request(transferPath(selection)),selection);if(epoch!==generation)return;
    selected=null;selectedWorkflow=null;selectedTransfer={...selection,review};
    $('review-title').textContent=selection.kind==='quarantine'?'Inspect selected import':'Inspect exact transfer';$('review-eyebrow').textContent='TRANSPORT ONLY';$('review-state').replaceChildren(text('span',selection.kind==='quarantine'?'Untrusted quarantine':review.outbox?.state==='received'?'Signed receipt observed':'No owner acceptance implied','badge uncertain'));
    $('review-details').replaceChildren();detail($('review-details'),'Connection',review.connection.label);detail($('review-details'),'Destination',review.connection.destination);detail($('review-details'),selection.kind==='quarantine'?'Expected sender':'Exact recipient',review.connection.peer_fingerprint);detail($('review-details'),'Packet type',review.packet_kind);detail($('review-details'),'Original expiry',datetime(review.expires));
    if(review.outbox){detail($('review-details'),'Current outbox',review.outbox.state);detail($('review-details'),'Total attempts',String(review.outbox.attempts));}
    $('review-content').textContent=selection.kind==='quarantine'?'This file is untrusted. Import verifies its original signature and current peer/source gates. It does not accept a proposal, start work or send a receipt.':'Only the original retained encrypted packet can be sent. A fixed mailbox acknowledgement proves neither signed receipt nor owner acceptance.';
    $('review-commitments').replaceChildren();detail($('review-commitments'),'Message ID',review.message_id);detail($('review-commitments'),'Packet digest',review.packet_digest);detail($('review-commitments'),'Review digest',review.review_digest);if(selection.kind==='quarantine')detail($('review-commitments'),'Selected file digest',selection.identifier);
    for(const a of review.attempts){detail($('review-commitments'),`Attempt ${a.sequence}`,`Uncertain · ${a.destination}`);detail($('review-commitments'),'Original file digest',a.file_digest);}
    if(!review.attempts.length)detail($('review-commitments'),'HTTPS attempts','None recorded');
    $('review-scope').textContent='Attempts are immutable history. Cancellation or sign-out after the final send gate cannot recall in-flight bytes. A retry consumes another bounded attempt without renewing permission. Refresh explicitly to inspect saved state.';
    $('review-message').textContent='';$('review-actions').replaceChildren();
    const action=review.allowed_actions[0];
    if(action&&(action==='import'||state.transfers.dispatch?.state!=='in_flight')){
      const label=text('label','','check-label transfer-confirm');const check=text('input','');check.type='checkbox';check.id='transfer-confirm';label.append(check,text('span',action==='import'?'Import only this selected file from this expected sender.':'Send only this original packet to this exact destination. This does not approve work.'));$('review-actions').append(label);
      $('review-actions').append(button(action==='import'?'Import selected packet':action==='retry'?'Send one explicit retry':'Send original packet once','button primary',()=>transferAction(action)));
    }else $('review-message').textContent=state.transfers.dispatch?.state==='in_flight'?'Another transfer is in flight. No additional send will be queued.':'This packet is stopped, expired, already received or unavailable. Its history remains inspectable.';
    $('review-actions').append(button('Close','button secondary',()=>{$('review-dialog').close();selectedTransfer=null;}));$('review-dialog').showModal();
  }catch(error){if(epoch===generation)handleFailure(error);}finally{release();}
}
async function transferAction(action){
  if(!selectedTransfer||busy||uncertainty.pending()||!selectedTransfer.review.allowed_actions.includes(action))return;
  if(!$('transfer-confirm')?.checked){$('review-message').textContent='Confirm the exact selected transfer before proceeding.';return;}
  const snapshot=selectedTransfer,body={review_digest:snapshot.review.review_digest};if(action!=='import')body.retry=action==='retry';
  await performWrite(transferPath(snapshot)+(action==='import'?'/import':'/send'),body,{target:'review-message',onSuccess:()=>{selectedTransfer=null;$('review-dialog').close();notice(action==='import'?'Selected packet imported. Review any proposal separately; a cached receipt is not sent automatically.':'One transfer attempt started. Delivery remains uncertain. Refresh saved state to inspect it; no automatic retry will occur.',true);}});
}
