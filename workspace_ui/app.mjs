import {operationGate,restoreWhenIdle,inspectionLatch,inspectSavedState,requestIsMutation} from './operations.mjs';
import {createConversations,inspectMessageOutcome,validateCatalogue} from './conversations.mjs';
import {money,amountOf,toMicro,ownerCurrency} from './missions.mjs';
import {homeGreeting,isEvening,budgetSummary,doneToday,doneLine,eveningSummary,shortKey} from './home.mjs';
import {botFace,ownerPair} from './bots.mjs';
import {SECTIONS,WORK_VIEWS,WORK_FILTERS,sectionOf,tabOf,receiptsOf,shortDigest,createInspect} from './depth.mjs';
import {createHostDrafts,validateDraftQueue} from './host_drafts.mjs';
import {createApprovals,validateListing} from './approvals.mjs';
import {homeQueue,CARD,askerOf,moreLine,closingLine,uncheckedParts} from './queue.mjs';
import {decisionQuestion,decisionRows,needsHold} from './decide.mjs';
import {holdButton} from './hold.mjs';
import {STEPS,teamsOf,teamCounts,teamLine,stepShare,planParts,partOf,partLead,resultsFor} from './team.mjs';
import {validateTransferReview,transferPath} from './transfers.mjs';
import {inviteFromText,joinFromHash,relayEnabled,validateRelay,linkLabel,expiresIn,joinProblem,syncLine,syncChanged,joinerCards} from './invites.mjs';
import {qrMatrix,qrPath} from './qr.mjs';
import {VIEWS,viewFromHash,matchesQuery,projectItems,boardGroups,workspaceTotals,activeTasks,attentionItems} from './projections.mjs';
import {plain,finiteDate,stateLabel,statusClass,isTerminal,isPeerActive,validateState,validateReview,proposalBody,peerBody,workflowEnabled,workflowStateLabel,validateWorkflowStatus,validateWorkflowReview,validateWorkflowResult,workflowSummary,canPrepareWorkflow} from './model.mjs';

// The product name is a placeholder while naming is decided. Change it here only.
export const PRODUCT={short:'Parlu',full:'Parlu'};
for(const node of document.querySelectorAll('[data-product]'))node.textContent=PRODUCT[node.dataset.product]??PRODUCT.short;
for(const node of document.querySelectorAll('[data-product-label]'))node.setAttribute('aria-label',node.dataset.productLabel.replace('{product}',PRODUCT.short));
document.title=PRODUCT.short+' · Your assistant workspace';
// The entrance shows four example assistants as their bot faces.
for(const [index,node] of [...document.querySelectorAll('.entrance-avatars .peer-avatar')].entries()){node.textContent='';node.append(botFace(['Beacon','Atlas','Mira','Orbit'][index]??'Parlu'));}

const $ = id => document.getElementById(id);
const mobileNavigation=matchMedia('(max-width:700px)'), besidePage=matchMedia('(min-width:1180px)'), sidebar=document.querySelector('.sidebar');
function setNavigation(open,{restoreFocus=false}={}){
  const wasOpen=document.body.classList.contains('sidebar-open');open=Boolean(open&&mobileNavigation.matches);if(!open)setOwnerMenu(false);
  document.body.classList.toggle('sidebar-open',open);sidebar.inert=mobileNavigation.matches&&!open;
  sidebar.setAttribute('aria-hidden',String(sidebar.inert));$('menu-toggle').setAttribute('aria-expanded',String(open));$('menu-toggle').setAttribute('aria-label',open?'Close navigation':'Open navigation');
  if(open&&!wasOpen){if(!everythingFolded){$('everything-toggle').setAttribute('aria-expanded','true');$('everything-list').hidden=false;}sidebar.querySelector('[data-view]')?.focus();}
  else if(wasOpen&&!open){if(restoreFocus&&mobileNavigation.matches)$('menu-toggle').focus();else if(sidebar.contains(document.activeElement))$('main').focus();}
}
mobileNavigation.addEventListener('change',()=>setNavigation(false));
// The relay's invite page hands an invite over after "#join=". Read it once, then take it out
// of the address bar and the history, so the secret part does not linger.
let pendingJoin=joinFromHash(location.hash);if(pendingJoin)history.replaceState(null,'',location.pathname+'#overview');
let token = null, generation = 0, busy = false, currentView = viewFromHash(location.hash), currentFilter = 'all', currentLayout = 'list', searchQuery = '';
let state = null, selected = null, selectedWorkflow = null, selectedTransfer = null;
const uncertainty=inspectionLatch();
const sectionLede={recents:'Everything that happened, every receipt and all work.',assistants:'The people you work with, beside their assistants.',money:'What your assistants may spend, and what they have.'};
const viewCopy = {
  overview:['Home','HOME','Your workspace, in motion.','People, assistants and the work you share.','Workspace results','Search your saved work'],
  inbox:['Inbox','INCOMING WORK','Inbox','Review the requests and artifacts shared with your assistant.','All incoming','Every proposal has its own decision'],
  tasks:['Work','SHARED WORK','All work','Follow every task from its first proposal to the exact result.','All tasks','Incoming and outgoing task requests'],
  artifacts:['Artifacts','SHARED ARTIFACTS','Artifacts','Find the exact artifacts prepared and shared across your network.','All artifacts','Drafts, received artifacts and saved decisions'],
  outbox:['Outbox','OUTGOING WORK','Outbox','Prepare the exact content. Review it before you release it.','All outgoing','Prepared and released proposals'],
  peers:['Assistants','YOUR NETWORK','Your assistants','A network of people and the assistants they choose to trust.','Assistant network','Enrolment is separate from approval'],
  approvals:['Approvals','WAITING FOR YOU','Your decisions, in one place.','Messages, questions and shared drafts your assistant has brought to you.','Approvals','Nothing moves until you choose'],
  conversations:['Conversations','SCOPED LOCAL HISTORY','Room for a conversation.','Persistent conversations with explicit membership and exact history consent.','Your conversations','Local coordinating host only'],
  transfers:['Transfers','EXPLICIT DELIVERY','Every handoff, deliberate.','Review an exact packet before each send or import.','Connections & transfers','No automatic delivery or retries'],
  'host-drafts':['Host drafts','INERT LOCAL DRAFTS','Inspect before anything moves.','Review exact drafts from a configured supported host.','Host task drafts','Inspection and dismissal only'],
  money:['Money','MONEY','Money','What your assistants may spend, and what they have.','Money','Budgets and missions'],
  team:['Team missions','MONEY','Team missions','One piece of work, split across several people’s assistants.','Team missions','Every part is reviewed on its own'],
  receipts:['Receipts','RECORDS','Recents','Everything that happened, every receipt and all work.','Receipts','Signed decisions and result hashes'],
  activity:['Activity','WORKSPACE ACTIVITY','Activity','The saved history of work moving through your workspace.','Recent activity','Recorded events from this assistant']
};
class RequestFailure extends Error { constructor(message,{unknown=false,unauthorised=false}={}) { super(message); this.unknown=unknown;this.unauthorised=unauthorised; } }
function text(tag,value,className) { const node=document.createElement(tag);node.textContent=String(value??'');if(className)node.className=className;return node; }
function button(label,className,handler) { const node=text('button',label,className);node.type='button';node.addEventListener('click',handler);return node; }
function detail(list,label,value) { list.append(text('dt',label),text('dd',plain(value)||'Unavailable')); }
function badge(value) { return text('span',stateLabel(value),'badge '+statusClass(value)); }
function symbolIcon(symbol,className) {
  const wrapper=text('span','',className);wrapper.setAttribute('aria-hidden','true');
  const icon=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');
  icon.setAttribute('class','icon');use.setAttribute('href','#'+symbol);icon.append(use);wrapper.append(icon);return wrapper;
}
function workIcon(kind,className,state) {
  const symbol=kind==='artifact'?'i-artifacts':state==='accepted'?'i-tasks':['rejected','revoked','cancelled','expired'].includes(state)?'i-task-closed':'i-task-open';
  return symbolIcon(symbol,className);
}
function nameAvatar(name,className='peer-avatar') {
  const label=plain(name,'?'),avatar=text('span',label.slice(0,1).toUpperCase(),className);
  let hash=0;for(const character of label.toLowerCase())hash=(hash*31+character.codePointAt(0))>>>0;
  avatar.dataset.tone=['indigo','amber','teal','rose'][hash%4];avatar.dataset.kind='assistant';avatar.setAttribute('aria-hidden','true');
  avatar.dataset.initial=avatar.textContent;avatar.textContent='';avatar.append(botFace(label));return avatar;
}
function datetime(value) { const time=finiteDate(value); return time===null?'Time not supplied':new Date(time*1000).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); }
function peerName(peerId) { const peer=state?.peers.find(peer=>peer.peer_id===peerId); return peer ? `${plain(peer.agent_id,'Assistant')} · ${plain(peer.owner_id,'Owner')}` : plain(peerId,'Unknown peer'); }
function identityText(identity) { if(typeof identity==='string')return identity;return `${plain(identity?.agent_id,'Assistant')} · ${plain(identity?.owner_id,'Owner')}`; }
function notice(message,success=false) { $('notice').textContent=message;$('notice').hidden=!message;$('notice').classList.toggle('success',success); }
function setBusy(value) { busy=value; document.querySelectorAll('button').forEach(node=>{ if(!node.classList.contains('close-dialog'))node.disabled=value; });if(!value)restorePanel(); }
const restorePanel=restoreWhenIdle({session:()=>generation,eligible:()=>Boolean(token&&state&&!busy&&!document.hidden&&['conversations','host-drafts','approvals'].includes(currentView)&&!$('item-list').childElementCount),restore:()=>render()});
const operations=operationGate(setBusy);
const conversations=createConversations({request,items:()=>state?.items??[],gate:operations.scope(),session:()=>generation,restore:()=>{if(token&&currentView==='conversations')render();},unknownFailure:message=>new RequestFailure(message,{unknown:true}),busy:()=>busy,uncertain:()=>uncertainty.pending(),failed:(error,operation)=>handleFailure(error,'notice','conversations',operation),active:()=>Boolean(token&&currentView==='conversations'&&!document.hidden)});
const approvals=createApprovals({request,gate:operations.scope(),restore:()=>{if(token&&currentView==='approvals')render();},session:()=>generation,busy:()=>busy,failed:error=>handleFailure(error,'notice','approvals'),active:()=>Boolean(token&&currentView==='approvals'&&!document.hidden)});
const hostDrafts=createHostDrafts({request,gate:operations.scope(),restore:()=>{if(token&&currentView==='host-drafts')render();},session:()=>generation,owner:()=>state?.identity.fingerprint,unknownFailure:message=>new RequestFailure(message,{unknown:true}),busy:()=>busy,uncertain:()=>uncertainty.pending(),failed:(error,operation)=>handleFailure(error,'notice','host-drafts',operation),active:()=>Boolean(token&&currentView==='host-drafts'&&!document.hidden)});
function resetSession(message='') {
  conversations.reset({sessionEnded:true});
  hostDrafts.reset({sessionEnded:true});approvals.reset({sessionEnded:true});
  generation++;token=null;state=null;selected=null;selectedWorkflow=null;selectedTransfer=null;uncertainty.reset();searchQuery='';
  $('search-input').value='';setNavigation(false);
  for(const id of ['home-when','home-paragraph','home-cards','done-line','money-panel','mission-rows','section-tabs','section-filters','menu-initials'])$(id)?.replaceChildren();$('done-line').hidden=true;$('home-count').hidden=true;inspect.reset();setOwnerMenu(false);panelFor=null;everythingFolded=false;setEverything(false);homeOffset=0;homeExtras={for:null,approvals:null,hostDrafts:null,conversations:null,failed:[]};currentTeam=null;teamTab='parts';$('team-view').replaceChildren();$('team-parts').replaceChildren();$('team-form').reset();storyOffset=0;if($('home-ask-input'))$('home-ask-input').value='';
  document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
  $('account').value='';$('workspace').hidden=true;$('login-screen').hidden=false;$('password').value='';
  $('item-list').replaceChildren();$('review-content').textContent='';$('review-details').replaceChildren();$('review-commitments').replaceChildren();$('review-actions').replaceChildren();
  for(const id of ['review-title','review-eyebrow','review-state','review-decide','review-scope','review-message','compose-message','peer-message','peer-connection-note','owner-name','agent-name','owner-avatar','connection-status','provider-status'])$(id).replaceChildren();
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
  const data=await inspectSavedState({latch:uncertainty,session:()=>generation,readState:async()=>{const value=validateState(await request('/api/state'));validateRelay(value.relay);return value;},inspectHost:()=>hostDrafts.inspectUncertain(),inspectConversation:operation=>inspectMessageOutcome({request,session:()=>generation,operation})});
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
    if(relayEnabled(state)&&OWNER_SENDS.test(path))queueMicrotask(()=>relaySync(true));
  } catch(error) { if(epoch===generation)handleFailure(returned&&!error.unauthorised?new RequestFailure('The operation returned, but its saved state could not be inspected. Refresh before acting again.',{unknown:true}):error,target); }
  finally { release(); }
}
// A decision made in Approvals, Conversations or From your apps changes what Home should show,
// so coming back to Home from one of them reads those lists again instead of reusing old cards.
const DECISION_VIEWS=['approvals','conversations','host-drafts'];
function leaveForHome(next){if(next==='overview'&&DECISION_VIEWS.includes(currentView))homeExtras={for:null,approvals:null,hostDrafts:null,conversations:null,failed:[]};}
function navigate(view,{filter='all'}={}) {
  setOwnerMenu(false);
  if(busy||!VIEWS.includes(view))return;
  leaveForHome(view);currentView=view;currentFilter=filter;searchQuery='';$('search-input').value='';
  if(location.hash!=='#'+view)history.pushState(null,'','#'+view);
  inspect.navigated();setNavigation(false);render();
}
function render() {
  if(!state)return;
  conversations.reset();
  hostDrafts.reset();approvals.reset();
  const owner=state.identity;$('owner-name').textContent=owner.owner_id;$('agent-name').textContent=`${plain(owner.agent_id,'Your assistant')} is ready`;$('owner-avatar').textContent=owner.owner_id.slice(0,2).toUpperCase();$('menu-initials').textContent=owner.owner_id.slice(0,2).toUpperCase();
  const totals=workspaceTotals(state);
  $('inbox-count').textContent=totals.pending;
  $('outbox-count').textContent=state.items.filter(item=>item.direction==='outgoing'&&!isTerminal(item)).length;
  $('pending-total').textContent=totals.pending;
  $('accepted-total').textContent=state.items.filter(item=>item.state==='accepted').length;$('peer-total').textContent=totals.peers;
  document.body.dataset.screen=currentView;const copy=viewCopy[currentView];['view-name','page-eyebrow','page-title','page-description','list-title','list-description'].forEach((id,index)=>$(id).textContent=copy[index]);
  const section=sectionOf(currentView);document.body.dataset.section=section;
  if(sectionLede[section]&&currentView!=='team'){$('page-title').textContent=SECTIONS[section].label;$('page-description').textContent=sectionLede[section];}
  const waiting=homeEntries().length;$('home-count').textContent=waiting;$('home-count').hidden=!waiting;
  renderSectionChrome(section);
  document.querySelectorAll('[data-view]').forEach(node=>{const here=node.dataset.view===currentView,lit=here||node.dataset.section===section;node.classList.toggle('active',lit);node.setAttribute('aria-current',here?'page':'false');});
  if(document.querySelector(`#everything-list [data-view="${currentView}"]`))setEverything(true);
  document.querySelectorAll('[data-filter]').forEach(node=>{node.classList.toggle('selected',node.dataset.filter===currentFilter);node.setAttribute('aria-pressed',String(node.dataset.filter===currentFilter));});
  document.querySelectorAll('[data-layout]').forEach(node=>{node.classList.toggle('selected',node.dataset.layout===currentLayout);node.setAttribute('aria-pressed',String(node.dataset.layout===currentLayout));});
  const overview=currentView==='overview'&&!searchQuery, moneyView=currentView==='money'&&!searchQuery, teamView=currentView==='team'&&!searchQuery, structural=['peers','activity','transfers','conversations','host-drafts','approvals','receipts'].includes(currentView);
  $('overview-panel').hidden=!overview;$('money-panel-view').hidden=!moneyView;$('team-view').hidden=!teamView;$('work-panel').hidden=overview||moneyView||teamView;
  $('summary').hidden=true;$('filters').hidden=structural||overview;$('view-toggle').hidden=structural||overview;$('add-peer').hidden=currentView!=='peers';
  $('search-clear').hidden=!searchQuery;
  $('search-input').disabled=['transfers','conversations','host-drafts','approvals'].includes(currentView);
  $('new-proposal').hidden=['conversations','host-drafts','approvals','team'].includes(currentView);
  $('search-input').setAttribute('placeholder',currentView==='transfers'?'Exact transfer selection below':currentView==='peers'?'Search assistants…':currentView==='activity'?'Search activity…':'Search work…');
  const provider=state.provider;
  $('provider-status').textContent=workflowEnabled(state)?'Synthetic workspace · Live calls disabled':provider?.live_enabled===true?'Provider activation reported by server':'Live provider calls disabled';
  $('item-list').replaceChildren();$('item-list').classList.toggle('board',currentLayout==='board'&&!structural);$('item-list').classList.toggle('peers-grid',currentView==='peers');
  if(overview)renderOverview(totals);else if(moneyView)renderMoney();else if(teamView)renderTeams();else if(currentView==='receipts')renderReceipts();else if(currentView==='peers')renderPeers();else if(currentView==='activity')renderHistory();else if(currentView==='transfers')renderTransfers();else if(currentView==='conversations')conversations.mount($('item-list'),state.conversations?.enabled===true);else if(currentView==='host-drafts')hostDrafts.mount($('item-list'),state.host_drafts?.enabled===true);else if(currentView==='approvals')approvals.mount($('item-list'),state.approvals?.enabled===true);else renderItems();
  const date=$('overview-date');if(date)date.textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
  // The Home count covers the whole queue wherever you are. The decision places read their own
  // lists, so Home reads them again when you come back from one.
  if(homeExtras.for!==state&&!DECISION_VIEWS.includes(currentView))loadHomeExtras();
  if(inspect.current&&panelAgain&&panelFor!==state)panelAgain();
}
// ===== Depth shell: section tabs, the Everything list and the Inspect panel =====
// A panel shows a saved record, so it is redrawn from the latest saved state after every refresh.
// `panelAgain` knows how to find that record again; it is dropped as soon as the panel closes.
let panelAgain=null,panelFor=null;
// On the phone the panel covers the page, so the page underneath takes no focus or presses.
function coverPage(){$('main').inert=!$('inspect').hidden&&mobileNavigation.matches;}
const inspect=createInspect({panel:$('inspect'),title:$('inspect-title'),sub:$('inspect-sub'),body:$('inspect-body'),pin:$('inspect-pin'),close:$('inspect-close'),back:$('inspect-back')},
  {onChange:open=>{if(!open)panelAgain=null;coverPage();}});
