'use strict';
// Trusted local operator UI. Hashes are navigation, never authorization.
const $ = id => document.getElementById(id);
let generation = 0, active = null, busy = false, cancelDialog = null;
let renderedHash = null;
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function current(view) { return view && view.generation === generation && view.hash === location.hash; }
function error(text) { $('error').textContent = text; $('error').hidden = false; }
function message(text) { $('message').textContent = text; }
function button(text, handler, cls = '', disabled = false) {
  const view = active;
  const node = element('button', text, cls); node.disabled = disabled || busy;
  node.addEventListener('click', () => {
    if (!node.disabled && !busy && !cancelDialog && current(view)) handler();
  });
  return node;
}
function heading(title, text) {
  $('content').append(element('h1', title), element('p', text, 'muted'));
}
function navigate(route) {
  // Invalidate old actions synchronously, before the browser dispatches hashchange.
  ++generation;
  if (cancelDialog) cancelDialog();
  location.hash = '#' + route;
  render();
}
function path(view, kind, id = '') {
  return [view.selector, view.owner, kind, ...(id ? [id] : [])].map(encodeURIComponent).join('/');
}
function scopedNavigate(view, route) {
  if (!current(view)) return;
  const [kind, owner, id] = route.split('/');
  navigate(path({...view, owner}, kind, id));
}
async function get(url) {
  const response = await fetch(url, {cache:'no-store', credentials:'omit'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Local read refused.');
  return data;
}
function read(view, kind, id) {
  const fields = {selector:view.selector, context:view.context, owner:view.owner};
  if (id) fields.id = id;
  return get('/api/' + kind + '?' + new URLSearchParams(fields));
}
async function mutate(view, request) {
  return post(view,'/api/action',{selector:view.selector,context:view.context,request});
}
async function post(view, url, payload, readOnly = false) {
  if (busy || !current(view)) return null;
  if (view.local_work_stopped && !(url === '/api/action' && payload.request && ['check','recover','decline','defer','withdraw_unused','close'].includes(payload.request.action))) { error('Local group stop prevents further work on this exact task. History and permitted cleanup remain available.'); return null; }
  // Serialize immediately. Nothing after an await can substitute a new scope.
  const body = JSON.stringify(payload);
  busy = true;
  const prior = new Map([...document.querySelectorAll('button,select')].map(n => [n,n.disabled]));
  prior.forEach((_,n) => { n.disabled = true; });
  $('error').hidden = true;
  try {
    let response, data;
    try {
      response = await fetch(url, {method:'POST', credentials:'omit', cache:'no-store',
        headers:{'Content-Type':'application/json','X-Owner-Fixture':'v7'}, body});
      data = await response.json();
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid response');
    } catch (_) {
      throw new Error(view.continuity && !readOnly ? 'The continuity action response was lost. It may have committed; the outcome is uncertain. Inspect continuity state without retrying. Nothing was signed or enrolled again automatically.' : view.relationship && !readOnly ? 'The group action response was lost. It may have committed. Inspect this exact group before deciding again. Nothing was retried automatically.' : readOnly ? 'The preview response was lost. A preview cannot create a task or review, or grant authority. Nothing was retried automatically.' : 'The response was lost. The action may have committed; delivery or cleanup may be uncertain. Inspect this exact task before deciding again. Nothing was retried automatically.');
    }
    if (!response.ok) throw new Error(data.error || 'Action refused. Inspect this exact task.');
    return current(view) ? data : null;
  } catch (exc) { if (current(view)) error(exc.message + ' No automatic retry.'); return null; }
  finally {
    busy = false;
    prior.forEach((disabled,n) => { if (n.isConnected) n.disabled = disabled; });
    // A view rendered while a call was pending has no actionable buttons until
    // a read-only refresh, avoiding accidental enablement of terminal controls.
    if (!current(view)) render();
  }
}
function composeField(container, labelText, id, tag = 'input') {
  const label = element('label',labelText); label.htmlFor = id;
  const input = element(tag); input.id = id; input.autocomplete = 'off';
  container.append(label,input); return input;
}
const TEXT_EXCHANGE = 'bounded-text-exchange-v1';
const SHORTLIST = 'public-resource-shortlist-v1';
function boundedText(value, maximum) { return typeof value === 'string' && [...value].length > 0 && [...value].length <= maximum; }
function renderComposer(view, previous = null) {
  heading('Compose a temporary task','Use fictional, nonprivate examples only. Previewing starts no service and grants no authority. Alice and Bob are fictional provider references, not real identities.');
  const form = element('div',undefined,'card composer');
  const name = composeField(form,'Short task identifier','composeName');
  name.maxLength = 48; name.placeholder = 'neighborhood-books';
  const direction = composeField(form,'Requesting fictional owner','composeRequester','select');
  for (const owner of ['alice','bob']) { const option = element('option',owner + ' → ' + (owner === 'alice' ? 'bob' : 'alice')); option.value = owner; direction.append(option); }
  direction.value = 'alice';
  const capability = composeField(form,'Capability (inert communication only)','composeCapability','select');
  for (const [value,label] of [[SHORTLIST,'Public-resource shortlist'],[TEXT_EXCHANGE,'Bounded plain-text exchange']]) { const option = element('option',label); option.value = value; capability.append(option); }
  capability.value = SHORTLIST;
  const query = composeField(form,'Fictional question or prompt (inert text)','composeQuery','textarea');
  query.maxLength = 512; query.rows = 5;
  const count = composeField(form,'Maximum result items','composeCount','select');
  for (const number of [1,2,3,4,5]) { const option = element('option',String(number)); option.value = String(number); count.append(option); }
  count.value = '2';
  const reply = composeField(form,'Maximum reply characters (1–512 Unicode characters)','composeReplyChars');
  reply.type = 'number'; reply.min = 1; reply.max = 512; reply.step = 1; reply.value = '512';
  if (previous) {
    name.value = previous.selector.slice(7); direction.value = previous.requester;
    query.value = previous.query; capability.value = previous.capability || SHORTLIST;
    count.value = String(previous.max_items || 2); reply.value = String(previous.max_reply_chars || 512);
  }
  function showCapability() {
    const isText = capability.value === TEXT_EXCHANGE; count.hidden = isText; reply.hidden = !isText;
    for (const label of form.children) { if (label.htmlFor === 'composeCount') label.hidden = isText; if (label.htmlFor === 'composeReplyChars') label.hidden = !isText; }
    query.maxLength = isText ? 1024 : 512;
  }
  capability.addEventListener('change',showCapability); showCapability();
  form.append(element('p','Two allowlisted capabilities: public-resource-shortlist-v1 and bounded-text-exchange-v1. No browsing, tool execution, scheduling or future authority is enabled. Up to eight custom task slots per launcher run; closed or uncertain slots cannot be reused.','muted small'));
  form.append(button('Preview exact task',async()=>{
    const slug = name.value;
    // Deliberately do not trim or silently rewrite text. The server validates
    // the exact entered spec and returns the sole snapshot eligible for review.
    const spec = {selector:'custom-' + slug,task_id:'task-' + slug,conversation_id:'conversation-' + slug,
      requester:direction.value,query:query.value};
    if (capability.value === TEXT_EXCHANGE) {
      const maximum = Number(reply.value);
      if (!Number.isInteger(maximum) || maximum < 1 || maximum > 512 || !boundedText(query.value,512)) { error('Enter a nonempty fictional prompt of at most 512 Unicode characters and an integer reply limit from 1 to 512.'); return; }
      spec.capability = TEXT_EXCHANGE; spec.max_reply_chars = maximum;
    } else if (capability.value === SHORTLIST) spec.max_items = Number(count.value);
    else { error('Unknown capability.'); return; }
    const preview = await post(view,'/api/task-preview',{spec},true);
    if (preview && current(view)) renderCompositionReview(view,preview);
  },'primary'),button('Back to tasks',()=>navigate('')));
  $('content').append(form);
}
function renderCompositionReview(view, preview) {
  // Capture the exact returned spec before any confirmation or await. Inputs
  // disappear rather than remaining editable behind the confirmation dialog.
  const snapshot = JSON.stringify(preview.spec), reviewDigest = preview.review_digest;
  const scope = Object.freeze({...view,selector:preview.selector,task:preview.task,context:preview.context,
    requester:preview.requester,responder:preview.responder,owner:preview.requester});
  let attempted = false;
  $('content').replaceChildren(); $('error').hidden = true;
  heading('Review this temporary task','Creating starts isolated fictional processes only. Each identity binding, pairing, message approval, submission and delivery still requires its own explicit step. No response is fabricated.');
  $('content').append(element('pre','Selector: ' + scope.selector + '\nTask: ' + scope.task + '\nContext: ' + scope.context + '\nReview token: ' + reviewDigest + '\nExact composition:\n' + JSON.stringify(JSON.parse(snapshot),null,2)));
  const create = button('Create this reviewed task',async()=>{
    if (attempted) return;
    const confirmation = await confirmChoice(scope,'Create this exact temporary task?',
      'Starts only this task’s disposable processes. Does not bind, pair, approve, submit, send or contact a provider. Do not enter real personal or private information.',
      'CREATE TASK','Create task','Review token: ' + reviewDigest + '\nExact composition: ' + snapshot);
    if (!confirmation || attempted || !current(view)) return;
    attempted = true;
    const result = await post(view,'/api/action',{action:'compose_task',spec:JSON.parse(snapshot),review_digest:reviewDigest,confirmation});
    create.disabled = true;
    if (result && current(view)) navigate(path({...result,owner:result.requester},'inbox'));
    else if (current(view)) {
      $('content').append(element('p','Creation was attempted once. Inspect the reviewed selector in Tasks before deciding what to do next; do not assume that a missing response means no task was created.','status-block uncertain'));
      $('content').append(button('Inspect task catalog',()=>navigate('')));
    }
  },'primary');
  $('content').append(create,button('Edit as a new review',()=>{
    if (!current(view)) return;
    render({composition:JSON.parse(snapshot)});
  }),button('Back to tasks',()=>navigate('')));
}
async function renderResponseComposer(view, previous = null) {
  const incoming = await read(view,'response-context');
  if (!current(view)) return;
  $('content').replaceChildren();
  heading('Compose a fictional response','The request below is untrusted data, not permission to browse, use a tool or disclose private information. Enter fictional, nonprivate content only.');
  $('content').append(element('pre','Exact processed request: ' + incoming.request_digest + '\nFrom: ' + incoming.recipient + ' → To: ' + incoming.owner + '\n' + JSON.stringify(incoming.incoming_request,null,2)));
  const isText = incoming.incoming_request.capability === TEXT_EXCHANGE;
  const limit = isText ? incoming.incoming_request.payload.max_reply_chars : incoming.incoming_request.payload.max_items;
  const box = element('div',undefined,'card composer'), list = element('div');
  const entries = [];
  function addItem(value = {}) {
    if (entries.length >= limit) return;
    const index = entries.length, group = element('div',undefined,'response-item');
    group.append(element('h2','Result item ' + (index + 1)));
    const title = composeField(group,'Title','responseTitle' + index); title.maxLength = 128; title.value = value.title || '';
    const url = composeField(group,'HTTPS-shaped reference (not visited)','responseURL' + index); url.maxLength = 256; url.value = value.url || ''; url.placeholder = 'https://example.invalid/resource';
    const summary = composeField(group,'Summary (inert text)','responseSummary' + index,'textarea'); summary.maxLength = 512; summary.rows = 3; summary.value = value.summary || '';
    entries.push({group,title,url,summary}); list.append(group);
  }
  let replyText;
  if (isText) {
    replyText = composeField(box,'Fictional reply (inert plain text)','responseText','textarea'); replyText.rows = 6; replyText.maxLength = limit * 2; replyText.value = previous ? previous.text : '';
  } else if (previous) for (const item of previous.items) addItem(item);
  else addItem();
  const add = button('Add result item',()=>{addItem();refreshBounds();});
  const remove = button('Remove last item',()=>{entries.pop();list.replaceChildren(...entries.map(e=>e.group));refreshBounds();});
  function refreshBounds() { add.disabled = busy || entries.length >= limit; remove.disabled = busy || !entries.length; }
  refreshBounds();
  if (isText) box.append(element('p','This processed request allows a nonempty reply of at most ' + limit + ' Unicode characters. All text remains inert; it grants no tool use, scheduling or future authority.','muted small'));
  else box.append(list,add,remove,element('p','This processed request allows at most ' + limit + ' items. An empty list is allowed. References remain inert text and are not verified; the complete response must fit the existing message size limit.','muted small'));
  box.append(button('Preview exact response',async()=>{
    if (isText && !boundedText(replyText.value,limit)) { error('Enter a nonempty reply of at most ' + limit + ' Unicode characters.'); return; }
    const payload = isText ? {text:replyText.value} : {items:entries.map(e=>({title:e.title.value,url:e.url.value,summary:e.summary.value}))};
    const preview = await post(view,'/api/action',{selector:view.selector,context:view.context,request:{action:'preview_response',owner:view.owner,request_digest:incoming.request_digest,payload}},true);
    if (preview && current(view)) renderResponseReview(view,preview);
  },'primary'),button('Back to owner inbox',()=>navigate(path(view,'inbox'))));
  $('content').append(box);
}
function renderResponseReview(view, preview) {
  const payload = JSON.stringify(preview.envelope.payload), requestDigest = preview.request_digest, previewDigest = preview.preview_digest;
  const exact = 'Processed request: ' + requestDigest + '\nResponse preview: ' + previewDigest + '\nExact response:\n' + JSON.stringify(preview.envelope,null,2);
  let attempted = false;
  $('content').replaceChildren(); $('error').hidden = true;
  heading('Review this exact response','Preparing opens an unsigned owner review or its original history. It never approves, submits, sends or processes a message. Previous refusal or withdrawal is retained.');
  $('content').append(element('pre',exact));
  const prepare = button('Prepare unsigned response review',async()=>{
    if (attempted) return;
    const confirmation = await confirmChoice(view,'Open this exact response for owner review?',
      'Create an unsigned review if none exists, or open the original review including its refusal or withdrawal. Approval and delivery require separate choices.',
      'REVIEW RESPONSE ' + view.owner,'Open unsigned review',exact);
    if (!confirmation || attempted || !current(view)) return;
    attempted = true;
    const result = await mutate(view,{action:'prepare_response',owner:view.owner,request_digest:requestDigest,payload:JSON.parse(payload),preview_digest:previewDigest,confirmation});
    prepare.disabled = true;
    if (result && current(view)) routeResult(view,result);
    else if (current(view)) $('content').append(element('p','Preparation was attempted once. Inspect the owner inbox for the original review before deciding again. A missing response is not proof that no review exists.','status-block uncertain'));
  },'primary');
  $('content').append(prepare,button('Edit response as a new preview',()=>{
    if (!current(view)) return;
    render({response:JSON.parse(payload)});
  }),button('Back to owner inbox',()=>navigate(path(view,'inbox'))));
}
function confirmChoice(view, title, description, phrase, label, exact = '') {
  if (!current(view) || cancelDialog || busy) return Promise.resolve(null);
  return new Promise(resolve => {
    const dialog = $('confirmDialog');
    $('dialogTitle').textContent = title;
    $('dialogBody').textContent = (view.continuity ? 'Fictional informational continuity review\n' : view.relationship ? 'Fictional group: ' + view.group_id + '\n' : 'Task: ' + view.task + '\nSelector: ' + view.selector + '\nContext: ' + view.context + '\nOwner: ' + view.owner + '\n') + exact + '\n' + description;
    $('confirmationLabel').textContent = 'Type ' + phrase + ' to continue';
    $('confirmation').value = ''; $('confirmation').placeholder = phrase;
    $('dialogConfirm').textContent = label; $('dialogConfirm').disabled = true;
    let done = false;
    const finish = value => {
      if (done) return; done = true;
      dialog.close(); cancelDialog = null;
      $('confirmation').oninput = null; $('dialogCancel').onclick = null;
      $('dialogConfirm').onclick = null; dialog.oncancel = null;
      resolve(current(view) ? value : null);
    };
    cancelDialog = () => finish(null);
    $('confirmation').oninput = () => { $('dialogConfirm').disabled = !current(view) || $('confirmation').value !== phrase; };
    $('dialogCancel').onclick = () => finish(null);
    $('dialogConfirm').onclick = () => { if (current(view) && $('confirmation').value === phrase) finish(phrase); };
    dialog.oncancel = event => { event.preventDefault(); finish(null); };
    dialog.showModal(); $('confirmation').focus();
  });
}
function routeResult(view, result) {
  if (!result || !current(view)) return;
  if (result.kind === 'request') scopedNavigate(view, `request/${result.card.owner}/${result.card.request_id}`);
  else if (result.kind === 'delivery') scopedNavigate(view, `delivery/${result.owner}/${result.delivery_id}`);
  else {
    if (result.reason) {
      $('content').replaceChildren();
      heading(result.kind === 'awaiting' ? 'Waiting for a reviewed response' : 'Task status',result.reason);
      $('content').append(element('pre','Task: ' + view.task + '\nContext: ' + view.context),
        button('Back to owner inbox',()=>navigate(path(view,'inbox'))));
      return;
    }
    navigate(path(view,'inbox'));
  }
}
function renderBindings(state, view) {
  heading('Explicit temporary identity bindings', 'Each task has independent fixture keys. Binding does not pair owners or authorize messages.');
  for (const binding of state.bindings) {
    const box = element('article', undefined, 'card');
    box.append(element('h2',binding.owner), element('pre',JSON.stringify(binding,null,2)));
    box.append(button(binding.approved ? 'Binding approved' : 'Review binding for ' + binding.owner, async () => {
      const confirmation = await confirmChoice(Object.freeze({...view,owner:binding.owner}),'Bind ' + binding.owner,
        'Approve only this displayed temporary transport binding. No outbound message is authorized.',
        'BIND ' + binding.owner,'Approve binding',JSON.stringify(binding,null,2));
      if (!confirmation) return;
      const result = await mutate(view,{action:'bind',owner:binding.owner,binding_digest:binding.digest,confirmation});
      if (result && current(view)) render();
    },'primary',binding.approved));
    $('content').append(box);
  }
}
function renderInbox(state, view) {
  heading(view.owner + '’s inbox','Viewing a request grants nothing. Prepare the next fictional review only when you choose.');
  if (!state.inbox.length) $('content').append(element('p','No owner requests yet.','card'));
  for (const card of state.inbox) {
    const box = element('article',undefined,'card');
    box.append(element('h2',card.action + ' · ' + card.state),element('p',card.request_id,'key'),
      button('Open review',()=>scopedNavigate(view,`request/${card.owner}/${card.request_id}`)));
    $('content').append(box);
  }
  $('content').append(element('p','Latest 20 owner requests. Historical refusals and deferrals are retained.','muted'),element('pre',JSON.stringify(state.summary,null,2)));
}

const confirmReview = confirmChoice;
function renderReview(card, view) {
  const act = request => mutate(view, request);
  const navigate = route => scopedNavigate(view, route);
  const showResult = result => routeResult(view, result);
  const exact = 'Request: ' + card.request_id + '\nReview token: ' + card.review_digest + '\nExact target: ' + JSON.stringify(card.decision.target) + '\n' + card.review;
  const confirmChoice = (title, description, phrase, label) => confirmReview(view, title, description, phrase, label, exact);
  $('content').append(element('pre', 'Task: ' + view.task + '\nContext: ' + view.context + '\nExact target: ' + JSON.stringify(card.decision.target)));
  heading('Review for ' + card.owner, 'Approval, submission and delivery are separate steps. Nothing is sent by viewing this page.');
  const container = element('article', undefined, 'card');
  const top = element('div', undefined, 'card-top'); top.append(element('h2', card.action), element('span', card.state.toUpperCase(), 'tag'));
  container.append(top, element('p', 'Request ' + card.request_id, 'muted small'), element('div', card.review, 'review'));
  if (card.reason) container.append(element('p', card.reason, 'status-block uncertain'));
  const actions = element('div', undefined, 'actions');
  const decisionActions = () => {
    actions.replaceChildren();
    if (card.state === 'pending' || card.state === 'deferred') {
      if (!view.local_work_stopped) actions.append(button('Approve exact request', async () => {
        const confirmation = await confirmChoice('Approve ' + card.action + ' for ' + card.owner,
          'Approve only this displayed decision and request ' + card.request_id + '. This saves the owner signature. Submission is a separate step; no message is dispatched yet.',
          'APPROVE ' + card.owner, 'Approve request');
        if (!confirmation) return;
        showResult(await act({action:'approve', owner:card.owner, request_id:card.request_id, review_digest:card.review_digest, confirmation}));
      }, 'primary'));
      for (const [action, label] of [['defer','Defer'],['decline','Decline']]) actions.append(button(label, async () => {
        const result = await act({action, owner:card.owner, request_id:card.request_id, review_digest:card.review_digest});
        if (result) { message(action === 'defer' ? 'Deferred. No approval granted; resume explicitly when ready.' : 'Declined. No approval granted; this request will not be replaced by the guide.'); navigate('inbox/' + card.owner); }
      }));
    } else if (card.stored_state === 'authorized' && card.state !== 'withdrawn') {
      if (card.state === 'authorized' && !view.local_work_stopped) actions.append(button('Submit approved request', async () => showResult(await act({action:'submit',owner:card.owner,request_id:card.request_id})), 'primary'));
      actions.append(button('Check committed approval', async () => showResult(await act({action:'recover',owner:card.owner,request_id:card.request_id}))));
    } else if (card.stored_state === 'submitted' && card.action === 'send') {
      actions.append(button('View delivery status', () => navigate(`delivery/${card.owner}/${card.request_id}`), 'primary'));
    }
    if (card.can_replace && !view.local_work_stopped) actions.append(button('Prepare new review', async () => {
      const confirmation = await confirmChoice('Prepare a new unsigned review?',
        'The old expired or stale draft is retained as replaced. This creates a new request for the same action, participants and task, and the exact message for a send, using current contact versions. It does not approve, submit or send anything. A fresh explicit approval will still be required.',
        'REVIEW ' + card.owner, 'Prepare new review');
      if (!confirmation) return;
      showResult(await act({action:'replace_review',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,confirmation}));
    }));
    if (card.can_withdraw) actions.append(button('Withdraw unused authorization', async () => {
      const confirmation = await confirmChoice('Permanently withdraw this unused authorization?',
        'Withdraw only the displayed authorization for ' + card.owner + ', request ' + card.request_id + '. This action signs and applies the withdrawal in one step. It is refused if any execution or queued delivery exists. The local executor permanently blocks the old signature, including when these records are reopened. This does not recall a message or create a fresh approval.',
        'WITHDRAW ' + card.owner, 'Withdraw unused authorization');
      if (!confirmation) return;
      showResult(await act({action:'withdraw_unused',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,confirmation}));
    }, 'danger'));
    if (card.can_prepare_fresh && !view.local_work_stopped) actions.append(button('Prepare fresh unsigned review', async () => {
      const confirmation = await confirmChoice('Prepare a separate fresh review?',
        'The withdrawn signature stays permanently blocked. Prepare a new unsigned request for the same action, participants, task and exact message, using current permissions. Fresh approval, submission and any delivery remain separate. Nothing is sent by this choice.',
        'REVIEW ' + card.owner, 'Prepare fresh unsigned review');
      if (!confirmation) return;
      showResult(await act({action:'fresh_after_withdrawal',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,confirmation}));
    }));
    if (card.withdrawn_successor) actions.append(button('Open fresh review', () => navigate(`request/${card.owner}/${card.withdrawn_successor}`)));
    for (const direction of (view.local_work_stopped ? [] : card.pairing_reviews) || []) actions.append(button('Review pairing for ' + direction.owner, async () => {
      const confirmation = await confirmChoice('Open ' + direction.owner + '’s pairing review?',
        'Pairing from ' + direction.owner + ' to ' + direction.peer + ' is ' + direction.state + ' for this exact task. Open an existing review or prepare a new unsigned one. This grants nothing. That owner must separately approve and submit; a refusal or deferral stays visible. The original message will still require a fresh send review.',
        'REVIEW PAIR ' + direction.owner, 'Open pairing review');
      if (!confirmation) return;
      showResult(await act({action:'review_pairing',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,direction_owner:direction.owner,confirmation}));
    }));
    for (const source of card.pairing_sources || []) actions.append(button('Return to ' + source.owner + '’s blocked send', () => navigate(`request/${source.owner}/${source.request_id}`)));
    if (card.replaced_by) actions.append(button('Open replacement review', () => navigate(`request/${card.owner}/${card.replaced_by}`), 'primary'));
    actions.append(button('Refresh review', render), button('Back to inbox', () => navigate('inbox/' + card.owner)));
  };
  if (card.state === 'deferred' && !view.local_work_stopped) {
    container.append(element('p', 'Paused. Returning to this page does not resume or approve it.', 'status-block'));
    actions.append(button('Resume review', decisionActions, 'primary'), button('Back to inbox', () => navigate('inbox/' + card.owner)));
  } else decisionActions();
  if (card.replaces) container.append(element('p', 'New unsigned review replacing request ' + card.replaces + '. No approval was carried forward.', 'muted'));
  if (card.replacement_blocker) container.append(element('p', 'A replacement cannot be prepared: ' + card.replacement_blocker, 'muted'));
  if (card.state === 'withdrawn') container.append(element('p', 'Unused authorization withdrawn. No delivery was queued by this authorization. Its original signature remains blocked in this local executor; nothing was recalled and no new approval was granted.', 'status-block'));
  if (card.fresh_review_blocker) container.append(element('p', 'A fresh review cannot be prepared: ' + card.fresh_review_blocker + '. Existing owner controls and the guide remain available.', 'muted'));
  if (((view.local_work_stopped ? [] : card.pairing_reviews) || []).length) container.append(element('p', 'Missing pairing is reviewed one owner at a time. Neither viewing nor preparing these reviews restores consent. Existing active pairing is not extended.', 'muted'));
  if ((card.pairing_sources || []).length) container.append(element('p', 'This separate pairing review was opened from a blocked send. Approval and submission grant only this pairing; they do not revive or send that message.', 'muted'));
  if (card.stored_state === 'declined') container.append(element('p', 'This request is terminally declined. A later signature cannot revive it through this workflow.', 'muted'));
  if (card.stored_state === 'submitted') container.append(element('p', 'Submitted means the control was applied or the message was enqueued. It is not evidence of delivery.', 'muted'));
  container.append(actions); $('content').append(container);
}
function renderDelivery(status, card, view) {
  const act = request => mutate(view, request);
  const navigate = route => scopedNavigate(view, route);
  const showResult = result => routeResult(view, result);
  const exact = 'Request: ' + card.request_id + '\nReview token: ' + card.review_digest + '\nExact target: ' + JSON.stringify(card.decision.target) + '\n' + card.review;
  const confirmChoice = (title, description, phrase, label) => confirmReview(view, title, description, phrase, label, exact);
  heading('Delivery to ' + card.decision.target.recipient, 'An approved message from ' + card.owner + '. Inspecting this status does not check a receiver or attempt another send.');
  const container = element('article', undefined, 'card');
  container.append(element('p', 'Delivery ' + status.delivery_id, 'key'));
  const block = element('div', undefined, 'status-block' + (status.state.includes('uncertain') || status.state === 'dispatched' ? ' uncertain' : ''));
  block.append(element('h2', status.label), element('p', 'Attempts recorded: ' + status.attempts + '. A started attempt may have reached the recipient even if no receipt has returned. Cancellation cannot recall it.'));
  container.append(block);
  const steps = element('div', undefined, 'steps');
  for (const [label, done] of [['Approved',true], ['Attempt started',status.attempts>0], ['Receipt verified',['received','processed','received_blocked'].includes(status.state)], ['Processed',status.state==='processed']]) steps.append(element('span',label,'step'+(done?' done':'')));
  container.append(steps);
  if (status.attempt_blocker) container.append(element('p', 'New attempts blocked: ' + status.attempt_blocker, 'muted'));
  if (status.state === 'received_blocked') container.append(element('p', 'The recipient received this message. Processing stopped; disclosure was not undone.', 'muted'));
  const actions = element('div', undefined, 'actions');
  actions.append(button('Check existing receipt', async () => showResult(await act({action:'check',owner:card.owner,request_id:card.request_id})), '', !status.can_check_receipt));
  actions.append(button(status.attempts ? 'Retry approved delivery' : 'Start approved delivery', async () => {
    const confirmation = await confirmChoice(status.attempts ? 'Retry this exact delivery?' : 'Start this exact delivery?',
      'Only the already-approved recipient and ciphertext are used. An uncertain previous attempt is checked for an existing receipt first. This is not a new approval or a live provider action, and an in-flight attempt cannot be recalled.',
      'SEND ' + card.owner, 'Start delivery attempt');
    if (!confirmation) return;
    showResult(await act({action:'attempt',owner:card.owner,request_id:card.request_id,confirmation}));
  }, 'primary', !status.can_start_attempt || view.local_work_stopped));
  actions.append(button('Process received message', async () => showResult(await act({action:'process',owner:card.owner,request_id:card.request_id})), '', !status.can_process || view.local_work_stopped));
  actions.append(button('Refresh status', render),button('Back to review',()=>navigate(`request/${card.owner}/${card.request_id}`)));
  container.append(actions,element('p','Receipt checking never dispatches or processes a message. No live provider action is created.','muted small'));
  $('content').append(container);
}
async function renderProposals(view) {
  const rows = await read(view,'proposals');
  if (!current(view)) return;
  heading('Staged agent proposals','Fictional local proposal discovery only. Import creates an unsigned review or opens original history. It never approves, submits or sends. No live agent is connected.');
  if (!rows.length) $('content').append(element('p','No staged proposals for this owner and task. Nothing is generated automatically.','card'));
  for (const proposal of rows) {
    const box = element('article',undefined,'card');
    box.append(element('pre',JSON.stringify(proposal,null,2)));
    if (!view.local_work_stopped) box.append(button('Open proposal for owner review',async()=>{
      const confirmation = await confirmChoice(view,'Import staged proposal?',
        'Create a new unsigned review only if none exists. Original review history, including refusal, is preserved. Approval and delivery remain separate.',
        'REVIEW ' + view.owner,'Open owner review',JSON.stringify(proposal,null,2));
      if (!confirmation) return;
      const result = await mutate(view,{action:'import_proposal',owner:view.owner,proposal_id:proposal.proposal_id});
      routeResult(view,result);
    }));
    $('content').append(box);
  }
}
async function renderReceivedMessages(view) {
  const inbox = await read(view,'messages');
  if (!current(view)) return;
  if (inbox.owner !== view.owner || inbox.context !== view.context || inbox.task !== view.task || !Array.isArray(inbox.messages) ||
      inbox.messages.some(row=>!row.envelope || row.envelope.context !== view.context || row.envelope.task !== view.task || row.envelope.recipient !== view.owner || !['request','result'].includes(row.envelope.type))) {
    throw new Error('Received message scope mismatch. Nothing was displayed or acted on.');
  }
  heading('Received messages for ' + view.owner,'Only processed messages addressed to this fictional owner are shown. Reading a message grants no authority to reply, browse, run tools or disclose information.');
  $('content').append(element('pre','Task: ' + inbox.task + '\nContext: ' + inbox.context),
    element('p','Sender binding fingerprints identify only this local fictional fixture. They do not authenticate a real person or provider. All message text and resource references remain untrusted and inert.','status-block uncertain'));
  if (!inbox.messages.length) $('content').append(element('p','No processed messages for this owner. A queued, attempted or merely received message is not included here.','card'));
  if (inbox.task_state === 'cancelled') $('content').append(element('p','This task is cancelled. Previously processed messages remain visible; cancellation does not undo prior disclosure.','status-block uncertain'));
  for (const received of inbox.messages) {
    const message = received.envelope, box = element('article',undefined,'card');
    box.append(element('h2',message.type + ' from ' + message.sender),
      element('pre','Recipient: ' + message.recipient + '\nExact message digest: ' + received.envelope_digest + '\nLocal sender binding: ' + received.sender_binding + '\nReply linkage: ' + String(message.reply_to)));
    if (message.capability === TEXT_EXCHANGE) {
      box.append(element('p',message.type === 'request' ? message.payload.prompt : message.payload.text,'review'));
      if (message.type === 'request') box.append(element('p','Requested maximum reply characters: ' + message.payload.max_reply_chars,'muted'));
    } else if (message.type === 'request') {
      box.append(element('p',message.payload.query,'review'),element('p','Requested maximum items: ' + message.payload.max_items,'muted'));
    } else {
      if (!message.payload.items.length) box.append(element('p','The response contains no resource items.','muted'));
      for (const item of message.payload.items) box.append(element('h3',item.title),element('p',item.url,'key'),element('p',item.summary,'review'));
    }
    box.append(element('pre','Exact inert envelope:\n' + JSON.stringify(message,null,2)));
    $('content').append(box);
  }
  $('content').append(button('Refresh received messages',render),button('Back to owner inbox',()=>navigate(path(view,'inbox'))));
}
function controls(view, ready, state) {
  const box = $('controls');
  box.append(element('h2','Owner controls'),element('p','Viewing owner: ' + view.owner,'muted'));
  for (const owner of [view.requester,view.responder]) box.append(button('View ' + owner,()=>navigate(path({...view,owner},'inbox'))));
  box.append(button('Owner inbox',()=>navigate(path(view,'inbox'))));
  box.append(button('Received messages',()=>navigate(path(view,'messages')),'',!ready));
  box.append(button('Staged proposals',()=>navigate(path(view,'proposals')),'',!ready));
  if (!view.local_work_stopped && state.response_composer && view.owner === view.responder) box.append(button('Compose response',()=>navigate(path(view,'response')),'',!ready || !state.summary || state.summary.task_state !== 'requested'));
  box.append(button('Prepare next review',async()=>routeResult(view,await mutate(view,{action:'next'})),'primary',!ready || view.local_work_stopped));
  box.append(button('Review cancellation',async()=>routeResult(view,await mutate(view,{action:'cancel',owner:view.owner})),'',!ready || view.local_work_stopped));
  const peer = view.owner === view.requester ? view.responder : view.requester;
  box.append(button('Review revocation of ' + peer,async()=>routeResult(view,await mutate(view,{action:'revoke',owner:view.owner,peer})),'',!ready || view.local_work_stopped));
  box.append(button('Close only this task',async()=>{
    const confirmation = await confirmChoice(view,'Discard only this temporary task?',
      'Stops this task’s temporary processes and discards its keys and records. The other task remains independent. The occupied slot cannot be recreated until launcher restart. Cleanup failure blocks this task and remains explicitly uncertain.',
      'DISCARD FIXTURE','Close task');
    if (!confirmation) return;
    const result = await mutate(view,{action:'close',confirmation});
    if (result && current(view)) { message('Selected task closed. The other task was not closed.'); render(); }
    else if (current(view)) {
      // Inspect metadata only, keeping the uncertainty message visible until refresh.
      const rows = await get('/api/tasks').catch(()=>null);
      if (rows && current(view)) {
        const row = rows.find(r=>r.selector===view.selector);
        if (row && row.phase !== 'open') render();
      }
    }
  },'danger'));
}
const GROUP_STOP_NOTICE = 'One-way local stop for the exact linked tasks in this launcher only. Any stopped group fences an overlapping task. No resume or global block. Started actions and disclosed data cannot be recalled. No immediate preemption or guaranteed deadline. Grouping grants no identity, pairing, approval or send authority.';
async function renderRelationships(view, rows, groupId) {
  const groups = await get('/api/relationships');
  if (!current(view)) return;
  if (!Array.isArray(groups) || groups.length > 8 || new Set(groups.map(group=>group && group.group_id)).size !== groups.length) throw new Error('Group scope metadata mismatch.');
  for (const group of groups) validateRelationshipRow(group,rows);
  heading('Fictional task groups','All labels and contents are fictional, inert text. Groups organize exact task contexts only. ' + GROUP_STOP_NOTICE);
  $('content').append(button('Refresh groups',()=>navigate('relationships')));
  for (const group of groups) $('content').append(button(group.group_id + ' · revision ' + group.revision + (group.stopped ? ' · stopped' : ''),()=>navigate('relationships/' + encodeURIComponent(group.group_id))));
  const group = groups.find(g=>g.group_id===groupId);
  if (groupId && !group) { error('Unknown group. Inspect the group list.'); return; }
  if (group) {
    $('content').append(element('h2',group.label),element('pre',JSON.stringify(group,null,2)));
    for (const member of group.members) {
      const task = rows.find(t=>t.selector===member.selector && t.context===member.context);
      $('content').append(element('p',member.selector + ' · ' + member.context + ' · ' + (task ? task.phase + (task.local_work_stopped ? ' · further work stopped' : '') : 'unavailable')));
      if (task) $('content').append(button('Inspect task ' + task.selector,()=>navigate(path({...task,owner:task.requester},'inbox'))));
    }
    if (group.stopped) return;
    $('content').append(button('Review stop further group work',()=>previewRelationship(view,{operation:'stop',group_id:group.group_id},rows,group),'danger'));
    if (group.members.some(m=>rows.some(t=>t.selector===m.selector && t.context===m.context && t.local_work_stopped))) { $('content').append(element('p','Attachment blocked: a member is fenced by another stopped group.')); return; }
    for (const task of rows.filter(t=>!t.local_work_stopped && !group.members.some(m=>m.selector===t.selector && m.context===t.context))) {
      $('content').append(button('Review attach ' + task.selector,()=>previewRelationship(view,{operation:'attach',group_id:group.group_id,member:{selector:task.selector,context:task.context}},rows,group)));
    }
    return;
  }
  const form=element('div',undefined,'card');
  const id=composeField(form,'Immutable fictional group ID (group- plus lowercase letters, digits or hyphens)','groupId'); id.maxLength=54; id.placeholder='group-fictional';
  const label=composeField(form,'Fictional group label (inert text)','groupLabel'); label.maxLength=80;
  const choices=[];
  for (const task of rows) {
    const input=composeField(form,task.selector + ' · ' + task.context + (task.local_work_stopped ? ' · stopped' : ''),'groupMember-' + task.selector); input.type='checkbox'; input.disabled=!!task.local_work_stopped;
    choices.push({input,selector:task.selector,context:task.context});
  }
  form.append(button('Preview exact group',()=>previewRelationship(view,{operation:'create',spec:{group_id:id.value,label:label.value,members:choices.filter(c=>c.input.checked && !c.input.disabled).map(c=>({selector:c.selector,context:c.context}))}},rows),'primary'));
  $('content').append(form);
}
function exactObject(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort());
}
function relationshipMembers(value, rows) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 10) throw new Error('Invalid group membership.');
  const members=value.map(member=>{
    if (!exactObject(member,['selector','context']) || typeof member.selector !== 'string' || typeof member.context !== 'string' ||
        !rows.some(row=>row.selector === member.selector && row.context === member.context)) throw new Error('Unknown exact task context in group review.');
    return {selector:member.selector,context:member.context};
  });
  if (new Set(members.map(member=>member.context)).size !== members.length) throw new Error('Duplicate group membership.');
  return members.sort((a,b)=>a.selector < b.selector ? -1 : a.selector > b.selector ? 1 : a.context < b.context ? -1 : a.context > b.context ? 1 : 0);
}
function validateRelationshipRow(group, rows) {
  if (!exactObject(group,['group_id','label','revision','members','stopped','stop_review']) ||
      typeof group.group_id !== 'string' || !/^group-[a-z0-9][a-z0-9-]{0,47}$/.test(group.group_id) ||
      typeof group.label !== 'string' || [...group.label].length < 1 || [...group.label].length > 80 || group.label !== group.label.trim() ||
      /[\u0000-\u001f\ud800-\udfff]/u.test(group.label) || !Number.isSafeInteger(group.revision) || group.revision < 1 || typeof group.stopped !== 'boolean') throw new Error('Group scope metadata mismatch.');
  relationshipMembers(group.members,rows);
  if (group.stopped) {
    if (!matchesRelationshipPreview(group.stop_review,{operation:'stop',group_id:group.group_id},rows,{...group,stopped:false,revision:group.revision-1})) throw new Error('Group stop history scope mismatch.');
  } else if (group.stop_review !== null) throw new Error('Group stop history scope mismatch.');
}
function matchesRelationshipPreview(preview, request, rows, group) {
  const fields={create:['operation','registry_revision','group_id','label','revision','members','review_digest'],
    attach:['operation','group_id','revision','members','member','review_digest'],
    stop:['operation','group_id','revision','members','review_digest']};
  if (!fields[request.operation] || !exactObject(preview,fields[request.operation]) || preview.operation !== request.operation ||
      typeof preview.review_digest !== 'string' || !/^[a-f0-9]{64}$/.test(preview.review_digest) ||
      !Number.isSafeInteger(preview.revision) || preview.revision < 1) return false;
  const equalMembers=(a,b)=>JSON.stringify(relationshipMembers(a,rows)) === JSON.stringify(relationshipMembers(b,rows));
  if (request.operation === 'create') return preview.group_id === request.spec.group_id && preview.label === request.spec.label &&
    preview.revision === 1 && Number.isSafeInteger(preview.registry_revision) && preview.registry_revision >= 0 && equalMembers(preview.members,request.spec.members);
  if (!group || group.stopped || preview.group_id !== request.group_id || group.group_id !== request.group_id ||
      preview.revision !== group.revision || !equalMembers(preview.members,group.members)) return false;
  return request.operation !== 'attach' || (equalMembers([preview.member],[request.member]) &&
    !group.members.some(member=>member.selector === preview.member.selector && member.context === preview.member.context));
}
async function previewRelationship(view, request, rows, group = null) {
  // Capture desired scope before awaiting a potentially delayed server response.
  const expected=JSON.parse(JSON.stringify(request)), known=JSON.parse(JSON.stringify(rows));
  const inspected=group ? JSON.parse(JSON.stringify(group)) : null;
  const preview=await post(view,'/api/relationship-preview',expected,true);
  if (!preview || !current(view)) return;
  try {
    if (!matchesRelationshipPreview(preview,expected,known,inspected)) throw new Error('Group review scope mismatch.');
  } catch (_) { error('Group review scope mismatch. No review or commit controls were displayed. Refresh the exact group before deciding again.'); return; }
  // Full server review is serialized before any dialog. No mutable form survives.
  const snapshot=JSON.stringify(preview);
  const scope=Object.freeze({...view,relationship:true,group_id:preview.group_id});
  const phrases={create:'CREATE GROUP',attach:'ATTACH TASK',stop:'STOP GROUP'};
  const phrase=phrases[preview.operation];
  if (!phrase) { error('Unknown relationship review operation.'); return; }
  ++generation; active=Object.freeze({...scope,generation});
  const reviewed=active;
  $('tasks').replaceChildren();
  for (const task of rows) $('tasks').append(button(task.selector + ' · ' + task.phase,()=>navigate(path({...task,owner:task.requester},'inbox'))));
  $('tasks').append(button('Fictional task groups',()=>navigate('relationships')));
  $('content').replaceChildren();
  heading('Review exact fictional group scope',GROUP_STOP_NOTICE);
  $('content').append(element('pre',JSON.stringify(JSON.parse(snapshot),null,2)));
  let attempted=false;
  const commit=button('Confirm reviewed group ' + preview.operation,async()=>{
    if (attempted) return;
    const confirmation=await confirmChoice(reviewed,'Confirm group ' + preview.operation,GROUP_STOP_NOTICE,phrase,'Confirm exact group',snapshot);
    if (!confirmation || !current(reviewed) || attempted) return;
    attempted=true; commit.disabled=true;
    const result=await post(reviewed,'/api/action',{action:'relationship_' + preview.operation,review:JSON.parse(snapshot),confirmation});
    if (result && current(reviewed)) navigate('relationships/' + encodeURIComponent(preview.group_id));
  },preview.operation==='stop'?'danger':'primary');
  $('content').append(commit,button('Inspect group without retry',()=>navigate('relationships/' + encodeURIComponent(preview.group_id))),button('Discard review and inspect groups',()=>navigate('relationships')));
}
const CONTINUITY_NOTICE = 'Fictional informational evidence only. Not real-person authentication, an account, provider identity, permission or shared task authority. Active means local recognition of historical possession signatures, not live possession or signer health. Labels and groups never imply an association.';
const RETIRE_NOTICE = 'Retirement permanently ends local continuity recognition. It DOES NOT stop task messages, cancel tasks or revoke grants. Use separate task or group stop controls for that. No reactivation, rotation or recovery.';
const CONTINUITY_ANCHOR = ['incarnation','identity_id','identity_version','continuity_root','fingerprint'];
const CONTINUITY_BODY = ['purpose',...CONTINUITY_ANCHOR,'association_id','selector','context','actor','owner_root','nonce','generation','issued_at','review_expires_at','certificate_expires_at'];
const continuityHex = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const continuityId = value => typeof value === 'string' && /^[a-z][a-z0-9-]{0,47}$/.test(value);
const continuityInt = (value, minimum = 1) => Number.isSafeInteger(value) && value >= minimum;
function continuityAnchor(anchor, incarnation, partial = false) {
  return (exactObject(anchor,CONTINUITY_ANCHOR) || (partial && exactObject(anchor,CONTINUITY_ANCHOR.slice(0,3)))) &&
    anchor.incarnation === incarnation && continuityHex(incarnation) && continuityId(anchor.identity_id) && anchor.identity_version === 1 &&
    (!('continuity_root' in anchor) || (continuityHex(anchor.continuity_root) && continuityHex(anchor.fingerprint)));
}
function continuityBody(body, state, rows) {
  if (!exactObject(body,CONTINUITY_BODY) || body.purpose !== 'informational-fictional-association-only' ||
      !['incarnation','continuity_root','fingerprint','context','owner_root','nonce'].every(k=>continuityHex(body[k])) ||
      !['identity_id','association_id','actor'].every(k=>continuityId(body[k])) ||
      !['identity_version','generation','issued_at','review_expires_at','certificate_expires_at'].every(k=>continuityInt(body[k])) ||
      body.identity_version !== 1 || body.owner_root === body.continuity_root ||
      !(body.issued_at < body.review_expires_at && body.review_expires_at <= body.issued_at + 120) ||
      !(body.review_expires_at < body.certificate_expires_at && body.certificate_expires_at <= body.issued_at + 86400)) return false;
  const identity = state.identities.find(i=>i.anchor.identity_id === body.identity_id);
  const task = rows.find(t=>t.selector === body.selector && t.context === body.context);
  return !!identity && CONTINUITY_ANCHOR.every(k=>body[k] === identity.anchor[k]) &&
    !!task && [task.requester,task.responder].includes(body.actor);
}
function validateContinuityState(state, rows) {
  if (exactObject(state,['enabled']) && state.enabled === false) return;
  if (!exactObject(state,['enabled','incarnation','identities','associations']) || state.enabled !== true || !continuityHex(state.incarnation) ||
      !Array.isArray(state.identities) || state.identities.length > 4 || !Array.isArray(state.associations) || state.associations.length > 20) throw new Error('Continuity metadata shape mismatch.');
  for (const i of state.identities) {
    if (!exactObject(i,['anchor','phase','cleanup']) || !['active','uncertain','retired'].includes(i.phase) || !['live','uncertain','disposed'].includes(i.cleanup) ||
        !continuityAnchor(i.anchor,state.incarnation,i.phase !== 'active') || (i.phase === 'active' && i.cleanup !== 'live')) throw new Error('Continuity identity scope mismatch.');
  }
  if (new Set(state.identities.map(i=>i.anchor.identity_id)).size !== state.identities.length) throw new Error('Duplicate continuity identity.');
  for (const row of state.associations) {
    if (!exactObject(row,['association_id','status','active','historical','review','certificate']) || !continuityId(row.association_id) ||
        !['active','retired','closed','stopped','expired','uncertain'].includes(row.status) || row.active !== (row.status === 'active') || row.historical !== true ||
        !exactObject(row.review,['body','review_digest']) || !continuityHex(row.review.review_digest) || !continuityBody(row.review.body,state,rows) || row.review.body.association_id !== row.association_id) throw new Error('Continuity history scope mismatch.');
    if (row.status === 'uncertain') { if (row.certificate !== null) throw new Error('Uncertain continuity evidence mismatch.'); }
    else if (!exactObject(row.certificate,['body','owner_signature','continuity_signature']) ||
        !CONTINUITY_BODY.every(k=>row.certificate.body && row.certificate.body[k] === row.review.body[k]) || !exactObject(row.certificate.body,CONTINUITY_BODY) ||
        !['owner_signature','continuity_signature'].every(k=>typeof row.certificate[k] === 'string' && /^[a-f0-9]{128}$/.test(row.certificate[k]))) throw new Error('Continuity certificate shape mismatch.');
  }
  if (new Set(state.associations.map(a=>a.association_id)).size !== state.associations.length) throw new Error('Duplicate continuity association.');
}
function matchesContinuityPreview(preview, request, state, rows) {
  if (!preview || !continuityHex(preview.review_digest)) return false;
  const i = state.identities.find(i=>i.anchor.identity_id === request.identity_id);
  if (request.operation === 'enroll') return exactObject(preview,['operation','incarnation','identity_id','generation','review_digest']) &&
    preview.operation === 'enroll' && preview.incarnation === state.incarnation && preview.identity_id === request.identity_id && continuityId(request.identity_id) &&
    continuityInt(preview.generation,0) && !i && state.identities.length < 4;
  if (!i) return false;
  if (request.operation === 'retire') return exactObject(preview,['operation',...Object.keys(i.anchor),'review_digest']) && preview.operation === 'retire' &&
    Object.keys(i.anchor).every(k=>preview[k] === i.anchor[k]);
  const b = preview.body, now = Math.floor(Date.now()/1000);
  const task = rows.find(t=>t.selector === request.selector && t.context === request.context);
  return request.operation === 'associate' && exactObject(preview,['body','review_digest']) && continuityBody(b,state,rows) &&
    ['identity_id','association_id','selector','context','actor'].every(k=>b[k] === request[k]) &&
    i.phase === 'active' && !!task && task.phase === 'open' && !task.local_work_stopped &&
    state.associations.length < 20 && !state.associations.some(a=>a.association_id === request.association_id) &&
    state.associations.filter(a=>a.review.body.selector === request.selector && a.review.body.context === request.context && a.review.body.actor === request.actor).every(a=>a.review.body.owner_root === b.owner_root) &&
    b.issued_at <= now && now < b.review_expires_at;
}
async function renderContinuity(view, rows) {
  const state = await get('/api/continuity');
  if (!current(view)) return;
  validateContinuityState(state,rows);
  heading('Fictional continuity proofs',CONTINUITY_NOTICE);
  $('content').append(button('Inspect continuity state',()=>navigate('continuity')));
  if (!state.enabled) {
    $('content').append(element('p','Continuity is disabled. No continuity keys or signer processes were started. To opt in, explicitly launch locally with --workspace --continuity. This page does not enable, restart or close anything.','card')); return;
  }
  $('content').append(element('pre','Workspace incarnation: ' + state.incarnation),
    element('p','Disposable local history: ' + state.identities.length + '/4 lifetime identity slots and ' + state.associations.length + '/20 lifetime association slots. Failed and uncertain slots are not recycled. Preview starts no key or process. Explicit enrollment starts a separate disposable continuity signer.','muted'),
    element('p','Association review acceptance: up to 120 seconds. Certificate recognition: at most 24 hours from preview creation. Review expiry after signing does not expire the certificate. Inspection never renews either window.','status-block uncertain'));
  for (const i of state.identities) {
    const box = element('article',undefined,'card');
    box.append(element('h2',i.anchor.identity_id + ' · ' + i.phase),element('p','Cleanup: ' + i.cleanup),element('pre',JSON.stringify(i.anchor,null,2)),element('p',RETIRE_NOTICE,'muted'));
    if (i.phase !== 'retired' || i.cleanup !== 'disposed') box.append(button('Preview retirement ' + i.anchor.identity_id,()=>previewContinuity(view,{operation:'retire',identity_id:i.anchor.identity_id},state,rows),'danger'));
    $('content').append(box);
  }
  for (const row of state.associations) {
    // Never style historical recognition as authority. Locally elapsed expiry or
    // known task/identity fences take precedence over a stale active read.
    const b = row.review.body, i = state.identities.find(i=>i.anchor.identity_id === b.identity_id), task = rows.find(t=>t.selector === b.selector && t.context === b.context);
    const status = row.status === 'active' ? i.phase !== 'active' ? 'retired' : task.phase !== 'open' ? 'closed' : task.local_work_stopped ? 'stopped' : Math.floor(Date.now()/1000) >= b.certificate_expires_at ? 'expired' : 'active (local historical recognition only)' : row.status;
    const box = element('article',undefined,'card');
    box.append(element('h2',row.association_id + ' · ' + status),element('p','Historical evidence only; not live possession or permission. Signatures are displayed as server-reported evidence, not independently verified in this browser.','status-block uncertain'),element('pre',JSON.stringify(row,null,2)));
    $('content').append(box);
  }
  if (state.identities.length < 4) {
    const form = element('div',undefined,'card');
    const id = composeField(form,'New fictional continuity identity ID','continuityIdentity'); id.maxLength = 48;
    form.append(button('Preview continuity enrollment',()=>previewContinuity(view,{operation:'enroll',identity_id:id.value},state,rows)));
    $('content').append(form);
  }
  const identities = state.identities.filter(i=>i.phase === 'active');
  const tasks = rows.filter(t=>t.phase === 'open' && !t.local_work_stopped);
  if (identities.length && tasks.length && state.associations.length < 20) {
    const form = element('div',undefined,'card');
    const id = composeField(form,'New fictional association ID','continuityAssociation'); id.maxLength = 48;
    const identity = composeField(form,'Existing active fictional identity','continuityAnchor','select');
    identities.forEach(i=>{ const o=element('option',i.anchor.identity_id); o.value=i.anchor.identity_id; identity.append(o); }); identity.value=identities[0].anchor.identity_id;
    const task = composeField(form,'Existing open, non-stopped task','continuityTask','select');
    tasks.forEach(t=>{ const o=element('option',t.selector + ' · ' + t.context); o.value=t.selector; task.append(o); }); task.value=tasks[0].selector;
    const actor = composeField(form,'Actual fictional task owner','continuityActor','select');
    function actors() {
      actor.replaceChildren(); const t=tasks.find(t=>t.selector === task.value); if (!t) return;
      for (const name of [t.requester,t.responder]) { const o=element('option',name); o.value=name; actor.append(o); } actor.value=t.requester;
    }
    task.addEventListener('change',actors); actors();
    form.append(button('Preview exact continuity association',()=>{
      const t=tasks.find(t=>t.selector === task.value);
      if (!t || ![t.requester,t.responder].includes(actor.value)) { error('Choose an exact existing task and its actual owner.'); return; }
      return previewContinuity(view,{operation:'associate',identity_id:identity.value,association_id:id.value,selector:t.selector,context:t.context,actor:actor.value},state,rows);
    }));
    $('content').append(form);
  }
}
async function previewContinuity(view, request, state, rows) {
  const expected=JSON.parse(JSON.stringify(request)), known=JSON.parse(JSON.stringify(state)), tasks=JSON.parse(JSON.stringify(rows));
  if (!continuityId(expected.identity_id) || (expected.operation === 'associate' && !continuityId(expected.association_id))) { error('Use a lowercase letter followed by at most 47 lowercase letters, digits or hyphens for fictional IDs.'); return; }
  const preview=await post(view,'/api/continuity-preview',expected,true);
  if (!preview || !current(view)) return;
  try { if (!matchesContinuityPreview(preview,expected,known,tasks)) throw Error(); }
  catch (_) { error('Continuity review scope mismatch or expired review. No confirmation controls were displayed. Inspect continuity state before deciding again.'); return; }
  const snapshot=JSON.stringify(preview), operation=expected.operation;
  const phrase=operation.toUpperCase() + ' CONTINUITY ' + preview.review_digest;
  ++generation; active=Object.freeze({...view,generation,continuity:true}); const reviewed=active;
  // Rebuild navigation under the new fence; detached form controls stay inert.
  $('tasks').replaceChildren();
  for (const task of tasks) $('tasks').append(button(task.selector + ' · ' + task.phase,()=>navigate(path({...task,owner:task.requester},'inbox'))));
  $('tasks').append(button('Fictional continuity proofs',()=>navigate('continuity')));
  $('content').replaceChildren();
  heading('Review exact continuity ' + operation,CONTINUITY_NOTICE);
  const notice=operation === 'retire' ? RETIRE_NOTICE : operation === 'enroll' ? 'Explicit enrollment starts one disposable signer, not an account or task.' : 'Confirming authorizes two informational possession signatures for this exact body only. No task creation, binding, pairing, grant or message. Owner root is the exact server-backed task-owner public root, not a verified real identity. The backend signer remains authoritative.';
  $('content').append(element('p',notice,'status-block uncertain'),element('pre',JSON.stringify(JSON.parse(snapshot),null,2)),element('pre','Exact confirmation phrase: ' + phrase));
  if (operation === 'associate') $('content').append(element('p','Up to 120-second review acceptance window; at most 24-hour certificate recognition from issued_at. No renewal by inspection.'));
  let attempted=false;
  const commit=button('Confirm reviewed continuity ' + operation,async()=>{
    if (attempted) return;
    if (operation === 'associate' && Math.floor(Date.now()/1000) >= preview.body.review_expires_at) { error('Review acceptance window expired. Inspect continuity state and prepare a fresh review.'); commit.disabled=true; return; }
    const confirmation=await confirmChoice(reviewed,'Confirm continuity ' + operation,notice,phrase,'Confirm exact continuity review',snapshot);
    if (!confirmation || !current(reviewed) || attempted) return;
    if (operation === 'associate' && Math.floor(Date.now()/1000) >= preview.body.review_expires_at) { error('Review acceptance window expired. Nothing was committed.'); commit.disabled=true; return; }
    attempted=true; commit.disabled=true;
    const result=await post(reviewed,'/api/action',{action:'continuity_' + operation,review:JSON.parse(snapshot),confirmation});
    // Inspect authoritative history after any successful response; do not treat
    // returned mutation JSON as proof of active authority or sign again.
    if (result && current(reviewed)) navigate('continuity');
  },operation === 'retire' ? 'danger' : 'primary');
  $('content').append(commit,button('Inspect continuity without retry',()=>navigate('continuity')),button('Discard continuity review',()=>navigate('continuity')));
}

