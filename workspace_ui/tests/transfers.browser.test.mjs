// Real Central shell -> owner HTTP -> disposable loopback TLS. Only the
// explicitly labelled lost-response/failed-inspection injections alter responses.
import {createRequire} from 'node:module';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=new URL(process.env.WORKSPACE_TRANSFER_URL||'');
assert.equal(base.hostname,'127.0.0.1');assert.equal(base.protocol,'http:');
const password=process.env.WORKSPACE_PASSWORD;assert.ok(password);
const evidence=process.env.WORKSPACE_SCREENSHOT_DIR;
if(evidence)await mkdir(evidence,{recursive:true});
const browser=await chromium.launch({headless:true});
let page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],writes=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{if(request.method()==='POST'&&!request.url().endsWith('/api/session'))writes.push({path:new URL(request.url()).pathname,body:request.postDataJSON()});});
const gate=process.env.WORKSPACE_TRANSFER_GATE;assert.ok(gate,'Explicit disposable synchronisation directory required');
let token;
const api=async(route,body)=>{
 const response=await page.request[body===undefined?'get':'post'](new URL(page.url()).origin+route,{headers:{Authorization:'Bearer '+token},...(body===undefined?{}:{data:body})});
 return {status:response.status(),value:await response.json()};
};
const snapshot=async()=>{const result=await api('/api/state');assert.equal(result.status,200);return result.value;};
const nav=async view=>{if(await page.locator('#menu-toggle').isVisible())await page.locator('#menu-toggle').click();await page.locator(`#navigation [data-view=${view}]`).click();};
const refresh=async()=>{await page.locator('#refresh').click();await page.waitForFunction(()=>!document.getElementById('refresh').disabled);await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();};
const idle=async()=>{for(let n=0;n<80;n++){const state=await snapshot();if(state.transfers.dispatch?.state!=='in_flight')return state;await page.waitForTimeout(100);}throw new Error('Disposable dispatch did not finish');};
const row=id=>page.locator('.transfer-row').filter({hasText:id});
const open=async id=>{await row(id).getByRole('button',{name:'Inspect via Fictional Atlas mailbox',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});};
const close=async()=>{await page.getByRole('button',{name:'Close review',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const send=async name=>{await page.locator('#transfer-confirm').check();await page.getByRole('button',{name,exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const screenshot=async(name,{fullPage=true}={})=>{
 if(!evidence)return;
 await page.evaluate(()=>document.fonts.ready.then(()=>undefined));
 if(await page.locator('#menu-toggle').isVisible()){
  assert.equal(await page.locator('body').evaluate(node=>node.classList.contains('sidebar-open')),false);
  await page.waitForFunction(()=>document.querySelector('.sidebar').inert&&document.querySelector('.sidebar').getBoundingClientRect().right<=0.5);
  assert.equal(await page.locator('.sidebar').getAttribute('aria-hidden'),'true');
 }
 await page.screenshot({path:path.join(evidence,name),fullPage});
};
try{
 await page.goto(base.origin);
 const login=page.waitForResponse(response=>response.url().endsWith('/api/session')&&response.request().method()==='POST');
 await page.locator('#password').fill(password);await page.getByRole('button',{name:'Unlock workspace'}).click();token=(await (await login).json()).token;
 await page.locator('#workspace').waitFor({state:'visible'});
 const initial=await snapshot(),delivery=initial.items.find(item=>item.title==='Central transfer delivery'),withdrawal=initial.items.find(item=>item.title==='Central transfer withdrawal');
 assert.ok(delivery&&withdrawal);const packet='proposal-'+delivery.id,withdrawPacket='proposal-'+withdrawal.id;
 for(const view of ['overview','inbox','tasks','artifacts','outbox','peers','transfers','activity'])await nav(view);
 assert.equal(writes.length,0,'navigation cannot send, import or change authority');
 const endpoint=`/api/transfers/fixture-peer/outbox/${packet}`;
 await nav('transfers');
 await page.route('**'+endpoint,async route=>{const actual=await route.fetch();const value=await actual.json();value.connection.peer_fingerprint='0'.repeat(64);await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});});
 await row(packet).getByRole('button',{name:'Inspect via Fictional Atlas mailbox',exact:true}).click();
 await page.locator('#notice').filter({hasText:'could not be verified'}).waitFor();assert.equal(await page.locator('#review-dialog').isVisible(),false);assert.equal(writes.length,0);
 await page.unroute('**'+endpoint);await open(packet);
 assert.equal(await page.getByRole('dialog',{name:'Inspect exact transfer',exact:true}).count(),1);
 await page.getByRole('button',{name:'Send original packet once',exact:true}).click();assert.equal(writes.length,0);
 await close();await open(packet);assert.equal(await page.locator('#transfer-confirm').isChecked(),false);
 let interruptions=0;
 await page.route('**'+endpoint+'/send',async route=>{interruptions++;const actual=await route.fetch();assert.equal(actual.status(),200);await route.fulfill({status:503,contentType:'application/json',body:'{"error":"Fixture lost response after actual dispatch"}'});});
 await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Send original packet once',exact:true}).click();
 await page.locator('#review-message').filter({hasText:'could not be confirmed'}).waitFor();
 await page.getByRole('button',{name:'Send original packet once',exact:true}).click();assert.equal(interruptions,1);
 await close();await page.unroute('**'+endpoint+'/send');
 await page.route('**/api/state',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"Fixture failed inspection"}'}));
 await page.locator('#refresh').click();await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
 await row(packet).getByRole('button',{name:'Inspect via Fictional Atlas mailbox',exact:true}).click();assert.equal(await page.locator('#review-dialog').isVisible(),false);
 await page.unroute('**/api/state');await idle();await refresh();
 let current=await snapshot();assert.equal(current.transfers.outbox.find(item=>item.message_id===packet).attempts,1);
 assert.match(await page.locator('#item-list').textContent(),/untrusted quarantine acknowledgement/);
 await open(packet);const stale=(await api(endpoint)).value;
 await send('Send one explicit retry');await idle();await refresh();
 current=await snapshot();assert.equal(current.transfers.outbox.find(item=>item.message_id===packet).attempts,2);
 // Replay the formerly exact review through the actual owner API. It must fail
 // and cannot silently become another retry after the retained attempts change.
 assert.equal((await api(endpoint+'/send',{review_digest:stale.review_digest,retry:true})).status,400);
 assert.equal((await snapshot()).transfers.outbox.find(item=>item.message_id===packet).attempts,2);
 await open(packet);await page.locator('.commitment-details summary').click();
 assert.match(await page.locator('#review-commitments').textContent(),/Attempt 1/);assert.match(await page.locator('#review-commitments').textContent(),/Attempt 2/);await close();
 const beforeImport=await snapshot();await page.locator('.transfer-import select').first().selectOption('fixture-peer');await page.getByRole('button',{name:'Inspect selected import',exact:true}).click();
 await page.locator('#review-dialog').waitFor({state:'visible'});assert.match(await page.locator('#review-state').textContent(),/Untrusted quarantine/);await send('Import selected packet');
 current=await snapshot();assert.deepEqual(current.items.map(item=>[item.id,item.state]),beforeImport.items.map(item=>[item.id,item.state]),'duplicate import must not accept any proposal');
 const cached=current.transfers.receipts.find(item=>item.peer===initial.transfers.connections[0].peer_fingerprint);assert.ok(cached);
 const receiptRow=page.locator('.transfer-row').filter({hasText:'Return original receipt'}).filter({hasText:cached.message_id});
 await receiptRow.getByRole('button',{name:'Inspect via Fictional Atlas mailbox',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});await send('Send original packet once');await idle();await refresh();
 assert.equal((await snapshot()).items.find(item=>item.title==='Browser acceptance task').state,'pending','returning a receipt does not accept work');
 // A distinct fictional owner now imports the exact delivered packet, then
 // separately returns its cached signed receipt over a second real TLS mailbox.
 const mainPage=page,mainToken=token;page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',error=>errors.push(error.message));
 const other=new URL(base);other.port=String(Number(base.port)+1);await page.goto(other.origin);
 const otherLogin=page.waitForResponse(response=>response.url().endsWith('/api/session')&&response.request().method()==='POST');
 await page.locator('#password').fill(password);await page.getByRole('button',{name:'Unlock workspace'}).click();token=(await (await otherLogin).json()).token;
 await page.locator('#workspace').waitFor({state:'visible'});await nav('transfers');
 let secondState=await snapshot(),chosen=null;
 for(const digest of secondState.transfers.quarantine){const review=await api(`/api/transfers/fixture-peer/quarantine/${digest}`);if(review.status===200&&review.value.message_id===packet)chosen=digest;}
 assert.ok(chosen,'exact delivery must exist in the other owner quarantine');
 await page.locator('.transfer-import select').first().selectOption('fixture-peer');await page.locator('.transfer-import select').nth(1).selectOption(chosen);
 await page.getByRole('button',{name:'Inspect selected import',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});await send('Import selected packet');
 secondState=await snapshot();assert.equal(secondState.items.find(item=>item.id===delivery.id).state,'pending');
 const returned=secondState.transfers.receipts.find(item=>item.incoming_id===packet);assert.ok(returned);
 await page.locator('.transfer-row').filter({hasText:'Return original receipt'}).filter({hasText:returned.message_id}).getByRole('button',{name:'Inspect via Fictional Beacon mailbox',exact:true}).click();
 await page.locator('#review-dialog').waitFor({state:'visible'});await send('Send original packet once');await idle();
 await page.locator('#logout').click();await page.locator('#login-screen').waitFor({state:'visible'});await page.close();page=mainPage;token=mainToken;
 await refresh();current=await snapshot();chosen=null;
 for(const digest of current.transfers.quarantine){const review=await api(`/api/transfers/fixture-peer/quarantine/${digest}`);if(review.status===200&&review.value.message_id===returned.message_id)chosen=digest;}
 assert.ok(chosen,'returned signed receipt must be individually imported');
 await page.locator('.transfer-import select').first().selectOption('fixture-peer');await page.locator('.transfer-import select').nth(1).selectOption(chosen);
 await page.getByRole('button',{name:'Inspect selected import',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});await send('Import selected packet');
 current=await snapshot();assert.equal(current.transfers.outbox.find(item=>item.message_id===packet).state,'received');
 assert.equal(current.items.find(item=>item.id===delivery.id).state,'released','signed transport receipt is not owner acceptance');
 const retainedReview=(await api(endpoint)).value;assert.equal(retainedReview.attempts.length,2);assert.ok(retainedReview.attempts.every(attempt=>attempt.state==='uncertain'),'immutable uncertainty is not rewritten by later receipt evidence');
 // The fixture pauses after the real TLS carrier returns. Withdrawal remains a
 // local stop and cannot claim that already transmitted bytes were recalled.
 await writeFile(path.join(gate,'arm'),'Pause this disposable transfer after actual TLS.');
 await open(withdrawPacket);await send('Send original packet once');
 let retained=false;for(let n=0;n<100;n++){try{await readFile(path.join(gate,'retained'));retained=true;break;}catch{await page.waitForTimeout(50);}}assert.equal(retained,true,'real TLS retention must precede withdrawal');
 current=await snapshot();assert.equal(current.transfers.dispatch.state,'in_flight');
 assert.match(await page.locator('#item-list').textContent(),/cannot be recalled/);
 const retryableReceipt=(await api(`/api/transfers/fixture-peer/receipt/${cached.incoming_id}`)).value;
 assert.deepEqual(retryableReceipt.allowed_actions,['retry'],'the underlying cached receipt must remain retryable to prove the single-flight UI gate');
 await page.locator('.transfer-row').filter({hasText:'Return original receipt'}).filter({hasText:cached.message_id}).getByRole('button',{name:'Inspect via Fictional Atlas mailbox',exact:true}).click();
 await page.locator('#review-dialog').waitFor({state:'visible'});
 assert.equal(await page.getByRole('button',{name:'Send one explicit retry',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Send original packet once',exact:true}).count(),0);
 assert.match(await page.locator('#review-message').textContent(),/in flight/);await close();
 await nav('outbox');const item=page.locator('#item-list article').filter({has:page.getByRole('button',{name:'Review Central transfer withdrawal',exact:true})});
 await item.getByRole('button',{name:'Review exact item',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});
 await page.getByRole('button',{name:'Withdraw proposal',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});
 await writeFile(path.join(gate,'release'),'Release disposable completion after local withdrawal.');
 await idle();await refresh();current=await snapshot();assert.equal(current.transfers.outbox.find(item=>item.message_id===withdrawPacket).state,'cancelled');
 assert.equal(current.transfers.outbox.find(item=>item.message_id===withdrawPacket).owner_acceptance,'not_established');
 await nav('transfers');await screenshot('central-transfers-desktop.png');
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.evaluate(()=>window.scrollTo(0,0));await screenshot('central-transfers-mobile.png',{fullPage:false});await open(packet);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await screenshot('central-transfers-review-mobile.png',{fullPage:false});
 await page.keyboard.press('Escape');await page.locator('#review-dialog').waitFor({state:'hidden'});
 await page.locator('#menu-toggle').click();assert.equal(await page.locator('.sidebar').evaluate(node=>node.inert),false);await page.keyboard.press('Escape');assert.equal(await page.locator('.sidebar').evaluate(node=>node.inert),true);
 await page.locator('#mobile-logout').click();await page.locator('#login-screen').waitFor({state:'visible'});
 for(const id of ['item-list','review-content','review-title','review-state','review-details','review-commitments','review-scope','owner-name','agent-name','notice'])assert.equal(await page.locator('#'+id).textContent(),'');
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(errors,[]);
 console.log('PASS Central transfers: real HTTP/TLS, navigation without writes, explicit confirmation, lost actual-dispatch response and failed-inspection fence, one explicit retry, stale-review rejection, separate exact import and cached receipt, in-flight withdrawal without recall, mobile focus and clean logout.');
}catch(error){console.error('CENTRAL TRANSFER FAILURE',JSON.stringify({errors,writes,message:await page.locator('#review-message').textContent(),notice:await page.locator('#notice').textContent()}));await screenshot('central-transfers-failure.png');throw error;}finally{await writeFile(path.join(gate,'release'),'Clean up disposable test gate.').catch(()=>{});await browser.close();}
