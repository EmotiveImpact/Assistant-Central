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
    // A room note or vote sent to several members is talk, not a part of a mission.
    if(item.direction!=='outgoing'||item.kind!=='task'||!item.context||item.room)continue;
    if(!groups.has(item.context))groups.set(item.context,[]);
    groups.get(item.context).push(item);
  }
  const teams=[];
  for(const [context,members] of groups){
    if(new Set(members.map(item=>item.peer_id)).size<2)continue;
    members.sort((a,b)=>Number(a.created_at)-Number(b.created_at));
    const shared=sharedName(members.map(item=>item.title));
    const parts=members.map(item=>{
      const step=partStep(item,items),access=accessFor(item,items),asking=access.find(entry=>entry.waiting&&step.step!=='Stopped');
      return {item,peer_id:item.peer_id,title:shared?String(item.title).trim().slice(shared.length+2).trim()||'Untitled part':String(item.title||'Untitled part'),
        ...step,needsYou:step.needsYou||Boolean(asking),asking,access,rules:item.team?.rules??null};
    });
    teams.push({context,title:shared||'Team mission',parts,people:[...new Set(members.map(item=>item.peer_id))],
      created_at:Math.max(...members.map(item=>Number(item.created_at)||0))});
  }
  return teams.sort((a,b)=>b.created_at-a.created_at);
}

// The team mission an item belongs to: one of its parts, or a result returned for a part.
export function partOf(state,item){
  if(!item)return null;
  for(const team of teamsOf(state)){
    const part=team.parts.find(entry=>entry.item.id===item.id||(item.kind==='artifact'&&item.direction==='incoming'&&item.parent_id===entry.item.id)
      ||entry.access.some(ask=>ask.item.id===item.id));
    if(part)return {team,part,result:part.item.id!==item.id&&item.kind==='artifact',access:part.access.some(ask=>ask.item.id===item.id)};
  }
  return null;
}

