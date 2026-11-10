// Real browser -> actual owner HTTP -> encrypted draft produced by official SDK.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const url=new URL(process.env.HOST_DRAFT_URL||'');
assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');
assert.ok(process.env.HOST_DRAFT_PASSWORD);
const captures=process.env.WORKSPACE_SCREENSHOT_DIR;if(captures)await mkdir(captures,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const errors=[],writes=[];page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname.includes('/host-drafts/'))writes.push(request.url());});
const nav=async()=>{if(await page.locator('#menu-toggle').isVisible())await page.locator('#menu-toggle').click();await page.locator('[data-view="host-drafts"]').click();await page.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();};
const inspect=async()=>{await page.getByRole('button',{name:'Inspect draft',exact:true}).click();await page.locator('#host-draft-dialog[open]').waitFor();};
const screenshot=async(name)=>{if(!captures)return;await page.evaluate(()=>document.fonts.ready.then(()=>undefined));if(await page.locator('#menu-toggle').isVisible())await page.waitForFunction(()=>document.querySelector('.sidebar').inert&&document.querySelector('.sidebar').getBoundingClientRect().right<=0.5);await page.screenshot({path:path.join(captures,name),fullPage:true});};
const noOverflow=async()=>assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
try{
 await page.goto(url.href);await page.locator('#password').fill(process.env.HOST_DRAFT_PASSWORD);await page.locator('#login-form button').click();await page.locator('#workspace').waitFor({state:'visible'});
 await nav();assert.equal(writes.length,0);await noOverflow();await screenshot('host-drafts-desktop.png');
 await inspect();assert.equal(await page.locator('#host-draft-dialog').getAttribute('aria-labelledby'),'host-draft-review-title');
 assert.ok((await page.locator('#host-draft-dialog').textContent()).includes('fictional_fixed_recipient'));
 assert.ok((await page.locator('#host-draft-dialog .artifact-content').textContent()).includes('<img src=x onerror='));
 assert.equal(await page.locator('#host-draft-dialog img').count(),0);assert.equal(await page.evaluate(()=>window.hostDraftExecuted),undefined);
 await page.getByRole('button',{name:'Dismiss exact draft',exact:true}).click();assert.equal(writes.length,0);
 await screenshot('host-draft-review-desktop.png');
 await page.keyboard.press('Escape');await page.locator('#host-draft-dialog').waitFor({state:'hidden'});assert.equal(await page.locator('#host-draft-dialog').textContent(),'');assert.equal(writes.length,0);
 // Browser history invalidates an open review without a write.
 await inspect();await page.goBack();await page.locator('#host-draft-dialog').waitFor({state:'hidden'});assert.equal(await page.locator('#host-draft-dialog').textContent(),'');assert.equal(writes.length,0);await nav();
 await page.setViewportSize({width:390,height:844});await noOverflow();await screenshot('host-drafts-mobile.png');await inspect();await noOverflow();await screenshot('host-draft-review-mobile.png');await page.getByRole('button',{name:'Close host draft review',exact:true}).click();
 // Hidden/visible transitions discard plaintext and obtain fresh current state.
 await inspect();await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});assert.equal(await page.locator('#host-draft-dialog').textContent(),'');
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});await page.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();await inspect();
 // Hide/return before an inspect response settles restores the active view.
 await page.getByRole('button',{name:'Close host draft review',exact:true}).click();
 let finishRead,readStarted;const readGate=new Promise(resolve=>finishRead=resolve),reading=new Promise(resolve=>readStarted=resolve);
 await page.route('**/api/host-drafts/*/*/review',async route=>{const response=await route.fetch();readStarted();await readGate;await route.fulfill({response});});
 await page.getByRole('button',{name:'Inspect draft',exact:true}).click();await reading;
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
 finishRead();await page.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();await page.unroute('**/api/host-drafts/*/*/review');
 assert.equal(await page.locator('#host-draft-dialog').textContent(),'');await inspect();
 let committed=0,finishDismiss,dismissStarted;const dismissGate=new Promise(resolve=>finishDismiss=resolve),dismissing=new Promise(resolve=>dismissStarted=resolve);
 await page.route('**/api/host-drafts/*/*/dismiss',async route=>{const response=await route.fetch();assert.equal(response.status(),200);const result=await response.json();assert.equal(result.status.state,'dismissed');committed++;dismissStarted();await dismissGate;await route.abort('failed');});
 await page.locator('#host-draft-dismiss-confirm').check();
 // Two synchronous clicks cannot launch two writes while the first owns the gate.
 await page.getByRole('button',{name:'Dismiss exact draft',exact:true}).evaluate(button=>{button.click();button.click();});
 await dismissing;
 // The write has committed; hide/return before its response is lost. Recovery
 // restores the view while retaining the global uncertainty latch.
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
 finishDismiss();
 await page.waitForFunction(()=>document.querySelector('#connection-status').textContent==='Inspection required');
 await page.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();
 await page.getByRole('button',{name:'Inspect draft',exact:true}).click();assert.equal(await page.locator('#host-draft-dialog').getAttribute('open'),null);
 assert.equal(committed,1);assert.equal(writes.length,1);assert.equal(await page.locator('#host-draft-dialog').textContent(),'');
 assert.equal(await page.getByRole('button',{name:'Dismiss exact draft',exact:true}).count(),0);
 await page.unroute('**/api/host-drafts/*/*/dismiss');await page.locator('#refresh').click();await page.getByRole('button',{name:'Inspect draft',exact:true}).waitFor();
 assert.ok((await page.locator('#item-list').textContent()).includes('Dismissed'));await inspect();
 assert.ok((await page.locator('#host-draft-dialog').textContent()).includes('Saved dismissal:'));assert.equal(await page.getByRole('button',{name:'Dismiss exact draft',exact:true}).count(),0);assert.equal(writes.length,1);
 await screenshot('host-draft-dismissed-mobile.png');await page.getByRole('button',{name:'Close host draft review',exact:true}).click();
 await page.locator('#mobile-logout').click();await page.locator('#login-screen').waitFor({state:'visible'});
 assert.equal(await page.locator('#item-list').textContent(),'');assert.equal(await page.locator('#host-draft-dialog').textContent(),'');assert.equal(await page.locator('#host-draft-dialog').getAttribute('open'),null);
 assert.deepEqual(errors,[]);console.log('PASS: official SDK draft, real owner HTTP, exact inert review, double-click gate, committed lost response, navigation, mobile and logout cleanup. No provider calls.');
}finally{await browser.close();}
