// Invite links, in the owner's words. Pure, so the page and the tests agree. Nothing here
// talks to the relay: it reads the saved relay state and turns it into lines and cards.

const HEX64=/^[0-9a-f]{64}$/;

// The part of an address that matters: an invite link from a relay, or a Parlu address that
// carries one after "#join=" (what the relay's invite page hands over). Returns the clean
// invite link, or '' when the text is not one.
export function inviteFromText(value){
  let textValue=String(value??'').trim();
  if(!textValue||textValue.length>4096)return '';
  const carried=textValue.indexOf('#join=');
  if(carried>=0){try{textValue=decodeURIComponent(textValue.slice(carried+6));}catch{return '';}}
  let url;try{url=new URL(textValue);}catch{return '';}
  if(!['https:','http:'].includes(url.protocol)||url.pathname!=='/invite'||url.search||!url.hash||url.username||url.password)return '';
  if(url.protocol==='http:'&&!['127.0.0.1','localhost'].includes(url.hostname))return '';
  if(!/^#[A-Za-z0-9_-]{40,2000}$/.test(url.hash))return '';
  return `${url.origin}/invite${url.hash}`;
}

// The relay page sends people to their own Parlu with the link after "#join=". Reading it
// once and clearing it keeps the secret part out of the address bar and the history.
export function joinFromHash(hash){
  const value=String(hash??'');
  return value.startsWith('#join=')?inviteFromText(value):'';
}

export function relayEnabled(state){
  const relay=state?.relay;
  return Boolean(relay&&relay.enabled===true&&Array.isArray(relay.invites)&&Array.isArray(relay.joiners)&&Array.isArray(relay.links));
}

export function validateRelay(relay){
  if(relay===undefined)return relay;
  if(!relay||relay.enabled!==true||typeof relay.relay_host!=='string'||!Array.isArray(relay.invites)||!Array.isArray(relay.joiners)||!Array.isArray(relay.links))throw new Error('Invalid relay state');
  if(relay.invites.length>64||relay.joiners.length>64||relay.links.length>128)throw new Error('Relay bounds exceeded');
  for(const invite of relay.invites)if(!/^[0-9a-f]{32}$/.test(String(invite?.id))||!['open','joined'].includes(invite.state))throw new Error('Invalid invite');
  for(const joiner of relay.joiners)if(!HEX64.test(String(joiner?.fingerprint))||!HEX64.test(String(joiner?.review_digest)))throw new Error('Invalid joiner');
  for(const link of relay.links)if(!HEX64.test(String(link?.peer_id))||!['joining','waiting','connected','closed'].includes(link.state))throw new Error('Invalid relay link');
  return relay;
}

// How a link to one person stands, from their side or yours.
export function linkLabel(state,peerId){
  const link=state?.relay?.links?.find(entry=>entry.peer_id===peerId);
  if(!link)return '';
  return {joining:'Joining',waiting:'Waiting for them to add you',connected:'Connected through the relay',closed:'Relay link closed'}[link.state]??'';
}

// When an invite stops working, in plain words.
export function expiresIn(joinBy,now=Date.now()/1000){
  const seconds=Math.round(Number(joinBy)-now);
  if(!Number.isFinite(seconds)||seconds<=0)return 'Expired';
  if(seconds<3600){const m=Math.max(1,Math.round(seconds/60));return `In ${m} minute${m===1?'':'s'}`;}
  if(seconds<48*3600){const h=Math.round(seconds/3600);return `In ${h} hour${h===1?'':'s'}`;}
  const d=Math.round(seconds/86400);return `In ${d} days`;
}

// Why joining could not go ahead, as one sentence the owner can act on.
export function joinProblem(reason,inviter='them'){
  return {
    own_invite:'This is your own invite. Send it to the person you want to connect with.',
    other_relay:'This invite uses a different relay from yours, so Parlu cannot join it yet.',
    revoked_before:`You removed ${inviter} before. Parlu does not add them back from a link.`,
    cannot_add:`Parlu could not add ${inviter}. Their assistant may already be listed under another key.`,
    invite_closed:'This invite has been used, revoked or has expired. Ask for a fresh one.',
    relay_refused:'The relay refused the request. Nothing was sent.',
    relay_closed:'The relay refused the request. Nothing was sent.',
    relay_unreachable:'The relay could not be reached. Nothing was sent. Try again in a moment.',
  }[reason]??'This invite could not be used.';
}

// One honest line after a sync. A relay answer is only ever "stored" or "not stored".
export function syncLine(summary){
  if(!summary)return '';
  if(summary.relay==='unreachable')return 'The relay could not be reached. Nothing was lost. Parlu tries again when you sync.';
  if(summary.relay==='refused')return 'The relay refused the request. Nothing was sent.';
  const bits=[];
  if(summary.joined)bits.push(summary.joined===1?'Someone used your invite.':`${summary.joined} people used your invites.`);
  if(summary.connected)bits.push(summary.connected===1?'One person added you.':`${summary.connected} people added you.`);
  if(summary.received)bits.push(summary.received===1?'One new item arrived.':`${summary.received} new items arrived.`);
  if(summary.sent)bits.push(summary.sent===1?'One item went to the relay.':`${summary.sent} items went to the relay.`);
  if(summary.waiting_to_send)bits.push(summary.waiting_to_send===1?'One item is ready to send.':`${summary.waiting_to_send} items are ready to send.`);
  if(summary.rejected)bits.push(summary.rejected===1?'One packet could not be read and was set aside.':`${summary.rejected} packets could not be read and were set aside.`);
  return bits.length?bits.join(' '):'Up to date.';
}

// Did a sync bring in anything that changes what the page shows?
export function syncChanged(summary){
  return Boolean(summary&&(summary.joined||summary.connected||summary.received||summary.sent||summary.receipts_sent||summary.rejected));
}

// A person who used one of your invites, as a card for Home's one queue.
export function joinerCards(state){
  if(!relayEnabled(state))return [];
  return state.relay.joiners.map(joiner=>({kind:'joiner',key:'joiner:'+joiner.invite_id,joiner,
    title:String(joiner.label||'').trim()?`Your invite for ${String(joiner.label).trim()}`:'Your invite',owner:joiner.owner_id,agent:joiner.agent_id}));
}