// One short line for a Home card, so a result reads as part of the bigger piece of work.
export function partLead(found){
  if(!found)return '';
  if(found.access)return `Access for ${found.part.title}, part of ${found.team.title}`;
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
  const asks=team.parts.filter(part=>part.asking).length;
  if(asks)bits.push(asks===1?'One assistant asks for access.':`${asks} assistants ask for access.`);
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

// Team records ------------------------------------------------------------------------------
// Three structured texts ride inside ordinary signed proposals (pilot/team.py checks them on
// both sides): a part with its rules and compute limit, a result that reports on every rule
// and the compute used, and a request for access for one part. The saved state carries a
// summary of each as item.team, so nothing here reads a proposal's text to draw the page.
export const PART='parlu/team-part/1\n',RESULT='parlu/team-result/1\n',ACCESS='parlu/team-access/1\n';
export const CURRENCIES=Object.freeze(['GBP','USD','EUR']);
const MAX_RULES=8,MAX_COMPUTE=1_000_000_000;
// Every rule comes back in the result with its side and outcome, so the rules together must leave
// room for that and a summary. pilot/team.py holds the same budget on the encoded rules.
export const RULES_BUDGET=2048;
const ruleBytes=rules=>rules.reduce((sum,rule)=>sum+bytes(JSON.stringify(rule)),0);

// A title made from words someone typed: cut on whole characters to fit both the form's 120
// characters and the saved 128 bytes, and say so with an ellipsis.
export function fitTitle(prefix,words){
  const full=`${prefix}${String(words??'').trim()}`;
  if(full.length<=120&&bytes(full)<=TITLE_BYTES)return full;
  const chars=[...full];
  while(chars.length&&(chars.join('').length+1>120||bytes(chars.join('')+'…')>TITLE_BYTES))chars.pop();
  return chars.join('').trimEnd()+'…';
}

// Rules are typed one per line. Blank lines go; a repeated rule is an error, not a quiet merge.
export function readRules(text){
  const rules=String(text??'').split('\n').map(line=>line.trim()).filter(Boolean);
  if(rules.length>MAX_RULES)throw new Error(`Up to ${MAX_RULES} rules on each side.`);
  for(const rule of rules)if(bytes(rule)>200)throw new Error(`Keep each rule short. “${rule.slice(0,40)}…” is too long.`);
  return rules;
}

export function partText({brief,must=[],mustNot=[],compute=null}){
  const clean=String(brief??'').trim();
  if(!clean||bytes(clean)>4096)throw new Error('Each part needs a brief.');
  const seen=new Set([...must,...mustNot]);if(seen.size!==must.length+mustNot.length)throw new Error('Each rule appears once.');
  if(ruleBytes([...must,...mustNot])>RULES_BUDGET)throw new Error('The rules are too long together. Shorten or combine some.');
  if(compute!==null&&!(Number.isInteger(compute.cap_micro)&&compute.cap_micro>0&&compute.cap_micro<=MAX_COMPUTE&&CURRENCIES.includes(compute.currency)))throw new Error('Enter a compute limit such as 0.50.');
  const text=PART+JSON.stringify({brief:clean,compute,rules:{must,must_not:mustNot}});
  if(text.length>4096||bytes(text)>8192)throw new Error('This part is too long. Shorten the brief or the rules.');
  return text;
}

// One check per rule of the part, in the part's order, and compute only in its currency.
export function ruleList(rules){
  return [...(rules?.must??[]).map(rule=>({rule,side:'must'})),...(rules?.must_not??[]).map(rule=>({rule,side:'must_not'}))];
}
export function resultText(summary,team,{kept=[],computeMicro=null}={}){
  const clean=String(summary??'').trim();if(!clean||bytes(clean)>4096)throw new Error('Say what was done, in a short summary.');
  const list=ruleList(team?.rules);if(kept.length!==list.length)throw new Error('Say for every rule whether it was kept.');
  let used=null;
  if(computeMicro!==null){
    if(!team?.compute)throw new Error('This part has no compute limit, so no compute is reported.');
    if(!Number.isInteger(computeMicro)||computeMicro<0||computeMicro>MAX_COMPUTE)throw new Error('Enter the compute used, such as 0.12.');
    used={micro:computeMicro,currency:team.compute.currency};
  }
  const text=RESULT+JSON.stringify({checks:list.map((entry,i)=>({...entry,kept:kept[i]===true})),compute_used:used,summary:clean});
  if(text.length>4096||bytes(text)>8192)throw new Error('This result is too long. Shorten the summary.');
  return text;
}
export function accessText({partTaskId,what,why,hours}){
  const w=String(what??'').trim(),y=String(why??'').trim(),h=Number(hours);
  if(!w||bytes(w)>200)throw new Error('Say what this part needs to read, briefly.');
  if(!y||bytes(y)>1000)throw new Error('Say why this part needs it.');
  if(!Number.isInteger(h)||h<1||h>168)throw new Error('Ask for between 1 hour and 7 days.');
  return ACCESS+JSON.stringify({hours:h,part_task_id:String(partTaskId),what:w,why:y});
}

// The words to show in a review instead of the raw record. Null for an ordinary proposal.
export function readTeamText(content){
  const text=String(content??'');
  for(const [prefix,record] of [[PART,'part'],[RESULT,'result'],[ACCESS,'access']]){
    if(!text.startsWith(prefix))continue;
    try{const value=JSON.parse(text.slice(prefix.length));if(value&&typeof value==='object'&&!Array.isArray(value))return {record,value};}catch{}
    return null;
  }
  return null;
}

// What has been asked and granted for one part: incoming access requests that name it.
export function accessFor(item,items=[]){
  return items.filter(entry=>entry.direction==='incoming'&&entry.kind==='task'&&entry.team?.record==='access'
    &&entry.peer_id===item.peer_id&&entry.context===item.context&&entry.team.part_task_id===item.task_id)
    .sort((a,b)=>Number(b.created_at)-Number(a.created_at)).map(entry=>({item:entry,what:entry.team.what,hours:entry.team.hours,
      until:Number(entry.created_at)+entry.team.hours*3600,
      granted:(entry.historical_state??entry.state)==='accepted',waiting:entry.state==='pending'}));
}

// A merge needs two signatures: the helper's release of the result, then your acceptance.
export function approvalsFor(part){
  const result=part.result;
  if(!result)return [];
  const decided=result.historical_state??result.state;
  return [{who:'helper',signed:true},{who:'you',signed:decided==='accepted',refused:decided==='rejected',waiting:result.state==='pending'}];
}

// Compute reported for a part's results, against its limit. Reported by the helper, not checked.
export function computeFor(item,items=[]){
  const limit=item.team?.compute??null,done=resultsFor(item,items).find(entry=>entry.team?.compute_used);
  return {limit,used:done?.team?.compute_used??null,over:Boolean(limit&&done?.team?.compute_used&&done.team.compute_used.micro>limit.cap_micro)};
}

// The mission's compute in each currency: limits agreed, and what helpers report.
export function teamCompute(team,items=[]){
  const totals=new Map();
  for(const part of team.parts){
    const {limit,used}=computeFor(part.item,items);if(!limit)continue;
    const row=totals.get(limit.currency)??{currency:limit.currency,limit:0,used:0};row.limit+=limit.cap_micro;if(used)row.used+=used.micro;totals.set(limit.currency,row);
  }
  return [...totals.values()];
}

// Each check a result reports, beside its rule.
export function checksFor(result){
  return (result?.team?.checks??[]).map(entry=>({rule:entry.rule,side:entry.side,kept:entry.kept===true}));
}
