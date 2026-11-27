// Rooms, boards, timelines, votes and groups. Pure, so the views and the tests agree.
//
// A room is not a new kind of record. It is every proposal that shares one exact context and
// carries a room note or vote (pilot/room.py), or a team mission (two or more assistants asked
// in one context). What each assistant found, thought, planned or changed its mind about rides
// inside an ordinary signed proposal, written by that person's own assistant. Every yes or no
// in a vote is the recipient's own signed decision. Nothing here reads a proposal's content;
// the saved state carries a checked summary of each record as item.room.
import {teamsOf,partStep} from './team.mjs';

export const COLUMNS=Object.freeze([['researching','Researching'],['doing','Doing'],['yes','Needs a yes'],['done','Done']]);
export const NOTE_WORDS=Object.freeze({finding:'Finding',idea:'Idea',plan:'Plan',change:'Changed their mind'});
export const RULE_WORDS=Object.freeze({most:'Most of us',all:'All of us'});
// Room glyph tints, inside the brand: teal for people, coral for asks, ink, and their quieter steps.
export const TINTS=Object.freeze(['#14897a','#ee7b5b','#1b1a17','#0e6b60','#c4522f','#6b6a65']);
const STOPPED=new Set(['rejected','expired','cancelled','revoked','withdrawn']);
const signed=item=>item?.historical_state??item?.state;
const when=item=>Number(item?.created_at)||0;

export function tintOf(context){
  let hash=0;for(const ch of String(context??''))hash=(hash*31+ch.charCodeAt(0))>>>0;
  return TINTS[hash%TINTS.length];
}

// The order things happened in, from the saved history: each item's arrival and each decision.
// History carries no clock, so its sequence is the truth about order; created_at gives the time.
export function sequenceOf(state){
  const made=new Map(),decided=new Map();
  for(const event of state?.history??[]){
    if(!event?.item_id)continue;
    if((event.event==='proposal_created'||event.event==='proposal_received')&&!made.has(event.item_id))made.set(event.item_id,event.sequence);
    if(event.event==='recipient_decided'||event.event==='peer_decision_observed')decided.set(event.item_id,event.sequence);
  }
  return {made,decided};
}

// Which contexts are rooms, and what each room is called.
export function roomContexts(state){
  const items=state?.items??[],names=new Map(),teams=teamsOf(state);
  for(const item of items)if(item.room?.room&&item.context)names.set(item.context,{name:item.room.room,at:when(item)});
  for(const team of teams)if(!names.has(team.context))names.set(team.context,{name:team.title,at:team.created_at});
  return names;
}

// One answer in a vote you asked: the recipient's own signed decision on their copy.
export function answerOf(ballot){
  const decided=signed(ballot);
  if(decided==='accepted')return 'yes';
  if(decided==='rejected')return 'no';
  if(ballot.state==='draft')return 'unsent';
  if(STOPPED.has(ballot.state))return 'none';
  return 'waiting';
}

// The room's rule decides what passes. "Most" needs more than half of everyone asked, the asker
// included; "all" needs every yes. A vote closes as soon as the outcome can no longer change.
export function tally(rule,stance,answers){
  const all=[stance==='yes'?'yes':stance==='no'?'no':'abstain',...answers];
  const yes=all.filter(a=>a==='yes').length,no=all.filter(a=>a==='no').length,open=all.filter(a=>a==='waiting'||a==='unsent').length,total=all.length;
  let outcome='open';
  if(rule==='all'){if(yes===total)outcome='passed';else if(all.some(a=>a!=='yes'&&a!=='waiting'&&a!=='unsent'))outcome='failed';}
  else if(yes*2>total)outcome='passed';else if((yes+open)*2<=total)outcome='failed';
  return {yes,no,open,total,outcome};
}

const actorOf=item=>item.direction==='outgoing'?'you':item.peer_id;