async function render(draft = null) {
  const token = ++generation, hash = location.hash;
  renderedHash = hash;
  if (cancelDialog) cancelDialog();
  $('error').hidden = true; $('error').textContent = ''; message('');
  $('content').replaceChildren(); $('controls').replaceChildren(); $('tasks').replaceChildren();
  active = Object.freeze({generation:token,hash});
  try {
    const rows = await get('/api/tasks');
    if (token !== generation || hash !== location.hash) return;
    const parts = hash.slice(1).split('/').map(decodeURIComponent);
    const row = rows.find(r=>r.selector===parts[0]);
    for (const task of rows) $('tasks').append(button(task.selector + ' · ' + task.phase,
      ()=>navigate(path({...task,owner:task.requester},'inbox')),task === row ? 'selected' : ''));
    $('tasks').append(button('Fictional task groups',()=>navigate('relationships')));
    $('tasks').append(button('Fictional continuity proofs',()=>navigate('continuity')));
    if (parts.length === 1 && parts[0] === 'continuity') return await renderContinuity(active,rows);
    if (parts[0] === 'relationships') return await renderRelationships(active,rows,parts[1]);
    $('tasks').append(button('Compose temporary task',()=>navigate('compose')));
    if (parts.length === 1 && parts[0] === 'compose') return renderComposer(active,draft && draft.composition);
    if (!row) { heading('Choose a fictional task','Garden, astronomy and composed tasks use separate temporary services, keys and records. Merely opening a task does not create it.'); return; }
    const owner = [row.requester,row.responder].includes(parts[1]) ? parts[1] : row.requester;
    let view = Object.freeze({...row,owner,generation:token,hash}); active = view;
    $('content').append(element('p',row.selector + ' · ' + row.phase,'eyebrow'),
      element('pre','Task: ' + row.task + '\nContext: ' + row.context + '\nRequester: ' + row.requester + ' → Responder: ' + row.responder,'task-meta'));
    if ((row.relationship_groups || []).length) $('content').append(element('pre','Fictional group memberships (overlap allowed):\n' + JSON.stringify(row.relationship_groups,null,2)));
    if (row.local_work_stopped) $('content').append(element('p',GROUP_STOP_NOTICE,'status-block'));
    if (row.phase === 'not_created' && row.local_work_stopped) { heading('Further local work stopped','This exact catalog task cannot be created. No service was started.'); return; }
    if (row.phase === 'not_created') {
      heading('Temporary service not created','Create only this selected task. This does not bind identities, pair, approve, submit or send.');
      $('content').append(button('Create selected temporary task',async()=>{
        const result = await mutate(view,{action:'create'});
        if (result && current(view)) render();
        else if (current(view)) {
          const rows = await get('/api/tasks').catch(()=>null);
          if (rows && current(view)) {
            const latest = rows.find(r=>r.selector===view.selector);
            if (latest && latest.phase !== 'not_created') render();
          }
        }
      },'primary'));
      return;
    }
    if (row.phase !== 'open') {
      heading(row.phase === 'closed' ? 'Task closed' : 'Task blocked: cleanup uncertain',
        row.phase === 'closed' ? 'Its temporary keys and records were discarded. No replacement was created. Other tasks remain available.' : 'Some temporary resources may remain. Affected task controls are blocked. Stop the launcher and inspect its temporary state; do not assume discard succeeded. Other tasks are independent.');
      return;
    }
    const state = await read(view,'state');
    if (!current(view)) return;
    if (state.phase !== 'bindings' && state.phase !== 'ready') {
      heading('Task unavailable: ' + state.phase,'No mutation controls are enabled. Cleanup may be incomplete; inspect the launcher.'); return;
    }
    view = Object.freeze({...view,local_work_stopped:!!(view.local_work_stopped || state.local_work_stopped),relationship_groups:state.relationship_groups || view.relationship_groups}); active = view;
    controls(view,state.phase === 'ready',state);
    if (view.local_work_stopped && (state.phase === 'bindings' || parts[2] === 'response')) { heading('Further local work stopped','Read-only task history. No binding, import, composition or new review is available.'); $('content').append(element('pre',JSON.stringify(state,null,2))); return; }
    if (state.phase === 'bindings') return renderBindings(state,view);
    if (parts[2] === 'request' && parts[3]) {
      const card = await read(view,'review',parts[3]);
      if (current(view)) renderReview(card,view);
    } else if (parts[2] === 'delivery' && parts[3]) {
      const [status,card] = await Promise.all([read(view,'delivery',parts[3]),read(view,'review',parts[3])]);
      if (current(view)) renderDelivery(status,card,view);
    } else if (parts[2] === 'proposals') await renderProposals(view);
    else if (parts[2] === 'messages') await renderReceivedMessages(view);
    else if (parts[2] === 'response') await renderResponseComposer(view,draft && draft.response);
    else renderInbox(state,view);
  } catch (exc) { if (token === generation && hash === location.hash) error(exc.message + ' No automatic retry.'); }
}
window.addEventListener('hashchange',()=>{ if (renderedHash !== location.hash) render(); });
render();
