// Team missions: one piece of work split across several people's assistants, with your own
// assistant as the lead. Pure, so the views and the tests agree. A team mission is not a new
// kind of record: it is your outgoing task proposals that share one exact context and go to
// two or more different assistants. Every part keeps its own exact review and receipt, and
// progress comes only from saved states.

export const STEPS=Object.freeze(['Plan','Asked','Building','Result','Done']);
const STOPPED=new Set(['rejected','expired','cancelled','revoked','withdrawn']);
// Saved state has two readings. `state` is what is true now: a withdrawn draft is "cancelled" and
// an unanswered request past its time is "expired". `historical_state` keeps the decision that was
// signed. Only a signed acceptance is read from history; what can still be done is read from now.
const accepted=item=>(item?.historical_state??item?.state)==='accepted';

// Every result returned for a part, newest first.
export function resultsFor(item,items=[]){
  return items.filter(entry=>entry.kind==='artifact'&&entry.direction==='incoming'&&entry.parent_id===item.id)
    .sort((a,b)=>Number(b.created_at)-Number(a.created_at));
}

// Where one part stands, from its own state and any result returned for it.
export function partStep(item,items=[]){
  const results=resultsFor(item,items),done=results.find(accepted);
  if(done)return {step:'Done',result:done,needsYou:false};
  const waiting=results.find(entry=>entry.state==='pending');
  if(waiting&&!STOPPED.has(item.state))return {step:'Result',result:waiting,needsYou:true};
  if(STOPPED.has(item.state))return {step:'Stopped',result:undefined,needsYou:false};
  if(item.state==='accepted')return {step:'Building',result:undefined,needsYou:false};
  if(item.state==='draft')return {step:'Plan',result:undefined,needsYou:true};
  return {step:'Asked',result:undefined,needsYou:false};
}

// The mission name every part title starts with: the longest shared lead that ends at ": ".
// A colon inside the name ("Launch: November") stays part of the name.
export function sharedName(titles){
  const list=titles.map(title=>String(title??'').trim());
  if(!list.length||list.some(title=>!title))return '';
  let lead=list[0];
  for(const title of list){let i=0;while(i<lead.length&&i<title.length&&lead[i]===title[i])i++;lead=lead.slice(0,i);}
  const at=lead.lastIndexOf(': ');
  return at>0?lead.slice(0,at).trim():'';
}

export function teamsOf(state){
  const items=state?.items??[],groups=new Map();
  for(const item of items){
    if(item.direction!=='outgoing'||item.kind!=='task'||!item.context)continue;
    if(!groups.has(item.context))groups.set(item.context,[]);
    groups.get(item.context).push(item);
  }
  const teams=[];
  for(const [context,members] of groups){
    if(new Set(members.map(item=>item.peer_id)).size<2)continue;
    members.sort((a,b)=>Number(a.created_at)-Number(b.created_at));
    const shared=sharedName(members.map(item=>item.title));
    const parts=members.map(item=>({item,peer_id:item.peer_id,title:shared?String(item.title).trim().slice(shared.length+2).trim()||'Untitled part':String(item.title||'Untitled part'),...partStep(item,items)}));
    teams.push({context,title:shared||'Team mission',parts,people:[...new Set(members.map(item=>item.peer_id))],
      created_at:Math.max(...members.map(item=>Number(item.created_at)||0))});
  }
  return teams.sort((a,b)=>b.created_at-a.created_at);
}

// The team mission an item belongs to: one of its parts, or a result returned for a part.
export function partOf(state,item){
  if(!item)return null;
  for(const team of teamsOf(state)){
    const part=team.parts.find(entry=>entry.item.id===item.id||(item.kind==='artifact'&&item.direction==='incoming'&&item.parent_id===entry.item.id));
    if(part)return {team,part,result:part.item.id!==item.id};
  }
  return null;
}

// One short line for a Home card, so a result reads as part of the bigger piece of work.
export function partLead(found){
  if(!found)return '';
  return found.result?`Result for ${found.part.title}, part of ${found.team.title}`:`${found.part.title}, part of ${found.team.title}`;
}

export function teamCounts(team){
  const counts=Object.fromEntries([...STEPS,'Stopped'].map(step=>[step,0]));
  for(const part of team.parts)counts[part.step]+=1;
  return counts;
}

// One honest line, in Home's voice.
export function teamLine(team){
  const c=teamCounts(team),n=team.parts.length,bits=[];
  bits.push(c.Done===n?`All ${n} parts are done.`:`${c.Done} of ${n} parts ${c.Done===1?'is':'are'} done.`);
  if(c.Result)bits.push(c.Result===1?'One result needs your check.':`${c.Result} results need your check.`);
  if(c.Plan)bits.push(c.Plan===1?'One part is ready for you to send.':`${c.Plan} parts are ready for you to send.`);
  if(c.Asked)bits.push(c.Asked===1?'One assistant is still deciding.':`${c.Asked} assistants are still deciding.`);
  if(c.Stopped)bits.push(c.Stopped===1?'One part stopped.':`${c.Stopped} parts stopped.`);
  return bits.join(' ');
}

// How far along each part is, as a share of the five steps, for the progress bar.
export function stepShare(step){
  const index=STEPS.indexOf(step);
  return index<0?0:(index+1)/STEPS.length;
}

const TITLE_BYTES=128,TEXT_BYTES=8192,bytes=value=>new TextEncoder().encode(value).length;

// The parts a new team mission will create: every row needs a title, an assistant and a brief.
export function planParts(mission,rows){
  const title=String(mission??'').trim();
  if(!title||title.length>60)throw new Error('Give the mission a short name, up to 60 characters.');
  const parts=rows.map(row=>({title:String(row.title??'').trim(),peer_id:String(row.peer_id??''),text:String(row.text??'').trim()}))
    .filter(row=>row.title||row.text);
  if(parts.length<2)throw new Error('A team mission needs at least two parts.');
  if(parts.length>6)throw new Error('Up to six parts for now.');
  for(const part of parts){
    if(!part.title||!part.peer_id||!part.text)throw new Error('Each part needs a name, an assistant and a brief.');
    // The saved limits count bytes, not characters, so check them before the first part is created.
    if(`${title}: ${part.title}`.length>120||bytes(`${title}: ${part.title}`)>TITLE_BYTES)throw new Error(`Keep each part name short. “${part.title}” is too long with the mission name.`);
    if(part.text.length>4096||bytes(part.text)>TEXT_BYTES)throw new Error(`The brief for “${part.title}” is too long.`);
  }
  if(new Set(parts.map(part=>part.peer_id)).size<2)throw new Error('Ask at least two different assistants.');
  return parts.map(part=>({...part,title:`${title}: ${part.title}`}));
}