mobileNavigation.addEventListener('change',coverPage);
function showPanel(key,heading,subtitle,draw,again,refresh){panelAgain=again;panelFor=state;inspect.open(key,heading,subtitle,draw,{refresh:refresh===true});}
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('close',()=>queueMicrotask(()=>{if(inspect.current&&document.activeElement===document.body)$('inspect-title').focus({preventScroll:true});})));
function setEverything(open){$('everything-toggle').setAttribute('aria-expanded',String(open));$('everything-list').hidden=!open;}
// Folding the list yourself is remembered until you sign out, so the phone drawer does not reopen it.
let everythingFolded=false;
$('everything-toggle').addEventListener('click',()=>{const open=$('everything-list').hidden;everythingFolded=!open;setEverything(open);});
$('everything-count').textContent=document.querySelectorAll('#everything-list .nav-link').length;
function renderSectionChrome(section){
  const tabs=$('section-tabs'),filters=$('section-filters');tabs.replaceChildren();filters.replaceChildren();
  const config=SECTIONS[section],showTabs=Boolean(config.tabs)&&!searchQuery;tabs.hidden=!showTabs;
  if(showTabs)for(const [view,label] of config.tabs){const on=tabOf(currentView)===view;const tab=button(label,'section-tab'+(on?' selected':''),()=>navigate(view));tab.dataset.goto=view;tab.setAttribute('aria-current',on?'page':'false');tabs.append(tab);}
  const showFilters=WORK_VIEWS.includes(currentView)&&!searchQuery;filters.hidden=!showFilters;
  if(showFilters)for(const [view,label] of WORK_FILTERS){const on=currentView===view;const chip=button(label,'filter-chip'+(on?' selected':''),()=>navigate(view));chip.dataset.goto=view;chip.setAttribute('aria-pressed',String(on));filters.append(chip);}
}
function panelSection(body,heading){const box=text('section','','inspect-card');if(heading)box.append(text('h3',heading,'inspect-label'));body.append(box);return box;}
function panelRow(box,label,value,mono=false){const row=text('div','','inspect-row');row.append(text('span',label),text(mono?'code':'span',value,mono?'inspect-mono':'inspect-value'));box.append(row);return row;}
function openIdentityPanel(refresh){
  const id=state.identity;
  showPanel('identity','Your identity',`${plain(id.agent_id,'Your assistant')}, ${cap(plain(id.owner_id,'you'))}'s assistant`,body=>{
    const keys=panelSection(body,'Keys');panelRow(keys,'Fingerprint',id.fingerprint,true);
    keys.append(text('p','Another owner compares this full fingerprint with you before enrolling your assistant.','inspect-note'));
    const publicIdentity=id.public||Object.fromEntries(Object.entries(id).filter(([key])=>['owner_id','agent_id','signing_key','exchange_key','version'].includes(key)));
    body.append(button('Show the public identity to share','button secondary',()=>showPublicIdentity(publicIdentity,id.fingerprint)));
  },()=>openIdentityPanel(true),refresh);
}
function openStatusPanel(refresh){
  showPanel('status','Workspace status','What this workspace can do right now',body=>{
    const box=panelSection(body,'Status');
    panelRow(box,'Saved state',$('connection-status').textContent||'Not checked yet');
    panelRow(box,'Model calls',$('provider-status').textContent||'Disabled');
    panelRow(box,'Content',state.synthetic_only?'Synthetic, fictional work only':'Owner content');
    panelRow(box,'Exchange',state.pilot?.loopback_only?'Local loopback only':'Configured delivery');
    const actions=text('div','','inspect-actions');actions.append(button('Refresh saved state','button secondary',()=>$('refresh').click()),button('Sync exchange','button secondary',()=>$('sync').click()));body.append(actions);
  },()=>openStatusPanel(true),refresh);
}
// Settings gathers what is already yours to change, in one place. It holds no switch of its
// own: every line opens the place where that thing really lives.
function openSettingsPanel(refresh){
  const id=state.identity,active=state.peers.filter(isPeerActive).length;
  showPanel('settings','Settings',`${cap(plain(id.owner_id,'You'))} and ${plain(id.agent_id,'your assistant')}`,body=>{
    const line=(box,label,value,run)=>{const row=button('','inspect-item',run);row.append(text('span',label),text('span',value,'inspect-value'));box.append(row);};
    // A line that leads to another place takes you there. A pinned panel stays only where it
    // has a column of its own beside the page. Anywhere narrower it would cover the place you
    // asked for, so it closes and the keyboard lands on the page.
    const go=view=>{const stays=inspect.pinned&&besidePage.matches;if(!stays)inspect.hide({restoreFocus:false});navigate(view);if(!stays)$('main').focus({preventScroll:true});};
    const you=panelSection(body,'You');
    line(you,'Your keys and identity',shortDigest(id.fingerprint),()=>openIdentityPanel());
    const people=panelSection(body,'Assistants');
    line(people,'Assistants you work with',active===1?'1 enrolled':`${active} enrolled`,()=>go('peers'));
    if(relayEnabled(state)){line(people,'Invite someone','A link or a QR code',()=>openInviteDialog());line(people,'Join with a link','Paste an invite you were sent',()=>openJoinDialog());}
    line(people,relayEnabled(state)?'Add an assistant by fingerprint':'Add an assistant','Check the fingerprint first',()=>{go('peers');openPeerDialog();});
    // Sending modes and private notes are set on a message waiting in Approvals, nowhere else.
    if(state.approvals?.enabled===true)line(people,'Sending modes and private notes','In Approvals',()=>go('approvals'));
    const device=panelSection(body,'This device');
    line(device,'Workspace status',$('connection-status').textContent||'Not checked yet',()=>openStatusPanel());
    line(device,'Lock and sign out','Clears this browser',()=>$('logout').click());
  },()=>openSettingsPanel(true),refresh);
}
function openAssistantPanel(peer,refresh){
  const o=cap(plain(peer.owner_id,'Owner')),a=plain(peer.agent_id,'Assistant');
  showPanel('peer:'+peer.peer_id,a,`${o}'s assistant`,body=>{
    const who=text('div','','inspect-who');who.append(ownerPair(o,a,'owner-pair','idle'),text('span',isPeerActive(peer)?'Trusted. Each proposal still needs your decision.':peer.state==='revoked'?'Revoked. Nothing new is accepted from this assistant.':'Status unavailable.','inspect-note'));body.append(who);
    const keys=panelSection(body,'Keys');panelRow(keys,'Fingerprint',peer.fingerprint,true);panelRow(keys,'Status',isPeerActive(peer)?'Enrolled':peer.state==='revoked'?'Revoked':'Unverified');
    const work=state.items.filter(item=>item.peer_id===peer.peer_id);
    const shared=panelSection(body,'Shared work');
    if(!work.length)shared.append(text('p','No shared work yet.','inspect-note'));
    for(const item of work.slice(0,6)){const row=button('','inspect-item',()=>openReview(item));row.append(text('span',plain(item.title,'Untitled')),badge(item.state));shared.append(row);}
    const mode=panelSection(body,'Sending mode');mode.append(text('p','Every proposal from this assistant waits for your exact decision. Sending modes and private notes for conversations live in Approvals.','inspect-note'));
    if(isPeerActive(peer)){const actions=text('div','','inspect-actions');actions.append(button('Propose work','button primary',()=>prepareCompose(peer.peer_id)));
      if(state.peers.filter(isPeerActive).length>1)actions.append(button('Start a team mission','button secondary',()=>openTeamDialog(peer.peer_id)));body.append(actions);
      removeSection(body,peer,o,a);}
  },()=>{const next=state.peers.find(entry=>entry.peer_id===peer.peer_id);if(next)openAssistantPanel(next,true);else inspect.hide({restoreFocus:false});},refresh);
}
// Removing an assistant is final: its key can never be trusted again here. The section starts
// folded, and opening it asks for a deliberate hold, with a plain button as the alternative.
function removeSection(body,peer,owner,agent){
  const box=panelSection(body,'Remove');box.classList.add('remove-peer');
  const open=button(`Remove ${agent}`,'button secondary',()=>{
    open.hidden=true;
    const confirmBox=text('div','','remove-confirm');
    const facts=text('ul','','remove-facts');
    for(const line of [`Nothing new from ${agent} will be accepted, and you cannot send to it.`,'Work you already shared stays in your history.',`This cannot be undone. To work with ${owner} again, they need a new assistant key.`])facts.append(text('li',line));
    const go=()=>performWrite(`/api/peers/${peer.peer_id}/revoke`,{},{target:'notice',onSuccess:result=>notice(result.relay&&result.relay!=='ok'&&result.relay_closed?`${agent} is removed. The relay could not be reached, so its link closes on the next sync.`:`${agent} is removed.`,true)});
    confirmBox.append(facts,holdButton('Hold to remove',go),text('p','Or remove with the button below.','hold-alt'),button(`Remove ${agent} now`,'button danger',go),button('Keep','text-button',()=>{confirmBox.remove();open.hidden=false;open.focus();}));
    box.append(confirmBox);
  });
  box.append(text('p',`Stop working with ${owner}'s assistant.`,'inspect-note'),open);
}
function openMissionPanel(item,refresh){
  const p=peerOf(item),o=cap(plain(p?.owner_id,'Owner')),a=plain(p?.agent_id,'Assistant');
  showPanel('mission:'+item.id,plain(item.title,'Mission'),`Mission with ${o} · ${money(item.mission_cap.cap_micro,item.mission_cap.currency)} limit`,body=>{
    const decide=panelSection(body);decide.classList.add('inspect-decide');decide.append(text('strong',plain(item.title,'Mission')),button(isTerminal(item)?'Inspect the exact agreement':'Review the exact agreement','button primary',()=>openReview(item)));
    const budget=panelSection(body,'Budget');
    const run=(state.workflow?.runs??[]).find(entry=>entry.item_id===item.id&&entry.mission_balance);
    if(run){const [left,cur]=amountOf(run.mission_balance,'available');budget.append(text('strong',money(left,cur),'money-figure small'),text('p',`left of ${money(...amountOf(run.mission_balance,'cap'))}`,'inspect-note'));}
    else{budget.append(text('strong',money(item.mission_cap.cap_micro,item.mission_cap.currency),'money-figure small'),text('p',(item.historical_state??item.state)==='accepted'?'Agreed limit. Spending shows here once the work runs on this workspace.':'Proposed limit. Nothing is agreed until both of you accept the exact agreement.','inspect-note'));}
    const keys=panelSection(body,'Who');const who=text('div','','inspect-who');who.append(ownerPair(o,a),text('span',`${a} ${item.direction==='outgoing'?'does the work':'asked for it'}`,'inspect-note'));keys.append(who);
    const status=panelSection(body,'Status');panelRow(status,'Agreement',stateLabel(item.historical_state??item.state));if(item.decision_digest)panelRow(status,'Receipt',shortDigest(item.decision_digest),true);
  },()=>{const next=state.items.find(entry=>entry.id===item.id&&entry.mission_cap);if(next)openMissionPanel(next,true);else inspect.hide({restoreFocus:false});},refresh);
}
// Receipts: every signed decision, and the content hash of every finished run, in saved state.
// A decision receipt opens the exact proposal. A result receipt opens the run that kept the result.
function openReceipt(r){if(!r.item)return;if(r.kind==='result'&&r.run?.run_id)openWorkflow(r.item,r.run.run_id);else openReview(r.item);}
function renderReceipts(){
  const receipts=receiptsOf(state).filter(r=>matchesQuery([r.item?.title,r.digest,r.kind],searchQuery));
  if(!receipts.length){empty('✓','No receipts yet.','A receipt appears here each time a decision is signed or a run returns a result.');return;}
  for(const r of receipts){
    const row=text('article','','item-row receipt-row');const main=text('div','','item-main');
    const open=button(plain(r.item?.title,'Untitled'),'item-title item-open',()=>openReceipt(r));open.setAttribute('aria-label','Review '+plain(r.item?.title,'receipt'));
    const h=text('h3','','item-heading');h.append(open);main.append(h,text('div',`${r.kind==='decision'?stateLabel(r.item.historical_state??r.item.state)+' · signed decision':'Result of a run · content hash'} · ${peerName(r.item?.peer_id)}`,'item-meta'),text('p',r.digest,'peer-fingerprint'));
    row.append(text('span','✓','receipt-mark'),main);$('item-list').append(row);
  }
}
// A panel opened from the sidebar gives the keyboard back to its launcher when it closes. On
// the phone the drawer has closed by then, so the button that opens the drawer takes its place.
function fromSidebar(launcher){setNavigation(false);(mobileNavigation.matches?$('menu-toggle'):launcher).focus({preventScroll:true});}
document.querySelectorAll('[data-panel]').forEach(node=>node.addEventListener('click',()=>{if(!state||busy)return;fromSidebar(node);if(node.dataset.panel==='identity')openIdentityPanel();else if(node.dataset.panel==='settings')openSettingsPanel();else openStatusPanel();}));
// Your menu, on the owner card: the same few places wherever you are.
function setOwnerMenu(open,{restoreFocus=false}={}){
  const menu=$('owner-menu'),toggle=$('owner-menu-toggle');if(menu.hidden===!open)return;
  menu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));
  if(open)menu.querySelector('button').focus();else if(restoreFocus)toggle.focus();
}
$('owner-menu-toggle').addEventListener('click',()=>{if(!state||busy)return;setOwnerMenu($('owner-menu').hidden,{restoreFocus:true});});
$('owner-menu').addEventListener('click',event=>{
  const choice=event.target.closest('[data-owner]')?.dataset.owner;if(!choice||!state||busy)return;
  setOwnerMenu(false);
  if(choice==='lock'){$('logout').click();return;}
  // Some places have no search of their own. Search then opens All work, where it does work.
  if(choice==='search'){if($('search-input').disabled)navigate('tasks');if(mobileNavigation.matches)setNavigation(true);$('search-input').focus();$('search-input').select();return;}
  fromSidebar($('owner-menu-toggle'));
  if(choice==='identity')openIdentityPanel();else if(choice==='settings')openSettingsPanel();else openStatusPanel();
});
$('owner-menu').addEventListener('keydown',event=>{
  const items=[...$('owner-menu').querySelectorAll('button')],at=items.indexOf(document.activeElement);
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOwnerMenu(false,{restoreFocus:true});}
  else if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();items[(at+(event.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}
  else if(event.key==='Home'||event.key==='End'){event.preventDefault();items.at(event.key==='Home'?0:-1).focus();}
  else if(event.key==='Tab')setOwnerMenu(false);
});
document.addEventListener('click',event=>{if(!$('owner-menu').hidden&&!event.target.closest('#owner-menu,#owner-menu-toggle'))setOwnerMenu(false);});
// ===== Team missions: your assistant leads; each part is a proposal reviewed on its own =====
let currentTeam=null,teamTab='parts';
const STEP_LABEL={Plan:'Ready to send',Asked:'Waiting for their yes',Building:'Building',Result:'Result to check',Done:'Done',Stopped:'Stopped'};
function teamPeer(id){return state.peers.find(peer=>peer.peer_id===id);}
function partAction(part){
  if(part.step==='Plan')return ['Review and send',()=>openReview(part.item)];
  if(part.step==='Result')return ['Check the result',()=>openReview(part.result)];
  return null;
}
function renderTeams(){
  const root=$('team-view');root.replaceChildren();
  const teams=teamsOf(state);
  if(!teams.length){
    const box=text('div','','empty-state team-empty');box.append(text('div','◎','empty-symbol'),text('h3','No team missions yet.'),
      text('p','Split one piece of work across two or more assistants. Each part is a proposal you review and send, and each assistant decides on its own.'),
      button('Start a team mission','button primary',openTeamDialog));
    root.append(box);return;
  }
  const team=teams.find(entry=>entry.context===currentTeam)??(teams.length===1?teams[0]:null);
  if(!team){
    const list=text('div','','mission-rows');
    for(const entry of teams){const row=button('','mission-row team-row',()=>{currentTeam=entry.context;teamTab='parts';renderTeams();});row.dataset.team=entry.context;
      const main=text('span','','done-main');main.append(text('strong',entry.title),text('span',`${entry.parts.length} parts · ${teamLine(entry)}`,'done-meta'));
      row.append(main,text('span','›','row-chevron'));list.append(row);}
    root.append(list,button('Start a team mission','button secondary team-start',openTeamDialog));return;
  }
  currentTeam=team.context;
  const me=cap(plain(state.identity.owner_id,'You')),mine=plain(state.identity.agent_id,'Your assistant');
  const head=text('header','','team-head');const words=text('div','','team-heading');
  words.append(text('span',`${mine} leads`,'team-lead'),text('h2',team.title,'team-title'),text('p',`${team.parts.length} parts · ${team.people.length} assistants`,'team-meta'));
  head.append(ownerPair(me,mine,'owner-pair team-pair','look'),words);
  if(teams.length>1)head.append(button('All team missions','text-button team-all',()=>{currentTeam=null;renderTeams();}));
  root.append(head,text('p',teamLine(team),'team-line'));
  const bar=text('div','','team-progress');bar.setAttribute('role','img');
  const counts=teamCounts(team);bar.setAttribute('aria-label',`${counts.Done} of ${team.parts.length} parts done`);
  for(const part of team.parts){const seg=text('span','','team-seg'+(part.step==='Stopped'?' stopped':''));const fill=text('i','');fill.style.width=`${Math.round(stepShare(part.step)*100)}%`;seg.append(fill);bar.append(seg);}
  root.append(bar);
  const members=text('div','','team-members');
  for(const id of team.people){const peer=teamPeer(id),o=cap(plain(peer?.owner_id,'Owner')),a=plain(peer?.agent_id,'Assistant');const chip=text('span','','team-chip');chip.append(ownerPair(o,a),text('span',`${o} · ${a}`));members.append(chip);}
  root.append(members);
  const tabs=text('nav','','section-tabs team-tabs');tabs.setAttribute('aria-label','Team mission');
  for(const [key,label] of [['parts','Parts'],['people','People'],['receipts','Receipts']]){const tab=button(label,'section-tab'+(teamTab===key?' selected':''),()=>{teamTab=key;renderTeams();});tab.dataset.teamTab=key;tab.setAttribute('aria-current',teamTab===key?'page':'false');tabs.append(tab);}
  root.append(tabs);
  if(teamTab==='people'){
    const list=text('div','','team-people');
    for(const id of team.people){const peer=teamPeer(id),o=cap(plain(peer?.owner_id,'Owner')),a=plain(peer?.agent_id,'Assistant'),mineParts=team.parts.filter(part=>part.peer_id===id);
      const card=text('article','','inspect-card team-person');const who=text('div','','inspect-who');who.append(ownerPair(o,a),text('strong',`${a}, ${o}'s assistant`));card.append(who);
      for(const part of mineParts){const row=text('div','','inspect-row');row.append(text('span',part.title),text('span',STEP_LABEL[part.step],'inspect-value'));card.append(row);}
      card.append(text('p',`${a} decides on each of its parts itself. Nothing it does reaches the others without your review.`,'inspect-note'));list.append(card);}
    root.append(list);return;
  }
  if(teamTab==='receipts'){
    const ids=new Set(team.parts.flatMap(part=>[part.item.id,...resultsFor(part.item,state.items).map(entry=>entry.id)]));
    const receipts=receiptsOf(state).filter(r=>r.item&&ids.has(r.item.id));
    if(!receipts.length){root.append(text('p','No receipts yet. A receipt appears here each time a part or a result is decided.','done-empty'));return;}
    const list=text('div','','mission-rows');
    for(const r of receipts){const row=button('','mission-row',()=>openReceipt(r));const main=text('span','','done-main');main.append(text('strong',plain(r.item.title,'Part')),text('span',`${r.kind==='decision'?'Signed decision':'Result of a run'} · ${shortDigest(r.digest)}`,'done-meta'));row.append(text('span','✓','receipt-mark'),main);list.append(row);}
    root.append(list);return;
  }
  const grid=text('div','','team-parts-grid');
  for(const part of team.parts){
    const peer=teamPeer(part.peer_id),o=cap(plain(peer?.owner_id,'Owner')),a=plain(peer?.agent_id,'Assistant');
    const card=text('article','','team-part'+(part.needsYou?' needs-you':''));card.dataset.itemId=part.item.id;card.dataset.step=part.step;
    const top=text('div','','team-part-head');const name=text('div','','team-part-name');name.append(text('strong',part.title),text('span',`${a}, ${o}'s assistant`,'team-part-who'));
    top.append(ownerPair(o,a),name,text('span',STEP_LABEL[part.step],'team-pill'+(part.needsYou?' needs':part.step==='Done'?' done':'')));card.append(top);
    const steps=text('ol','','team-steps');const at=STEPS.indexOf(part.step);
    STEPS.forEach((step,index)=>{const li=text('li',step,index<at?'past':index===at?'now':'');steps.append(li);});
    card.append(steps);
    const actions=text('div','','team-part-actions');const action=partAction(part);
    if(action)actions.append(button(action[0],'button primary',action[1]));
    actions.append(button('Details','button secondary',()=>openPartPanel(team,part)));card.append(actions);grid.append(card);
  }
  root.append(grid,button('Start another team mission','button secondary team-start',openTeamDialog));
}
function openPartPanel(team,part,refresh){
  const peer=teamPeer(part.peer_id),o=cap(plain(peer?.owner_id,'Owner')),a=plain(peer?.agent_id,'Assistant');
  showPanel('part:'+part.item.id,part.title,`Part of ${team.title} · ${a}`,body=>{
    const action=partAction(part);
    if(action){const decide=panelSection(body);decide.classList.add('inspect-decide');decide.append(text('strong',part.step==='Plan'?'Ready for you to send':'A result is waiting for your check'),button(action[0],'button primary',action[1]));}
    const progress=panelSection(body,'Progress');const at=STEPS.indexOf(part.step);
    STEPS.forEach((step,index)=>panelRow(progress,step,index<at?'Done':index===at?'Now':part.step==='Stopped'?'—':'Not yet'));
    if(part.step==='Stopped')progress.append(text('p','This part stopped. Its history stays here.','inspect-note'));
    const who=panelSection(body,'Who');const pair=text('div','','inspect-who');pair.append(ownerPair(o,a),text('span',`${a} decides on this part itself.`,'inspect-note'));who.append(pair);
    const status=panelSection(body,'Records');panelRow(status,'Proposal',stateLabel(part.item.state));
    const returned=resultsFor(part.item,state.items)[0];
    if(returned)panelRow(status,'Result',stateLabel(returned.state));
    if(part.item.decision_digest)panelRow(status,'Receipt',shortDigest(part.item.decision_digest),true);
    body.append(button('Open the exact proposal','button secondary',()=>openReview(part.item)));
  },()=>{const nextTeam=teamsOf(state).find(entry=>entry.context===team.context),nextPart=nextTeam?.parts.find(entry=>entry.item.id===part.item.id);
    if(nextPart)openPartPanel(nextTeam,nextPart,true);else inspect.hide({restoreFocus:false});},refresh);
}
function teamRow(index,first){
  const row=text('fieldset','','team-part-row');row.append(text('legend',`Part ${index+1}`));
  const name=text('label','Part name');const nameInput=text('input','');nameInput.name='part_title';nameInput.maxLength=50;nameInput.placeholder='For example, Card deposits';name.append(nameInput);
  const who=text('label','Assistant');const select=text('select','');select.name='part_peer';
  const active=state.peers.filter(isPeerActive);
  for(const peer of active){const option=text('option',`${plain(peer.agent_id,'Assistant')}, ${cap(plain(peer.owner_id,'Owner'))}'s assistant`);option.value=peer.peer_id;select.append(option);}
  const order=first&&active.some(peer=>peer.peer_id===first)?[first,...active.filter(peer=>peer.peer_id!==first).map(peer=>peer.peer_id)]:active.map(peer=>peer.peer_id);
  if(order.length)select.value=order[index%order.length];who.append(select);
  const brief=text('label','Brief','full');const area=text('textarea','');area.name='part_text';area.rows=2;area.maxLength=4096;area.value='SYNTHETIC ONLY: ';brief.append(area);
  row.append(name,who,brief);return row;
}
function openTeamDialog(first){
  if(!state||busy||uncertainty.pending())return;
  if(state.peers.filter(isPeerActive).length<2){navigate('peers');notice('A team mission needs at least two enrolled assistants. Enrol another trusted peer first.');return;}
  const form=$('team-form');form.reset();$('team-message').textContent='';const lead=typeof first==='string'?first:undefined;$('team-form').dataset.first=lead??'';$('team-parts').replaceChildren(teamRow(0,lead),teamRow(1,lead));
  $('team-intro').textContent=`${plain(state.identity.agent_id,'Your assistant')} leads. Each part becomes a proposal you review and send on its own, and each assistant decides for itself. Nothing is sent yet.`;
  $('team-add-part').hidden=false;openDialog('team-dialog');
}
$('team-add-part').addEventListener('click',()=>{const parts=$('team-parts');if(parts.children.length>=6)return;parts.append(teamRow(parts.children.length,$('team-form').dataset.first||undefined));$('team-add-part').hidden=parts.children.length>=6;});
$('team-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending())return;
  const form=event.currentTarget;
  try{
    if(!form.elements.team_synthetic.checked)throw new Error('Confirm that you may share this fictional work.');
    const rows=[...$('team-parts').children].map(row=>({title:row.querySelector('[name=part_title]').value,peer_id:row.querySelector('[name=part_peer]').value,text:row.querySelector('[name=part_text]').value.replace(/^SYNTHETIC ONLY:\s*$/,'')}));
    const parts=planParts(form.elements.mission.value,rows),context=newContext(),minutes=form.elements.minutes.value;
    const bodies=parts.map(part=>proposalBody({kind:'task',peer_id:part.peer_id,title:part.title,text:part.text,context,task_id:'team-'+crypto.randomUUID(),minutes,synthetic:'on'}));
    let created=0;
    for(const body of bodies){const before=created;await performWrite('/api/proposals',body,{target:'team-message',onSuccess:()=>{created++;}});if(created===before)break;}
    if(created===bodies.length){$('team-dialog').close();currentTeam=context;teamTab='parts';navigate('team');notice(`${bodies.length} parts prepared. Review and send each one; every assistant decides on its own.`,true);}
    else if(!$('team-message').textContent)$('team-message').textContent=`Prepared ${created} of ${bodies.length} parts. The rest were not created, and nothing has been sent.`;
    else $('team-message').textContent=`Prepared ${created} of ${bodies.length} parts, and nothing has been sent. `+$('team-message').textContent;
  }catch(error){$('team-message').textContent=error.message;}
});
document.querySelectorAll('[data-jump]').forEach(node=>node.addEventListener('click',()=>navigate(node.dataset.jump)));
document.querySelector('[data-action=lock]')?.addEventListener('click',()=>$('logout').click());
$('money-start').addEventListener('click',()=>{if(!state)return;if(state.peers.some(isPeerActive)){prepareCompose();const kind=$('compose-form').elements.kind;kind.value='mission';configureKind();}else navigate('peers');});
function empty(symbol,title,description,action,target=$('item-list')) {
  const box=text('div','','empty-state');box.append(text('div',symbol,'empty-symbol'),text('h3',title),text('p',description));if(action)box.append(button(action.label,'button secondary',action.run));target.append(box);
}
function peerAvatar(peerId,className='peer-avatar') {
  const peer=state.peers.find(peer=>peer.peer_id===peerId),name=plain(peer?.agent_id,'?');
  return nameAvatar(name,className);
}
function itemRow(item) {
  const row=text('article','','item-row');row.dataset.itemId=item.id;
  const main=text('div','','item-main');
  const heading=button(plain(item.title,'Untitled proposal'),'item-title item-open',()=>openReview(item));heading.setAttribute('aria-label','Review '+plain(item.title,'proposal'));const title=text('h3','','item-heading');title.append(heading);main.append(title);
  const meta=text('div','','item-meta');meta.append(text('span',plain(item.task_id,plain(item.id)).slice(0,28),'task-ref'),text('span','·'),text('span',item.direction==='incoming'?'Incoming':'Outgoing'),text('span','·'),text('span',peerName(item.peer_id)));main.append(meta);
  const right=text('div','','row-right');right.append(badge(item.state),peerAvatar(item.peer_id),button(isTerminal(item)?'Inspect':'Review exact item','button secondary row-action',()=>openReview(item)));
  const run=state.workflow?.runs.find(run=>run.item_id===item.id);
  if(run){main.append(text('p',workflowSummary(run),'workflow-note'));right.append(button('Inspect synthetic run','button secondary workflow-action',()=>openWorkflow(item,run.run_id)));}
  const symbol=workIcon(item.kind,'item-icon '+item.kind+' '+statusClass(item.state),item.state);
  row.append(symbol,main,right);return row;
}
function renderItems() {
  // Money and Team missions have no list of their own, so a search from them looks across all work.
  const items=projectItems(state,['money','team'].includes(currentView)?'overview':currentView,currentFilter,searchQuery);
  if(searchQuery)$('list-description').textContent=`${items.length} ${items.length===1?'result':'results'} for “${searchQuery}”`;
  else $('list-description').textContent=`${items.length} ${currentView==='artifacts'?'artifacts':currentView==='tasks'?'tasks':'proposals'} · ${viewCopy[currentView][5]}`;
  if(!items.length){empty('⌕',searchQuery?'No matching work.':currentFilter!=='all'?'No matching proposals.':currentView==='artifacts'?'Your artifacts will live here.':'A little room for what comes next.',searchQuery?'Try a title, task reference, assistant or status.':'Create a proposal, or sync the exchange to inspect incoming work.',searchQuery?{label:'Clear search',run:clearSearch}:undefined);return;}
  if(currentLayout==='board'){
    const board=text('div','','board-columns');
    for(const group of boardGroups(items)){
      const column=text('section','','board-column '+group.id),heading=text('div','','board-heading'),mark=text('span','','board-state-mark '+group.id);mark.setAttribute('aria-hidden','true');heading.append(mark,text('h3',group.label),text('span',group.items.length,'group-count'));
      const rows=text('div','','board-items');for(const item of group.items)rows.append(itemRow(item));
      if(!group.items.length)rows.append(text('p','No items','board-empty'));
      column.append(heading,rows);board.append(column);
    }
    $('item-list').append(board);
  }else for(const item of items)$('item-list').append(itemRow(item));
}
function overviewItem(item) {
  const row=button('','overview-row',()=>openReview(item));row.dataset.itemId=item.id;
  row.append(workIcon(item.kind,'overview-item-icon '+item.kind+' '+statusClass(item.state),item.state));
  const main=text('span','','overview-row-main');main.append(text('strong',plain(item.title,'Untitled proposal')),text('span',peerName(item.peer_id)+' · '+plain(item.task_id).slice(0,28),'overview-row-meta'));
  row.append(main,badge(item.state),text('span','↗','overview-arrow'));return row;
}
let homeOffset=0;
let storyOffset=0;
function cap(value){const v=String(value??'');return v.charAt(0).toUpperCase()+v.slice(1);}
function peerOf(item){return state.peers.find(peer=>peer.peer_id===item.peer_id);}
// Decide: what this exact decision spends, shares and keeps, above the exact content.
// Money needs a deliberate hold; the plain button below stays as the alternative.
function renderDecide(item,review){
  const box=$('review-decide');box.replaceChildren();
  const deciding=review.allowed_actions.some(action=>['accept','release'].includes(action));box.hidden=!deciding;if(!deciding)return;
  const peer=peerOf(item),names={agent:plain(peer?.agent_id,'their assistant'),owner:cap(plain(peer?.owner_id,'them')),actions:review.allowed_actions};
  box.append(text('p',decisionQuestion(item,names),'decide-question'));
  const rows=text('dl','','decide-rows');
  for(const [key,value] of decisionRows(item,names)){const row=text('div','','decide-row'+(key==='Keeps'?' quiet':''));row.append(text('dt',key),text('dd',value));rows.append(row);}
  box.append(rows);
  if(review.allowed_actions.includes('accept')&&needsHold(item,'accept')){
    const current=selected;
    box.append(holdButton('Hold to agree',()=>{if(selected===current&&$('review-dialog').open)decideSelected('accept');}),text('p','Or agree with the button below.','hold-alt'));
  }
}
// Home is a short honest paragraph (at most three sentences) and one decision per card.
// The cards are one queue of everything that needs you: proposals from saved state, plus
// questions, messages and shared drafts (Approvals), conversation invitations and drafts
// from your apps, each read without writing. A card never decides on its own: its button
// opens the exact review, or the place where that exact decision is made.
let homeExtras={for:null,approvals:null,hostDrafts:null,conversations:null,failed:[]};
async function loadHomeExtras(){
  const epoch=generation,snapshot=state,next={for:snapshot,approvals:null,hostDrafts:null,conversations:null,failed:[]};homeExtras.for=snapshot;
  const read=(enabled,path,validate,key,label)=>enabled?request(path,{readOnly:true}).then(value=>{next[key]=validate(value);}).catch(()=>{next.failed.push(label);}):null;
  await Promise.all([read(snapshot.approvals?.enabled===true,'/api/approvals',validateListing,'approvals','Approvals'),
    read(snapshot.conversations?.enabled===true,'/api/conversations',validateCatalogue,'conversations','Conversations'),
    read(snapshot.host_drafts?.enabled===true,'/api/host-drafts',validateDraftQueue,'hostDrafts','your apps')].filter(Boolean));
  if(epoch!==generation||!token||state!==snapshot)return;
  // A valid answer can still say that part of it could not be checked. That is not an empty queue.
  next.failed.push(...uncheckedParts(next));homeExtras=next;
  if(currentView==='overview'&&!searchQuery)renderHome();else{const waiting=homeEntries().length;$('home-count').textContent=waiting;$('home-count').hidden=!waiting;}
}
function homeEntries(){
  const extras=homeExtras.for===state?homeExtras:{};
  return homeQueue({proposals:attentionItems(state),approvals:extras.approvals,hostDrafts:extras.hostDrafts,conversations:extras.conversations,joiners:joinerCards(state)});
}
function renderHome(){
  const say=$('home-paragraph'),cards=$('home-cards');if(!say||!cards)return;
  say.replaceChildren();cards.replaceChildren();
  const queue=homeEntries(),failed=homeExtras.for===state?homeExtras.failed:[];
  $('home-count').textContent=queue.length;$('home-count').hidden=!queue.length;
  const when=$('home-when');if(when)when.textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'})+' · '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  const n=queue.length,first=n?queue[homeOffset%n]:undefined,hour=new Date().getHours(),done=doneToday(state.items);
  const me=cap(plain(state.identity.owner_id,'there')),mine=plain(state.identity.agent_id,'Your assistant');say.append(text('span',`${homeGreeting(hour)} ${me}. `));
  if(!n&&isEvening(hour)&&done.length)say.append(text('span',eveningSummary(done,peerOf)+' '));
  if(!n){say.append(text('b',failed.length?closingLine(failed):'Nothing needs you right now.'));if(isEvening(hour)&&done.length)renderStory(done);return;}
  const who=entry=>askerOf(entry,{me,mine,peer:entry.item?peerOf(entry.item):undefined});
  const asker=who(first),owner=cap(plain(asker.owner,'Someone')),agent=plain(asker.agent,'their assistant');
  const pair=()=>ownerPair(owner,agent,'owner-pair inline','look');
  if(first.kind==='proposal')say.append(text('span',`${owner}'s `),pair(),text('span',` ${agent} sent `),text('b',first.title));
  else if(first.kind==='question')say.append(text('span','Your '),pair(),text('span',` ${agent} asked you `),text('b',`“${first.title}”`));
  else if(first.kind==='message')say.append(text('span','Your '),pair(),text('span',` ${agent} `),text('b','wants to send a message for you'));
  else if(first.kind==='invite')say.append(text('span',`${owner}'s `),pair(),text('span',` ${agent} `),text('b','invited you to a conversation'));
  else if(first.kind==='joiner')say.append(text('span',`${owner} and `),pair(),text('span',` ${agent} `),text('b','used your invite and ask to connect'));
  else if(first.kind==='shared-draft')say.append(text('b','A shared draft waits for your agreement'));
  else say.append(text('span','A draft from one of your apps, '),text('b',`“${first.title}”`),text('span',','));
  say.append(text('span',moreLine(n)),text('b',closingLine(failed)));
  const order=queue.slice(homeOffset%n).concat(queue.slice(0,homeOffset%n)).slice(0,3);
  order.forEach((entry,index)=>{
    const ask=who(entry),o=cap(plain(ask.owner,'Owner')),a=plain(ask.agent,'Assistant'),copy=CARD[entry.kind];
    const card=text('article','','home-card depth-'+index);card.dataset.queueKey=entry.key;if(entry.item)card.dataset.itemId=entry.item.id;card.dataset.kind=entry.kind;
    const head=text('div','','home-card-head'),label=text('span','','home-card-who');label.append(text('strong',ask.yours?`${a}, your assistant`:`${a}, ${o}'s assistant`),text('small',`${(homeOffset+index)%n+1} of ${n}`));
    head.append(ownerPair(o,a,'owner-pair',index===0?'look':'idle'),label);card.append(head);
    if(copy.lead)card.append(text('p',copy.lead.charAt(0)===copy.lead.charAt(0).toUpperCase()?copy.lead:`${a} ${copy.lead}`,'home-card-lead'));
    const belongs=entry.kind==='proposal'?partLead(partOf(state,entry.item)):'';if(belongs){const lead=text('p',belongs,'home-card-lead');lead.dataset.team='true';card.append(lead);}
    card.append(text('p',entry.title,'home-card-title'));
    const open=()=>entry.kind==='proposal'?openReview(entry.item):entry.kind==='joiner'?openJoinerPanel(entry.joiner):navigate(entry.view);
    if(index===0){const actions=text('div','','home-card-actions');
      if(n>1)actions.append(button('Not now','button home-later',()=>{homeOffset++;renderHome();}));
      actions.append(button(copy.action,'button primary home-agree',open));card.append(actions);
      card.tabIndex=0;card.setAttribute('aria-label',`${ask.yours?a+', your assistant':a+', '+o+"'s assistant"}: ${entry.title}. Right arrow opens it, left arrow shows the next card.`);
      card.addEventListener('keydown',event=>{if(event.target!==card)return;if(event.key==='ArrowRight'){event.preventDefault();open();}else if(event.key==='ArrowLeft'&&n>1){event.preventDefault();homeOffset++;renderHome();$('home-cards').querySelector('.depth-0')?.focus();}});}
    else card.setAttribute('aria-hidden','true');
    cards.append(card);
  });
}
// The evening story: one finished piece of work at a time, with the owner's reaction.
// Neither button changes a permission: in this workspace nothing runs without the owner's
// yes, so "Don't do that again" reopens what was agreed, where it can be cancelled.
function renderStory(done){
  const cards=$('home-cards'),item=done[storyOffset%done.length],p=peerOf(item);
  const o=cap(plain(p?.owner_id,'You')),a=plain(p?.agent_id,state.identity.agent_id);
  const card=text('article','','home-card story-card depth-0');card.dataset.itemId=item.id;
  const head=text('div','','home-card-head');const who=text('span','','home-card-who');who.append(text('strong',`${a}, ${o}'s assistant`),text('small',done.length>1?`Story ${storyOffset%done.length+1} of ${done.length}`:'Today'));
  head.append(ownerPair(o,a,'owner-pair','done'),who);
  card.append(head,text('p',plain(item.title,'Untitled'),'home-card-title'),text('p',doneLine(item,p)+'.','story-line'));
  const actions=text('div','','home-card-actions');
  actions.append(button('Don’t do that again','button home-later',()=>{notice(`${a} can’t start anything without your yes. Here is what was agreed, so you can cancel it or decline the next one.`);openReview(item);}));
  actions.append(button(done.length>1?'Good, next':'Good','button primary home-good',()=>{storyOffset++;if(done.length>1)renderStory(done);else card.classList.add('story-seen');}));
  card.append(actions);cards.replaceChildren(card);
}
// Done today: one quiet line on Home. "See all" opens the agreed work in Recents.
function renderDone(){
  const line=$('done-line');if(!line)return;line.replaceChildren();
  const done=doneToday(state.items);line.hidden=!done.length;if(!done.length)return;
  const first=done[0],p=peerOf(first);
  const names=done.slice(0,2).map(item=>`“${plain(item.title,'Untitled')}”`),rest=done.length-names.length;
  line.append(ownerPair(cap(plain(p?.owner_id,state.identity.owner_id)),plain(p?.agent_id,state.identity.agent_id),'owner-pair','done'),
    text('span',`Done today: ${names.join(rest?', ':' and ')}${rest?` and ${rest} more`:''}. `),button('See all','text-button done-all',()=>openDonePanel()));
}
// See all shows exactly what the line counted: everything agreed today, results included.
function openDonePanel(refresh){
  const done=doneToday(state.items);
  if(!done.length){if(refresh===true)inspect.hide({restoreFocus:false});return;}
  showPanel('done','Done today',`${done.length} agreed today`,body=>{
    const list=panelSection(body,'Agreed today');
    for(const item of done){const row=button('','inspect-item',()=>openReview(item));row.append(text('span',plain(item.title,'Untitled')),badge(item.historical_state??item.state));list.append(row);}
    body.append(button('Open receipts','button secondary',()=>navigate('receipts')));
  },()=>openDonePanel(true),refresh);
}
// Money: real mission budgets only, and every mission agreement with its spending limit.
function missionsOf(){
  const seen=new Map();
  for(const item of state.items){if(item.kind!=='task'||!item.mission_cap)continue;const prior=seen.get(item.context);if(!prior||item.created_at>prior.created_at)seen.set(item.context,item);}
  return [...seen.values()].sort((a,b)=>b.created_at-a.created_at);
}
function renderMoney(){
  const panel=$('money-panel'),rows=$('mission-rows');if(!panel||!rows)return;
  panel.replaceChildren();rows.replaceChildren();
  const totals=budgetSummary(state.workflow?.runs??[],state.items);
  if(!totals.length){
    panel.append(text('strong','No budgets yet','money-figure empty'),text('p','A budget appears here once you agree a mission with a spending limit.','money-note'));
  }else{
    const main=totals[0],budgets=main.budgets===1?'one budget':main.budgets+' budgets';
    if(main.unknown){
      panel.append(text('strong',money(main.cap,main.currency),'money-figure'),text('span',`Agreed across ${budgets}`,'money-label'));
      panel.append(text('p',main.unknown===main.budgets?'Spending shows here once the work runs on this workspace.':`Spent ${money(main.spent,main.currency)} · Held ${money(main.held,main.currency)} where visible here`,'money-note'));
    }else{
      panel.append(text('strong',money(main.available,main.currency),'money-figure'),text('span',`Left across ${budgets}`,'money-label'));
      const bar=text('div','','money-bar');const fill=text('span','','money-fill');fill.style.width=`${main.cap?Math.min(100,Math.round((main.spent+main.held)/main.cap*100)):0}%`;bar.append(fill);
      bar.setAttribute('role','img');bar.setAttribute('aria-label',`${money(main.spent+main.held,main.currency)} used or held of ${money(main.cap,main.currency)}`);
      panel.append(bar,text('p',`Spent ${money(main.spent,main.currency)} · Held ${money(main.held,main.currency)} · Limit ${money(main.cap,main.currency)}`,'money-note'));
    }
    for(const other of totals.slice(1))panel.append(text('p',other.unknown?`Also ${money(other.cap,other.currency)} agreed in ${other.currency}`:`Also ${money(other.available,other.currency)} left in ${other.currency}`,'money-note'));
    panel.append(text('p','Simulated spending. No real payment is made.','money-note muted'));
  }
  for(const team of teamsOf(state)){
    const row=button('','mission-row team-row',()=>{currentTeam=team.context;teamTab='parts';navigate('team');});row.dataset.team=team.context;
    const main=text('span','','done-main');main.append(text('strong',team.title),text('span',`Team mission · ${team.parts.length} parts · ${teamLine(team).split('. ')[0].replace(/\.$/,'')}`,'done-meta'));
    row.append(ownerPair(cap(plain(state.identity.owner_id,'You')),plain(state.identity.agent_id,'Your assistant')),main,text('span','›','row-chevron'));rows.append(row);
  }
  const missions=missionsOf();
  if(!missions.length&&!teamsOf(state).length)rows.append(text('p','No missions yet. A mission is a piece of work with a spending limit and checks that both owners agree.','done-empty'));
  for(const item of missions){
    const p=peerOf(item),o=cap(plain(p?.owner_id,'Owner')),a=plain(p?.agent_id,'Assistant');
    const row=button('','mission-row',()=>openMissionPanel(item));row.dataset.itemId=item.id;
    const main=text('span','','done-main');main.append(text('strong',plain(item.title,'Untitled mission')),text('span',`${money(item.mission_cap.cap_micro,item.mission_cap.currency)} limit · ${stateLabel(item.historical_state??item.state)}`,'done-meta'));
    row.append(ownerPair(o,a),main,text('span','›','row-chevron'));rows.append(row);
  }
}
function renderOverview() {
  renderHome();renderDone();
  if($('home-ask-input'))$('home-ask-input').placeholder=`Ask ${plain(state.identity.agent_id,'your assistant')} to start something…`;
}
function renderPeers() {
  if(relayEnabled(state)&&!searchQuery)renderRelayStrip();
  const own=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',plain(state.identity.agent_id,'Your assistant'),'item-title'),text('div',plain(state.identity.owner_id)+' · Your assistant','item-meta'),text('p',state.identity.fingerprint,'peer-fingerprint'));
  const identity=state.identity.public||Object.fromEntries(Object.entries(state.identity).filter(([key])=>['owner_id','agent_id','signing_key','exchange_key','version'].includes(key)));
  const right=text('div','','row-right');right.append(text('span','Your assistant','badge local'),button('View public identity','button secondary',()=>showPublicIdentity(identity,state.identity.fingerprint)));
  own.append(nameAvatar(state.identity.agent_id,'peer-avatar local'),main,right);
  if(matchesQuery([state.identity.agent_id,state.identity.owner_id,'your assistant'],searchQuery))$('item-list').append(own);
  const peers=state.peers.filter(peer=>matchesQuery([peer.agent_id,peer.owner_id,peer.peer_id,peer.fingerprint,peer.state],searchQuery));
  if(!state.peers.length&&!searchQuery){if(relayEnabled(state))empty('⊞','Good work is connected.','Invite someone with a link, or join with a link you were sent.',{label:'Invite someone',run:openInviteDialog});else empty('⊞','Good work is connected.','Exchange public identities with another owner and verify their full fingerprint.',{label:'Enrol a peer',run:openPeerDialog});return;}
  for(const peer of peers) {
    const row=text('article','','item-row peer-row');const main=text('div','','item-main');main.append(text('h3',plain(peer.agent_id,'Assistant'),'item-title'),text('div',plain(peer.owner_id,'Owner'),'item-meta'));if(linkLabel(state,peer.peer_id))main.append(text('div',linkLabel(state,peer.peer_id),'relay-link-state'));main.append(text('p',peer.fingerprint,'peer-fingerprint'));
    const right=text('div','','row-right');right.append(text('span',isPeerActive(peer)?'Enrolled':peer.state==='revoked'?'Revoked':'Status unavailable',isPeerActive(peer)?'badge accepted':'badge revoked'));
    right.append(button('Open','button secondary row-action',()=>openAssistantPanel(peer)));
    row.append(peerAvatar(peer.peer_id),main,right);$('item-list').append(row);
  }
  if(!$('item-list').childElementCount)empty('⌕','No matching assistants.','Try an assistant name, owner or fingerprint.',{label:'Clear search',run:clearSearch});
}

