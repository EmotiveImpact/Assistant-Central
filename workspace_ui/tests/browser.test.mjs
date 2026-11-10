// Real browser -> authenticated owner HTTP API -> disposable synthetic runtime.
// The single interrupted response below deliberately hides a real committed write.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';

const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const url=new URL(process.env.WORKSPACE_URL||'');
assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');
if(!process.env.WORKSPACE_PASSWORD)throw new Error('Disposable fixture password required');
const screenshots=process.env.WORKSPACE_SCREENSHOT_DIR;
if(screenshots)await mkdir(screenshots,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[],writes=[],externalRequests=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{
  const requestURL=new URL(request.url()),pathname=requestURL.pathname;
  if(['http:','https:'].includes(requestURL.protocol)&&requestURL.origin!==url.origin)externalRequests.push(request.url());
  if(['POST','DELETE'].includes(request.method())&&pathname!=='/api/session')writes.push({path:pathname,body:request.postDataJSON()});
});
const article=title=>page.locator('#item-list article').filter({has:page.getByRole('button',{name:'Review '+title,exact:true})});
const nav=async view=>{
  if(await page.locator('#menu-toggle').isVisible()&&!await page.locator('body').evaluate(node=>node.classList.contains('sidebar-open')))await page.locator('#menu-toggle').click();
  await page.locator(`#navigation [data-view="${view}"]`).click();
  await page.waitForFunction(value=>document.querySelector(`#navigation [data-view="${value}"]`)?.getAttribute('aria-current')==='page',view);
};
const noOverflow=async()=>{
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  const clipped=await page.locator('#main .section-heading, #main .panel-controls, #main .item-title, #main .peer-fingerprint, #main .badge, #main .row-action').evaluateAll(nodes=>nodes.filter(node=>{
    if(!node.getClientRects().length)return false;const r=node.getBoundingClientRect();return r.left<-.5||r.right>innerWidth+.5;
  }).map(node=>node.className));
  assert.deepEqual(clipped,[],'visible work content must not be clipped by the main panel');
};
const screenshot=async(name,{fullPage=true}={})=>{
  if(!screenshots)return;
  await page.evaluate(()=>document.fonts.ready.then(()=>undefined));
  if(await page.locator('#menu-toggle').isVisible()){
    assert.equal(await page.locator('body').evaluate(node=>node.classList.contains('sidebar-open')),false);
    await page.waitForFunction(()=>document.querySelector('.sidebar').inert&&document.querySelector('.sidebar').getBoundingClientRect().right<=0.5);
    assert.equal(await page.locator('.sidebar').getAttribute('aria-hidden'),'true');
  }
  await page.screenshot({path:path.join(screenshots,name),fullPage});
};
const closeReview=async()=>{await page.getByRole('button',{name:'Close review',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const openItem=async title=>{await article(title).getByRole('button',{name:/^(Review exact item|Inspect)$/}).click();await page.locator('#review-dialog').waitFor({state:'visible'});};
const action=async name=>{await page.getByRole('button',{name,exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const assertAppHeading=async selector=>{
  const style=await page.locator(selector).evaluate(node=>{
    const s=getComputedStyle(node);return {size:s.fontSize,weight:s.fontWeight,lineHeight:s.lineHeight,
      tracking:s.letterSpacing,features:s.fontFeatureSettings,opticalSizing:s.fontOpticalSizing};
  });
  assert.deepEqual(style,{size:'20px',weight:'590',lineHeight:'26.6px',tracking:'-0.24px',
    features:'"cv01", "ss03"',opticalSizing:'auto'});
};

try {
  const fontResponsePromise=page.waitForResponse(response=>new URL(response.url()).pathname==='/InterVariable.woff2');
  await page.goto(url.origin);
  const fontResponse=await fontResponsePromise;
  assert.equal(fontResponse.status(),200,'the actual variable font must load, not a system fallback');
  assert.equal(fontResponse.headers()['content-type'],'font/woff2');
  const fontBytes=await fontResponse.body();
  assert.equal(fontBytes.subarray(0,4).toString(),'wOF2');
  assert.equal(createHash('sha256').update(fontBytes).digest('hex'),
    '693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3');
  await page.evaluate(()=>document.fonts.ready.then(()=>undefined));
  const fontEvidence=await page.evaluate(()=>({
    family:getComputedStyle(document.body).fontFamily,
    ready:document.fonts.check('510 13px "Inter Variable"'),
    loaded:[...document.fonts].some(face=>face.family.replaceAll('"','').replaceAll("'",'')==='Inter Variable'&&face.status==='loaded'),
  }));
  assert.ok(fontEvidence.family.startsWith('"Inter Variable"'),fontEvidence.family);
  assert.equal(fontEvidence.ready,true);
  assert.equal(fontEvidence.loaded,true,'a declared family alone does not prove a loaded webfont');
  await noOverflow();await screenshot('central-platform-login.png');
  for(const width of [768,701,390]){
    await page.setViewportSize({width,height:1000});await noOverflow();
    assert.equal(await page.locator('.login-story').evaluate(node=>node.scrollWidth<=node.clientWidth),true,'entrance headline must fit at '+width);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#password').fill(process.env.WORKSPACE_PASSWORD);
  await page.getByRole('button',{name:'Unlock workspace'}).click();
  await page.locator('#workspace').waitFor({state:'visible'});
  assert.equal(await page.locator('#password').inputValue(),'');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  assert.match(await page.locator('#owner-name').textContent(),/blair/i);
  await page.locator('#overview-panel').waitFor({state:'visible'});
  const navStyle=await page.locator('#navigation [data-view="inbox"]').evaluate(node=>{
    const s=getComputedStyle(node);return {font:s.fontFamily,size:s.fontSize,weight:s.fontWeight,
      radius:s.borderRadius,height:node.getBoundingClientRect().height,color:s.color,
      features:s.fontFeatureSettings,opticalSizing:s.fontOpticalSizing};
  });
  assert.ok(navStyle.font.startsWith('"Inter Variable"'));
  assert.deepEqual({size:navStyle.size,weight:navStyle.weight,radius:navStyle.radius,height:navStyle.height,color:navStyle.color},
    {size:'13px',weight:'510',radius:'8px',height:28,color:'rgb(208, 214, 224)'});
  assert.equal(navStyle.features,'normal');
  assert.equal(navStyle.opticalSizing,'auto');
  await assertAppHeading('#page-title');
  const attentionIds=await page.locator('#overview-attention [data-item-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.itemId));
  const workIds=await page.locator('#overview-work [data-item-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.itemId));
  assert.equal(workIds.some(id=>attentionIds.includes(id)),false,'overview sections must not repeat the same work');
  assert.equal(await page.locator('#attention-count').textContent(),'3');
  assert.equal(await page.locator('.overview-row .badge').first().evaluate(node=>getComputedStyle(node).padding),'0px 11px 0px 7px');
  await page.setViewportSize({width:800,height:1000});
  assert.equal(await page.locator('#new-proposal').evaluate(node=>getComputedStyle(node).fontSize),'13px');
  await noOverflow();
  await page.setViewportSize({width:1440,height:1000});
  await noOverflow();await screenshot('central-platform-overview.png');
  await page.setViewportSize({width:390,height:844});await noOverflow();
  await screenshot('central-platform-mobile.png',{fullPage:false});
  await screenshot('central-platform-mobile-full.png');
  await page.setViewportSize({width:1440,height:1000});

  // Browse all projections without changing any saved work or authority.
  for(const view of ['inbox','tasks','artifacts','outbox','peers','activity','overview']){
    await nav(view);await noOverflow();
    if(view==='artifacts')await screenshot('central-platform-artifacts.png');
    if(view==='peers')await screenshot('central-platform-assistants.png');
  }
  assert.equal(writes.length,0,'navigation must never mutate owner state');
  await page.locator('.overview-metric').filter({hasText:'Accepted tasks'}).click();
  assert.equal(await page.locator('#accepted-filter').isVisible(),true);
  assert.ok(await page.locator('#item-list article').count()>0);
  assert.equal(await page.locator('#item-list article').count(),await page.locator('#item-list article .badge.accepted').count());
  assert.equal(await page.locator('#item-list .item-icon.artifact').count(),0);
  await nav('tasks');
  await page.keyboard.press('Control+k');assert.equal(await page.locator('#search-input').evaluate(node=>node===document.activeElement),true);
  await page.locator('#search-input').fill('Map the onboarding');
  assert.equal(await article('Map the onboarding journey').count(),1);
  assert.equal(await page.locator('#item-list article').count(),1);
  await page.locator('#search-input').fill('no-fixture-has-this-title');
  assert.equal(await page.locator('#item-list article').count(),0);
  await page.locator('#search-clear').click();
  assert.ok(await page.locator('#item-list article').count()>=5);
  await page.locator('[data-layout="board"]').click();
  assert.ok(await page.locator('.board-column').count()>=2);
  await noOverflow();await screenshot('central-platform-work-board.png');
  await page.locator('[data-layout="list"]').click();
  await page.locator('#main').focus();await page.keyboard.press('n');
  await page.locator('#compose-dialog').waitFor({state:'visible'});
  await page.keyboard.press('Escape');await page.locator('#compose-dialog').waitFor({state:'hidden'});
  assert.equal(writes.length,0,'search, layout and opening a form must not submit work');

  await nav('inbox');
  await openItem('Review the research brief');
  await assertAppHeading('#review-title');
  assert.match(await page.locator('#review-content').textContent(),/SYNTHETIC/);
  assert.equal(await page.locator('#review-content *').count(),0);
  assert.match(await page.locator('#review-scope').textContent(),/does not start work/);
  await action('Accept exact proposal');
  await article('Review the research brief').locator('.badge.accepted').waitFor();
  await openItem('Explore the visual direction');await action('Reject proposal');
  await article('Explore the visual direction').locator('.badge.rejected').waitFor();
  assert.deepEqual(writes.map(write=>write.body.decision),['accept','reject']);
  for(const write of writes)assert.match(write.body.review_digest,/^[a-f0-9]{64}$/);

  // Four independently reviewed transitions retain the original fixture result.
  await openItem('Shape the launch narrative');await action('Accept exact proposal');
  await openItem('Shape the launch narrative');await action('Prepare synthetic run');
  const openRun=async()=>{await article('Shape the launch narrative').getByRole('button',{name:'Inspect synthetic run',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'visible'});};
  await openRun();assert.equal(await page.getByRole('button',{name:'Run synthetic fixture once'}).count(),0);
  await action('Approve synthetic request');
  await openRun();await action('Run synthetic fixture once');
  await openRun();assert.match(await page.locator('#review-title').textContent(),/original synthetic result/i);
  assert.match(await page.locator('#review-content').textContent(),/SYNTHETIC/);
  assert.equal(await page.locator('#review-content *').count(),0);
  assert.match(await page.locator('#review-scope').textContent(),/does not release/);
  await screenshot('central-platform-result-review.png');
  await action('Stage exact artifact');
  const resultArtifact=page.locator('#item-list article').filter({has:page.locator('.item-icon.artifact')});
  await resultArtifact.locator('.badge.draft').waitFor();
  await resultArtifact.getByRole('button',{name:'Review exact item',exact:true}).click();
  await page.locator('#review-dialog').waitFor({state:'visible'});await action('Approve & release');
  await resultArtifact.locator('.badge.released').waitFor();
  const workflowWrites=writes.filter(write=>write.path.includes('/workflows/')||write.path.endsWith('/workflow'));
  assert.deepEqual(workflowWrites.map(write=>write.path.split('/').at(-1)),['workflow','approve','run','stage']);
  assert.equal(workflowWrites[1].body.review_digest,workflowWrites[2].body.review_digest);
  assert.notEqual(workflowWrites[2].body.review_digest,workflowWrites[3].body.review_digest);

  // Composing creates an unpublished draft and renders hostile markup as text.
  await page.locator('#new-proposal').click();await page.locator('#compose-dialog').waitFor({state:'visible'});
  const inertContent='SYNTHETIC ONLY: <img src=x onerror="window.artifactExecuted=true">\nThis is fixture text, not an instruction.';
  await page.locator('#compose-form [name="title"]').fill('Inert review text');
  await page.locator('#compose-form [name="text"]').fill(inertContent);
  await page.locator('#compose-form [name="synthetic"]').check();
  await page.getByRole('button',{name:'Create for review',exact:true}).click();
  await page.locator('#compose-dialog').waitFor({state:'hidden'});
  await article('Inert review text').locator('.badge.draft').waitFor();
  await openItem('Inert review text');
  assert.equal(await page.locator('#review-content').textContent(),inertContent);
  assert.equal(await page.locator('#review-content *').count(),0);
  assert.equal(await page.evaluate(()=>window.artifactExecuted),undefined);
  await closeReview();

  // Commit a release but lose its response. A second click must not retry it.
  await nav('outbox');await openItem('Draft the launch announcement');
  let interruptedPath=null,interruptionCount=0;
  await page.route('**/api/items/*/release',async route=>{
    interruptionCount++;interruptedPath=new URL(route.request().url()).pathname;
    const actual=await route.fetch();assert.equal(actual.status(),200);
    await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic lost response after commit'})});
  });
  await page.getByRole('button',{name:'Approve & release',exact:true}).click();
  await page.locator('#review-message').filter({hasText:'could not be confirmed'}).waitFor();
  await page.getByRole('button',{name:'Approve & release',exact:true}).click();
  assert.equal(interruptionCount,1);
  assert.equal(writes.filter(write=>write.path===interruptedPath).length,1);
  await closeReview();
  await page.unroute('**/api/items/*/release');
  await page.getByRole('button',{name:'Inspect saved state after an uncertain outcome'}).click();
  await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();
  await article('Draft the launch announcement').locator('.badge.released').waitFor();

  await nav('peers');await page.getByRole('button',{name:'View public identity'}).click();
  const publicIdentity=JSON.parse(await page.locator('#review-content').textContent());
  assert.deepEqual(Object.keys(publicIdentity).sort(),['agent_id','exchange_key','owner_id','signing_key']);await closeReview();
  for(const width of [768,390]){
    await page.setViewportSize({width,height:844});
    for(const view of ['overview','tasks','artifacts','peers','activity']){await nav(view);await noOverflow();}
    await nav('tasks');await page.locator('[data-layout="board"]').click();await noOverflow();await page.locator('[data-layout="list"]').click();
  }
  await page.locator('#menu-toggle').click();
  assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'),'true');
  assert.equal(await page.locator('.sidebar').evaluate(node=>node.inert),false);
  assert.equal(await page.locator('#navigation [data-view="overview"]').evaluate(node=>node===document.activeElement),true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'),'false');
  assert.equal(await page.locator('.sidebar').evaluate(node=>node.inert),true);
  assert.equal(await page.locator('#menu-toggle').evaluate(node=>node===document.activeElement),true);
  await nav('overview');await screenshot('central-platform-mobile-after-decisions.png',{fullPage:false});
  assert.equal(await page.locator('#mobile-logout').isVisible(),true);
  await page.locator('#mobile-logout').click();await page.locator('#login-screen').waitFor({state:'visible'});
  assert.equal(await page.locator('#item-list').textContent(),'');assert.equal(await page.locator('#review-content').textContent(),'');
  assert.equal(await page.locator('#overview-stats').textContent(),'');
  await page.reload();await page.locator('#login-screen').waitFor({state:'visible'});
  assert.equal(await page.locator('#workspace').isVisible(),false);
  assert.deepEqual(errors,[]);
  assert.deepEqual(externalRequests,[],'the font and all workspace assets must stay same-origin');
  console.log('PASS workspace browser: exact local Inter Variable bytes and loaded face, measured Linear nav and heading typography, no external asset requests, seven state-backed views, search and layouts without writes, keyboard navigation, exact accept/reject, separately approved synthetic work and artifact release, committed-but-lost response without duplicate retry, public-only identity, desktop/tablet/mobile layouts and session cleanup.');
} catch(error) {
  if(screenshots)await page.screenshot({path:path.join(screenshots,'central-platform-failure.png'),fullPage:true}).catch(()=>{});
  throw error;
} finally { await browser.close(); }
