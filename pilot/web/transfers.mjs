// Exact UI projections only. The server rechecks authentication and retained bytes.
const HEX=/^[a-f0-9]{64}$/, ID=/^[A-Za-z0-9_.-]{1,128}$/, CONNECTION=/^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/;
const integer=value=>Number.isInteger(value)&&value>=0;
const safe=value=>typeof value==='string';
function connection(value){
  if(!value||!CONNECTION.test(value.id)||!safe(value.label)||!value.label||value.label.length>80||!HEX.test(value.peer_fingerprint)||!safe(value.destination)||value.destination.length>512)throw new Error('Invalid configured connection');
  const url=new URL(value.destination);
  if(url.protocol!=='https:'||url.pathname!=='/v1/quarantine'||url.username||url.password||url.search||url.hash)throw new Error('Invalid configured destination');
}
function outbox(row){
  if(!row||!ID.test(row.message_id)||!HEX.test(row.packet_digest)||!HEX.test(row.peer)||!['queued','uncertain','received','cancelled'].includes(row.state)||!integer(row.attempts)||row.attempts>5||!Number.isFinite(row.expires)||row.transport_receipt_only!==true||row.owner_acceptance!=='not_established'||row.work_execution!=='not_established')throw new Error('Invalid retained outbox');
}
export function validateTransfers(value){
  if(!value||typeof value.enabled!=='boolean'||value.authorises_execution!==false||value.automatic_delivery!==false)throw new Error('Invalid transfer state');
  for(const [key,max] of [['connections',16],['outbox',1024],['receipts',1024],['quarantine',1024]])if(!Array.isArray(value[key])||value[key].length>max)throw new Error('Invalid transfer lists');
  const ids=new Set();for(const c of value.connections){connection(c);if(ids.has(c.id))throw new Error('Duplicate connection');ids.add(c.id);}
  if(!value.enabled&&value.connections.length)throw new Error('Disabled connection mismatch');
  value.outbox.forEach(outbox);
  for(const r of value.receipts)if(!ID.test(r.incoming_id)||!ID.test(r.message_id)||!HEX.test(r.peer)||!Number.isFinite(r.expires))throw new Error('Invalid cached receipt');
  if(value.quarantine.some(d=>!HEX.test(d)))throw new Error('Invalid quarantine selection');
  const d=value.dispatch;if(d!==null&&(!d||!ID.test(d.message_id)||!ids.has(d.connection_id)||!['in_flight','finished','outcome_unknown'].includes(d.state)||d.delivery!=='uncertain'||d.authorises_execution!==false||typeof d.transport_acknowledged!=='boolean'))throw new Error('Invalid dispatch observation');
  return value;
}
export function validateTransferReview(value,selected){
  const c=selected.connection;
  if(!value||value.kind!==selected.kind||value.identifier!==selected.identifier||!ID.test(value.message_id)||!HEX.test(value.packet_digest)||!HEX.test(value.review_digest)||!Number.isFinite(value.expires)||!['proposal','receipt','decision','cancel'].includes(value.packet_kind)||value.authorises_execution!==false||value.owner_acceptance!=='not_established'||value.authenticated!==(selected.kind!=='quarantine'))throw new Error('Invalid exact transfer review');
  connection(value.connection);
  if(['id','label','peer_fingerprint','destination'].some(k=>value.connection[k]!==c[k]))throw new Error('Transfer connection changed');
  if(!Array.isArray(value.attempts)||value.attempts.length>5||!Array.isArray(value.allowed_actions)||value.allowed_actions.length>1||value.allowed_actions.some(a=>!(selected.kind==='quarantine'?['import']:['send','retry']).includes(a)))throw new Error('Invalid transfer actions');
  let sequence=0;
  for(const a of value.attempts){if(!integer(a.sequence)||a.sequence<=sequence||a.message_id!==value.message_id||a.packet_digest!==value.packet_digest||!HEX.test(a.file_digest)||a.recipient!==c.peer_fingerprint||a.state!=='uncertain'||!safe(a.destination)||a.kind!==value.packet_kind)throw new Error('Invalid immutable attempt');sequence=a.sequence;}
  if(selected.kind==='outbox'){outbox(value.outbox);if(value.outbox.message_id!==selected.identifier||value.message_id!==selected.identifier||value.outbox.peer!==c.peer_fingerprint||value.outbox.packet_digest!==value.packet_digest)throw new Error('Outbox binding changed');}
  else if(value.outbox!==null)throw new Error('Unexpected outbox authority');
  if(value.outbox&&value.allowed_actions.length&&(!['queued','uncertain'].includes(value.outbox.state)||value.outbox.attempts>=5))throw new Error('Stopped outbox cannot send');
  const prior=Math.max(value.outbox?.attempts||0,value.attempts.length);
  if(value.allowed_actions.includes('send')&&prior||value.allowed_actions.includes('retry')&&!prior)throw new Error('Explicit retry mismatch');
  return value;
}
export function transferPath(selection){return `/api/transfers/${encodeURIComponent(selection.connection.id)}/${selection.kind}/${encodeURIComponent(selection.identifier)}`;}
