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
async function goView(page,view){
  if(await page.locator('#menu-toggle').isVisible())await page.locator('#menu-toggle').click();
  const target=page.locator(`#navigation [data-view="${view}"]`);if(!await target.isVisible())await page.locator('#everything-toggle').click();
  await target.click();await page.waitForFunction(()=>!document.body.classList.contains('sidebar-open')||innerWidth>700);
}
async function openItem(page,title){
  const row=page.locator('#item-list article').filter({has:page.getByRole('button',{name:'Review '+title,exact:true})});
  await row.getByRole('button',{name:/^(Review exact item|Inspect)$/}).click();await page.locator('#review-dialog').waitFor({state:'visible'});
}
async function decide(page,name){await page.locator('#review-actions').getByRole('button',{name,exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});}
async function sync(page,words){await page.locator('#sync').click();if(words)await page.locator('#notice').filter({hasText:words}).waitFor();else await page.waitForTimeout(1500);}
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
  await maya.locator('#notice').filter({hasText:'Edem adds you'}).waitFor();

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

  // A team part with rules and a compute limit. Maya agrees, reports on every rule, and Edem merges.
  const part='parlu/team-part/1\n'+JSON.stringify({brief:'SYNTHETIC ONLY: Take a card deposit when a guest books.',
    compute:{cap_micro:500000,currency:'GBP'},rules:{must:['Tests pass'],must_not:['Store card numbers']}});
  await edem.locator('#new-proposal').click();await edem.locator('#compose-dialog').waitFor({state:'visible'});
  await edem.locator('#compose-form [name="title"]').fill('Supper club app: Card deposits');
  await edem.locator('#compose-form [name="text"]').fill(part);
  await edem.locator('#compose-form [name="synthetic"]').check();
  await edem.getByRole('button',{name:'Create for review',exact:true}).click();await edem.locator('#compose-dialog').waitFor({state:'hidden'});
  await goView(edem,'outbox');await openItem(edem,'Supper club app: Card deposits');
  assert.match(await edem.locator('#review-content').textContent(),/✓ Must: Tests pass\n✕ Must not: Store card numbers/);
  await decide(edem,'Approve & release');await sync(edem);
  await sync(maya);await goView(maya,'inbox');await openItem(maya,'Supper club app: Card deposits');
  assert.match(await maya.locator('#review-decide').textContent(),/Up to £0\.50 of compute for this part/);
  assert.equal(await maya.locator('#review-decide .hold-button').count(),1,'agreeing to spend compute is a hold');
  await decide(maya,'Accept exact proposal');await sync(maya);
  await goView(maya,'tasks');await openItem(maya,'Supper club app: Card deposits');
  await maya.locator('#review-actions').getByRole('button',{name:'Return the result',exact:true}).click();
  await maya.locator('#team-reply-dialog').waitFor({state:'visible'});
  await maya.locator('#team-reply-form [name="summary"]').fill('SYNTHETIC ONLY: Deposits are taken when a guest books.');
  await maya.locator('#team-reply-form [name="kept"]').nth(0).check();await maya.locator('#team-reply-form [name="kept"]').nth(1).check();
  await maya.locator('#team-reply-form [name="compute"]').fill('0.12');
  await shot(maya,'team-1-result-phone.png');
  await maya.locator('#team-reply-submit').click();await maya.locator('#team-reply-dialog').waitFor({state:'hidden'});
  await goView(maya,'outbox');await openItem(maya,'Result: Supper club app: Card deposits');await decide(maya,'Approve & release');await sync(maya);
  await sync(edem);await goView(edem,'artifacts');await openItem(edem,'Result: Supper club app: Card deposits');
  assert.equal(await edem.locator('.decide-question').textContent(),'Merge “Supper club app: Card deposits” from Otto?');
  assert.match(await edem.locator('#review-decide').textContent(),/Otto reports £0\.12 of compute.*Every rule kept \(2\)/s);
  await shot(edem,'team-2-merge.png');
  await decide(edem,'Accept exact proposal');

  // Maya asks for access for that one part; Edem's yes is consent, so it is offered as a hold.
  await goView(maya,'tasks');await openItem(maya,'Supper club app: Card deposits');
  await maya.locator('#review-actions').getByRole('button',{name:'Ask for access',exact:true}).click();
  await maya.locator('#team-reply-dialog').waitFor({state:'visible'});
  await maya.locator('#team-reply-form [name="what"]').fill('Read the supper club calendar');
  await maya.locator('#team-reply-form [name="why"]').fill('SYNTHETIC ONLY: Deposits follow the booking dates.');
  await maya.locator('#team-reply-submit').click();await maya.locator('#team-reply-dialog').waitFor({state:'hidden'});
  await goView(maya,'outbox');await openItem(maya,'Access: Read the supper club calendar');await decide(maya,'Approve & release');await sync(maya);
  await sync(edem);await goView(edem,'inbox');await openItem(edem,'Access: Read the supper club calendar');
  assert.equal(await edem.locator('.decide-question').textContent(),'Let Otto read the supper club calendar?');
  assert.match(await edem.locator('#review-decide').textContent(),/for one part only.*1 day from when it asked/s);
  assert.match(await edem.locator('#review-content').textContent(),/^For the part: Supper club app: Card deposits \(reference /);
  await edem.locator('#review-decide').getByRole('button',{name:'Hold to agree'}).waitFor();
  await shot(edem,'team-3-access.png');
  await decide(edem,'Accept exact proposal');
  await goAssistants(edem);

  // Edem removes Otto. It is final, so it is folded away and needs a second, deliberate step.
  await edem.locator('#item-list .peer-row').filter({hasText:'Otto'}).getByRole('button',{name:'Open'}).click();
  await edem.locator('#inspect').getByRole('button',{name:'Remove Otto',exact:true}).click();
  assert.match(await edem.locator('#inspect .remove-facts').textContent(),/cannot be undone/);
  await shot(edem,'invite-5-remove.png');
  await edem.locator('#inspect').getByRole('button',{name:'Remove Otto now'}).click();
  await edem.locator('#notice').filter({hasText:'Otto is removed.'}).waitFor();
  await edem.locator('#item-list .peer-row').filter({hasText:'Otto'}).filter({hasText:'Revoked'}).waitFor();

  assert.deepEqual(errors,[]);
  console.log('Invite link browser test passed.');
}finally{await browser.close();}
