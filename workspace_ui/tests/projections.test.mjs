import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// The launcher serves the existing pilot model at /model.mjs. Resolve that
// same module for Node without adding a second copy or changing its contents.
const modelURL=new URL('../../pilot/web/model.mjs',import.meta.url).href;
const source=(await readFile(new URL('../projections.mjs',import.meta.url),'utf8'))
  .replace("from './model.mjs'",`from ${JSON.stringify(modelURL)}`);
const {VIEWS,viewFromHash,matchesQuery,projectItems,boardGroups,workspaceTotals,activeTasks,attentionItems}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

const task=(id,state,direction='incoming',extra={})=>({id,state,direction,kind:'task',title:'Fictional design brief',task_id:'research-'+id,peer_id:'atlas',...extra});
function fixture(){
  return {peers:[{peer_id:'atlas',agent_id:'Atlas',owner_id:'Alex',state:'active'},{peer_id:'other',agent_id:'Inactive assistant',owner_id:'Blair',state:'revoked'}],items:[
    task('pending','pending'),task('accepted','accepted'),task('rejected','rejected'),task('draft','draft','outgoing'),
    task('shared','released','outgoing'),task('artifact','accepted','incoming',{kind:'artifact',title:'Exact community outline'}),
    task('expired','expired'),task('uncertain','uncertain','outgoing'),task('unknown','future_state')
  ]};
}
const ids=items=>items.map(item=>item.id).sort();

test('hash navigation accepts only known literal routes',()=>{
  for(const view of VIEWS)assert.equal(viewFromHash('#'+view),view);
  for(const hash of ['','#unknown','#%74asks','#tasks?accept=true','#<script>',null,{},'#TASKS'])assert.equal(viewFromHash(hash),'overview');
});

test('task and artifact views keep their exact kind across both directions',()=>{
  const state=fixture();
  assert.deepEqual(ids(projectItems(state,'artifacts')),['artifact']);
  assert.deepEqual(ids(projectItems(state,'tasks')),['accepted','draft','expired','pending','rejected','shared','uncertain','unknown']);
  assert.deepEqual(ids(projectItems(state,'outbox')),['draft','shared','uncertain']);
  assert.ok(projectItems(state,'inbox').every(item=>item.direction==='incoming'));
});

test('accepted metric filter cannot include rejected or expired decisions',()=>{
  const state=fixture();
  assert.deepEqual(ids(projectItems(state,'tasks','accepted')),['accepted']);
  assert.deepEqual(ids(projectItems(state,'tasks','decided')),['accepted','expired','rejected']);
  assert.deepEqual(ids(projectItems(state,'tasks','pending')),['draft','pending']);
  assert.deepEqual(ids(projectItems(state,'inbox','pending')),['pending']);
});

test('unknown display scopes fail closed rather than showing an unintended collection',()=>{
  assert.deepEqual(projectItems(fixture(),'permissions'),[]);
  assert.deepEqual(projectItems(fixture(),'overview','automatically-approved'),[]);
});

test('board preserves each item exactly once and never treats uncertainty as acceptance',()=>{
  const state=fixture(),groups=boardGroups(state.items);
  assert.deepEqual(ids(groups.flatMap(group=>group.items)),ids(state.items));
  assert.equal(new Set(groups.flatMap(group=>group.items.map(item=>item.id))).size,state.items.length);
  assert.deepEqual(ids(groups.find(group=>group.id==='unknown').items),['uncertain','unknown']);
  assert.deepEqual(ids(groups.find(group=>group.id==='accepted').items),['accepted','artifact']);
  assert.deepEqual(ids(groups.find(group=>group.id==='closed').items),['expired','rejected']);
  assert.deepEqual(ids(groups.find(group=>group.id==='shared').items),['shared']);
});

test('search requires every literal term and can match a pinned peer and task reference',()=>{
  assert.deepEqual(ids(projectItems(fixture(),'tasks','all','aLeX research-accepted')),['accepted']);
  assert.deepEqual(ids(projectItems(fixture(),'artifacts','all','outline atlas')),['artifact']);
  assert.deepEqual(projectItems(fixture(),'tasks','all','nonexistent'),[]);
  assert.equal(matchesQuery(['<img onerror=not-code>'], '<img'),true);
  assert.equal(matchesQuery(['Fictional task'], '.*'),false);
  assert.equal(matchesQuery([null,undefined,14,{},'literal'],'literal'),true);
  assert.equal(matchesQuery(['First','Second'],'  second   FIRST  '),true);
});

test('overview counts only actual incoming pending, accepted tasks, artifacts and active peers',()=>{
  assert.deepEqual(workspaceTotals(fixture()),{pending:1,acceptedTasks:1,artifacts:1,peers:1});
  assert.deepEqual(workspaceTotals({items:[],peers:[]}),{pending:0,acceptedTasks:0,artifacts:0,peers:0});
});

test('overview never presents closed or unknown work as active and surfaces uncertainty for inspection',()=>{
  const state=fixture();
  assert.deepEqual(ids(activeTasks(state)),['accepted','draft','pending','shared']);
  assert.deepEqual(ids(attentionItems(state)),['pending','uncertain','unknown']);
  for(const status of ['cancelled','canceled','withdrawn','revoked'])state.items.push(task(status,status));
  assert.deepEqual(ids(activeTasks(state)),['accepted','draft','pending','shared']);
  assert.deepEqual(ids(attentionItems(state)),['pending','uncertain','unknown']);
});

test('projections do not reorder or alter the authoritative state',()=>{
  const state=fixture(),snapshot=structuredClone(state);
  for(const item of state.items)Object.freeze(item);
  for(const peer of state.peers)Object.freeze(peer);
  Object.freeze(state.items);Object.freeze(state.peers);Object.freeze(state);
  projectItems(state,'tasks','accepted');boardGroups(state.items);workspaceTotals(state);
  assert.deepEqual(state,snapshot);
  assert.deepEqual(projectItems(state,'overview').map(item=>item.id),snapshot.items.map(item=>item.id).reverse());
});
