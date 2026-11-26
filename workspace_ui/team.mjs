// Team missions: one piece of work split across several people's assistants, with your own
// assistant as the lead. Pure, so the views and the tests agree. A team mission is not a new
// kind of record: it is your outgoing task proposals that share one exact context and go to
// two or more different assistants. Every part keeps its own exact review and receipt, and
// progress comes only from saved states.

export const STEPS=Object.freeze(['Plan','Asked','Building','Result','Done']);
const STOPPED=new Set(['rejected','expired','cancelled','revoked','withdrawn']);
const decided=item=>item?.historical_state??item?.state;

// Where one part stands, from its own state and any result returned for it.
export function partStep(item,items=[]){
  const result=items.filter(entry=>entry.kind==='artifact'&&entry.direction==='incoming'&&entry.parent_id===item.id)
    .sort((a,b)=>Number(b.created_at)-Number(a.created_at))[0];
  const state=decided(item);
  if(STOPPED.has(state))return {step:'Stopped',result,needsYou:false};
  if(result){
    const r=decided(result);
    if(r==='accepted')return {step:'Done',result,needsYou:false};
    if(!STOPPED.has(r))return {step:'Result',result,needsYou:true};
  }
  if(state==='accepted')return {step:'Building',result:undefined,needsYou:false};
  if(state==='draft')return {step:'Plan',result:undefined,needsYou:true};
  return {step:'Asked',result:undefined,needsYou:false};
}

// "Supper club app: Card deposits" splits into the mission and the part.
export function splitTitle(title){
  const text=String(title??'').trim(),at=text.indexOf(': ');
  return at>0?[text.slice(0,at).trim(),text.slice(at+2).trim()||text]:['',text||'Untitled part'];
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
    const names=members.map(item=>splitTitle(item.title)[0]),shared=names[0]&&names.every(name=>name===names[0])?names[0]:'';
    const parts=members.map(item=>({item,peer_id:item.peer_id,title:shared?splitTitle(item.title)[1]:String(item.title||'Untitled part'),...partStep(item,items)}));
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
    if(`${title}: ${part.title}`.length>120)throw new Error('Keep each part name short.');
  }
  if(new Set(parts.map(part=>part.peer_id)).size<2)throw new Error('Ask at least two different assistants.');
  return parts.map(part=>({...part,title:`${title}: ${part.title}`}));
}