// Everything in one room, as entries for the Threads tab, cards for the Board and events for the Timeline.
export function buildRoom(state,context,name){
  const items=(state?.items??[]).filter(item=>item.context===context);
  const {made,decided}=sequenceOf(state);
  const seq=item=>made.get(item.id)??when(item);
  const members=new Set(items.map(item=>item.peer_id).filter(Boolean));
  const team=teamsOf(state).find(entry=>entry.context===context)??null;
  const entries=[];

  // Notes. The same note sent to several members is one entry with several recipients.
  const notes=new Map();
  for(const item of items){
    if(item.room?.record!=='note'||!item.room.summary)continue;
    const key=item.direction==='outgoing'?`you\n${item.room.thread}\n${item.room.note}\n${item.room.summary}`:item.id;
    if(!notes.has(key))notes.set(key,{type:'note',who:actorOf(item),items:[],note:item.room,thread:item.room.thread,at:when(item),seq:seq(item),task_ids:new Set()});
    const entry=notes.get(key);entry.items.push(item);entry.task_ids.add(item.task_id);entry.seq=Math.min(entry.seq,seq(item));
  }
  // A later note that names an earlier one replaces it on the board.
  const noteEntries=[...notes.values()];
  for(const entry of noteEntries){
    if(!entry.note.replaces)continue;
    const earlier=noteEntries.find(other=>other!==entry&&other.task_ids.has(entry.note.replaces));
    if(earlier){earlier.replacedBy=entry;entry.replaces=earlier;}
  }
  entries.push(...noteEntries);

  // Votes. Your copies share one vote_id; each copy someone else sent you is its own entry.
  const votes=new Map();
  for(const item of items){
    if(item.room?.record!=='vote'||!item.room.question)continue;
    if(item.direction==='outgoing'){
      const key='you\n'+item.room.vote_id;
      if(!votes.has(key))votes.set(key,{type:'vote',who:'you',vote:item.room,thread:item.room.thread,items:[],at:when(item),seq:seq(item)});
      const entry=votes.get(key);entry.items.push(item);entry.seq=Math.min(entry.seq,seq(item));
    }else{
      votes.set(item.id,{type:'vote',who:item.peer_id,vote:item.room,thread:item.room.thread,items:[item],at:when(item),seq:seq(item),incoming:true});
    }
  }
  for(const entry of votes.values()){
    if(entry.incoming){
      const item=entry.items[0],answer=answerOf(item);
      entry.mine=answer==='waiting'?'waiting':answer;
      entry.answers=[{who:'you',answer:entry.mine,seq:decided.get(item.id)}];
      entry.result={outcome:'unknown'};
    }else{
      entry.answers=entry.items.map(item=>({who:item.peer_id,answer:answerOf(item),seq:decided.get(item.id),item}));
      entry.result=tally(entry.vote.rule,entry.vote.stance,entry.answers.map(a=>a.answer));
    }
    entries.push(entry);
  }

  // Tasks in the room that are not notes or votes: team mission parts and ordinary asks.
  for(const item of items){
    if(item.room||item.kind!=='task'||item.team?.record==='access')continue;
    const results=items.filter(entry=>entry.kind==='artifact'&&entry.parent_id===item.id).sort((a,b)=>when(b)-when(a));
    entries.push({type:'task',who:actorOf(item),items:[item],item,results,resultSeq:new Map(results.map(result=>[result.id,seq(result)])),thread:team&&team.parts.some(part=>part.item.id===item.id)?'Parts':'Asks',at:when(item),seq:seq(item),
      title:item.title,step:item.direction==='outgoing'?partStep(item,state.items).step:null});
  }
  entries.sort((a,b)=>a.seq-b.seq);

  const threads=[...new Set(entries.map(entry=>entry.thread).filter(Boolean))];
  const board=Object.fromEntries(COLUMNS.map(([id])=>[id,[]]));
  for(const entry of entries){const column=columnOf(entry);if(column)board[column].push(entry);}
  const timeline=timelineOf(entries,decided);
  const needsYou=board.yes.length;
  const done=board.done.length,total=COLUMNS.reduce((sum,[id])=>sum+board[id].length,0);
  for(const entry of entries)entry.roomName=name;
  return {context,name,tint:tintOf(context),members:[...members],threads,entries,board,timeline,needsYou,done,total,team,
    last:Math.max(0,...items.map(when)),changes:entries.filter(entry=>entry.type==='note'&&entry.note.note==='change').length,
    votes:entries.filter(entry=>entry.type==='vote')};
}

