// Decide: the exact review opens with three plain rows, Spends, Shares and Keeps, worked out
// from the proposal and its verified review only. Nothing here invents a figure: spending
// appears only when a signed mission limit exists, and every amount is simulated.
import {exactMoney} from './missions.mjs';

const quote=value=>`“${String(value||'Untitled').trim()}”`;

// The question at the top of the review, in the owner's words.
export function decisionQuestion(item,{agent='their assistant',owner='them'}={}){
  const record=item.team?.record;
  if(item.direction==='incoming'&&record==='result')return `Merge ${quote(String(item.title??'').replace(/^Result: /,''))} from ${agent}?`;
  if(item.direction==='incoming'&&record==='access')return `Let ${agent} ${String(item.team.what??'have this access').replace(/^./,c=>c.toLowerCase())}?`;
  if(item.direction==='outgoing')return `Send ${quote(item.title)} to ${owner}?`;
  if(item.kind==='artifact')return `Accept ${quote(item.title)} from ${agent}?`;
  return `Agree to ${quote(item.title)} for ${owner}?`;
}

// Three rows. The last one is always what stays yours.
const plural=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
function ruleCount(rules){const n=(rules?.must?.length??0)+(rules?.must_not?.length??0);return n?plural(n,'rule'):'no rules';}

// Team records have their own three rows: a part's limit and rules, a result's checks, an access grant.
function teamRows(item,{agent,owner,actions}){
  const team=item.team,record=team.record;
  if(record==='part'){
    const limit=team.compute?exactMoney(team.compute.cap_micro,team.compute.currency):null;
    if(item.direction==='outgoing')return [
      ['Spends',limit?`Up to ${limit} of compute for this part if ${agent} agrees.`:'Nothing. This part has no compute limit.'],
      ['Shares',`This part's brief and its ${ruleCount(team.rules)} with ${agent}, ${owner}'s assistant. Nobody else.`],
      ['Keeps',`The rest of the mission. ${agent} agrees to its own part only, and you can withdraw before it does.`]];
    return [
      ['Spends',limit?`Up to ${limit} of compute for this part.`:'Nothing. This part has no compute limit.'],
      ['Shares',actions.includes('accept')?`Your agreement to this part and its ${ruleCount(team.rules)}, as a signed receipt ${agent} can check.`:`Nothing new. ${agent} already has this part.`],
      ['Keeps','Everything else. Agreeing does not start work, run a model or give access to anything.']];
  }
  if(record==='result'){
    const checks=team.checks??[],broken=checks.filter(entry=>!entry.kept).length,used=team.compute_used;
    return [
      ['Spends',used?`${agent} reports ${exactMoney(used.micro,used.currency)} of compute. Reported, not checked by Parlu.`:'Nothing reported.'],
      ['Checks',!checks.length?'This part had no rules.':broken?`${plural(broken,'rule')} not kept, by ${agent}'s own report.`:`Every rule kept (${checks.length}), by ${agent}'s own report.`],
      ['Shares',`Your merge approval, as a signed receipt ${agent} can check. ${agent} signed the result when it sent it.`],
      ['Keeps','Everything else. Merging does not pass the result on to anyone.']];
  }
  if(record==='access'){
    const hours=Number(team.hours);
    return [
      ['Shares',`Your consent for ${agent} to ${String(team.what??'').replace(/^./,c=>c.toLowerCase())}, for one part only.`],
      ['For',`${hours<24?plural(hours,'hour'):plural(Math.round(hours/24),'day')} from when it asked. Parlu records the consent; it does not open anything itself.`],
      ['Keeps','Everything else. Not now leaves the ask waiting, and it ends when it expires.']];
  }
  return null;
}

export function decisionRows(item,{agent='their assistant',owner='them',actions=[]}={}){
  if(item.team?.record){const rows=teamRows(item,{agent,owner,actions});if(rows)return rows;}
  const cap=item.mission_cap&&Number.isFinite(Number(item.mission_cap.cap_micro))?exactMoney(item.mission_cap.cap_micro,item.mission_cap.currency):null;
  if(item.direction==='outgoing'){
    return [
      ['Spends',cap?`Up to ${cap} from this mission's limit if ${agent} agrees. Simulated, no real payment.`:'Nothing. This proposal has no spending limit.'],
      ['Shares',`This exact ${item.kind==='artifact'?'result':'request'} with ${agent}, ${owner}'s assistant. Nobody else.`],
      ['Keeps',`Everything else. ${agent} still makes its own decision, and you can withdraw before it does.`],
    ];
  }
  const accepting=actions.includes('accept');
  return [
    ['Spends',cap?`Up to ${cap} from this mission's limit. Simulated, no real payment.`:'Nothing. This proposal has no spending limit.'],
    ['Shares',accepting?`Your decision, as a signed receipt ${agent} can check.`:`Nothing new. ${agent} already has this proposal.`],
    ['Keeps',item.kind==='artifact'?'Everything else. Accepting does not pass it on to anyone.':'Everything else. Agreeing does not start work, run a model or allow onward sharing.'],
  ];
}

// Money and consent need a deliberate hold; an ordinary yes is a button.
export function needsHold(item,action){
  if(action!=='accept')return false;
  // Consent to access is always a hold; so is agreeing to spend compute on a part.
  if(item.team?.record==='access')return true;
  if(item.team?.record==='part')return Boolean(item.team.compute);
  return Boolean(item.mission_cap);
}
