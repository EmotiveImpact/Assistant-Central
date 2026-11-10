import test from 'node:test';
import assert from 'node:assert/strict';
import {validateTransfers,validateTransferReview,transferPath} from '../transfers.mjs';
import {peerBody} from '../model.mjs';
const a='a'.repeat(64),b='b'.repeat(64),c={id:'peer',label:'Fictional peer',peer_fingerprint:a,destination:'https://mailbox.invalid/v1/quarantine'};
const row={message_id:'proposal-'+b,packet_digest:b,peer:a,state:'queued',attempts:0,expires:2000000000,transport_receipt_only:true,owner_acceptance:'not_established',work_execution:'not_established'};
const selection={connection:c,kind:'outbox',identifier:row.message_id};
const review=()=>({connection:c,kind:'outbox',identifier:row.message_id,message_id:row.message_id,packet_kind:'proposal',packet_digest:b,review_digest:a,expires:row.expires,outbox:{...row},attempts:[],allowed_actions:['send'],authorises_execution:false,owner_acceptance:'not_established',authenticated:true});
const state=()=>({enabled:true,connections:[c],outbox:[{...row}],receipts:[],quarantine:[],dispatch:null,authorises_execution:false,automatic_delivery:false});
test('transfer snapshot keeps authority false and recognises only bounded retained state',()=>{
 assert.equal(validateTransfers(state()).outbox[0].state,'queued');
 for(const mutate of [s=>s.automatic_delivery=true,s=>s.authorises_execution=true,s=>s.outbox[0].state='accepted',s=>s.outbox[0].attempts=6,s=>s.connections.push(c),s=>s.connections[0]={...c,destination:'https://user:password@mailbox.invalid/v1/quarantine'},s=>s.quarantine=['../secret']]){const s=state();mutate(s);assert.throws(()=>validateTransfers(s));}
});
test('transfer review binds exact connection, destination, original message and digest',()=>{
 assert.equal(validateTransferReview(review(),selection).message_id,row.message_id);
 for(const mutate of [r=>r.connection={...c,id:'other'},r=>r.connection={...c,destination:'https://other.invalid/v1/quarantine'},r=>r.message_id='other',r=>r.outbox.packet_digest=a,r=>r.authorises_execution=true,r=>r.authenticated=false,r=>r.allowed_actions=['accept'],r=>r.outbox.state='received']){const r=review();mutate(r);assert.throws(()=>validateTransferReview(r,selection));}
});
test('prior attempts require an explicit retry and remain immutable uncertain evidence',()=>{
 const r=review();r.outbox.attempts=1;r.outbox.state='uncertain';r.attempts=[{sequence:1,message_id:r.message_id,packet_digest:b,file_digest:a,recipient:a,destination:c.destination,kind:'proposal',state:'uncertain'}];
 assert.throws(()=>validateTransferReview(r,selection));r.allowed_actions=['retry'];validateTransferReview(r,selection);
 r.attempts[0].state='received';assert.throws(()=>validateTransferReview(r,selection));
});
test('quarantine review is explicitly unauthenticated and import-only',()=>{
 const s={connection:c,kind:'quarantine',identifier:a};const r={...review(),kind:s.kind,identifier:a,outbox:null,authenticated:false,allowed_actions:['import']};
 validateTransferReview(r,s);r.authenticated=true;assert.throws(()=>validateTransferReview(r,s));
});
test('configured HTTPS enrolment still requires independently checked exact fingerprint',()=>{
 const fields={verified:'on',expected_fingerprint:a,public_identity:'{"owner_id":"test"}',connection_id:'peer'};
 assert.deepEqual(peerBody(fields,[c]),{public_identity:{owner_id:'test'},expected_fingerprint:a,connection_id:'peer'});
 assert.throws(()=>peerBody({...fields,expected_fingerprint:b},[c]));assert.throws(()=>peerBody({...fields,verified:''},[c]));
 assert.equal(transferPath(selection),'/api/transfers/peer/outbox/'+row.message_id);
});
