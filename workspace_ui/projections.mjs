// Read-only projections. Display groups and search never create authority.
import {plain, isPending, isTerminal, isPeerActive, stateLabel, statusClass} from './model.mjs';

export const VIEWS = Object.freeze(['overview','inbox','tasks','artifacts','outbox','peers','transfers','activity']);
export function viewFromHash(hash) {
  const value = plain(hash).replace(/^#/, '');
  return VIEWS.includes(value) ? value : 'overview';
}
export function matchesQuery(values, query='') {
  const terms = plain(query).trim().toLowerCase().split(/\s+/).filter(Boolean);
  const haystack = values.map(value=>plain(value)).join(' ').toLowerCase();
  return terms.every(term=>haystack.includes(term));
}
export function projectItems(state, view='overview', filter='all', query='') {
  if(!['overview','inbox','tasks','artifacts','outbox'].includes(view)||!['all','pending','accepted','decided'].includes(filter))return [];
  return state.items.filter(item=> {
    if(view==='inbox' && item.direction!=='incoming')return false;
    if(view==='outbox' && item.direction!=='outgoing')return false;
    if(view==='tasks' && item.kind!=='task')return false;
    if(view==='artifacts' && item.kind!=='artifact')return false;
    if(filter==='pending' && !isPending(item))return false;
    if(filter==='accepted' && item.state!=='accepted')return false;
    if(filter==='decided' && !isTerminal(item))return false;
    const peer=state.peers.find(peer=>peer.peer_id===item.peer_id);
    return matchesQuery([item.title,item.id,item.task_id,item.kind,item.direction,item.state,stateLabel(item.state),peer?.agent_id,peer?.owner_id],query);
  }).slice().reverse();
}
export function boardGroups(items) {
  const groups=[{id:'review',label:'To review',items:[]},{id:'accepted',label:'Accepted',items:[]},{id:'shared',label:'Shared',items:[]},{id:'closed',label:'Closed',items:[]},{id:'unknown',label:'Needs inspection',items:[]}];
  for(const item of items){
    const index=isPending(item)?0:item.state==='accepted'?1:['released','queued','delivered'].includes(item.state)?2:isTerminal(item)?3:4;
    groups[index].items.push(item);
  }
  return groups.filter(group=>group.id!=='unknown'||group.items.length);
}
export function activeTasks(state) {
  return projectItems(state,'tasks').filter(item=>isPending(item)||['accepted','released','queued','delivered'].includes(item.state));
}
export function attentionItems(state) {
  return projectItems(state,'overview').filter(item=>(item.direction==='incoming'&&isPending(item))||item.state==='uncertain'||statusClass(item.state)==='unknown');
}
export function workspaceTotals(state) {
  return {
    pending:state.items.filter(item=>item.direction==='incoming'&&isPending(item)).length,
    acceptedTasks:state.items.filter(item=>item.kind==='task'&&item.state==='accepted').length,
    artifacts:state.items.filter(item=>item.kind==='artifact').length,
    peers:state.peers.filter(isPeerActive).length,
  };
}
