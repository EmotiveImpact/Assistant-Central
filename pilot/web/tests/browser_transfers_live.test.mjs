// Real owner HTTP + real disposable loopback TLS fixture. No HTTP route mocks.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const base=process.env.LIVE_PILOT_URL,password=process.env.LIVE_PILOT_PASSWORD;
assert.ok(base&&password,'Explicit disposable fixture required');
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);await page.locator('#password').fill(password);await page.getByRole('button',{name:'Unlock workspace'}).click();await page.locator('#workspace').waitFor({state:'visible'});
 await page.locator('[data-view=transfers]').click();
 const outbox=page.locator('.transfer-row').filter({hasText:'Queued'}).first();await outbox.getByRole('button',{name:'Inspect via Fictional Atlas mailbox'}).click();
 await page.locator('#review-dialog').waitFor({state:'visible'});await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Send original packet once',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});
 for(let i=0;i<10;i++){await page.locator('#refresh').click();await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();if((await page.locator('#item-list').textContent()).includes('untrusted quarantine acknowledgement'))break;await page.waitForTimeout(100);}
 assert.match(await page.locator('#item-list').textContent(),/untrusted quarantine acknowledgement/);
 const uncertain=page.locator('.transfer-row').filter({hasText:'Delivery uncertain'}).first();await uncertain.getByRole('button',{name:'Inspect via Fictional Atlas mailbox'}).click();if(!await page.locator('.commitment-details').evaluate(e=>e.open))await page.locator('.commitment-details summary').click();assert.match(await page.locator('#review-commitments').textContent(),/Attempt/);assert.equal(await page.getByRole('button',{name:'Send one explicit retry',exact:true}).count(),1);await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.locator('.transfer-import select').first().selectOption('fixture-peer');await page.getByRole('button',{name:'Inspect selected import',exact:true}).click();assert.match(await page.locator('#review-state').textContent(),/Untrusted quarantine/);await page.locator('#review-dialog').waitFor({state:'visible'});await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Import selected packet',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});
 const receipt=page.locator('.transfer-row').filter({hasText:'Return original receipt'}).first();await receipt.getByRole('button',{name:'Inspect via Fictional Atlas mailbox'}).click();await page.locator('#review-dialog').waitFor({state:'visible'});await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Send original packet once',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});
 await page.locator('#refresh').click();await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();
 if(process.env.PILOT_SCREENSHOT_DIR){await mkdir(process.env.PILOT_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-live-desktop.png'),fullPage:true});}
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(process.env.PILOT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-live-mobile.png'),fullPage:true});
 await page.locator('.transfer-row').filter({hasText:'Delivery uncertain'}).first().getByRole('button',{name:'Inspect via Fictional Atlas mailbox'}).click();if(!await page.locator('.commitment-details').evaluate(e=>e.open))await page.locator('.commitment-details summary').click();
 if(process.env.PILOT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-live-review-mobile.png'),fullPage:true});
 await page.keyboard.press('Escape');await page.locator('#review-dialog').waitFor({state:'hidden'});await page.locator('#mobile-logout').click();await page.locator('#login-screen').waitFor({state:'visible'});
 assert.equal(await page.locator('#item-list').textContent(),'');assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(errors,[]);
 console.log('PASS live transfers: actual authenticated HTTP, original packet sent through real loopback TLS, immutable attempt review, separately selected duplicate import and cached receipt return, desktop/mobile layout and logout.');
}catch(error){console.error('LIVE TRANSFER FAILURE',JSON.stringify({errors,message:await page.locator('#review-message').textContent(),notice:await page.locator('#notice').textContent()}));if(process.env.PILOT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-live-failure.png'),fullPage:true});throw error;}finally{await browser.close();}