function showPublicIdentity(identity,fingerprint) {
  $('review-decide').hidden=true;$('review-decide').replaceChildren();selected=null;selectedWorkflow=null;selectedTransfer=null;$('review-title').textContent='Your public identity';$('review-eyebrow').textContent='SHARE AND VERIFY';$('review-state').replaceChildren();$('review-details').replaceChildren();detail($('review-details'),'Fingerprint',fingerprint);
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
    renderDecide(item,review);
    const parent=state.items.find(candidate=>candidate.id===item.parent_id);
    if(item.kind==='artifact' && item.direction==='incoming' && ['pending','accepted'].includes(item.state) && parent?.peer_mission===true) {
      const current=selected;
      $('review-actions').append(button('Check mission evidence','button secondary',async()=>{
        if(busy||selected!==current)return;
        const unlock=operations.acquire();
        try {
          const report=await request('/api/items/'+encodeURIComponent(item.id)+'/mission-evidence');
          if(epoch!==generation || selected!==current || !$('review-dialog').open)return;
          if(report.artifact_id!==item.id || report.parent_task_id!==item.parent_id || report.recipient_decision_required!==true)throw new Error('Evidence mismatch');
          $('review-message').textContent=report.findings.map(f=>f.kind+' ('+f.value+'): '+f.status).join(' · ');
        }catch(error){if(epoch===generation&&selected===current)handleFailure(error,'review-message');}
        finally{unlock();}
      }));
    }
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
  $('review-decide').hidden=true;$('review-decide').replaceChildren();selected=null;selectedTransfer=null;$('review-title').textContent=heading;$('review-eyebrow').textContent='LOCAL SYNTHETIC REHEARSAL';$('review-state').replaceChildren(text('span',workflowStateLabel(run.state),'badge '+statusClass(run.state)));
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
      if(value.review.mission_quote) {
        const q=value.review.mission_quote;
        detail($('review-details'),'Simulated reservation',money(...amountOf(q,'reserve')));
        if(run.mission_balance) detail($('review-details'),'Available simulated budget',money(...amountOf(run.mission_balance,'available'))+' of '+money(...amountOf(q,'cap')));
      }
      if(run.allowed_actions.includes('approve'))$('review-actions').append(button('Approve synthetic request','button primary',()=>workflowAction('approve')));
      if(run.allowed_actions.includes('run'))$('review-actions').append(button('Run synthetic fixture once','button primary',()=>workflowAction('run')));
    } else if(run.allowed_actions.includes('review_result')) {
      const peer=state.peers.find(peer=>peer.peer_id===item.peer_id);
      const value=validateWorkflowResult(await request(`/api/workflows/${encodeURIComponent(runId)}/result`),run,item,peer);
      if(epoch!==generation)return;
      selectedWorkflow={item:{...item},run,review:value,mode:'result'};
      $('review-title').textContent='Review original synthetic result';$('review-content').textContent=value.content;
      if(run.mission_usage) detail($('review-details'),'Simulated usage',money(...amountOf(run.mission_usage,'actual')));
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
function prepareCompose(peerId){
  if(busy||uncertainty.pending())return;
  if(!state.peers.some(isPeerActive)){navigate('peers');notice('Enrol an active trusted peer before preparing a proposal.');return;}
  $('compose-form').reset();$('compose-message').textContent='';$('proposal-peer').replaceChildren();
  for(const peer of state.peers.filter(isPeerActive)){const option=text('option',`${plain(peer.agent_id,'Assistant')} · ${plain(peer.owner_id,'Owner')}`);option.value=peer.peer_id;$('proposal-peer').append(option);}
  const form=$('compose-form');form.elements.context.value=newContext();form.elements.task_id.value='task-'+crypto.randomUUID();form.elements.text.value='SYNTHETIC ONLY: ';
  if(typeof peerId==='string'&&[...$('proposal-peer').options].some(option=>option.value===peerId))$('proposal-peer').value=peerId;
  $('compose-form').elements.mission_currency.value=ownerCurrency();configureKind();openDialog('compose-dialog');
}
function configureKind(){
  const form=$('compose-form'),artifact=form.elements.kind.value==='artifact';$('parent-field').hidden=!artifact;$('proposal-parent').required=artifact;
  const mission=form.elements.kind.value==='mission';
  $('mission-fields').hidden=!mission;
  for(const key of ['mission_deliverable','mission_value','mission_budget'])form.elements[key].required=mission;
  form.elements.context.closest('label').hidden=mission;
  $('workflow-permission-field').hidden=artifact||(!mission&&!workflowEnabled(state));
  if($('workflow-permission-field').hidden)form.elements.synthetic_run.checked=false;
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
    if(pendingJoin){const carried=pendingJoin;pendingJoin='';if(relayEnabled(state))queueMicrotask(()=>openJoinDialog(carried));else notice('This copy of Parlu has no relay set up, so it cannot open the invite yet. Start Parlu with --relay first.');}
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
// Both carriers: assistants added by address use the direct exchange, invited ones the relay.
$('sync').addEventListener('click',()=>performWrite('/api/exchange',{}, {onSuccess:()=>{if(relayEnabled(state))setTimeout(()=>relaySync(true,{announce:true}));else notice('Exchange checked. Review new items and saved delivery outcomes below.',true);}}));
$('new-proposal').addEventListener('click',prepareCompose);
function setQuickMenu(open){$('quick-menu').hidden=!open;$('glass-plus').setAttribute('aria-expanded',String(open));$('glass-plus').classList.toggle('open',open);}
$('glass-plus').addEventListener('click',()=>setQuickMenu($('quick-menu').hidden));
// The Ask bar drafts a proposal from what you typed. Nothing is sent until you review it.
$('home-ask')?.addEventListener('submit',event=>{event.preventDefault();const typed=$('home-ask-input').value.trim();prepareCompose();const form=$('compose-form');if(!$('compose-dialog').open)return;if(typed){form.elements.title.value=typed.slice(0,120);form.elements.text.value='SYNTHETIC ONLY: '+typed;}$('home-ask-input').value='';});
$('quick-menu').addEventListener('click',event=>{const choice=event.target.closest('[data-quick]')?.dataset.quick;if(!choice)return;setQuickMenu(false);if(choice==='proposal')prepareCompose();else if(choice==='team')openTeamDialog();else if(choice==='mission')navigate('conversations');else if(choice==='invite')openInviteDialog();else if(choice==='join')openJoinDialog();else{navigate('peers');openPeerDialog();}});$('add-peer').addEventListener('click',openPeerDialog);
document.querySelectorAll('[data-view]').forEach(node=>node.addEventListener('click',()=>navigate(node.dataset.view)));
document.querySelectorAll('[data-filter]').forEach(node=>node.addEventListener('click',()=>{if(busy)return;currentFilter=node.dataset.filter;render();}));
document.querySelectorAll('.close-dialog').forEach(node=>node.addEventListener('click',()=>{if(busy)return;node.closest('dialog').close();selected=null;selectedWorkflow=null;selectedTransfer=null;}));
document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();else{selected=null;selectedWorkflow=null;selectedTransfer=null;}}));
$('proposal-kind').addEventListener('change',configureKind);$('proposal-parent').addEventListener('change',selectParent);
$('compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending())return;const form=event.currentTarget;const fields=Object.fromEntries(new FormData(form));fields.peer_id=form.elements.peer_id.value;
  if(fields.kind==='artifact')fields.parent_expires=state.items.find(item=>item.id===fields.parent_id)?.expires;
  try {
    let path='/api/proposals', body;
    if(fields.kind==='mission'){
      if(fields.synthetic!=='on')throw new Error('Confirm that you may share this fictional brief.');
      const criterion=fields.mission_check==='max_utf8_bytes'?Number(fields.mission_value):fields.mission_value;
      const cap=toMicro(fields.mission_budget);if(cap===null)throw new Error('Enter a spending limit such as 0.50.');
      path='/api/mission-offers';
      body={agreed:{goal:fields.title,deliverable:fields.mission_deliverable,executor:fields.peer_id,
        criteria:[{kind:fields.mission_check,value:criterion}],cap_micro:cap,currency:fields.mission_currency},
        brief:fields.text,task_id:fields.task_id,expires:Math.floor(Date.now()/1000)+Number(fields.minutes)*60,permit_fixture:fields.synthetic_run==='on'};
    }else body=proposalBody(fields);
    await performWrite(path,body,{target:'compose-message',onSuccess:()=>{$('compose-dialog').close();currentView='outbox';currentFilter='all';searchQuery='';$('search-input').value='';history.replaceState(null,'','#outbox');render();notice('Proposal prepared. Open it to review the exact content before release.',true);}});}catch(error){$('compose-message').textContent=error.message;}
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
  const next=viewFromHash(location.hash);leaveForHome(next);
  currentView=next;currentFilter='all';searchQuery='';$('search-input').value='';
  inspect.navigated();setNavigation(false);render();
}
window.addEventListener('popstate',restoreLocation);
window.addEventListener('hashchange',restoreLocation);
window.addEventListener('focus',()=>{if(token&&['conversations','host-drafts','approvals'].includes(currentView)&&!document.hidden&&!busy)render();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&token&&['conversations','host-drafts','approvals'].includes(currentView)&&!busy)render();});
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
  if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();if(mobileNavigation.matches)setNavigation(true);$('search-input').focus();$('search-input').select();}
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
    $('review-decide').hidden=true;$('review-decide').replaceChildren();$('review-title').textContent=selection.kind==='quarantine'?'Inspect selected import':'Inspect exact transfer';$('review-eyebrow').textContent='TRANSPORT ONLY';$('review-state').replaceChildren(text('span',selection.kind==='quarantine'?'Untrusted quarantine':review.outbox?.state==='received'?'Signed receipt observed':'No owner acceptance implied','badge uncertain'));
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

