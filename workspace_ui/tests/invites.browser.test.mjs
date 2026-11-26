// Two real copies of Parlu and one local relay, in Chromium. Edem makes an invite, Maya opens
// it from the relay's own invite page, both see the same code, and Edem adds Maya. No model,
// no key to paste and no fingerprint to type.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const edemURL=new URL(process.env.EDEM_URL||''),mayaURL=new URL(process.env.MAYA_URL||''),relayURL=new URL(process.env.RELAY_URL||'');
for(const url of [edemURL,mayaURL,relayURL]){assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');}
const password=process.env.WORKSPACE_PASSWORD;if(!password)throw new Error('Disposable fixture password required');
const screenshots=process.env.WORKSPACE_SCREENSHOT_DIR;if(screenshots)await mkdir(screenshots,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const errors=[];
async function open(url,{phone=false}={}){
  const context=await browser.newContext(phone?{viewport:{width:390,height:844},isMobile:true,hasTouch:true}:{viewport:{width:1440,height:1000}});
  await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:url.origin}).catch(()=>{});
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  return page;
}
async function signIn(page){
  await page.locator('#password').fill(password);await page.locator('#login-form button[type=submit]').click();
  await page.locator('#workspace').waitFor({state:'visible'});
}
async function goAssistants(page){
  if(await page.locator('#menu-toggle').isVisible())await page.locator('#menu-toggle').click();
  const target=page.locator('#navigation [data-view="peers"]');if(!await target.isVisible())await page.locator('#everything-toggle').click();
  await target.click();await page.locator('.relay-strip').waitFor();
  // On a phone the drawer slides away; wait until it has gone before reading or drawing the page.
  await page.waitForFunction(()=>!document.body.classList.contains('sidebar-open')&&document.querySelector('.sidebar').getBoundingClientRect().right<=0.5||innerWidth>700);
}
const shot=async(page,name)=>{if(screenshots)await page.screenshot({path:path.join(screenshots,name),fullPage:true});};

try{
  // Edem makes an invite from the Assistants page.
  const edem=await open(edemURL);await edem.goto(edemURL.href);await signIn(edem);await goAssistants(edem);
  await edem.locator('.relay-strip').getByRole('button',{name:'Invite someone'}).click();
  await edem.locator('#invite-dialog input[name=label]').fill('Maya');
  await edem.locator('#invite-submit').click();
  await edem.locator('#invite-ready').waitFor({state:'visible'});
  const link=await edem.locator('#invite-link').inputValue(),code=(await edem.locator('#invite-code').textContent()).trim();
  assert.ok(link.startsWith(relayURL.origin+'/invite#'),'the link points at the relay, with the secret after #');
  assert.match(code,/^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/);
  assert.equal(await edem.locator('#invite-qr svg path').count(),1,'a QR code is drawn');
  assert.equal(await edem.locator('#invite-title').textContent(),'An invite for Maya');
  await shot(edem,'invite-1-ready.png');
  await edem.locator('#invite-dialog .dialog-footer .close-dialog').click();
  await edem.locator('.relay-row').filter({hasText:`code ${code}`}).waitFor();

  // On a computer the relay's page hands the link to local Parlu after "#join=".
  const desk=await open(mayaURL);
  await desk.goto(link);
  const handoff=await desk.locator('#open').getAttribute('href');
  assert.ok(handoff.startsWith('http://127.0.0.1:8877/#join='),'the relay page hands over to local Parlu');
  assert.equal(decodeURIComponent(handoff.split('#join=')[1]),link);
  assert.equal(await desk.locator('#copy').isVisible(),false);
  // On a phone, loopback is the phone itself, so the page offers to copy the link instead.
  const maya=await open(mayaURL,{phone:true});
  await maya.goto(link);
  await maya.locator('#copy').waitFor({state:'visible'});
  assert.equal(await maya.locator('#open').isVisible(),false,'no button that cannot reach Parlu');
  await maya.goto(mayaURL.origin+'/#join='+encodeURIComponent(link));
  assert.ok(!maya.url().includes('join='),'the invite is taken out of the address bar straight away');
  await signIn(maya);
  await maya.locator('#join-review').waitFor({state:'visible'});
  assert.equal((await maya.locator('#join-code').textContent()).trim(),code,'both people see the same code');
  assert.match(await maya.locator('#join-who').textContent(),/Edem and Juniper/);
  assert.match(await maya.locator('#join-facts').textContent(),/never agrees to any work/);
  await shot(maya,'invite-2-join-phone.png');
  await maya.locator('#join-submit').click();
  await maya.locator('#join-dialog').waitFor({state:'hidden'});
  assert.match(await maya.locator('#notice').textContent(),/Edem adds you/);

  // Edem syncs and finds Maya waiting on Home, then checks the code and adds her.
  await edem.locator('#sync').click();
  await edem.locator('#notice').filter({hasText:'Someone used your invite.'}).waitFor();
  await edem.locator('#navigation [data-view="overview"]').click();
  const card=edem.locator('.home-card.depth-0[data-kind="joiner"]');await card.waitFor();
  assert.match(await edem.locator('#home-paragraph').textContent(),/used your invite/);
  await card.getByRole('button',{name:'Check and add'}).click();
  await edem.locator('#inspect .pair-code').filter({hasText:code}).waitFor();
  await shot(edem,'invite-3-check-and-add.png');
  await edem.locator('#inspect').getByRole('button',{name:'Add Maya and Otto'}).click();
  await edem.locator('#notice').filter({hasText:'Maya is connected'}).waitFor();
  await goAssistants(edem);
  await edem.locator('#item-list .peer-row').filter({hasText:'Otto'}).filter({hasText:'Connected through the relay'}).waitFor();

  // Maya's copy hears back on its next sync and shows Edem as connected.
  await maya.locator('#sync').click();
  await maya.locator('#notice').filter({hasText:'One person added you.'}).waitFor();
  await goAssistants(maya);
  await maya.locator('#item-list .peer-row').filter({hasText:'Juniper'}).filter({hasText:'Connected through the relay'}).waitFor();
  assert.equal(await maya.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'no sideways scroll on a phone');
  await shot(maya,'invite-4-connected-phone.png');

  // Opening the link again is refused before anything is sent, and the working link stays.
  await maya.locator('.relay-strip').getByRole('button',{name:'Join with a link'}).click();
  await maya.locator('#join-link').fill(link);await maya.locator('#join-submit').click();
  await maya.locator('#join-message').filter({hasText:'already connected'}).waitFor();
  await maya.locator('#join-dialog .close-dialog').first().click();
  await maya.locator('#item-list .peer-row').filter({hasText:'Juniper'}).filter({hasText:'Connected through the relay'}).waitFor();

  assert.deepEqual(errors,[]);
  console.log('Invite link browser test passed.');
}finally{await browser.close();}
