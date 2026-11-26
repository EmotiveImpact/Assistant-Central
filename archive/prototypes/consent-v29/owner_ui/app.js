'use strict';
const $ = id => document.getElementById(id);
let busy = false;
let generation = 0;
let phase = 'bindings';
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(text, handler, cls = '', disabled = false) {
  const node = element('button', text, cls);
  node.disabled = disabled;
  node.addEventListener('click', () => { if (!busy) handler(); });
  return node;
}
function error(message) { $('error').textContent = message; $('error').hidden = false; }
function clearError() { $('error').hidden = true; $('error').textContent = ''; }
function message(text) { $('message').textContent = text; }
async function get(path) {
  const response = await fetch(path, {cache: 'no-store', credentials: 'omit'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The local fixture could not return this view.');
  return data;
}
async function act(body) {
  if (busy) return null;
  busy = true; document.body.classList.add('pending-call');
  const prior = new Map([...document.querySelectorAll('button,select')].map(node => [node, node.disabled]));
  prior.forEach((_, node) => { node.disabled = true; });
  clearError();
  try {
    let response, data;
    try {
      response = await fetch('/api/action', {method: 'POST', credentials: 'omit', cache: 'no-store',
        headers: {'Content-Type': 'application/json', 'X-Owner-Fixture': 'v7'}, body: JSON.stringify(body)});
      data = await response.json();
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid action response');
    } catch (_) {
      throw new Error('The response was lost. The action may have committed. Inspect the request or check its receipt; do not repeat it blindly. Nothing was retried automatically.');
    }
    if (!response.ok) throw new Error(data.error || 'Action refused. Refresh the review before deciding again.');
    return data;
  } catch (exc) { error(exc.message); return null; }
  finally {
    busy = false; document.body.classList.remove('pending-call');
    prior.forEach((disabled, node) => { if (node.isConnected) node.disabled = disabled; });
  }
}
function confirmChoice(title, description, phrase, label) {
  return new Promise(resolve => {
    const dialog = $('confirmDialog');
    $('dialogTitle').textContent = title; $('dialogBody').textContent = description;
    $('confirmationLabel').textContent = 'Type ' + phrase + ' to continue';
    $('confirmation').value = ''; $('confirmation').placeholder = phrase;
    $('dialogConfirm').textContent = label; $('dialogConfirm').disabled = true;
    let done = false;
    const finish = value => {
      if (done) return; done = true;
      dialog.close(); $('confirmation').oninput = null;
      $('dialogCancel').onclick = null; $('dialogConfirm').onclick = null; dialog.oncancel = null;
      resolve(value);
    };
    $('confirmation').oninput = () => { $('dialogConfirm').disabled = $('confirmation').value !== phrase; };
    $('dialogCancel').onclick = () => finish(null);
    $('dialogConfirm').onclick = () => finish($('confirmation').value);
    dialog.oncancel = event => { event.preventDefault(); finish(null); };
    dialog.showModal(); $('confirmation').focus();
  });
}
function navigate(route) {
  const value = '#' + route;
  if (location.hash === value) render(); else location.hash = value;
}
function showResult(result) {
  if (!result) return;
  if (result.kind === 'request') {
    $('owner').value = result.card.owner;
    navigate(`request/${result.card.owner}/${result.card.request_id}`);
  } else if (result.kind === 'delivery') {
    $('owner').value = result.owner;
    navigate(`delivery/${result.owner}/${result.delivery_id}`);
  } else if (result.kind === 'complete' || result.kind === 'stopped') {
    message(result.reason); navigate('inbox/' + $('owner').value);
  }
}
function heading(title, description) {
  const intro = element('div', undefined, 'intro');
  intro.append(element('p', 'OWNER WORKSPACE', 'eyebrow'), element('h1', title), element('p', description, 'muted'));
  $('content').append(intro);
}
function renderBindings(state) {
  heading('Start with explicit identities', 'Approve a disposable transport binding for each fictional owner. These signatures prove fixture key possession, not a real person’s identity. No messages are sent by binding.');
  const cards = element('div', undefined, 'cards');
  for (const binding of state.bindings) {
    const card = element('article', undefined, 'card');
    const top = element('div', undefined, 'card-top');
    top.append(element('h3', binding.owner), element('span', binding.approved ? 'APPROVED' : 'NEEDS REVIEW', 'tag'));
    card.append(top, element('p', 'May receive from: ' + binding.receive_from.join(', '), 'muted'),
      element('p', 'Transport public key', 'eyebrow'), element('p', binding.transport_pubkey, 'key'),
      element('p', 'Meeting: ' + state.meeting + '. Expires: ' + new Date(binding.expires_at * 1000).toISOString(), 'muted small'));
    card.append(button(binding.approved ? 'Binding approved' : 'Review binding', async () => {
      const confirmation = await confirmChoice('Bind ' + binding.owner,
        'This approves the displayed transport key and exact meeting for fictional ' + binding.owner + '. Receiving peers: ' + binding.receive_from.join(', ') + '. It does not authorize any outbound message.',
        'BIND ' + binding.owner, 'Approve binding');
      if (!confirmation) return;
      const result = await act({action:'bind', owner:binding.owner, binding_digest:binding.digest, confirmation});
      if (result) { message('Fixture binding approved. No message sent.'); render(); }
    }, 'primary', binding.approved));
    cards.append(card);
  }
  $('content').append(cards);
}
function renderInbox(state) {
  heading(state.owner + '’s inbox', 'Each request is a decision for this owner only. Opening or refreshing a review grants nothing. Start the guide only when you want the next fictional request prepared.');
  const card = element('div', undefined, 'card');
  if (!state.inbox.length) {
    card.classList.add('empty'); card.append(element('h2', 'No requests yet'), element('p', 'Prepare the next review to begin. Binding identities did not pair contacts, approve disclosures or send anything.', 'muted'));
  }
  for (const item of state.inbox) {
    const row = element('div', undefined, 'request-row');
    const text = element('div');
    text.append(element('h3', item.action + ' · ' + item.state), element('small', item.request_id));
    if (item.reason) text.append(element('p', item.reason, 'muted'));
    row.append(text, button('Open review', () => navigate(`request/${item.owner}/${item.request_id}`)));
    card.append(row);
  }
  $('content').append(card, element('p', 'Showing the latest 20 requests for this fictional owner. Declined requests are retained, not silently recreated.', 'muted small'));
}
function renderReview(card) {
  heading('Review for ' + card.owner, 'Approval, submission and delivery are separate steps. Nothing is sent by viewing this page.');
  const container = element('article', undefined, 'card');
  const top = element('div', undefined, 'card-top'); top.append(element('h2', card.action), element('span', card.state.toUpperCase(), 'tag'));
  container.append(top, element('p', 'Request ' + card.request_id, 'muted small'), element('div', card.review, 'review'));
  if (card.reason) container.append(element('p', card.reason, 'status-block uncertain'));
  const actions = element('div', undefined, 'actions');
  const decisionActions = () => {
    actions.replaceChildren();
    if (card.state === 'pending' || card.state === 'deferred') {
      actions.append(button('Approve exact request', async () => {
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
      if (card.state === 'authorized') actions.append(button('Submit approved request', async () => showResult(await act({action:'submit',owner:card.owner,request_id:card.request_id})), 'primary'));
      actions.append(button('Check committed approval', async () => showResult(await act({action:'recover',owner:card.owner,request_id:card.request_id}))));
    } else if (card.stored_state === 'submitted' && card.action === 'send') {
      actions.append(button('View delivery status', () => navigate(`delivery/${card.owner}/${card.request_id}`), 'primary'));
    }
    if (card.can_replace) actions.append(button('Prepare new review', async () => {
      const confirmation = await confirmChoice('Prepare a new unsigned review?',
        'The old expired or stale draft is retained as replaced. This creates a new request for the same action, participants and meeting, and the exact message for a send, using current contact versions. It does not approve, submit or send anything. A fresh explicit approval will still be required.',
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
    if (card.can_prepare_fresh) actions.append(button('Prepare fresh unsigned review', async () => {
      const confirmation = await confirmChoice('Prepare a separate fresh review?',
        'The withdrawn signature stays permanently blocked. Prepare a new unsigned request for the same action, participants, meeting and exact message, using current permissions. Fresh approval, submission and any delivery remain separate. Nothing is sent by this choice.',
        'REVIEW ' + card.owner, 'Prepare fresh unsigned review');
      if (!confirmation) return;
      showResult(await act({action:'fresh_after_withdrawal',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,confirmation}));
    }));
    if (card.withdrawn_successor) actions.append(button('Open fresh review', () => navigate(`request/${card.owner}/${card.withdrawn_successor}`)));
    for (const direction of card.pairing_reviews || []) actions.append(button('Review pairing for ' + direction.owner, async () => {
      const confirmation = await confirmChoice('Open ' + direction.owner + '’s pairing review?',
        'Pairing from ' + direction.owner + ' to ' + direction.peer + ' is ' + direction.state + ' for this exact meeting. Open an existing review or prepare a new unsigned one. This grants nothing. That owner must separately approve and submit; a refusal or deferral stays visible. The original message will still require a fresh send review.',
        'REVIEW PAIR ' + direction.owner, 'Open pairing review');
      if (!confirmation) return;
      showResult(await act({action:'review_pairing',owner:card.owner,request_id:card.request_id,review_digest:card.review_digest,direction_owner:direction.owner,confirmation}));
    }));
    for (const source of card.pairing_sources || []) actions.append(button('Return to ' + source.owner + '’s blocked send', () => navigate(`request/${source.owner}/${source.request_id}`)));
    if (card.replaced_by) actions.append(button('Open replacement review', () => navigate(`request/${card.owner}/${card.replaced_by}`), 'primary'));
    actions.append(button('Refresh review', render), button('Back to inbox', () => navigate('inbox/' + card.owner)));
  };
  if (card.state === 'deferred') {
    container.append(element('p', 'Paused. Returning to this page does not resume or approve it.', 'status-block'));
    actions.append(button('Resume review', decisionActions, 'primary'), button('Back to inbox', () => navigate('inbox/' + card.owner)));
  } else decisionActions();
  if (card.replaces) container.append(element('p', 'New unsigned review replacing request ' + card.replaces + '. No approval was carried forward.', 'muted'));
  if (card.replacement_blocker) container.append(element('p', 'A replacement cannot be prepared: ' + card.replacement_blocker, 'muted'));
  if (card.state === 'withdrawn') container.append(element('p', 'Unused authorization withdrawn. No delivery was queued by this authorization. Its original signature remains blocked in this local executor; nothing was recalled and no new approval was granted.', 'status-block'));
  if (card.fresh_review_blocker) container.append(element('p', 'A fresh review cannot be prepared: ' + card.fresh_review_blocker + '. Existing owner controls and the guide remain available.', 'muted'));
  if ((card.pairing_reviews || []).length) container.append(element('p', 'Missing pairing is reviewed one owner at a time. Neither viewing nor preparing these reviews restores consent. Existing active pairing is not extended.', 'muted'));
  if ((card.pairing_sources || []).length) container.append(element('p', 'This separate pairing review was opened from a blocked send. Approval and submission grant only this pairing; they do not revive or send that message.', 'muted'));
  if (card.stored_state === 'declined') container.append(element('p', 'This request is terminally declined. A later signature cannot revive it through this workflow.', 'muted'));
  if (card.stored_state === 'submitted') container.append(element('p', 'Submitted means the control was applied or the message was enqueued. It is not evidence of delivery.', 'muted'));
  container.append(actions); $('content').append(container);
}
function renderDelivery(status, card) {
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
      'Only the already-approved recipient and ciphertext are used. An uncertain previous attempt is checked for an existing receipt first. This is not a new approval or a calendar booking, and an in-flight attempt cannot be recalled.',
      'SEND ' + card.owner, 'Start delivery attempt');
    if (!confirmation) return;
    showResult(await act({action:'attempt',owner:card.owner,request_id:card.request_id,confirmation}));
  }, 'primary', !status.can_start_attempt));
  actions.append(button('Process received message', async () => showResult(await act({action:'process',owner:card.owner,request_id:card.request_id})), '', !status.can_process));
  actions.append(button('Refresh status', render),button('Back to review',()=>navigate(`request/${card.owner}/${card.request_id}`)));
  container.append(actions,element('p','Receipt checking never dispatches or processes a message. No calendar booking is created.','muted small'));
  $('content').append(container);
}
async function render() {
  const token = ++generation; clearError();
  const parts = location.hash.slice(1).split('/');
  const route = ['inbox','request','delivery'].includes(parts[0]) ? parts[0] : 'inbox';
  const owner = ['alice','bob','charlie','dana'].includes(parts[1]) ? parts[1] : $('owner').value;
  $('owner').value = owner;
  try {
    const state = await get('/api/state?owner=' + encodeURIComponent(owner));
    if (token !== generation) return;
    phase = state.phase; $('content').replaceChildren();
    for (const id of ['nextButton','cancelButton','revokeButton']) $(id).disabled = phase !== 'ready';
    $('summary').textContent = state.summary ? `${state.summary.receiver_receipts} verified receipts · ${state.summary.transitions} processed messages\n${state.summary.agreed ? 'All four accepted. No booking made.' : 'Meeting not yet agreed.'}` : 'No scheduling information disclosed.';
    if (phase === 'bindings') return renderBindings(state);
    if (phase === 'cleanup_uncertain') { heading('Cleanup incomplete', 'Fixture actions are blocked. Some temporary resources may remain. Retry Discard fixture, or stop the launcher and check its temporary state. Nothing is approved or retried automatically.'); return; }
    if (phase === 'closed') { heading('Fixture closed','Temporary records and keys were discarded. There is no automatic identity recovery.'); return; }
    if (route === 'request' && parts[2]) {
      const card = await get('/api/review?owner=' + owner + '&id=' + encodeURIComponent(parts[2]));
      if (token === generation) renderReview(card);
    } else if (route === 'delivery' && parts[2]) {
      const [status, card] = await Promise.all([get('/api/delivery?owner=' + owner + '&id=' + encodeURIComponent(parts[2])),get('/api/review?owner=' + owner + '&id=' + encodeURIComponent(parts[2]))]);
      if (token === generation) renderDelivery(status,card);
    } else renderInbox(state);
  } catch (exc) { if (token === generation) error(exc.message + ' No action was retried.'); }
}
$('owner').addEventListener('change', () => navigate('inbox/' + $('owner').value));
$('inboxButton').addEventListener('click', () => { if (!busy) navigate('inbox/' + $('owner').value); });
$('nextButton').addEventListener('click', async () => { if (!busy && phase === 'ready') showResult(await act({action:'next'})); });
$('cancelButton').addEventListener('click', async () => { if (!busy && phase === 'ready') showResult(await act({action:'cancel',owner:$('owner').value})); });
$('revokeButton').addEventListener('click', async () => { if (!busy && phase === 'ready') showResult(await act({action:'revoke',owner:$('owner').value,peer:$('peer').value})); });
$('closeButton').addEventListener('click', async () => {
  if (busy) return;
  const confirmation = await confirmChoice('Discard this fixture?', 'This stops the local fixture and discards its temporary records and generated keys. Closing only this browser tab does not stop it. There is no later identity or inbox recovery.', 'DISCARD FIXTURE','Discard fixture');
  if (!confirmation) return;
  const result = await act({action:'close',confirmation});
  if (result) { ++generation; phase='closed'; $('content').replaceChildren(); heading('Fixture discarded','The local process was stopped and temporary records and keys were discarded. You can close this tab.'); document.querySelectorAll('button,select').forEach(node=>node.disabled=true); }
});
window.addEventListener('hashchange',render);
render();
