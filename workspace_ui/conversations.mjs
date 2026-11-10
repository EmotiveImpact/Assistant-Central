import {operationGate} from './operations.mjs';
export {operationGate} from './operations.mjs';
// Trusted local-host owner controls. Text stays inert; no model receives history.
const ID=/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/, HEX=/^[a-f0-9]{64}$/;
const assert=(value)=>{if(!value)throw new Error('Conversation state could not be verified.');};
const list=(value,max)=>{assert(Array.isArray(value)&&value.length<=max);return value;};
export function validateCatalogue(value){
  assert(value?.local_host_only===true&&value.audience==='local-owner-only'&&value.execution_authority===false&&HEX.test(value.principal));
  list(value.actors,32).forEach(a=>assert(HEX.test(a.principal)&&typeof a.owner_id==='string'&&a.owner_id.length<=64&&typeof a.agent_id==='string'&&a.agent_id.length<=64));
  assert(value.actors.some(a=>a.principal===value.principal));
  list(value.rooms,256).forEach(r=>assert(ID.test(r.id)&&HEX.test(r.admin)&&['direct','group'].includes(r.mode)));
  list(value.invitations,50).forEach(i=>assert(ID.test(i.id)&&ID.test(i.conversation_id)&&HEX.test(i.principal)&&HEX.test(i.admin)));
  return value;
}
export function validateRoom(value,id,principal){
  assert(value?.id===id&&HEX.test(value.admin)&&['direct','group'].includes(value.mode));
  const b=value.binding;assert(b?.conversation_id===id&&b.principal===principal&&ID.test(b.member_epoch)&&Number.isSafeInteger(b.policy_generation)&&b.policy_generation>0);
  list(value.participants,32).forEach(p=>assert(HEX.test(p.principal)&&ID.test(p.epoch)));
  assert(value.participants.some(p=>p.principal===principal&&p.epoch===b.member_epoch));return value;
}
export function validateMessages(messages,id){
  list(messages,25).forEach(m=>{assert(ID.test(m.id)&&m.conversation_id===id&&HEX.test(m.author)&&HEX.test(m.provenance_digest)&&m.trust==='untrusted-message'&&m.execution_authority===false&&['message','quote','summary'].includes(m.kind)&&typeof m.text==='string'&&new TextEncoder().encode(m.text).length<=16384);list(m.sources,32).forEach(s=>assert(ID.test(s.id)&&HEX.test(s.digest)));});
  assert(new Set(messages.map(m=>m.id)).size===messages.length);return messages;
}
export function validateHistoryReview(value,room,principal,recipient,ids){
  const s=value?.statement;assert(s?.domain==='assistant-central-conversation/1/history-grant'&&ID.test(s.id)&&s.conversation_id===room.id&&s.issuer===principal&&s.recipient===recipient&&s.audience==='local-owner-only'&&s.policy_generation===room.binding.policy_generation&&s.member_epoch===room.participants.find(p=>p.principal===recipient)?.epoch&&HEX.test(value.review_digest)&&value.execution_authority===false&&value.recipient?.principal===recipient&&typeof s.purpose==='string'&&s.purpose.length<=512&&Number.isFinite(s.expires_at));
  validateMessages(value.messages,room.id);list(s.events,25);assert(s.events.length===ids.length&&value.messages.length===ids.length);
  s.events.forEach((e,i)=>assert(e.id===ids[i]&&e.id===value.messages[i].id&&e.digest===value.messages[i].provenance_digest&&value.messages[i].author===principal));return value;
}
function node(tag,text='',className=''){const e=document.createElement(tag);e.textContent=String(text);e.className=className;return e;}
function btn(label,action,kind='secondary'){const b=node('button',label,'button '+kind);b.type='button';b.addEventListener('click',action);return b;}
function field(label,input){const e=node('label',label);e.append(input);return e;}
function select(options){const s=node('select');for(const [value,label] of options){const o=node('option',label);o.value=value;s.append(o);}return s;}