// Where one entry sits on the board, or null when it no longer belongs there.
export function columnOf(entry){
  if(entry.type==='note'){
    if(entry.replacedBy)return null;
    if(entry.who==='you'&&entry.items.every(item=>item.state==='draft'))return 'yes';
    return {researching:'researching',doing:'doing',done:'done'}[entry.note.stage]??'researching';
  }
  if(entry.type==='vote'){
    if(entry.incoming)return entry.mine==='waiting'&&entry.items[0].state==='pending'?'yes':entry.mine==='yes'||entry.mine==='no'?'done':null;
    if(entry.items.some(item=>item.state==='draft'))return 'yes';
    return entry.result.outcome==='open'?'doing':'done';
  }
  if(entry.type==='task'){
    const item=entry.item;
    if(item.direction==='outgoing')return {Plan:'yes',Asked:'researching',Building:'doing',Result:'yes',Done:'done'}[entry.step]??null;
    if(entry.results.some(result=>signed(result)==='accepted'))return 'done';
    if(item.state==='pending')return 'yes';
    if(signed(item)==='accepted')return 'doing';
    return null;
  }
  return null;
}

// Every finding, change of mind, ask, vote, answer and yes, in the order it happened.
export function timelineOf(entries,decided=new Map()){
  const events=[];
  const push=(seq,at,who,kind,entry,extra={})=>events.push({seq:Number(seq)||0,at,who,kind,entry,...extra});
  for(const entry of entries){
    if(entry.type==='note'){
      push(entry.seq,entry.at,entry.who,entry.note.note==='change'?'change':'note',entry);
    }else if(entry.type==='vote'){
      push(entry.seq,entry.at,entry.who,'vote',entry);
      let last=entry.seq;
      for(const answer of entry.answers){
        if(answer.answer!=='yes'&&answer.answer!=='no')continue;
        const at=answer.seq??entry.seq+0.5;last=Math.max(last,at);
        push(at,null,answer.who,'answer',entry,{answer:answer.answer});
      }
      if(!entry.incoming&&entry.result.outcome!=='open')push(last+0.01,null,'room','outcome',entry,{outcome:entry.result.outcome});
    }else if(entry.type==='task'){
      const item=entry.item;
      if(item.state!=='draft')push(entry.seq,entry.at,entry.who,'ask',entry);
      const choice=signed(item),answeredBy=item.direction==='outgoing'?item.peer_id:'you';
      if(choice==='accepted'||choice==='rejected')push(decided.get(item.id)??entry.seq+0.5,null,answeredBy,choice==='accepted'?'agree':'decline',entry);
      for(const result of entry.results){
        push(entry.resultSeq?.get(result.id)??entry.seq+0.6,when(result),result.direction==='incoming'?result.peer_id:'you','result',entry,{result});
        const merged=signed(result);
        if(merged==='accepted')push(decided.get(result.id)??entry.seq+0.7,null,result.direction==='incoming'?'you':result.peer_id,'merge',entry,{result});
      }
    }
  }
  return events.sort((a,b)=>a.seq-b.seq);
}

export function roomsOf(state){
  const rooms=[];
  for(const [context,{name}] of roomContexts(state))rooms.push(buildRoom(state,context,name));
  return rooms.sort((a,b)=>(b.needsYou>0)-(a.needsYou>0)||b.last-a.last);
}

