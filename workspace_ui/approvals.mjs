// One approval inbox: messages your assistant proposed, questions it asked,
// shared drafts waiting for you, and your own timeline. Text stays inert:
// everything is written with textContent and nothing here runs or sends on
// its own. Each decision is a separate request with the exact digest shown.
const ID=/^[A-Za-z0-9_-]{1,64}$/, HEX=/^[a-f0-9]{64}$/;
const assert=value=>{if(!value)throw new Error('Approval state could not be verified.');};
const list=(value,max)=>{assert(Array.isArray(value)&&value.length<=max);return value;};
const str=(value,max=16384)=>typeof value==='string'&&value.length<=max;

export const MODES=Object.freeze({
  review_each:'Ask me before every message',
  check_in:'Send on its own, but check in with me every few messages',
  within_limits:'Send on its own within the limits I set',
});

export function validateListing(value){
  assert(value&&typeof value==='object'&&typeof value.note==='string');
  list(value.messages,500).forEach(m=>assert(ID.test(m.draft_id)&&ID.test(m.assistant_id)&&ID.test(m.conversation_id)&&str(m.text)&&HEX.test(m.digest)));
  list(value.questions,500).forEach(q=>{assert(ID.test(q.question_id)&&str(q.question,2048)&&q.state==='waiting'&&Number.isFinite(q.expires_at));list(q.options,4).forEach(o=>assert(str(o,256)));assert(q.options.length>=2);});
  list(value.drafts,500).forEach(d=>assert(ID.test(d.draft_id)&&ID.test(d.conversation_id)&&str(d.text)&&Number.isSafeInteger(d.revision)&&d.execution_authority===false));
  assert(typeof value.drafts_available==='boolean'&&value.count===value.messages.length+value.questions.length+value.drafts.length);
  return value;
}

export function validateDraftReview(value,id){
  assert(value?.draft_id===id&&str(value.text)&&HEX.test(value.review_digest)&&Number.isSafeInteger(value.revision)&&typeof value.scope==='string');
  list(value.people,32).forEach(p=>assert(str(p,64)));return value;
}

const WHO={you:'You',your_assistant:'Your assistant',someone_else:'Someone else',system:'Central'};
const WHAT={
  message_received:'received a message',message_proposed:'proposed a message for you to check',
  message_sent_by_assistant:'sent a message within your settings',message_approved:'approved and sent a message',
  message_declined:'declined a proposed message',message_failed:'could not deliver a message',
  policy_changed:'changed how your assistant may send',guidance_changed:'updated private guidance for your assistant',
  draft_started:'started a shared draft',draft_revised:'revised a shared draft',draft_suggested:'suggested changes to a shared draft',
  question_asked:'asked you a question',question_answered:'answered a question',mission_activity:'recorded mission activity',
};

// A plain sentence for one timeline entry. Unknown kinds stay readable.
export function describeEntry(entry){
  assert(entry&&Number.isSafeInteger(entry.seq)&&typeof entry.kind==='string');
  const who=WHO[entry.role]??'Someone', what=WHAT[entry.kind]??entry.kind.replaceAll('_',' ');
  return `${who} ${what}`;
}

function node(tag,text='',className=''){const e=document.createElement(tag);e.textContent=String(text);if(className)e.className=className;return e;}
function btn(label,action,kind='secondary'){const b=node('button',label,'button '+kind);b.type='button';b.addEventListener('click',action);return b;}
const when=seconds=>new Date(seconds*1000).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});

