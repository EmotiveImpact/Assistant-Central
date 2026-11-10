// Exact local owner review. Untrusted host text is never HTML or a model prompt.
const ID=/^[A-Za-z0-9_-]{1,64}$/, HEX=/^[a-f0-9]{64}$/;
const need=value=>{if(!value)throw new Error('Host draft state could not be verified.');};
const object=(value,keys)=>{need(value&&typeof value==='object'&&!Array.isArray(value));need(Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k)));};
const textValue=(value,max)=>{need(typeof value==='string'&&value.length>0&&value.length<=max&&value.isWellFormed()&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/u.test(value));};
const date=value=>need(Number.isSafeInteger(value)&&value>0);
const state=value=>need(['awaiting_owner_review','dismissed'].includes(value));
export function validateDraftQueue(value){
  object(value,['connections','local_only','execution_authority']);need(value.local_only===true&&value.execution_authority===false&&Array.isArray(value.connections)&&value.connections.length<=8);
  const ids=new Set();
  for(const c of value.connections){object(c,['id','available','items']);need(ID.test(c.id)&&!ids.has(c.id)&&typeof c.available==='boolean'&&Array.isArray(c.items)&&c.items.length<=32);ids.add(c.id);if(!c.available)need(c.items.length===0);
    const drafts=new Set();for(const item of c.items){object(item,['draftId','title','state']);need(ID.test(item.draftId)&&!drafts.has(item.draftId));drafts.add(item.draftId);textValue(item.title,160);state(item.state);}
  }return value;
}
export function validateDraftReview(value,draftId,principal){
  object(value,['draft','status','binding','digest','reviewToken','reviewExpiresAt','decision']);
  object(value.draft,['requestId','title','instruction']);need(ID.test(value.draft.requestId));textValue(value.draft.title,160);textValue(value.draft.instruction,4000);
  const s=value.status;object(s,['draftId','state','ownerConsent','transportReceipt','execution']);need(s.draftId===draftId&&ID.test(draftId)&&s.ownerConsent==='not_requested'&&s.transportReceipt==='none'&&s.execution==='not_started');state(s.state);
  const b=value.binding;object(b,['ownerId','hostId','sessionId','conversationId','recipientId','expiresAt']);need(HEX.test(b.ownerId)&&b.ownerId===principal);for(const k of ['hostId','sessionId','conversationId','recipientId'])need(ID.test(b[k]));date(b.expiresAt);
  need(HEX.test(value.digest));textValue(value.reviewToken,2048);date(value.reviewExpiresAt);need(value.reviewExpiresAt<=b.expiresAt);
  if(s.state==='dismissed'){object(value.decision,['decisionId','digest','decision']);need(ID.test(value.decision.decisionId)&&value.decision.digest===value.digest&&value.decision.decision==='dismissed');}else need(value.decision===null);
  return value;
}
function node(tag,value='',classes=''){const n=document.createElement(tag);n.textContent=String(value);n.className=classes;return n;}
function button(label,fn,kind='secondary'){const n=node('button',label,'button '+kind);n.type='button';n.addEventListener('click',fn);return n;}
export function createHostDrafts({request,busy,setBusy,failed,active,session,owner,unknownFailure,restore}){
  let epoch=0,root=null,queue=null,selected=null,lease=null,expiryTimer=null;
  const dialog=node('dialog','','review-dialog');dialog.id='host-draft-dialog';dialog.setAttribute('aria-labelledby','host-draft-review-title');document.body.append(dialog);
  const clearReview=()=>{selected=null;clearTimeout(expiryTimer);expiryTimer=null;if(dialog.open)dialog.close();dialog.replaceChildren();};
  dialog.addEventListener('close',clearReview);
  dialog.addEventListener('cancel',event=>{if(busy())event.preventDefault();else clearReview();});
  function reset({sessionEnded=false}={}){epoch++;clearReview();if(root)root.replaceChildren();root=null;queue=null;if(sessionEnded&&lease){lease=null;setBusy(false);}}
  async function load(){const stamp=epoch;const value=validateDraftQueue(await request('/api/host-drafts'));if(stamp===epoch&&active())queue=value;}
  async function run(fn,{write=false}={}){
    if(busy()||!root||!active())return;
    const stamp=epoch,sessionStamp=session(),currentLease={};lease=currentLease;setBusy(true);
    const current=()=>stamp===epoch&&sessionStamp===session()&&active();
    try{await fn(current);}
    catch(error){if(current()){clearReview();root.replaceChildren(node('p','Host draft access unavailable. Refresh saved state before deciding.','scope-note'));queue=null;failed(error);}}
    finally{if(lease===currentLease){lease=null;setBusy(false);}if(write&&stamp!==epoch&&sessionStamp===session())failed(unknownFailure('The dismiss request finished after its view was closed. Refresh saved state to inspect the result.'));if(!root&&!document.hidden&&sessionStamp===session()&&active())restore();}
  }
  const route=(connection,id)=>`/api/host-drafts/${connection}/${id}`;
  function render(){
    if(!root||!queue||!active())return;root.replaceChildren();
    const section=node('section','','host-draft-section');section.append(node('h2','Host task drafts'),node('p','These drafts came from a configured local host. Saving a draft is not owner notification, task consent, delivery or execution. You can inspect it and dismiss it. Nothing is sent or started here. Review is available only during the original host lease, at most 15 minutes; this is not a persistent owner archive.','scope-note'));
    section.append(button('Refresh host drafts',()=>run(async current=>{clearReview();await load();if(current())render();})));
    if(!queue.connections.length)section.append(node('p','No host draft connections are configured for this authenticated owner.','scope-note'));
    for(const connection of queue.connections){const group=node('section','','host-draft-group');group.append(node('h3',connection.id));
      if(!connection.available){group.append(node('p','This host binding is unavailable, expired or revoked. Retained drafts cannot be inspected here; this is not an empty successfully checked queue.','scope-note'));section.append(group);continue;}
      if(!connection.items.length)group.append(node('p','No drafts in this current host session.','scope-note'));
      for(const item of connection.items){const row=node('article','','item-row');row.dataset.draftId=item.draftId;row.append(node('strong',item.title),node('span',item.state==='dismissed'?'Dismissed':'Awaiting owner review','badge'));
        row.append(button('Inspect draft',()=>run(async current=>{const review=validateDraftReview(await request(route(connection.id,item.draftId)+'/review'),item.draftId,owner());if(current())showReview(connection.id,review);})));group.append(row);}
      section.append(group);
    }root.append(section);
  }
  function showReview(connection,review){
    clearReview();selected=review;const header=node('header','','dialog-header'),title=node('h2',review.draft.title);title.id='host-draft-review-title';header.append(title,button('Close host draft review',clearReview));
    const body=node('div','','dialog-body'),details=node('dl','','review-details');
    for(const [label,value] of [['Owner fingerprint',review.binding.ownerId],['Host',review.binding.hostId],['Host session',review.binding.sessionId],['Conversation',review.binding.conversationId],['Fixed recipient',review.binding.recipientId],['Host lease expires',new Date(review.binding.expiresAt).toISOString()],['Exact review expires',new Date(review.reviewExpiresAt).toISOString()],['Draft ID',review.status.draftId],['Request ID',review.draft.requestId],['Exact review digest',review.digest]])details.append(node('dt',label),node('dd',value));
    body.append(node('p',review.status.state==='dismissed'?'This exact draft was dismissed. Its saved decision is retained.':'Exact untrusted host draft. Inspect the complete content and fixed bindings.','scope-note'),details,node('pre',review.draft.instruction,'artifact-content'),node('p','Dismissal records only a local review decision. It does not approve a task, contact the recipient, share history, deliver a proposal or execute a tool.','scope-note'));
    dialog.append(header,body);
    if(review.status.state==='dismissed'){const receipt=node('p','Saved dismissal: '+review.decision.decisionId,'peer-fingerprint');body.append(receipt);}
    else if(review.reviewExpiresAt>Date.now()){
      const footer=node('footer','','dialog-footer'),label=node('label','','check-label'),check=node('input');check.type='checkbox';check.id='host-draft-dismiss-confirm';label.append(check,node('span','Dismiss only this exact draft.'));
      const dismiss=button('Dismiss exact draft',()=>{if(!check.checked||selected!==review||Date.now()>=review.reviewExpiresAt)return;
        run(async current=>{let returned=false;try{await request(route(connection,review.status.draftId)+'/dismiss',{method:'POST',body:{digest:review.digest,reviewToken:review.reviewToken}});returned=true;if(!current())return;clearReview();await load();if(current())render();}
          catch(error){throw returned&&!error.unauthorised?unknownFailure('The dismissal returned, but its saved state could not be inspected. Refresh before acting again.'):error;}},{write:true});},'danger');
      footer.append(label,dismiss);dialog.append(footer);
      expiryTimer=setTimeout(()=>{if(selected===review){clearReview();if(root)root.prepend(node('p','The exact review expired. Inspect the draft again before deciding.','scope-note'));}},Math.max(0,review.reviewExpiresAt-Date.now()));
    }else body.append(node('p','This review has expired. Close it and inspect the current draft again.','scope-note'));
    dialog.showModal();
  }
  function mount(target,enabled){reset();root=target;
    if(!enabled){root.append(node('p','Host draft review is disabled. A trusted local host must explicitly configure an existing owner fingerprint and current bridge binding. No live assistant account is connected.','scope-note'));return;}
    const stamp=epoch;root.append(node('p','Checking this owner’s current host drafts…','scope-note'));
    (async()=>{try{await load();if(stamp===epoch&&active())render();}catch(error){if(stamp===epoch){root.replaceChildren(node('p','Host draft access unavailable. Refresh saved state.','scope-note'));failed(error);}}})();
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&root)reset();});
  return {mount,reset};
}
