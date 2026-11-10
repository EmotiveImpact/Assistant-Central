// Actual separate browser sessions -> loopback owner services -> encrypted ledger.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url),{chromium}=require('playwright');
const url=new URL(process.env.CONVERSATION_URL||'');assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');
const password=process.env.CONVERSATION_PASSWORD;if(!password)throw new Error('Disposable fixture password required');
const screenshots=process.env.WORKSPACE_SCREENSHOT_DIR;if(screenshots)await mkdir(screenshots,{recursive:true});
const browser=await chromium.launch({headless:true});const pages={},errors=[],writes=[],tokens={};
const noOverflow=async p=>assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
const screenshot=async(p,name)=>{if(screenshots){await p.evaluate(()=>document.fonts.ready.then(()=>undefined));await p.screenshot({path:path.join(screenshots,name),fullPage:true});}};
async function nav(p){if(await p.locator('#menu-toggle').isVisible())await p.locator('#menu-toggle').click();await p.locator('[data-view=conversations]').click();await p.getByRole('button',{name:'New conversation',exact:true}).waitFor();}
async function open(p){await p.getByRole('button',{name:/^(Conversation|Group) · thread_1$/}).click();await p.getByLabel('Message to the members shown above').waitFor();}
async function refresh(p){await p.bringToFront();await p.locator('#refresh').click();await p.getByRole('button',{name:'New conversation',exact:true}).waitFor();await open(p);}
async function selectOld(p){const article=p.locator('.conversation-history article').filter({hasText:'Only Alice and Bob saw this earlier plan.'});await article.getByRole('checkbox').check();}
async function review(p){await selectOld(p);const recipient=p.getByLabel('Exact recipient',{exact:true});await recipient.waitFor();assert.equal(await p.getByRole('combobox',{name:'Exact recipient',exact:true}).count(),1);await recipient.selectOption({label:'carol · carol_assistant'});await p.getByLabel('Purpose',{exact:true}).fill('Give Carol this exact earlier plan');await p.getByRole('button',{name:'Review exact history share',exact:true}).click();await p.locator('#conversation-dialog').waitFor({state:'visible'});}
async function approve(p){await p.locator('#history-confirm').check();await p.getByRole('button',{name:'Approve exact history share',exact:true}).click();}
try{
  for(const name of ['alice','bob','carol']){
    const context=await browser.newContext({viewport:{width:1440,height:1000}});const p=await context.newPage();pages[name]=p;
    p.on('response',async r=>{if(new URL(r.url()).pathname==='/api/session'&&r.request().method()==='POST'&&r.ok())tokens[name]=(await r.json()).token;});p.on('pageerror',e=>errors.push(name+': '+e.message));p.on('request',r=>{if(r.method()==='POST'&&!/\/(history|read|context|grant-review|message-outcome)$/.test(new URL(r.url()).pathname))writes.push({name,path:new URL(r.url()).pathname,body:r.postDataJSON()});});
    await p.goto(url.href);await p.locator('#account').fill(name);await p.locator('#password').fill(password);await p.getByRole('button',{name:/Unlock workspace/}).click();await p.locator('#workspace').waitFor({state:'visible'});assert.equal(await p.locator('#owner-name').textContent(),name);await nav(p);
  }
  const {alice,bob,carol}=pages;
  const api=async(name,path,body)=>{const r=await pages[name].request.fetch(new URL(path,url).href,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+tokens[name]},...(body===undefined?{}:{data:body})});assert.equal(r.status(),200);return r.json();};
  const bound=async name=>{const r=await api(name,'/api/conversations/thread_1');return {member_epoch:r.binding.member_epoch,policy_generation:r.binding.policy_generation};};
  const catalogue=await api('alice','/api/conversations');const principal=name=>catalogue.actors.find(a=>a.owner_id===name).principal;
  assert.equal(await carol.locator('.conversation-rooms button').count(),0);
  assert.equal(await carol.locator('#item-list').textContent().then(t=>t.includes('earlier plan')),false);
  await carol.getByRole('button',{name:'Join future messages only',exact:true}).click();await open(carol);
  assert.equal(await carol.locator('.conversation-message').count(),0);
  await refresh(alice);
  assert.equal(await alice.locator('.conversation-history article').count(),3);
  assert.equal(await alice.locator('.conversation-history img,.conversation-history script').count(),0);
  assert.equal(await alice.evaluate(()=>window.conversationXss),undefined);
  await review(alice);assert.match(await alice.locator('#conversation-dialog').textContent(),/Only Alice and Bob/);
  assert.equal(await alice.locator('#conversation-dialog').textContent().then(t=>t.includes('Bobs earlier words')),false);
  await noOverflow(alice);await screenshot(alice,'central-conversations-exact-review.png');
  await alice.locator('#conversation-dialog').getByRole('button',{name:'Close',exact:true}).click();assert.equal(await alice.locator('#conversation-dialog').textContent(),'');
  await review(alice);await approve(alice);await alice.locator('#conversation-dialog').waitFor({state:'hidden'});
  await refresh(carol);assert.equal(await carol.locator('.conversation-history article').count(),1);assert.match(await carol.locator('.conversation-history').textContent(),/Only Alice and Bob/);
  await carol.getByLabel('Search only visible history').fill('Bobs');await carol.getByRole('button',{name:'Search history',exact:true}).click();await carol.getByText('No visible messages match.',{exact:true}).waitFor();
  await refresh(alice);await alice.getByRole('button',{name:'My issued history grants',exact:true}).click();await alice.getByRole('button',{name:'Revoke this grant',exact:true}).click();await alice.locator('#conversation-dialog').waitFor({state:'hidden'});
  await refresh(carol);assert.equal(await carol.locator('.conversation-message').count(),0);
  // Membership changes between preparation and approval invalidate exact review.
  await refresh(bob);await refresh(alice);await review(alice);
  await api('bob','/api/conversations/thread_1/remove',{binding:await bound('bob'),recipient:principal('bob')});
  await approve(alice);await alice.locator('#conversation-dialog').waitFor({state:'hidden'});assert.equal(await alice.locator('#conversation-dialog').textContent(),'');
  await refresh(carol);assert.equal(await carol.locator('.conversation-message').count(),0);
  // A composer cannot silently widen or survive removal/rejoin.
  await carol.getByLabel('Message to the members shown above').fill('Stale membership draft must not send.');
  await api('alice','/api/conversations/thread_1/remove',{binding:await bound('alice'),recipient:principal('carol')});
  await carol.getByRole('button',{name:'Send to current members',exact:true}).click();await carol.getByText('Conversation unavailable. Refresh to inspect current membership and coordinator unlock.',{exact:true}).waitFor();
  assert.equal(await carol.locator('.conversation-history article').count(),0);
  await api('alice','/api/conversations/thread_1/invite',{binding:await bound('alice'),recipient:principal('carol')});
  await carol.locator('#refresh').click();await carol.getByRole('button',{name:'Join future messages only',exact:true}).click();await open(carol);assert.equal(await carol.locator('.conversation-message').count(),0);
  // Exercise the actual component privacy handler while a real committed HTTP
  // response is held. Controlled visibility events are intentional: they make
  // this interruption deterministic without claiming physical-tab scheduling.
  await refresh(alice);let releaseHeld,markHeld;const held=new Promise(resolve=>{markHeld=resolve;});
  await alice.route('**/api/conversations/thread_1/message',async route=>{const response=await route.fetch();assert.equal(response.status(),200);await new Promise(resolve=>{releaseHeld=resolve;markHeld();});await route.fulfill({response});});
  await alice.getByLabel('Message to the members shown above').fill('Committed while the conversation view is hidden.');await alice.getByRole('button',{name:'Send to current members',exact:true}).click();await held;
  await alice.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await alice.locator('#item-list').textContent(),'');assert.equal(await alice.locator('#refresh').isDisabled(),true);
  await alice.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('focus'));document.querySelector('#refresh').click();});
  assert.equal(await alice.locator('#refresh').isDisabled(),true);releaseHeld();
  await alice.waitForFunction(()=>document.querySelector('#connection-status').textContent==='Inspection required');
  await alice.unroute('**/api/conversations/thread_1/message');const beforeBlocked=writes.length;
  await alice.getByRole('button',{name:'New conversation',exact:true}).click();assert.equal(writes.length,beforeBlocked);
  await refresh(alice);assert.equal(await alice.locator('.conversation-history article').filter({hasText:'Committed while the conversation view is hidden.'}).count(),1);
  assert.equal(await alice.locator('#connection-status').textContent(),'Saved state checked');
  assert.equal(writes.filter(w=>w.name==='alice'&&w.path.endsWith('/message')&&w.body?.text==='Committed while the conversation view is hidden.').length,1);
  // Ending the actual session still discards every in-memory recovery ticket.
  // The exact committed inspection above did not replay the earlier message.
  await alice.locator('#logout').click();await alice.locator('#login-screen').waitFor({state:'visible'});
  await alice.locator('#account').fill('alice');await alice.locator('#password').fill(password);await alice.getByRole('button',{name:/Unlock workspace/}).click();await alice.locator('#workspace').waitFor({state:'visible'});await nav(alice);
  // Real committed message with lost response: no automatic or repeated retry.
  await refresh(alice);let swallowed=0;
  await alice.route('**/api/conversations/thread_1/message',async route=>{swallowed++;const response=await route.fetch();assert.equal(response.status(),200);await route.abort('failed');});
  await alice.getByLabel('Message to the members shown above').fill('One committed message with a lost response.');await alice.getByRole('button',{name:'Send to current members',exact:true}).dblclick();await alice.getByText('Conversation unavailable. Refresh to inspect current membership and coordinator unlock.',{exact:true}).waitFor();
  await alice.unroute('**/api/conversations/thread_1/message');assert.equal(swallowed,1);
  // A failed read-only inspection leaves the original ticket retryable.
  let inspectionReads=0;await alice.route('**/api/conversations/thread_1/message-outcome',async route=>{inspectionReads++;if(inspectionReads===1)await route.abort('failed');else await route.continue();});
  await alice.locator('#refresh').click();await alice.getByText('The workspace could not be reached. This inspection made no changes.',{exact:true}).waitFor();
  assert.equal(await alice.locator('#connection-status').textContent(),'Inspection required');
  await refresh(alice);assert.equal(inspectionReads,2);await alice.unroute('**/api/conversations/thread_1/message-outcome');
  assert.equal(await alice.locator('#connection-status').textContent(),'Saved state checked');
  assert.equal(await alice.locator('.conversation-history article').filter({hasText:'One committed message with a lost response.'}).count(),1);
  assert.equal(writes.filter(w=>w.name==='alice'&&w.path.endsWith('/message')&&w.body?.text==='One committed message with a lost response.').length,1);
  await noOverflow(alice);await screenshot(alice,'central-conversations-desktop.png');
  // Dismissed/navigation-hidden text is removed from the DOM, not merely hidden.
  await alice.locator('.conversation-history article').first().getByRole('checkbox').check();await alice.getByRole('button',{name:'Inspect selected context',exact:true}).click();await alice.locator('#conversation-dialog').waitFor({state:'visible'});await alice.keyboard.press('Escape');assert.equal(await alice.locator('#conversation-dialog').textContent(),'');
  await alice.locator('[data-view=overview]').click();assert.equal(await alice.locator('#conversation-dialog').textContent(),'');assert.equal(await alice.locator('#item-list').textContent().then(t=>t.includes('earlier plan')),false);
  await alice.goBack();await alice.getByRole('button',{name:'New conversation',exact:true}).waitFor();await open(alice);
  await carol.setViewportSize({width:390,height:844});await refresh(carol);await noOverflow(carol);await carol.waitForFunction(()=>document.querySelector('.sidebar').inert&&document.querySelector('.sidebar').getBoundingClientRect().right<=0.5);await screenshot(carol,'central-conversations-mobile.png');
  await carol.locator('#mobile-logout').click();await carol.locator('#login-screen').waitFor({state:'visible'});assert.equal(await carol.locator('#item-list').textContent(),'');assert.equal(await carol.locator('#conversation-dialog').textContent(),'');
  await carol.reload();assert.equal(await carol.locator('#workspace').isVisible(),false);
  // A send dropped before dispatch is still inconclusive to the client. The
  // missing outcome never clears its hold or enables automatic replay.
  await refresh(alice);let absentSends=0;
  await alice.route('**/api/conversations/thread_1/message',async route=>{absentSends++;await route.abort('failed');});
  await alice.getByLabel('Message to the members shown above').fill('An absent outcome is not safe to resend.');await alice.getByRole('button',{name:'Send to current members',exact:true}).click();
  await alice.getByText('Conversation unavailable. Refresh to inspect current membership and coordinator unlock.',{exact:true}).waitFor();await alice.unroute('**/api/conversations/thread_1/message');
  await refresh(alice);assert.equal(await alice.locator('#connection-status').textContent(),'Inspection required');assert.equal(absentSends,1);
  assert.equal(await alice.locator('.conversation-history article').filter({hasText:'An absent outcome is not safe to resend.'}).count(),0);
  const absentCount=writes.length;await alice.getByRole('button',{name:'New conversation',exact:true}).click();assert.equal(writes.length,absentCount);
  // Last coordinator sign-out locks conversation retrieval for still-authenticated actors.
  await alice.bringToFront();await alice.locator('#logout').click();await alice.locator('#login-screen').waitFor({state:'visible'});
  await bob.bringToFront();await bob.locator('#refresh').click();await bob.getByText('Conversation access unavailable. The coordinating owner must keep an active session in a separate browser context. Refresh after they unlock.',{exact:true}).waitFor();
  assert.equal(await bob.locator('.conversation-history article').count(),0);assert.equal(await bob.locator('#owner-name').textContent(),'bob');
  assert.deepEqual(errors,[]);
  console.log('PASS separate real owner sessions, future-only join, inert history, exact source-author grant/revoke, stale membership/review, removed/rejoined owner, exact committed outcome recovery without retry, retryable read failure, inconclusive absence, scoped context, history navigation, hidden DOM, coordinator lock and mobile logout.');
}catch(error){for(const [name,p]of Object.entries(pages))if(screenshots)await p.screenshot({path:path.join(screenshots,`central-conversations-failure-${name}.png`),fullPage:true}).catch(()=>{});throw error;}
finally{await browser.close();}