// One honest line about a room, in Home's voice.
export function roomLine(room){
  const bits=[];
  const passed=room.votes.filter(vote=>vote.result.outcome==='passed').length,open=room.votes.filter(vote=>vote.result.outcome==='open').length;
  if(room.needsYou)bits.push(room.needsYou===1?'One thing needs your yes.':`${room.needsYou} things need your yes.`);
  bits.push(`${room.done} of ${room.total} done.`);
  if(open)bits.push(open===1?'One vote is open.':`${open} votes are open.`);
  if(passed)bits.push(passed===1?'One vote passed.':`${passed} votes passed.`);
  if(room.changes)bits.push(room.changes===1?'One change of mind.':`${room.changes} changes of mind.`);
  return bits.join(' ');
}

export const TIMELINE_FILTERS=Object.freeze([['all','Everything'],['note','Findings'],['change','Changes of mind'],['vote','Votes'],['yes','Yeses']]);
export function filterTimeline(events,filter){
  if(filter==='note')return events.filter(event=>event.kind==='note');
  if(filter==='change')return events.filter(event=>event.kind==='change');
  if(filter==='vote')return events.filter(event=>['vote','answer','outcome'].includes(event.kind));
  if(filter==='yes')return events.filter(event=>event.kind==='agree'||event.kind==='merge'||(event.kind==='answer'&&event.answer==='yes')||(event.kind==='outcome'&&event.outcome==='passed'));
  return events;
}

// Groups: people and their assistants who work together. Two assistants are in one group when
// they share a room, directly or through someone else. You are in every group.
export function groupsOf(state,rooms=roomsOf(state)){
  const parent=new Map(),find=id=>{while(parent.get(id)!==id){parent.set(id,parent.get(parent.get(id)));id=parent.get(id);}return id;};
  for(const room of rooms)for(const id of room.members)if(!parent.has(id))parent.set(id,id);
  for(const room of rooms)for(const id of room.members.slice(1))parent.set(find(id),find(room.members[0]));
  const groups=new Map();
  for(const room of rooms){
    if(!room.members.length)continue;
    const key=find(room.members[0]);
    if(!groups.has(key))groups.set(key,{peers:new Set(),rooms:[]});
    const group=groups.get(key);room.members.forEach(id=>group.peers.add(id));group.rooms.push(room);
  }
  return [...groups.values()].map(group=>{
    const votes=group.rooms.flatMap(room=>room.votes),ties=new Map();
    for(const room of group.rooms)for(const a of room.members)for(const b of room.members)if(a<b){const k=a+'\n'+b;ties.set(k,(ties.get(k)??0)+room.entries.length);}
    return {peers:[...group.peers],rooms:group.rooms,
      decided:group.rooms.reduce((sum,room)=>sum+room.timeline.filter(event=>event.kind==='agree'||event.kind==='merge'||event.kind==='outcome').length,0),
      passed:votes.filter(vote=>vote.result.outcome==='passed').length,
      open:votes.filter(vote=>vote.result.outcome==='open').length,
      changes:group.rooms.reduce((sum,room)=>sum+room.changes,0),
      rules:[...new Set(votes.map(vote=>vote.vote.rule))],
      needsYou:group.rooms.reduce((sum,room)=>sum+room.needsYou,0),
      last:Math.max(0,...group.rooms.map(room=>room.last)),
      ties:[...ties].map(([key,weight])=>{const [a,b]=key.split('\n');return {a,b,weight};})};
  }).sort((a,b)=>b.last-a.last);
}

