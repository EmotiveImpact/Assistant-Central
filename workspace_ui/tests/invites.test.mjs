import test from 'node:test';
import assert from 'node:assert/strict';
import {inviteFromText,joinFromHash,relayEnabled,validateRelay,linkLabel,expiresIn,joinProblem,syncLine,syncChanged,joinerCards} from '../invites.mjs';

const secret='eyJ2Ijoy'+'A'.repeat(60)+'_-';
const link=`https://parlu-relay.vercel.app/invite#${secret}`;
const hex=c=>c.repeat(64);

test('an invite link is read from what people paste',()=>{
  assert.equal(inviteFromText(link),link);
  assert.equal(inviteFromText(`  ${link}\n`),link);
  assert.equal(inviteFromText(`http://127.0.0.1:8877/#join=${encodeURIComponent(link)}`),link);
  assert.equal(inviteFromText(`http://127.0.0.1:9001/invite#${secret}`),`http://127.0.0.1:9001/invite#${secret}`);
  for(const bad of ['',null,'hello',`http://relay.example/invite#${secret}`,`https://parlu-relay.vercel.app/other#${secret}`,
    `https://parlu-relay.vercel.app/invite?x=1#${secret}`,'https://parlu-relay.vercel.app/invite#short',`https://u:p@parlu-relay.vercel.app/invite#${secret}`,
    `ftp://parlu-relay.vercel.app/invite#${secret}`,`https://parlu-relay.vercel.app/invite#${secret}<script>`,'x'.repeat(5000),'#join=%E0%A4%A'])
    assert.equal(inviteFromText(bad),'',String(bad).slice(0,40));
});

test('a join carried in the address is taken only from #join=',()=>{
  assert.equal(joinFromHash('#join='+encodeURIComponent(link)),link);
  assert.equal(joinFromHash('#peers'),'');
  assert.equal(joinFromHash(''),'');
});

test('relay state is checked before anything is drawn from it',()=>{
  const relay={enabled:true,relay_host:'parlu-relay.vercel.app',invites:[{id:'a'.repeat(32),state:'open'}],joiners:[{fingerprint:hex('b'),review_digest:hex('c')}],links:[{peer_id:hex('d'),state:'connected'}]};
  assert.equal(validateRelay(relay),relay);
  assert.equal(validateRelay(undefined),undefined);
  assert.equal(relayEnabled({relay}),true);
  assert.equal(relayEnabled({}),false);
  for(const broken of [null,{...relay,enabled:false},{...relay,invites:[{id:'x',state:'open'}]},{...relay,links:[{peer_id:hex('d'),state:'odd'}]},{...relay,joiners:[{fingerprint:'x',review_digest:hex('c')}]}])
    assert.throws(()=>validateRelay(broken));
  assert.equal(linkLabel({relay},hex('d')),'Connected through the relay');
  assert.equal(linkLabel({relay},hex('e')),'');
});

test('expiry reads in plain words',()=>{
  assert.equal(expiresIn(1000,1000),'Expired');
  assert.equal(expiresIn(1000+60,1000),'In 1 minute');
  assert.equal(expiresIn(1000+600,1000),'In 10 minutes');
  assert.equal(expiresIn(1000+3600,1000),'In 1 hour');
  assert.equal(expiresIn(1000+24*3600,1000),'In 24 hours');
  assert.equal(expiresIn(1000+7*86400,1000),'In 7 days');
  assert.equal(expiresIn('nope',1000),'Expired');
});

test('every refusal has one sentence the owner can act on',()=>{
  for(const reason of ['own_invite','other_relay','revoked_before','cannot_add','invite_closed','already_linked','relay_refused','relay_closed','relay_unreachable'])
    assert.notEqual(joinProblem(reason,'Maya'),'This invite could not be used.',reason);
  assert.match(joinProblem('revoked_before','Maya'),/Maya/);
  assert.equal(joinProblem('anything else'),'This invite could not be used.');
});

test('a sync is described without claiming more than the relay said',()=>{
  assert.equal(syncLine(null),'');
  assert.equal(syncLine({relay:'ok'}),'Up to date.');
  assert.match(syncLine({relay:'unreachable',sent:0}),/could not be reached/);
  assert.equal(syncLine({relay:'ok',joined:1,received:2,sent:1,waiting_to_send:1}),
    'Someone used your invite. 2 new items arrived. One item went to the relay. One item is ready to send.');
  assert.equal(syncChanged({relay:'ok',sent:0,received:0}),false);
  assert.equal(syncChanged({relay:'ok',receipts_sent:1}),true);
});

test('people who used an invite become Home cards',()=>{
  const state={relay:{enabled:true,relay_host:'r',invites:[],links:[],joiners:[{invite_id:'a'.repeat(32),label:'Maya',owner_id:'maya',agent_id:'Otto',fingerprint:hex('b'),review_digest:hex('c')}]}};
  const [card]=joinerCards(state);
  assert.deepEqual([card.kind,card.key,card.title,card.owner,card.agent],['joiner','joiner:'+'a'.repeat(32),'Your invite for Maya','maya','Otto']);
  assert.deepEqual(joinerCards({}),[]);
});
