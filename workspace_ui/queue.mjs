// One queue of everything that needs you, worked out from saved state and read-only listings.
// Pure, so Home and the tests agree. Nothing here decides anything: each entry names the
// place where the exact decision is made, and Home only opens it.
const clip=(value,max=90)=>{const t=String(value??'').replace(/\s+/g,' ').trim();return t.length>max?t.slice(0,max-1)+'…':t;};

export function homeQueue({proposals=[],approvals=null,hostDrafts=null,conversations=null,joiners=[]}={}){
  const queue=proposals.map(item=>({kind:'proposal',key:'item:'+item.id,item,title:clip(item.title,120)||'Untitled proposal'}));
  // Someone used one of your invites: nothing is added until you check them and say yes.
  for(const j of joiners)queue.push({kind:'joiner',key:j.key,joiner:j.joiner,title:clip(j.title),view:'peers',owner:j.owner,agent:j.agent});
  if(approvals){
    for(const q of approvals.questions??[])queue.push({kind:'question',key:'question:'+q.question_id,title:clip(q.question),view:'approvals'});
    for(const m of approvals.messages??[])queue.push({kind:'message',key:'message:'+m.draft_id,title:clip(m.text),view:'approvals'});
    for(const d of approvals.drafts??[])queue.push({kind:'shared-draft',key:'draft:'+d.draft_id,title:clip(d.text),view:'approvals'});
  }
  if(conversations){
    for(const i of conversations.invitations??[]){
      if(i.principal!==conversations.principal)continue;
      const admin=(conversations.actors??[]).find(a=>a.principal===i.admin);
      queue.push({kind:'invite',key:'invite:'+i.id,title:clip(i.conversation_id),view:'conversations',owner:admin?.owner_id,agent:admin?.agent_id});
    }
  }
  if(hostDrafts){
    for(const c of hostDrafts.connections??[])for(const d of c.items??[]){
      if(d.state==='awaiting_owner_review')queue.push({kind:'host-draft',key:`host:${c.id}:${d.draftId}`,title:clip(d.title),view:'host-drafts'});
    }
  }
  return queue;
}

// A listing can answer and still say that part of it could not be checked: shared drafts the
// host has not opened yet, or an app whose connection has lapsed. Those parts are named, so
// Home never reads them as an empty queue.
export function uncheckedParts({approvals=null,hostDrafts=null}={}){
  const parts=[];
  if(approvals&&approvals.drafts_available===false)parts.push('shared drafts');
  if((hostDrafts?.connections??[]).some(connection=>connection.available===false))parts.push('one of your apps');
  return parts;
}

// The words on a card: what is being asked, and the one button that opens the decision.
export const CARD=Object.freeze({
  proposal:{lead:'',action:'Review and agree'},
  question:{lead:'asked you a question',action:'Answer it'},
  message:{lead:'wants to send a message for you',action:'Check the message'},
  'shared-draft':{lead:'A shared draft waits for your agreement',action:'Read the draft'},
  invite:{lead:'invited you to a conversation',action:'See the invitation'},
  joiner:{lead:'used your invite and asks to connect',action:'Check and add'},
  'host-draft':{lead:'A draft arrived from one of your apps',action:'Inspect the draft'},
});

// Who is asking. Your own assistant asks questions and proposes messages; a shared draft
// and an app draft have no single author to name, so the card says what it is instead.
export function askerOf(entry,{me,mine,peer}={}){
  if(entry.kind==='proposal')return {owner:peer?.owner_id||'Someone',agent:peer?.agent_id||'Their assistant',yours:false};
  if(entry.kind==='invite'||entry.kind==='joiner')return {owner:entry.owner||'Someone',agent:entry.agent||'Their assistant',yours:false};
  return {owner:me||'You',agent:mine||'Your assistant',yours:true};
}

// "and 2 more wait for you", or the honest single-item ending.
export function moreLine(count){
  if(count<=1)return ' and it needs your decision. ';
  return ` and ${count-1} more ${count===2?'waits':'wait'} for you. `;
}

// The closing sentence never claims "nothing else" for a place it could not check.
export function closingLine(failed=[]){
  if(!failed.length)return 'Nothing else needs you.';
  const places=failed.length===1?failed[0]:failed.slice(0,-1).join(', ')+' and '+failed.at(-1);
  return `I couldn’t check ${places} just now.`;
}