// A sentence for one timeline event. `name(who)` gives the assistant's name, or "You".
export function eventLine(event,name,titleOf=entry=>entry.title){
  const who=name(event.who),entry={...event.entry,title:titleOf(event.entry)};
  const quote=value=>`“${String(value??'').trim()}”`;
  switch(event.kind){
    case 'note':return {finding:`${who} found`,idea:`${who} suggested`,plan:`${who} planned`}[entry.note.note]??`${who} noted`;
    case 'change':return `${who} changed their mind`;
    case 'vote':return entry.incoming?`${who} asked the room to vote`:`${who} asked the room to vote`;
    case 'answer':return `${who} voted ${event.answer}`;
    case 'outcome':return event.outcome==='passed'?`The vote passed, ${entry.result.yes} of ${entry.result.total} yes`:`The vote did not pass, ${entry.result.yes} of ${entry.result.total} yes`;
    case 'ask':return `${who} asked for ${quote(entry.title)}`;
    case 'agree':return `${who} agreed to ${quote(entry.title)}`;
    case 'decline':return `${who} turned down ${quote(entry.title)}`;
    case 'result':return `${who} returned a result for ${quote(entry.title)}`;
    case 'merge':return `${who} accepted the result for ${quote(entry.title)}`;
    default:return who;
  }
}

// Where a sticky sits on the canvas when nobody has moved it: one column per assistant, in the
// order they first spoke, newest note lowest. Moving a sticky is a view preference only.
export function canvasLayout(room,{width=220,gap=28,rowGap=18,height=128}={}){
  const lanes=[],positions=new Map(),counts=new Map();
  for(const entry of room.entries){
    if(entry.type==='task'&&!columnOf(entry))continue;
    if(!lanes.includes(entry.who))lanes.push(entry.who);
    const lane=lanes.indexOf(entry.who),row=counts.get(entry.who)??0;counts.set(entry.who,row+1);
    positions.set(entry,{x:40+lane*(width+gap),y:72+row*(height+rowGap)});
  }
  return {lanes,positions,width,laneWidth:width+gap};
}

// Room records, written the same way pilot/room.py checks them. The owner's assistant posts a
// note or a vote as one signed copy to each member; each copy is reviewed and sent on its own.
export const NOTE='parlu/room-note/1\n',VOTE='parlu/room-vote/1\n';
const bytes=value=>new TextEncoder().encode(value).length;
const field=(value,limit,message)=>{const text=String(value??'').trim();if(!text||bytes(text)>limit)throw new Error(message);return text;};
// Keys in sorted order with compact separators, matching json.dumps(sort_keys=True) in Python.
const encode=(prefix,value)=>prefix+JSON.stringify(Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]])));
export function noteText({room,thread,summary,note='finding',stage='researching',replaces=null,why=null}){
  if(!['finding','idea','plan','change'].includes(note)||!['researching','doing','done'].includes(stage))throw new Error('Choose what kind of note this is.');
  if(note==='change'&&(!replaces||!why))throw new Error('A change of mind says what it replaces and why.');
  return encode(NOTE,{room:field(room,120,'Give the room a short name.'),thread:field(thread,80,'Name the thread, for example Food.'),note,stage,
    summary:field(summary,2000,'Say what your assistant found, in a few lines.'),replaces,why:why===null?null:field(why,1000,'Say briefly why.')});
}
export function voteText({room,thread,question,voteId,rule='most',stance='yes',why=null}){
  if(!['most','all'].includes(rule))throw new Error('Choose who must agree.');
  if(!['yes','no','abstain'].includes(stance))throw new Error('Choose your own vote.');
  if(!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/.test(String(voteId??'')))throw new Error('This vote needs an id.');
  return encode(VOTE,{room:field(room,120,'Give the room a short name.'),thread:field(thread,80,'Name the thread, for example Food.'),
    question:field(question,400,'Ask a yes or no question.'),rule,stance,vote_id:voteId,why:why===null?null:field(why,1000,'Say briefly why.')});
}
// The title each copy carries, so lists elsewhere still read well: "Food: Lunch at 1pm".
export function recordTitle(thread,words,prefix=''){
  const full=`${prefix}${String(thread??'').trim()}: ${String(words??'').replace(/\s+/g,' ').trim()}`;
  const chars=[...full];if(full.length<=110&&bytes(full)<=120)return full;
  while(chars.length&&(chars.join('').length>108||bytes(chars.join('')+'…')>120))chars.pop();
  return chars.join('').trimEnd()+'…';
}
