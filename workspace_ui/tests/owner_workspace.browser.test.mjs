// Combined composition acceptance against fresh, actual local HTTP accounts.
// Controlled visibility events test the handler, not physical tab scheduling.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const url=new URL(process.env.OWNER_WORKSPACE_URL||'');
assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');assert.ok(process.env.OWNER_WORKSPACE_PASSWORD);
const captures=process.env.WORKSPACE_SCREENSHOT_DIR;if(captures)await mkdir(captures,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const pages={},tokens={},errors=[],writes=[];
const nav=async(page,view)=>{if(await page.locator('#menu-toggle').isVisible())await page.locator('#menu-toggle').click();await page.locator(`[data-view="${view}"]`).click();};
const showRoom=async page=>{await page.locator('.conversation-rooms button').first().click();await page.getByLabel('Message to the members shown above').waitFor();};
const capture=async(page,name)=>{assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));if(captures){await page.evaluate(()=>document.fonts.ready.then(()=>undefined));await page.screenshot({path:path.join(captures,name),fullPage:true});}};
async function api(name,route,body){const response=await pages[name].request.fetch(new URL(route,url).href,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+tokens[name]},...(body===undefined?{}:{data:body})});assert.equal(response.status(),200);return response.json();}
try{
  for(const name of ['alice','bob','carol']){
    const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=pages[name]=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(request.method()==='POST')writes.push({name,path:new URL(request.url()).pathname,body:request.postDataJSON()});});
    await page.goto(url.href);await page.locator('#account').fill(name);await page.locator('#password').fill(process.env.OWNER_WORKSPACE_PASSWORD);
    const login=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/session');await page.locator('#login-form button').click();tokens[name]=(await (await login).json()).token;
    await page.locator('#workspace').waitFor({state:'visible'});assert.equal(await page.locator('#owner-name').textContent(),name);
    await nav(page,'host-drafts');await page.getByRole('button',{name:'Refresh host drafts',exact:true}).waitFor();
    if(name==='carol')assert.match(await page.locator('#item-list').textContent(),/No host draft connections/);
    else{assert.match(await page.locator('#item-list').textContent(),new RegExp(name+'_queue'));assert.doesNotMatch(await page.locator('#item-list').textContent(),new RegExp((name==='alice'?'bob':'alice')+'_queue'));}
  }
  const {alice,bob,carol}=pages;
  await alice.bringToFront();await alice.getByRole('button',{name:'Inspect draft',exact:true}).click();await alice.locator('#host-draft-dialog[open]').waitFor();
  assert.match(await alice.locator('#host-draft-dialog').textContent(),/alice_fictional_recipient/);
  await capture(alice,'owner-workspace-host-desktop.png');
  let finish,committed;const holding=new Promise(resolve=>committed=resolve),release=new Promise(resolve=>finish=resolve);
  await alice.route('**/api/host-drafts/*/*/dismiss',async route=>{const response=await route.fetch();assert.equal(response.status(),200);committed();await release;await route.fulfill({response});});
  await alice.locator('#host-draft-dismiss-confirm').check();await alice.getByRole('button',{name:'Dismiss exact draft',exact:true}).evaluate(button=>{button.click();button.click();});await holding;
  // History/hash navigation is not disabled by the pending request's button gate.
  await alice.evaluate(()=>{location.hash='conversations';});await alice.getByRole('button',{name:'New conversation',exact:true}).waitFor();
  assert.equal(await alice.locator('#host-draft-dialog').textContent(),'');
  const count=writes.length;await alice.getByRole('button',{name:'New conversation',exact:true}).evaluate(button=>button.click());assert.equal(writes.length,count);
  await alice.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});assert.equal(await alice.locator('#item-list').textContent(),'');
  await alice.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});finish();
  await alice.waitForFunction(()=>document.querySelector('#connection-status').textContent==='Inspection required');await alice.getByRole('button',{name:'New conversation',exact:true}).waitFor();
  await alice.getByRole('button',{name:'New conversation',exact:true}).click();assert.equal(writes.length,count);
  await alice.unroute('**/api/host-drafts/*/*/dismiss');await alice.locator('#refresh').click();await showRoom(alice);
  // Real passive polling retains text only while the exact audience is stable.
  await alice.getByLabel('Message to the members shown above').fill('An unsent local plan that must survive a new message.');
  const room=await api('bob','/api/conversations/thread_1');await api('bob','/api/conversations/thread_1/message',{binding:{member_epoch:room.binding.member_epoch,policy_generation:room.binding.policy_generation},request_id:'combined_poll_message',text:'A new fictional message while Alice is typing.'});
  await alice.getByText('A new fictional message while Alice is typing.',{exact:true}).waitFor({timeout:25000});assert.equal(await alice.getByLabel('Message to the members shown above').inputValue(),'An unsent local plan that must survive a new message.');
  await carol.bringToFront();await nav(carol,'conversations');await carol.getByRole('button',{name:'Join future messages only',exact:true}).click();await showRoom(carol);assert.equal(await carol.locator('.conversation-history article').count(),0);
  await alice.bringToFront();await alice.waitForFunction(()=>document.querySelector('.conversation-compose textarea')?.value==='',{},{timeout:25000});
  assert.equal(writes.filter(w=>w.name==='alice'&&w.path.endsWith('/message')).length,0);
  await capture(alice,'owner-workspace-conversations-desktop.png');
  await bob.bringToFront();await bob.setViewportSize({width:390,height:844});await nav(bob,'conversations');await showRoom(bob);await capture(bob,'owner-workspace-conversations-mobile.png');
  await nav(bob,'host-drafts');await bob.getByRole('button',{name:'Inspect draft',exact:true}).click();await bob.locator('#host-draft-dialog[open]').waitFor();await capture(bob,'owner-workspace-host-mobile.png');
  assert.match(await bob.locator('#host-draft-dialog').textContent(),/bob_fictional_recipient/);assert.doesNotMatch(await bob.locator('#host-draft-dialog').textContent(),/alice_fictional_recipient/);
  await bob.keyboard.press('Escape');assert.equal(await bob.locator('#host-draft-dialog').textContent(),'');
  await alice.bringToFront();await alice.locator('#logout').click();await alice.locator('#login-screen').waitFor({state:'visible'});assert.equal(await alice.locator('#item-list').textContent(),'');assert.equal(await alice.locator('#conversation-dialog').textContent(),'');
  await bob.bringToFront();await bob.locator('#refresh').click();await bob.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();assert.equal(await bob.locator('#owner-name').textContent(),'bob');
  await nav(bob,'conversations');await bob.getByText('Conversation access unavailable. The coordinating owner must keep an active session in a separate browser context. Refresh after they unlock.',{exact:true}).waitFor();assert.equal(await bob.locator('.conversation-history article').count(),0);
  await bob.locator('#mobile-logout').click();await bob.locator('#login-screen').waitFor({state:'visible'});assert.equal(await bob.locator('#host-draft-dialog').textContent(),'');assert.equal(await bob.locator('#item-list').textContent(),'');
  assert.equal(writes.filter(w=>w.path.endsWith('/dismiss')).length,1);assert.deepEqual(errors,[]);
  console.log('PASS combined desktop/mobile local accounts, per-owner queues, cross-panel pending gate and privacy recovery, stable unsent draft, changed audience clearing and coordinator lock.');
}finally{await browser.close();}
