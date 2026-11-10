// Pure projections and validation. Unknown states/actions never supply authority.
const HEX = /^[a-f0-9]{64}$/;
const ACTIONS = new Set(['accept', 'reject', 'release', 'cancel']);
const TERMINAL = new Set(['accepted', 'rejected', 'cancelled', 'canceled', 'withdrawn', 'revoked', 'expired']);
const PENDING = new Set(['pending', 'proposed', 'draft', 'received', 'awaiting_review', 'prepared']);
const WORKFLOW_ACTIONS = new Set(['review','approve','run','cancel','review_result','stage']);
const WORKFLOW_STATES = new Set(['prepared','approved','cancelled','uncertain','completed','expired']);
export const FIXTURE_GRANT = Object.freeze({provider:'openai',model:'synthetic-research-v1',max_output_tokens:128});
export function workflowEnabled(state) { return state?.workflow?.enabled===true && state.workflow.synthetic_only===true && state.workflow.live_enabled===false; }
export function workflowStateLabel(state) { return ({prepared:'Run awaiting approval',approved:'Run approved',cancelled:'Run cancelled',uncertain:'Run outcome uncertain',completed:'Original result retained',expired:'Run approval expired'})[state]||'Run status unavailable'; }
export function workflowSummary(run) {
  const status=workflowStateLabel(run.state);
  if(!run.artifact_id)return status;
  const artifact=({draft:'Draft awaiting release',released:'Artifact released',accepted:'Artifact accepted',rejected:'Artifact rejected',cancelled:'Artifact cancelled',expired:'Artifact expired'})[run.artifact_state]||'Artifact status unavailable';
  return `${status} · ${artifact}`;
}
export const labels = Object.freeze({pending:'To review', proposed:'To review', draft:'Awaiting release', prepared:'Awaiting release', received:'To review', awaiting_review:'To review', accepted:'Accepted', rejected:'Rejected', cancelled:'Cancelled', canceled:'Cancelled', withdrawn:'Withdrawn', revoked:'Revoked', expired:'Expired', uncertain:'Outcome uncertain', released:'Released', queued:'Queued', delivered:'Delivered'});
export function plain(value, fallback='') { return typeof value === 'string' ? value : fallback; }
export function finiteDate(value) { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
export function stateLabel(value) { return labels[value] || 'Status unavailable'; }
export function statusClass(value) { return Object.hasOwn(labels,value) ? value : 'unknown'; }
export function isPending(item) { return PENDING.has(item.state); }
export function isTerminal(item) { return TERMINAL.has(item.state); }
export function isPeerActive(peer) { return peer.state==='active'; }
export function filteredItems(items,view,filter) {
  return items.filter(item => item.direction === (view === 'outbox' ? 'outgoing' : 'incoming'))
    .filter(item => filter === 'all' || (filter === 'pending' ? isPending(item) : isTerminal(item)));
}
export function validateState(value) {
  if (!value || typeof value !== 'object' || !value.identity || typeof value.identity !== 'object') throw new Error('Invalid workspace state');
  const identity = value.identity;
  if (!plain(identity.owner_id) || !plain(identity.agent_id) || !HEX.test(plain(identity.fingerprint))) throw new Error('Invalid workspace identity');
  if (!Array.isArray(value.peers) || !Array.isArray(value.items) || !Array.isArray(value.history)) throw new Error('Invalid workspace lists');
  if (value.items.length > 4096 || value.peers.length > 128 || value.history.length > 10000) throw new Error('Workspace bounds exceeded');
  const ids = new Set();
  for (const item of value.items) {
    if (!item || !plain(item.id) || ids.has(item.id) || !['incoming','outgoing'].includes(item.direction) || !['task','artifact'].includes(item.kind) || !plain(item.state)) throw new Error('Invalid proposal metadata');
    ids.add(item.id);
  }
  for (const peer of value.peers) {
    if (!peer || !plain(peer.peer_id) || !HEX.test(plain(peer.fingerprint))) throw new Error('Invalid peer identity');
  }
  if (value.workflow !== undefined) {
    const workflow=value.workflow;
    if (!workflow || typeof workflow.enabled!=='boolean' || workflow.synthetic_only!==true || workflow.live_enabled!==false || !Array.isArray(workflow.runs) || workflow.runs.length>256) throw new Error('Invalid synthetic workflow state');
    const runs=new Set();
    for(const run of workflow.runs){const item=value.items.find(item=>item.id===run.item_id);if(!item||runs.has(run.run_id))throw new Error('Invalid workflow task');validateWorkflowStatus(run,item);runs.add(run.run_id);}
  }
  return value;
}
export function fixturePermission(value) { return value?.provider==='openai' && value.model===FIXTURE_GRANT.model && value.max_output_tokens===128 && Object.keys(value).length===3; }
export function canPrepareWorkflow(state,item,review,now=Date.now()/1000) {
  return workflowEnabled(state) && item.direction==='incoming' && item.kind==='task' && item.state==='accepted' && item.expires>now && state.peers.some(peer=>peer.peer_id===item.peer_id&&isPeerActive(peer)) && review.content!==null && fixturePermission(review.source_permissions?.provider_disclosure) && !state.workflow.runs.some(run=>run.item_id===item.id);
}
export function validateWorkflowStatus(value,item) {
  if(!value || value.run_id!=='work-'+item.id || value.item_id!==item.id || item.direction!=='incoming' || item.kind!=='task' || !WORKFLOW_STATES.has(value.state) || !HEX.test(plain(value.review_digest)) || value.synthetic_only!==true || value.live_enabled!==false || value.live_provider_verified!==false || value.authorises_publication!==false || value.retry_allowed!==false || typeof value.workflow_enabled!=='boolean' || typeof value.cancel_requested!=='boolean' || !Array.isArray(value.allowed_actions))throw new Error('Invalid exact workflow state');
  if(value.allowed_actions.some(action=>!WORKFLOW_ACTIONS.has(action)) || new Set(value.allowed_actions).size!==value.allowed_actions.length || (!value.workflow_enabled&&value.allowed_actions.some(action=>!['review','review_result'].includes(action))))throw new Error('Invalid workflow actions');
  if(value.allowed_actions.includes('approve')&&value.state!=='prepared' || value.allowed_actions.includes('run')&&value.state!=='approved' || value.allowed_actions.some(action=>['stage','review_result'].includes(action))&&value.state!=='completed' || value.cancel_requested&&value.allowed_actions.some(action=>['approve','run','stage','review_result'].includes(action)))throw new Error('Invalid workflow transition');
  if(value.artifact_id!==null&&!HEX.test(plain(value.artifact_id)) || value.result_digest!==null&&!HEX.test(plain(value.result_digest)) || value.result_review_digest!==null&&!HEX.test(plain(value.result_review_digest)) || value.artifact_id&&value.allowed_actions.includes('stage'))throw new Error('Invalid retained workflow commitments');
  return value;
}
export function validateWorkflowReview(value,run,item,identity) {
  const review=value?.review,binding=review?.binding,request=review?.request;
  if(!review || value.run_id!==run.run_id || value.review_digest!==run.review_digest || value.synthetic_only!==true || review.synthetic_only!==true || review.domain!=='assistant-central-responses-pilot/1/review' || review.run_id!==run.run_id || review.owner!==identity.owner_id || review.agent!==identity.agent_id || review.endpoint!=='https://api.openai.com/v1/responses' || binding?.item_id!==item.id || binding.context!==item.context || binding.payload_digest!==item.artifact_digest || !fixturePermission({provider:binding?.provider,model:binding?.model,max_output_tokens:binding?.max_output_tokens}) || request?.model!==FIXTURE_GRANT.model || request.max_output_tokens!==128 || typeof request.input!=='string' || !request.input || request.input.length>16384 || !Array.isArray(request.tools) || request.tools.length || request.tool_choice!=='none' || request.store!==false || request.stream!==false || request.background!==false)throw new Error('Invalid exact synthetic request review');
  return value;
}
export function validateWorkflowResult(value,run,item,peer) {
  const review=value?.review,recipient=review?.recipient,publicIdentity=peer?.public||peer;
  if(!review || value.run_id!==run.run_id || !HEX.test(plain(value.review_digest)) || value.synthetic_only!==true || value.authorises_publication!==false || review.synthetic_only!==true || review.domain!=='assistant-central-synthetic-workflow/1/result-review' || review.run_id!==run.run_id || review.item_id!==item.id || review.parent_id!==item.id || review.context!==item.context || review.provider_review_digest!==run.review_digest || review.result_digest!==run.result_digest || !HEX.test(plain(review.source_permissions_digest)) || typeof value.content!=='string' || !value.content || value.content.length>16384 || review.text!==value.content || !plain(review.title) || typeof review.expires!=='number' || !Number.isFinite(review.expires) || review.expires>item.expires || !recipient || !publicIdentity || ['owner_id','agent_id','signing_key','exchange_key'].some(key=>!plain(recipient[key])||recipient[key]!==publicIdentity[key]))throw new Error('Invalid exact original-result review');
  const artifact=review.artifact;
  if(!artifact || !HEX.test(plain(review.artifact_id)) || artifact.kind!=='artifact' || artifact.parent_id!==item.id || artifact.task_id!==item.task_id || artifact.context!==item.context || artifact.text!==value.content || artifact.title!==review.title || artifact.expires!==review.expires || artifact.artifact_digest!==run.result_digest || ['owner_id','agent_id','signing_key','exchange_key'].some(key=>artifact.recipient?.[key]!==recipient[key]))throw new Error('Invalid exact return artifact');
  if(run.result_review_digest!==null&&run.result_review_digest!==value.review_digest)throw new Error('Result review commitment changed');
  return value;
}
export function validateReview(value,item) {
  if (!value || value.item_id !== item.id || !HEX.test(plain(value.review_digest)) || !HEX.test(plain(value.context)) || !HEX.test(plain(value.artifact_digest)) || !(value.content===null||typeof value.content==='string') || (value.content?.length||0)>16384 || !Array.isArray(value.allowed_actions)) throw new Error('Invalid exact review');
  if (item.context && value.context !== item.context) throw new Error('Review context changed');
  if (item.artifact_digest && value.artifact_digest !== item.artifact_digest) throw new Error('Review artifact changed');
  if (value.allowed_actions.some(action => !ACTIONS.has(action)) || new Set(value.allowed_actions).size !== value.allowed_actions.length) throw new Error('Invalid review actions');
  if (item.direction === 'outgoing' && value.allowed_actions.some(action => action === 'accept' || action === 'reject')) throw new Error('Wrong decision authority');
  if (item.direction === 'incoming' && value.allowed_actions.includes('release')) throw new Error('Wrong release authority');
  if (value.content===null && value.allowed_actions.some(action=>action==='accept'||action==='release')) throw new Error('Content is unavailable for approval');
  if (isTerminal(item) && value.allowed_actions.some(action => action !== 'cancel' && !(action==='reject'&&item.historical_state==='pending'))) throw new Error('Terminal decision cannot be renewed');
  return value;
}
export function proposalBody(fields,now=Date.now()/1000) {
  const minutes = Number(fields.minutes);
  if (!['task','artifact'].includes(fields.kind) || !plain(fields.peer_id) || !plain(fields.title).trim() || !plain(fields.text).trim() || !HEX.test(plain(fields.context)) || !/^[A-Za-z0-9_.:-]{1,96}$/.test(plain(fields.task_id)) || ![15,30,60].includes(minutes) || fields.synthetic !== 'on') throw new Error('Check the proposal fields and fictional-content confirmation.');
  if (fields.title.length > 120 || fields.text.length > 4096 || !Number.isFinite(now)) throw new Error('Proposal is outside the allowed bounds.');
  const result = {peer_id:fields.peer_id,kind:fields.kind,title:fields.title,text:fields.text,context:fields.context,task_id:fields.task_id,expires:Math.floor(now)+minutes*60};
  if(fields.synthetic_run==='on') { if(fields.kind!=='task')throw new Error('Only an originating task can permit the synthetic rehearsal.');result.provider_disclosure={...FIXTURE_GRANT}; }
  if (fields.kind === 'artifact') {
    if (!plain(fields.parent_id)) throw new Error('Choose the accepted task this artifact answers.');
    result.parent_id = fields.parent_id;
    if(fields.parent_expires!==undefined){const expiry=Number(fields.parent_expires);if(!Number.isFinite(expiry)||expiry<=now)throw new Error('The original task has expired.');result.expires=Math.min(result.expires,Math.floor(expiry));}
  }
  return result;
}
export function peerBody(fields) {
  if (fields.verified !== 'on' || !HEX.test(plain(fields.expected_fingerprint))) throw new Error('Check and confirm the full peer fingerprint.');
  let identity;
  try { identity = JSON.parse(fields.public_identity); } catch { throw new Error('Enter a valid public identity object.'); }
  if (!identity || Array.isArray(identity) || typeof identity !== 'object' || Object.keys(identity).some(key => /private|secret|password|token/i.test(key))) throw new Error('Only a public identity can be enrolled.');
  const result={public_identity:identity,expected_fingerprint:fields.expected_fingerprint};
  if (!fields.endpoint)throw new Error('Enter the other local pilot’s address.');
  if (fields.endpoint) {
    let endpoint;
    try { endpoint=new URL(fields.endpoint); } catch { throw new Error('Enter a valid local pilot address.'); }
    if (endpoint.protocol !== 'http:' || endpoint.hostname!=='127.0.0.1' || !endpoint.port || Number(endpoint.port)<1024 || Number(endpoint.port)>65535 || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || !['','/'].includes(endpoint.pathname) || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{3,4}\/?$/.test(fields.endpoint)) throw new Error('Use the other local pilot’s exact 127.0.0.1 HTTP address and port.');
    result.endpoint=endpoint.origin;
  }
  return result;
}
