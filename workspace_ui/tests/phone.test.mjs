import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePhone,startLink,phoneNote,ANSWER_LIMIT} from '../phone.mjs';

const ready={available:true,paired:false,mode:'notice',bot:'parlu_fictional_bot',reachable:true};

test('phone status is checked before anything is drawn',()=>{
  assert.equal(validatePhone(ready),ready);
  assert.equal(validatePhone({available:false,paired:false,reason:'not_set_up'}).reason,'not_set_up');
  for(const bad of [null,{},{...ready,mode:'loud'},{...ready,bot:'x y'},{...ready,reachable:'yes'},{available:false,paired:false,reason:'odd'},{...ready,paired:'no'}])
    assert.throws(()=>validatePhone(bad));
});

test('only the exact Telegram start link for this bot and code is used',()=>{
  const code='0123456789abcdef',bot='parlu_fictional_bot';
  const made={code,bot,start_link:`https://t.me/${bot}?start=${code}`};
  assert.equal(startLink(made),made.start_link);
  assert.equal(startLink({...made,start_link:'https://evil.example/?start='+code}),'');
  assert.equal(startLink({...made,bot:null,start_link:null}),'');
  assert.equal(startLink({...made,code:'not-hex'}),'');
});

test('the panel says plainly what the phone will see',()=>{
  assert.match(phoneNote(ready),/never what it says/);
  assert.match(phoneNote({...ready,mode:'full'}),/not end-to-end encrypted/);
  assert.match(phoneNote({...ready,reachable:false}),/cannot reach Telegram/);
  assert.match(phoneNote({available:false,paired:false,reason:'no_bot_token'}),/token is missing/);
  assert.match(phoneNote({available:false,paired:false,reason:'not_set_up'}),/not set up/);
  assert.match(ANSWER_LIMIT,/never approves/);
});