// Passive refresh may keep only an unsent draft for this exact audience.
export function nextComposer(previous,context,{passive=false}={}){
  if(passive&&previous?.submitted)return null;
  if(passive&&previous&&['session','principal','conversationId','memberEpoch','policyGeneration'].every(key=>previous.context[key]===context[key]))return previous;
  return {context:{...context},requestId:crypto.randomUUID().replaceAll('-',''),text:'',submitted:false};
}

// Match pilot.crypto.canonical exactly: fixed sorted keys, UTF-8, no Unicode
// normalisation. TextEncoder replaces unpaired surrogates, while Python refuses
// them, so reject those before either hashing or dispatching the original send.
export function canonicalMessageRequest({kind='message',text,source_ids=[]}){
  assert(['message','quote','summary'].includes(kind)&&typeof text==='string');
  for(let i=0;i<text.length;i++){
    const code=text.charCodeAt(i);
    if(code>=0xd800&&code<=0xdbff){const next=text.charCodeAt(++i);assert(next>=0xdc00&&next<=0xdfff);}
    else assert(code<0xdc00||code>0xdfff);
  }
  assert(text.length>0&&new TextEncoder().encode(text).length<=16384);
  list(source_ids,32).forEach(id=>assert(typeof id==='string'&&ID.test(id)));
  assert(new Set(source_ids).size===source_ids.length&&(kind==='message'||source_ids.length>0));
  return JSON.stringify({kind,source_ids,text});
}
export async function messageRequestDigest(value){
  const bytes=new TextEncoder().encode(canonicalMessageRequest(value));
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(hash),byte=>byte.toString(16).padStart(2,'0')).join('');
}
function validateMessageOperation(operation){
  assert(operation?.type==='message-outcome'&&Number.isSafeInteger(operation.session)&&typeof operation.principal==='string'&&HEX.test(operation.principal)&&typeof operation.conversationId==='string'&&ID.test(operation.conversationId)&&typeof operation.memberEpoch==='string'&&ID.test(operation.memberEpoch)&&Number.isSafeInteger(operation.policyGeneration)&&operation.policyGeneration>0&&typeof operation.requestId==='string'&&ID.test(operation.requestId)&&typeof operation.requestDigest==='string'&&HEX.test(operation.requestDigest));
  return operation;
}
export async function prepareMessageOperation(context,requestId,text){
  const {session,principal,conversationId,memberEpoch,policyGeneration}=context;
  const requestDigest=await messageRequestDigest({text});
  // Explicitly select bounded fields. Never retain the composer, plaintext,
  // token, source event payloads or a mutable binding in the recovery ticket.
  return Object.freeze(validateMessageOperation({type:'message-outcome',session,principal,conversationId,memberEpoch,policyGeneration,requestId,requestDigest}));
}
export async function inspectMessageOutcome({request,session,operation}){
  if(operation?.type!=='message-outcome')return false;
  validateMessageOperation(operation);
  const stamp=session();if(operation.session!==stamp)return false;
  const result=await request(`/api/conversations/${operation.conversationId}/message-outcome`,{method:'POST',readOnly:true,body:{binding:{member_epoch:operation.memberEpoch,policy_generation:operation.policyGeneration},request_id:operation.requestId,expected_request_digest:operation.requestDigest}});
  if(stamp!==session())return false;
  if(result?.status==='inconclusive'){assert(Object.keys(result).length===1);return false;}
  assert(result?.status==='committed'&&Object.keys(result).length===2);
  const event=validateMessages([result.event],operation.conversationId)[0];
  assert(event.author===operation.principal);
  const digest=await messageRequestDigest({kind:event.kind,text:event.text,source_ids:event.sources.map(source=>source.id)});
  assert(digest===operation.requestDigest);
  // The inspected words never enter a DOM, cache or retained controller state.
  return stamp===session();
}
export async function inspectMutation(write,inspect,unknownFailure){
  let returned=false;
  try{await write();returned=true;return await inspect();}
  catch(error){throw returned&&!error.unauthorised?unknownFailure('The operation returned, but its saved state could not be inspected. Refresh before acting again.'):error;}
}
export function createConversations({request,busy,uncertain=()=>false,setBusy,gate=operationGate(setBusy),failed,active,unknownFailure,session,restore}){
  let epoch=0,root=null,catalogue=null,room=null,messages=[],query='',after=null,timer=null,review=null,composer=null;
  const dialog=document.getElementById('conversation-dialog');
  const clearDialog=()=>{review=null;dialog.replaceChildren();if(dialog.open)dialog.close();};
  dialog.addEventListener('close',clearDialog);
  dialog.addEventListener('cancel',e=>{if(busy())e.preventDefault();else clearDialog();});
  function reset({sessionEnded=false}={}){epoch++;if(sessionEnded)gate.reset();clearTimeout(timer);timer=null;composer=null;catalogue=null;room=null;messages=[];query='';after=null;clearDialog();if(root)root.replaceChildren();root=null;}
  function name(p){const a=catalogue?.actors.find(a=>a.principal===p);return a?`${a.owner_id} · ${a.agent_id}`:p;}
  function binding(){return {member_epoch:room.binding.member_epoch,policy_generation:room.binding.policy_generation};}
  const route=(suffix='')=>`/api/conversations/${room.id}${suffix}`;
  async function run(action,{write=false,operation=null}={}){
    if(busy()||(write&&uncertain())||!root||!active())return;
    const stamp=epoch,sessionStamp=session(),release=gate.acquire(),tracked={operation,dispatched:false};
    try{await action(()=>stamp===epoch&&sessionStamp===session()&&active(),tracked);}
    catch(error){if(stamp===epoch&&sessionStamp===session()){clearDialog();root.replaceChildren(node('p','Conversation unavailable. Refresh to inspect current membership and coordinator unlock.','scope-note'));room=null;messages=[];composer=null;failed(error,tracked.operation);}}
    finally{release();if(write&&tracked.dispatched&&stamp!==epoch&&sessionStamp===session()){failed(unknownFailure('The action finished after its view was closed. Refresh saved state before acting again.'),tracked.operation);}if(!root&&!document.hidden&&sessionStamp===session()&&active())restore();}
  }
  async function loadRoom(id){
    const stamp=epoch,principal=catalogue.principal,q=query,cursor=after;
    const next=validateRoom(await request(`/api/conversations/${id}`),id,principal);
    if(stamp!==epoch)return;
    const b={member_epoch:next.binding.member_epoch,policy_generation:next.binding.policy_generation};
    const result=await request(`/api/conversations/${id}/history`,{method:'POST',readOnly:true,body:{binding:b,...(q?{query:q}:{}),...(cursor?{after:cursor}:{})}});
    if(stamp!==epoch)return;
    room=next;messages=validateMessages(result.messages,id);
  }
  async function load(){
    const selected=room?.id,stamp=epoch;
    const next=validateCatalogue(await request('/api/conversations'));
    if(stamp!==epoch)return;
    catalogue=next;
    if(selected&&catalogue.rooms.some(r=>r.id===selected))await loadRoom(selected);
    else {room=null;messages=[];query='';after=null;}
  }
  function schedule(){clearTimeout(timer);timer=setTimeout(()=>{if(!root||!active())return;if(busy()){schedule();return;}run(async current=>{const previous=JSON.stringify({catalogue,room,messages});await load();if(current()){if(previous!==JSON.stringify({catalogue,room,messages})){clearDialog();render({passive:true});}else schedule();}});},15000);}
  async function mutate(path,body,prepare=null){
    await run(async(current,tracked)=>{
      if(prepare){tracked.operation=await prepare();if(!current())return;}
      tracked.dispatched=true;
      await inspectMutation(()=>request(path,{method:'POST',body}),async()=>{if(!current())return;clearDialog();after=null;query='';await load();if(current())render();},unknownFailure);
    },{write:true,operation:prepare?null:Object.freeze({path,requestId:body.request_id||null,id:body.id||null,session:session()})});
  }
  function render({passive=false}={}){
    if(!root||!active())return;root.replaceChildren();
    const boundary=node('div','','conversation-boundary');boundary.append(node('strong','One trusted coordinating host'),node('p','Each person uses their own local owner password. The coordinating owner must remain signed in separately. This host can see authorised plaintext. These are local account identities, not verified people or independent remote assistants.'),node('p','Joining shares future messages only. History access here is local-owner-only and never permits model/provider disclosure.'));root.append(boundary);
    const toolbar=node('div','','conversation-toolbar');toolbar.append(btn('My issued history grants',()=>run(async current=>{const result=await request('/api/conversations/grants');list(result.grants,50);if(current())showGrants(result.grants,true);})),btn('New conversation',()=>mutate('/api/conversations',{id:crypto.randomUUID().replaceAll('-','')}),'primary'),btn('Refresh conversations',()=>run(async current=>{clearDialog();after=null;query='';await load();if(current())render();})));root.append(toolbar);
    const invitations=node('section','','conversation-invitations');invitations.append(node('h2','Invitations'));
    for(const i of catalogue.invitations){const row=node('div','','conversation-invite');row.append(node('p',`${name(i.admin)} → ${name(i.principal)} · ${i.conversation_id}`));if(i.principal===catalogue.principal)row.append(btn('Join future messages only',()=>mutate(`/api/conversations/invitations/${i.id}/accept`,{}),'primary'));row.append(btn(i.principal===catalogue.principal?'Decline invitation':'Cancel invitation',()=>mutate(`/api/conversations/invitations/${i.id}/cancel`,{})));invitations.append(row);}
    if(!catalogue.invitations.length)invitations.append(node('p','No pending invitations.'));
    else invitations.append(node('p','Latest 50 pending invitations. No earlier messages or message counts are disclosed.','scope-note'));
    root.append(invitations);
    const layout=node('div','','conversation-layout'),rooms=node('nav','','conversation-rooms');rooms.setAttribute('aria-label','Your conversations');
    for(const r of catalogue.rooms){const b=btn(`${r.mode==='group'?'Group':'Conversation'} · ${r.id.slice(0,8)}`,()=>run(async current=>{clearDialog();query='';after=null;await loadRoom(r.id);if(current())render();}));b.setAttribute('aria-current',String(room?.id===r.id));rooms.append(b);}
    if(!catalogue.rooms.length)rooms.append(node('p','Create a conversation or accept an invitation.'));
    layout.append(rooms);const panel=node('section','','conversation-room');layout.append(panel);root.append(layout);
    if(!room){composer=null;panel.append(node('h2','A conversation starts with permission.'),node('p','Choose a conversation. No previews are generated from inaccessible history.'));schedule();return;}
    panel.append(node('h2',room.mode==='group'?'Group conversation':'Direct conversation'),node('p',room.id,'peer-fingerprint'));
    const participants=node('ul','','conversation-participants');
    for(const p of room.participants){const row=node('li',name(p.principal));if(p.principal!==room.admin&&(room.admin===catalogue.principal||p.principal===catalogue.principal))row.append(btn(p.principal===catalogue.principal?'Leave conversation':'Remove member',()=>mutate(route('/remove'),{binding:binding(),recipient:p.principal}),'danger'));participants.append(row);}panel.append(participants);
    if(room.admin===catalogue.principal){const choices=catalogue.actors.filter(a=>!room.participants.some(p=>p.principal===a.principal));if(choices.length){const form=node('form','','conversation-inline'),recipient=select(choices.map(a=>[a.principal,name(a.principal)]));form.append(field('Invite an existing local owner',recipient),btn('Invite future messages only',()=>mutate(route('/invite'),{binding:binding(),recipient:recipient.value})));form.addEventListener('submit',e=>e.preventDefault());panel.append(form);}}
    const search=node('form','','conversation-inline'),input=node('input');input.type='search';input.maxLength=256;input.value=query;search.append(field('Search only visible history',input),btn('Search history',()=>run(async current=>{query=input.value.trim();after=null;await loadRoom(room.id);if(current())render();})));search.addEventListener('submit',e=>{e.preventDefault();search.querySelector('button').click();});panel.append(search);
    const history=node('div','','conversation-history');history.setAttribute('aria-label','Visible messages');const chosen=new Set();
    for(const m of messages){const item=node('article','','conversation-message');item.dataset.eventId=m.id;const check=node('input');check.type='checkbox';check.setAttribute('aria-label','Select message '+m.id);check.addEventListener('change',()=>check.checked?chosen.add(m.id):chosen.delete(m.id));item.append(field(name(m.author),check),node('p',m.text,'conversation-text'),node('small',m.id,'peer-fingerprint'));history.append(item);}
    if(!messages.length)history.append(node('p',query?'No visible messages match.':'No visible messages on this page. Earlier history is not shared automatically.'));panel.append(history);
    const paging=node('div','','conversation-toolbar');paging.append(btn('First page',()=>run(async current=>{after=null;await loadRoom(room.id);if(current())render();})));
    if(messages.length===25)paging.append(btn('Next visible page',()=>run(async current=>{after=messages.at(-1).id;await loadRoom(room.id);if(current())render();})));panel.append(paging);
    const context=btn('Inspect selected context',()=>run(async current=>{if(!chosen.size)return;const result=await request(route('/context'),{method:'POST',readOnly:true,body:{binding:binding(),event_ids:[...chosen]}});assert(result.audience==='local-owner-only'&&result.execution_authority===false&&result.conversation_id===room.id&&result.member_epoch===room.binding.member_epoch&&result.policy_generation===room.binding.policy_generation);validateMessages(result.messages,room.id);if(current())showDialog('Local owner context',result.messages,'This exact context is for this owner only. It is not sent to an assistant or model.');}));panel.append(context);
    composer=nextComposer(composer,{session:session(),principal:catalogue.principal,conversationId:room.id,memberEpoch:room.binding.member_epoch,policyGeneration:room.binding.policy_generation},{passive});
    if(composer){
      const currentComposer=composer,compose=node('form','','conversation-compose'),draft=node('textarea');draft.rows=4;draft.maxLength=16384;draft.required=true;draft.placeholder='Write to the current members…';draft.value=composer.text;
      draft.addEventListener('input',()=>{if(composer===currentComposer&&!currentComposer.submitted)currentComposer.text=draft.value;});
      const bound=binding();
      compose.append(field('Message to the members shown above',draft),node('p','Membership changes invalidate this draft. Refresh and review the new audience before sending.','scope-note'),btn('Send to current members',()=>{if(busy()||uncertain()||composer!==currentComposer||currentComposer.submitted||!compose.reportValidity()||!draft.value.trim())return;currentComposer.submitted=true;const text=draft.value;mutate(route('/message'),{binding:bound,request_id:currentComposer.requestId,text},()=>prepareMessageOperation(currentComposer.context,currentComposer.requestId,text));},'primary'));compose.addEventListener('submit',e=>e.preventDefault());panel.append(compose);
    }else panel.append(node('p','Inspect saved state before composing another message.','scope-note'));
    const share=node('section','','conversation-sharing');share.append(node('h3','Share your own earlier messages'),node('p','Select exact messages above. You cannot approve another author’s words. Derived sources need their own author permissions. Revocation stops future retrieval, not copies already seen.'));
    const recipients=room.participants.filter(p=>p.principal!==catalogue.principal);
    if(recipients.length){const form=node('form','','conversation-grant-form'),recipient=select(recipients.map(p=>[p.principal,name(p.principal)])),purpose=node('input'),minutes=select([['15','15 minutes'],['60','1 hour'],['1440','24 hours']]);purpose.maxLength=512;purpose.required=true;form.append(field('Exact recipient',recipient),field('Purpose',purpose),field('Access expires after',minutes),btn('Review exact history share',()=>{if(!form.reportValidity()||!chosen.size)return;const ids=[...chosen];if(ids.some(id=>messages.find(m=>m.id===id)?.author!==catalogue.principal)){failed(new Error('Select only your own messages.'));return;}run(async current=>{const r=validateHistoryReview(await request(route('/grant-review'),{method:'POST',readOnly:true,body:{binding:binding(),recipient:recipient.value,event_ids:ids,purpose:purpose.value,expires_at:Math.floor(Date.now()/1000)+Number(minutes.value)*60}}),room,catalogue.principal,recipient.value,ids);if(current())showGrant(r);});},'primary'));form.addEventListener('submit',e=>e.preventDefault());share.append(form);}
    share.append(btn('Inspect my history grants',()=>run(async current=>{const result=await request(route('/grants'));list(result.grants,50);if(current())showGrants(result.grants);})));panel.append(share);schedule();
  }
  function showDialog(title,items,scope){clearDialog();const header=node('header','','dialog-header');header.append(node('h2',title),btn('Close',clearDialog));const content=node('div','','dialog-body');content.append(node('p',scope,'scope-note'));for(const m of items){const a=node('article','','conversation-message');a.append(node('strong',name(m.author)),node('p',m.text,'conversation-text'),node('small',m.id,'peer-fingerprint'));content.append(a);}dialog.append(header,content);dialog.showModal();}
  function showGrant(value){showDialog('Review exact history share',value.messages,'Only these exact messages become available to the named local owner, in this membership epoch, until expiry. No provider disclosure.');review=value;const s=value.statement,details=node('dl','','detail-list');for(const [label,value] of [['Recipient',name(s.recipient)],['Recipient fingerprint',s.recipient],['Membership epoch',s.member_epoch],['Purpose',s.purpose],['Expires',new Date(s.expires_at*1000).toLocaleString()],['Review digest',value.review_digest]])details.append(node('dt',label),node('dd',value));const confirm=node('input');confirm.type='checkbox';confirm.id='history-confirm';const footer=node('footer','','dialog-footer');footer.append(field('I approve only these messages for this recipient.',confirm),btn('Approve exact history share',()=>{if(!confirm.checked||review!==value)return;mutate(`/api/conversations/grants/${s.id}/approve`,{review_digest:value.review_digest});},'primary'));dialog.querySelector('.dialog-body').prepend(details);dialog.append(footer);}
  function showGrants(grants,all=false){showDialog('My history grants',[],'Latest 50 grants issued by this owner. Revocation is available after leaving too, but cannot recall already disclosed copies.');const body=dialog.querySelector('.dialog-body');for(const g of grants){const s=g.statement;assert(s?.issuer===catalogue.principal&&(all||s.conversation_id===room.id)&&s.audience==='local-owner-only'&&ID.test(s.id)&&['active','expired','revoked','inactive-membership'].includes(g.status));const row=node('article','','conversation-message');row.append(node('strong',`${name(s.recipient)} · ${g.status}`),node('p',s.purpose),node('small','Conversation '+s.conversation_id,'peer-fingerprint'),node('small',s.id,'peer-fingerprint'));if(g.status!=='revoked')row.append(btn('Revoke this grant',()=>mutate(`/api/conversations/grants/${s.id}/revoke`,{}),'danger'));body.append(row);}if(!grants.length)body.append(node('p','No more grants issued by this owner.'));if(grants.length===50)body.append(btn('Next older grants',()=>run(async current=>{const result=await request('/api/conversations/grants/list',{method:'POST',readOnly:true,body:{after:grants.at(-1).statement.id,...(!all?{conversation_id:room.id}:{})}});list(result.grants,50);if(current())showGrants(result.grants,all);})));}
  function mount(target,enabled){reset();root=target;if(!active())return;if(!enabled){root.append(node('p','Conversations are disabled. The host can enable a private configuration of existing local owner accounts. No remote assistants are connected.','scope-note'));return;}
    const stamp=epoch;root.append(node('p','Checking current owner access…'));(async()=>{try{await load();if(stamp===epoch&&active())render();}catch(error){if(stamp===epoch){root.replaceChildren(node('p','Conversation access unavailable. The coordinating owner must keep an active session in a separate browser context. Refresh after they unlock.','scope-note'));failed(error);}}})();
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&root){reset();} });
  return {mount,reset};
}
