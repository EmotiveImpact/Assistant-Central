// Decide: the exact review opens with three plain rows, Spends, Shares and Keeps, worked out
// from the proposal and its verified review only. Nothing here invents a figure: spending
// appears only when a signed mission limit exists, and every amount is simulated.
import {exactMoney} from './missions.mjs';

const quote=value=>`“${String(value||'Untitled').trim()}”`;

// The question at the top of the review, in the owner's words.
export function decisionQuestion(item,{agent='their assistant',owner='them'}={}){
  if(item.direction==='outgoing')return `Send ${quote(item.title)} to ${owner}?`;
  if(item.kind==='artifact')return `Accept ${quote(item.title)} from ${agent}?`;
  return `Agree to ${quote(item.title)} for ${owner}?`;
}

// Three rows. The last one is always what stays yours.
export function decisionRows(item,{agent='their assistant',owner='them',actions=[]}={}){
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
  return action==='accept'&&Boolean(item.mission_cap);
}