export function createApprovals({request,busy,gate,failed,active,session,restore}){
  let epoch=0,root=null,listing=null,timeline=null,review=null;
  function reset({sessionEnded=false}={}){epoch++;review=null;if(root)root.replaceChildren();root=null;listing=null;timeline=null;if(sessionEnded)gate.reset();}
  async function load(){
    const stamp=epoch;
    const value=validateListing(await request('/api/approvals'));
    const entries=await request('/api/approvals/timeline',{method:'POST',body:{}});
    list(entries?.entries,200);
    if(stamp===epoch&&active()){listing=value;timeline=entries;}
  }
  async function run(fn){
    if(busy()||!root||!active())return;
    const stamp=epoch,sessionStamp=session(),release=gate.acquire();
    const current=()=>stamp===epoch&&sessionStamp===session()&&active();
    try{await fn(current);if(current()){await load();if(current())render();}}
    catch(error){if(current()){root.replaceChildren(node('p','Approvals are unavailable. Refresh saved state before deciding.','scope-note'));listing=null;failed(error);}}
    finally{release();if(!root&&!document.hidden&&sessionStamp===session()&&active())restore();}
  }
  const post=(path,body)=>request(path,{method:'POST',body});

  function messageCard(m){
    const card=node('article','','approval-card');card.dataset.kind='message';card.dataset.id=m.draft_id;
    card.append(node('div',`Your assistant ${m.assistant_id} wants to send this in ${m.conversation_id}`,'approval-meta'));
    card.append(node('blockquote',m.text,'approval-text'));
    const actions=node('div','','approval-actions');
    actions.append(btn('Send this exact message',()=>run(()=>post(`/api/approvals/messages/${m.draft_id}/approve`,{digest:m.digest})),'primary'),
                   btn('Decline',()=>run(()=>post(`/api/approvals/messages/${m.draft_id}/decline`,{}))));
    card.append(actions,settings(m.assistant_id,m.conversation_id));
    return card;
  }

  function settings(assistantId,conversationId){
    const box=node('details','','approval-settings');box.append(node('summary','How this assistant may send here'));
    const choice=node('select');choice.setAttribute('aria-label','Sending mode');
    for(const [value,label] of Object.entries(MODES)){const o=node('option',label);o.value=value;choice.append(o);}
    const note=node('textarea');note.rows=2;note.maxLength=2000;note.placeholder='A private note for your assistant. Only your assistant reads it.';note.setAttribute('aria-label','Private guidance');
    const target={assistant_id:assistantId,conversation_id:conversationId};
    box.append(choice,btn('Save sending mode',()=>run(()=>post('/api/approvals/policy',{...target,mode:choice.value}))),
               note,btn('Add private note',()=>{const text=note.value.trim();if(text)run(()=>post('/api/approvals/guidance',{...target,add:text}));}));
    box.append(node('p','Sending on its own is limited and expires. You can switch back to asking first at any time.','scope-note'));
    return box;
  }

  function questionCard(q){
    const card=node('article','','approval-card');card.dataset.kind='question';card.dataset.id=q.question_id;
    card.append(node('div',`Your assistant asks, until ${when(q.expires_at)}`,'approval-meta'),node('p',q.question,'approval-text'));
    const actions=node('div','','approval-actions');
    q.options.forEach((option,index)=>actions.append(btn(option,()=>run(()=>post(`/api/approvals/questions/${q.question_id}/answer`,{option:index})))));
    card.append(actions,node('p','Your answer is information for your assistant. It approves nothing on its own.','scope-note'));
    return card;
  }

  function draftCard(d){
    const card=node('article','','approval-card');card.dataset.kind='draft';card.dataset.id=d.draft_id;
    card.append(node('div',`${d.author_name} shared a draft, revision ${d.revision}`,'approval-meta'),node('blockquote',d.text,'approval-text'));
    const actions=node('div','','approval-actions');
    if(review?.draft_id===d.draft_id){
      card.append(node('p',review.scope,'scope-note'),node('p',`Agreeing with: ${review.people.join(', ')||'just you'}`,'approval-meta'));
      actions.append(btn('Agree to this exact text',()=>run(async()=>{const digest=review.review_digest;review=null;await post(`/api/approvals/drafts/${d.draft_id}/approve`,{review_digest:digest});}),'primary'),
                     btn('Not now',()=>{review=null;render();}));
    }else{
      actions.append(btn('Review to agree',()=>run(async current=>{const value=validateDraftReview(await post(`/api/approvals/drafts/${d.draft_id}/review`,{conversation_id:d.conversation_id}),d.draft_id);if(current())review=value;})));
    }
    card.append(actions);return card;
  }

  function section(title,items,make,empty){
    const s=node('section','','approval-section');s.append(node('h2',`${title} (${items.length})`));
    if(!items.length)s.append(node('p',empty,'scope-note'));else items.forEach(item=>s.append(make(item)));
    return s;
  }

  function render(){
    if(!root||!listing||!active())return;root.replaceChildren();
    root.append(node('p',listing.note,'scope-note'));
    root.append(section('Messages to check',listing.messages,messageCard,'Nothing your assistant wants to send is waiting.'));
    root.append(section('Questions for you',listing.questions,questionCard,'Your assistant has not asked you anything.'));
    root.append(section('Shared drafts',listing.drafts,draftCard,listing.drafts_available?'No shared drafts are waiting for you.':'Shared drafts appear here once the host owner has opened this page.'));
    const t=node('section','','approval-section');t.append(node('h2','Your timeline'));
    const entries=timeline?.entries??[];
    if(!entries.length)t.append(node('p','Nothing has happened yet.','scope-note'));
    const rows=node('ol','','approval-timeline');
    for(const entry of entries.slice().reverse()){const li=node('li');li.append(node('time',when(entry.at)),node('span',describeEntry(entry)));rows.append(li);}
    t.append(rows);root.append(t);
  }

  function mount(target,enabled){reset();root=target;if(!active())return;
    if(!enabled){root.append(node('p','Approvals are not available on this host.','scope-note'));return;}
    const stamp=epoch;root.append(node('p','Checking what is waiting for you…','scope-note'));
    (async()=>{try{await load();if(stamp===epoch&&active())render();}catch(error){if(stamp===epoch&&root){root.replaceChildren(node('p','Approvals are unavailable. Refresh saved state.','scope-note'));failed(error);}}})();
  }
  return {mount,reset};
}