// Invite links ---------------------------------------------------------------------------
// One person makes a link (or shows its QR code); the other opens it in their own Parlu. Both
// check the same short code, and the person who made the link adds the other. Joining never
// agrees to any work, and nothing here needs a model or an AI key.
const OWNER_SENDS=/^\/api\/items\/[A-Za-z0-9_.-]{1,128}\/(?:release|decision|cancel)$/;
let joinReview=null,relayBusy=false;
function joinWho(owner,agent,line){const who=text('div','','join-person');who.append(ownerPair(owner,agent,'owner-pair','look'));const words=text('div','');words.append(text('strong',`${owner} and ${agent}`),text('span',line,'item-meta'));who.append(words);return who;}
function factList(list,rows){list.replaceChildren();for(const [label,value] of rows)list.append(text('dt',label),text('dd',value));}
function drawQr(holder,link){
  holder.replaceChildren();
  let drawn;try{drawn=qrPath(qrMatrix(link));}catch{holder.append(text('p','The link is too long for a QR code. Copy it instead.','scope-note'));return;}
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${drawn.size} ${drawn.size}`);svg.setAttribute('shape-rendering','crispEdges');svg.setAttribute('aria-hidden','true');
  const back=document.createElementNS(ns,'rect');back.setAttribute('width',drawn.size);back.setAttribute('height',drawn.size);back.setAttribute('fill','#fff');
  const marks=document.createElementNS(ns,'path');marks.setAttribute('d',drawn.path);marks.setAttribute('fill','#1b1a17');svg.append(back,marks);holder.append(svg);
}
function openInviteDialog(){
  if(busy||uncertainty.pending()||!state)return;
  if(!relayEnabled(state)){notice('This copy of Parlu has no relay set up. Start it with --relay to make invite links.');return;}
  $('invite-form').reset();$('invite-message').textContent='';$('invite-copied').textContent='';
  $('invite-make').hidden=false;$('invite-ready').hidden=true;$('invite-submit').hidden=false;$('invite-copy').hidden=true;$('invite-title').textContent='Invite someone';
  openDialog('invite-dialog');
}
function showInviteReady(invite){
  $('invite-make').hidden=true;$('invite-ready').hidden=false;$('invite-submit').hidden=true;$('invite-copy').hidden=false;
  $('invite-title').textContent=invite.label?`An invite for ${invite.label}`:'Your invite is ready';
  drawQr($('invite-qr'),invite.link);$('invite-code').textContent=invite.code;$('invite-link').value=invite.link;$('invite-expires').textContent=expiresIn(invite.join_by);
  $('invite-copied').textContent='';
}
$('invite-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending()||!$('invite-ready').hidden)return;
  const form=event.currentTarget,epoch=generation,release=operations.acquire();$('invite-message').textContent='';
  try{
    const made=await request('/api/invites',{method:'POST',body:{label:form.elements.label.value.trim(),hours:Number(form.elements.hours.value)}});
    if(epoch!==generation)return;
    if(made.made!==true){$('invite-message').textContent=joinProblem('relay_'+made.relay);return;}
    if(!inviteFromText(made.link)||typeof made.code!=='string')throw new RequestFailure('The invite could not be checked. Try again.');
    showInviteReady(made);await refresh();
  }catch(error){if(epoch===generation)handleFailure(error,'invite-message');}
  finally{release();}
});
$('invite-copy').addEventListener('click',async()=>{
  const field=$('invite-link');
  try{await navigator.clipboard.writeText(field.value);$('invite-copied').textContent='Link copied. Send it to them, then check the code together.';}
  catch{field.focus();field.select();$('invite-copied').textContent='Press Ctrl+C or ⌘C to copy the selected link.';}
});
async function showInviteAgain(invite){
  if(busy||uncertainty.pending())return;const epoch=generation;
  try{const again=await request(`/api/invites/${invite.id}`);if(epoch!==generation)return;openInviteDialog();if($('invite-dialog').open)showInviteReady(again);}
  catch(error){if(epoch===generation)handleFailure(error);}
}
function openJoinDialog(carried=''){
  if(busy||uncertainty.pending()||!state)return;
  if(!relayEnabled(state)){notice('This copy of Parlu has no relay set up. Start it with --relay to join with a link.');return;}
  joinReview=null;$('join-form').reset();$('join-message').textContent='';$('join-paste').hidden=false;$('join-review').hidden=true;$('join-submit').textContent='Check the link';
  openDialog('join-dialog');
  if(carried&&$('join-dialog').open){$('join-link').value=carried;$('join-form').requestSubmit();}
}
$('join-link').addEventListener('input',()=>{joinReview=null;$('join-message').textContent='';});
$('join-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||uncertainty.pending())return;
  const epoch=generation,release=operations.acquire();$('join-message').textContent='';
  try{
    if(!joinReview){
      const link=inviteFromText($('join-link').value);
      if(!link){$('join-message').textContent='That does not look like a Parlu invite link. Paste the whole address, including the part after #.';return;}
      const review=await request('/api/invites/open',{method:'POST',body:{link}});
      if(epoch!==generation)return;
      const owner=cap(plain(review.inviter?.owner_id,'Someone')),agent=plain(review.inviter?.agent_id,'their assistant');
      if(review.ok!==true){$('join-message').textContent=joinProblem(review.reason,owner);return;}
      joinReview={link,review,owner};
      $('join-paste').hidden=true;$('join-review').hidden=false;$('join-title').textContent=`Join ${owner}`;
      $('join-who').replaceChildren(joinWho(owner,agent,review.label?`Invite: ${review.label}`:'invites you to connect'));
      $('join-code').textContent=review.code;
      $('join-check').textContent=`Ask ${owner} which code they see. Join only if it is the same.`;
      factList($('join-facts'),[['Shares',`Your name, ${plain(state.identity.agent_id,'your assistant')}'s name and its public keys, with ${owner} only.`],
        ['Keeps','Everything else. Joining never agrees to any work: every proposal still needs your own yes.'],
        ['Through',`The relay at ${review.relay_host}. It carries sealed packets and cannot read them.`],
        ...(review.known?[['Already',`${owner} is already in your assistants. Joining adds a link through the relay.`]]:[])]);
      $('join-submit').textContent=`Join ${owner}`;$('join-submit').focus();return;
    }
    const {link,review,owner}=joinReview;
    const joined=await request('/api/invites/accept',{method:'POST',body:{link,review_digest:review.review_digest}});
    if(epoch!==generation)return;
    if(joined.joined!==true){$('join-message').textContent=joinProblem(joined.reason,owner);await refresh();return;}
    joinReview=null;$('join-dialog').close();
    notice(`Sent. ${owner} adds you when they see your request, and both of you will see the same code.`,true);
    await refresh();
  }catch(error){if(epoch===generation)handleFailure(error,'join-message');}
  finally{release();}
});
function openJoinerPanel(joiner){
  if(!joiner)return;
  const o=cap(plain(joiner.owner_id,'Someone')),a=plain(joiner.agent_id,'their assistant');
  showPanel('joiner:'+joiner.invite_id,`${o} wants to connect`,`${a}, ${o}'s assistant`,body=>{
    body.append(joinWho(o,a,joiner.label?`Used your invite for ${joiner.label}`:'Used your invite'));
    const check=panelSection(body,'Check the code');check.append(text('div',joiner.code,'pair-code'));
    check.append(text('p',`Ask ${o} which code they see. Add them only if it is the same.`,'inspect-note'));
    const keys=panelSection(body,'Keys');panelRow(keys,'Fingerprint',joiner.fingerprint,true);
    const scope=panelSection(body,'What adding does');
    panelRow(scope,'Shares',`Your name, your assistant's name and its public keys, with ${o} only.`);
    panelRow(scope,'Keeps','Everything else. Each proposal from them still needs your own yes.');
    const actions=text('div','','inspect-actions');
    actions.append(button(`Add ${o} and ${a}`,'button primary',()=>decideJoiner(joiner,'add')),button('Decline','button secondary',()=>decideJoiner(joiner,'decline')));
    body.append(actions);
  },()=>{const next=state?.relay?.joiners?.find(entry=>entry.invite_id===joiner.invite_id);if(next)openJoinerPanel(next);else inspect.hide({restoreFocus:false});});
}
function decideJoiner(joiner,decision){
  const o=cap(plain(joiner.owner_id,'them'));
  performWrite(`/api/invites/${joiner.invite_id}/joiner`,{decision,review_digest:joiner.review_digest},{onSuccess:result=>{
    inspect.hide({restoreFocus:false});
    if(result.decided!==true)notice(joinProblem(result.reason,o));
    else notice(result.added?`${o} is connected. You can send each other proposals now, and each one still needs a yes.`:`Declined. ${o} was not added.`,true);
  }});
}
function renderRelayStrip(){
  const relay=state.relay,strip=text('section','','relay-strip');
  const head=text('div','','relay-head'),words=text('div','');words.append(text('h3','Connect with someone','item-title'),text('p','Invite someone with a link or a QR code, or join with a link you were sent. No keys to copy.','relay-note'));
  const actions=text('div','','relay-actions');actions.append(button('Invite someone','button primary',openInviteDialog),button('Join with a link','button secondary',()=>openJoinDialog()));
  head.append(words,actions);strip.append(head);
  for(const joiner of relay.joiners){
    const o=cap(plain(joiner.owner_id,'Someone')),a=plain(joiner.agent_id,'Assistant'),row=text('div','','relay-row needs-you');
    row.append(ownerPair(o,a,'owner-pair','look'),text('span',`${o} and ${a} used ${joiner.label?`your invite for ${joiner.label}`:'your invite'}`),button('Check and add','button primary row-action',()=>openJoinerPanel(joiner)));strip.append(row);
  }
  for(const invite of relay.invites.filter(entry=>entry.state==='open')){
    const row=text('div','','relay-row'),label=text('span','');label.append(text('strong',invite.label||'Invite'),text('span',` · code ${invite.code} · ${expiresIn(invite.join_by)}`,'relay-note'));
    row.append(label,button('Show again','button secondary row-action',()=>showInviteAgain(invite)),button('Revoke','button secondary row-action',()=>performWrite(`/api/invites/${invite.id}/revoke`,{},{onSuccess:()=>notice('Invite revoked. Nobody can join with it now.',true)})));strip.append(row);
  }
  const line=syncLine(relay.last_sync);if(line)strip.append(text('p',line,'relay-sync'));
  $('item-list').append(strip);
}
// Fetching from the relay while you are signed in brings in joins, receipts and new items. It
// never accepts anything. Sending happens only when you release, decide or press Sync.
async function relaySync(send,{announce=false}={}){
  if(!token||!relayEnabled(state)||relayBusy||(send&&(busy||uncertainty.pending())))return;
  const epoch=generation;relayBusy=true;const release=send?operations.acquire():()=>{};
  try{
    const summary=await request('/api/relay/sync',{method:'POST',body:{send}});
    if(epoch!==generation)return;
    if(syncChanged(summary)||announce)await refresh();
    if(announce)notice(syncLine(summary),summary.relay==='ok');
    else if(summary.relay!=='ok'&&send)notice(syncLine(summary));
  }catch(error){if(epoch===generation&&(send||error.unauthorised))handleFailure(error);}
  finally{relayBusy=false;release();}
}
setInterval(()=>{if(document.visibilityState==='visible'&&!busy&&!uncertainty.pending())relaySync(false);},15000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&!busy&&!uncertainty.pending())relaySync(false);});
