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
  const target=page.locator(`#navigation [data-view="${view}"]`);
  if(!await target.isVisible())await page.locator('#everything-toggle').click();
  await target.click();
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
const checkContrast=async()=>{
  const failures=await page.evaluate(()=>{
    const rgba=value=>{const parts=value.match(/[\d.]+/g)?.map(Number)||[];return [parts[0]||0,parts[1]||0,parts[2]||0,parts.length>3?parts[3]:1];};
    const mix=(fg,bg)=>fg.slice(0,3).map((v,i)=>v*fg[3]+bg[i]*(1-fg[3]));
    const background=node=>{if(!node)return [255,255,255];const value=rgba(getComputedStyle(node).backgroundColor);return mix(value,background(node.parentElement));};
    const luminance=rgb=>rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
    const failures=[];
    for(const node of document.querySelectorAll('.nav-section,.section-link,.network-link,.peer-fingerprint,.metric-note,.item-meta,.task-ref,.board-empty,.group-count,.review-details dt,.commitment-details summary,input[placeholder],textarea[placeholder]')){
      if(!node.getClientRects().length)continue;
      const placeholder=node.matches('input,textarea'),style=getComputedStyle(node,placeholder?'::placeholder':null);
      const bg=background(node),fg=mix(rgba(style.color),bg),a=luminance(fg),b=luminance(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      if(ratio<4.5)failures.push({element:node.id||node.className,placeholder,ratio,foreground:style.color,background:bg});
    }
    return failures;
  });
  assert.deepEqual(failures,[],'ordinary quiet and placeholder text must meet 4.5:1 on actual surfaces');
};
const closeReview=async()=>{await page.getByRole('button',{name:'Close review',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const openItem=async title=>{await article(title).getByRole('button',{name:/^(Review exact item|Inspect)$/}).click();await page.locator('#review-dialog').waitFor({state:'visible'});};
const action=async name=>{await page.getByRole('button',{name,exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});};
const HEADINGS={page:{size:'36px',lineHeight:'42px',tracking:'-1.26px'},dialog:{size:'22px',lineHeight:'28px',tracking:'-0.33px'}};
const assertAppHeading=async(selector,kind='page')=>{
  const style=await page.locator(selector).evaluate(node=>{
    const s=getComputedStyle(node);return {size:s.fontSize,weight:s.fontWeight,lineHeight:s.lineHeight,
      tracking:s.letterSpacing,features:s.fontFeatureSettings,opticalSizing:s.fontOpticalSizing};
  });
  assert.deepEqual(style,{size:HEADINGS[kind].size,weight:'800',lineHeight:HEADINGS[kind].lineHeight,tracking:HEADINGS[kind].tracking,
    features:'"cv01", "ss03"',opticalSizing:'auto'});
};

try {
  const fontResponsePromise=page.waitForResponse(response=>new URL(response.url()).pathname==='/PlusJakartaSansVariable.woff2');
  await page.goto(url.origin);
  await checkContrast();
  const fontResponse=await fontResponsePromise;
  assert.equal(fontResponse.status(),200,'the actual variable font must load, not a system fallback');
  assert.equal(fontResponse.headers()['content-type'],'font/woff2');
  const fontBytes=await fontResponse.body();
  assert.equal(fontBytes.subarray(0,4).toString(),'wOF2');
  assert.equal(createHash('sha256').update(fontBytes).digest('hex'),
    '1262bff0591c36094d058ab102b84ce34eb1e547e8ff00557bf8d55449e58e40');
  await page.evaluate(()=>document.fonts.ready.then(()=>undefined));
  const fontEvidence=await page.evaluate(()=>({
    family:getComputedStyle(document.body).fontFamily,
    ready:document.fonts.check('510 13px "Plus Jakarta Sans"'),
    loaded:[...document.fonts].some(face=>face.family.replaceAll('"','').replaceAll("'",'')==='Plus Jakarta Sans'&&face.status==='loaded'),
  }));
  assert.ok(fontEvidence.family.startsWith('"Plus Jakarta Sans"'),fontEvidence.family);
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
  assert.equal(await page.locator('#everything-list').isVisible(),false,'Everything starts folded away');
  assert.deepEqual(await page.locator('.nav-primary .nav-link').evaluateAll(nodes=>nodes.map(node=>node.textContent.replace(/\d+$/,'').trim())),['Home','Recents','Assistants','Money']);
  const navStyle=await page.locator('#navigation [data-view="activity"]').evaluate(node=>{
    const s=getComputedStyle(node);return {font:s.fontFamily,size:s.fontSize,weight:s.fontWeight,
      radius:s.borderRadius,height:node.getBoundingClientRect().height,color:s.color,
      features:s.fontFeatureSettings,opticalSizing:s.fontOpticalSizing};
  });
  assert.ok(navStyle.font.startsWith('"Plus Jakarta Sans"'));
  assert.deepEqual({size:navStyle.size,weight:navStyle.weight,radius:navStyle.radius,height:navStyle.height,color:navStyle.color},
    {size:'13.5px',weight:'600',radius:'999px',height:40,color:'rgb(62, 59, 53)'});
  assert.equal(navStyle.features,'normal');
  assert.equal(navStyle.opticalSizing,'auto');
  await assertAppHeading('#page-title');
  await page.setViewportSize({width:1366,height:768});
  await page.locator('#logout').scrollIntoViewIfNeeded();
  const logoutBox=await page.locator('#logout').boundingBox();
  assert.ok(logoutBox&&logoutBox.y+logoutBox.height<=768,'sign out must stay reachable on a short desktop screen');
  await page.setViewportSize({width:1440,height:1000});
  // Home is calm: the paragraph, one card at a time, the Ask bar and one Done today line.
  assert.equal(await page.locator('#home-count').textContent(),'3');
  assert.equal(await page.locator('#home-cards .home-card').count(),3,'three decisions wait, shown one at a time');
  assert.match(await page.locator('#done-line').textContent(),/^Done today: “[^”]+”, “[^”]+” and 1 more\. See all$/);
  assert.equal(await page.locator('#done-line .person-dot').count(),1,'the done line keeps the owner beside the bot');
  // Money and keys moved to their own place and to the Inspect panel.
  await nav('money');
  assert.match(await page.locator('#money-panel').textContent(),/No budgets yet/);
  assert.match(await page.locator('#mission-rows').textContent(),/No missions yet/);
  await nav('peers');
  await page.locator('.peer-row').filter({hasText:'Orbit'}).getByRole('button',{name:'Open',exact:true}).click();
  await page.locator('#inspect').waitFor({state:'visible'});
  assert.equal(await page.locator('#inspect-title').textContent(),'Orbit');
  assert.match(await page.locator('#inspect-body').textContent(),/Fingerprint[0-9a-f]{64}/);
  assert.equal(await page.locator('#inspect-title').evaluate(node=>node===document.activeElement),true,'opening the panel moves focus to its heading');
  await page.locator('#inspect-pin').click();
  assert.equal(await page.locator('#inspect-pin').getAttribute('aria-pressed'),'true');
  await nav('money');
  assert.equal(await page.locator('#inspect').isVisible(),true,'a pinned panel stays open between places');
  const panelBox=await page.locator('#inspect').boundingBox(),mainBox=await page.locator('#main').boundingBox();
  assert.ok(panelBox.x>=mainBox.x+mainBox.width,'on a wide screen the pinned panel sits beside the page, not over it');
  await page.locator('#inspect-pin').click();await nav('activity');
  assert.equal(await page.locator('#inspect').isVisible(),false,'an unpinned panel closes when you move');
  await page.locator('#everything-toggle').click();
  assert.equal(await page.locator('#everything-toggle').getAttribute('aria-expanded'),'true');
  await page.locator('[data-panel="identity"]').click();
  assert.equal(await page.locator('#inspect-title').textContent(),'Your identity');
  await page.keyboard.press('Escape');await page.locator('#inspect').waitFor({state:'hidden'});
  assert.equal(writes.length,0,'inspecting never writes');
  await nav('overview');
  await page.locator('#home-ask-input').fill('Plan the team offsite');
  await page.locator('#home-ask-input').press('Enter');
  await page.locator('#compose-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#compose-form [name="title"]').inputValue(),'Plan the team offsite');
  assert.equal(await page.locator('#home-ask-input').inputValue(),'');
  await page.keyboard.press('Escape');await page.locator('#compose-dialog').waitFor({state:'hidden'});
  assert.equal(writes.length,0,'the Ask bar only drafts: nothing is sent until the owner reviews it');
  await page.setViewportSize({width:800,height:1000});
  assert.equal(await page.locator('#new-proposal').evaluate(node=>getComputedStyle(node).fontSize),'13px');
  await noOverflow();
  await page.setViewportSize({width:1440,height:1000});
  await noOverflow();await screenshot('central-platform-overview.png');
  await page.setViewportSize({width:390,height:844});await noOverflow();
  assert.equal(await page.locator('.glass-bar').isVisible(),true,'the phone keeps Home, Recents and + in reach');
  assert.equal(await page.locator('#menu-initials').textContent(),'BL');
  await screenshot('central-platform-mobile.png',{fullPage:false});
  await screenshot('central-platform-mobile-full.png');
  await page.setViewportSize({width:1440,height:1000});

  // Browse all projections without changing any saved work or authority.
  for(const view of ['inbox','tasks','artifacts','outbox','peers','transfers','activity','receipts','money','overview']){
    await nav(view);await noOverflow();await checkContrast();
    const route=await page.evaluate(()=>location.hash);
    await page.locator('.skip-link').focus();await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>location.hash),route,'skip link must not change the route');
    assert.equal(await page.locator('#main').evaluate(node=>document.activeElement===node),true);
    if(view==='artifacts')await screenshot('central-platform-artifacts.png');
    if(view==='peers')await screenshot('central-platform-assistants.png');
    if(['tasks','inbox','artifacts','outbox'].includes(view)){
      assert.equal(await page.locator('#navigation [data-view="activity"]').getAttribute('class'),'nav-link active','work lives in Recents');
      assert.equal(await page.locator('#section-filters [data-goto]').count(),5);
      assert.equal(await page.locator(`#section-filters [data-goto="${view}"]`).getAttribute('aria-pressed'),'true');
      assert.equal(await page.locator('#section-tabs [data-goto="tasks"]').getAttribute('aria-current'),'page');
      assert.equal(await page.locator('#item-list .badge').first().evaluate(node=>getComputedStyle(node).padding),'0px 11px 0px 7px');
    }
    if(view==='activity'){
      assert.deepEqual(await page.locator('#section-tabs [data-goto]').allTextContents(),['Activity','Receipts','All work']);
      assert.equal(await page.locator('#page-title').textContent(),'Recents');
    }
    if(view==='receipts')assert.ok(await page.locator('#item-list .receipt-row').count()>0,'signed decisions appear as receipts');
  }
  assert.equal(writes.length,0,'navigation must never mutate owner state');
  await page.locator('#done-line .done-all').click();
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
  await checkContrast();
  await noOverflow();await screenshot('central-platform-work-board.png');
  await page.locator('[data-layout="list"]').click();
  await page.locator('#main').focus();await page.keyboard.press('n');
  await page.locator('#compose-dialog').waitFor({state:'visible'});
  assert.equal(await page.getByRole('dialog',{name:'Prepare a proposal',exact:true}).count(),1);await checkContrast();
  await page.keyboard.press('Escape');await page.locator('#compose-dialog').waitFor({state:'hidden'});
  assert.equal(writes.length,0,'search, layout and opening a form must not submit work');

  await nav('inbox');
  await openItem('Review the research brief');
  assert.equal(await page.getByRole('dialog',{name:'Review the research brief',exact:true}).count(),1);await checkContrast();
  await assertAppHeading('#review-title','dialog');
  assert.match(await page.locator('#review-content').textContent(),/SYNTHETIC/);
  assert.equal(await page.locator('#review-content *').count(),0);
  assert.match(await page.locator('#review-scope').textContent(),/does not start work/);
  // Decide: Spends, Shares and Keeps sit above the exact content. No money, so no hold.
  assert.match(await page.locator('#review-decide .decide-question').textContent(),/^Agree to “Review the research brief” for \S+\?$/);
  assert.deepEqual(await page.locator('#review-decide dt').allTextContents(),['Spends','Shares','Keeps']);
  assert.match(await page.locator('#review-decide dd').first().textContent(),/^Nothing\./);
  assert.equal(await page.locator('#review-decide .hold-control').count(),0,'no money, no hold');
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

  // Team missions: your assistant leads, and every part is a proposal reviewed on its own.
  await nav('team');
  assert.match(await page.locator('#team-view').textContent(),/No team missions yet\./);
  assert.equal(await page.locator('#navigation [data-view="money"]').getAttribute('class'),'nav-link active','team missions live in Money');
  const beforeTeam=writes.length;
  await page.locator('#team-view').getByRole('button',{name:'Start a team mission',exact:true}).click();
  await page.locator('#team-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#team-parts .team-part-row').count(),2);
  await page.locator('#team-form [name="mission"]').fill('Supper club app');
  const teamRows=page.locator('#team-parts .team-part-row');
  await teamRows.nth(0).locator('[name="part_title"]').fill('Card deposits');
  await teamRows.nth(0).locator('[name="part_text"]').fill('SYNTHETIC ONLY: Take a card deposit when a guest books.');
  await teamRows.nth(1).locator('[name="part_title"]').fill('Calendar sync');
  await teamRows.nth(1).locator('[name="part_text"]').fill('SYNTHETIC ONLY: Keep the supper club calendar in step.');
  await checkContrast();await screenshot('central-platform-team-new.png');
  await page.getByRole('button',{name:'Create the parts for review',exact:true}).click();
  await page.locator('#team-message').filter({hasText:'fictional'}).waitFor();
  assert.equal(writes.length,beforeTeam,'nothing is created until the content is confirmed as fictional');
  await page.locator('#team-form [name="team_synthetic"]').check();
  await page.getByRole('button',{name:'Create the parts for review',exact:true}).click();
  await page.locator('#team-dialog').waitFor({state:'hidden'});
  const teamWrites=writes.slice(beforeTeam);
  assert.deepEqual(teamWrites.map(write=>write.path),['/api/proposals','/api/proposals']);
  assert.equal(teamWrites[0].body.context,teamWrites[1].body.context,'every part shares one mission context');
  assert.notEqual(teamWrites[0].body.peer_id,teamWrites[1].body.peer_id,'each part goes to a different assistant');
  assert.deepEqual(teamWrites.map(write=>write.body.title),['Supper club app: Card deposits','Supper club app: Calendar sync']);
  await page.locator('#team-view .team-part').nth(1).waitFor();
  assert.equal(await page.locator('#team-view .team-title').textContent(),'Supper club app');
  assert.equal(await page.locator('#team-view .team-line').textContent(),'0 of 2 parts are done. 2 parts are ready for you to send.');
  assert.deepEqual(await page.locator('#team-view .team-part').evaluateAll(nodes=>nodes.map(node=>node.dataset.step)),['Plan','Plan']);
  assert.equal(await page.locator('#team-view .team-seg').count(),2);
  await noOverflow();await checkContrast();await screenshot('central-platform-team.png');
  await page.locator('#team-view .team-part').first().getByRole('button',{name:'Details',exact:true}).click();
  await page.locator('#inspect').waitFor({state:'visible'});
  assert.equal(await page.locator('#inspect-title').textContent(),'Card deposits');
  assert.match(await page.locator('#inspect-sub').textContent(),/^Part of Supper club app/);
  await screenshot('central-platform-team-part.png');
  await page.keyboard.press('Escape');await page.locator('#inspect').waitFor({state:'hidden'});
  await page.locator('[data-team-tab="people"]').click();
  assert.equal(await page.locator('#team-view .team-person').count(),2);
  await page.locator('[data-team-tab="parts"]').click();
  await page.setViewportSize({width:390,height:844});await noOverflow();
  await screenshot('central-platform-team-mobile.png');
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#team-view .team-part').first().getByRole('button',{name:'Review and send',exact:true}).click();
  await page.locator('#review-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#review-title').textContent(),'Supper club app: Card deposits');
  await closeReview();
  await nav('money');
  assert.match(await page.locator('#mission-rows .team-row').textContent(),/Supper club app/);
  assert.equal(writes.length,beforeTeam+2,'browsing a team mission never writes');

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

  await nav('peers');await page.locator('#add-peer').click();
  assert.equal(await page.getByRole('dialog',{name:'Enrol a trusted peer',exact:true}).count(),1);await checkContrast();
  await page.keyboard.press('Escape');await page.locator('#peer-dialog').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'View public identity'}).click();
  assert.equal(await page.locator('#review-decide').isVisible(),false,'showing an identity is not a decision');
  const publicIdentity=JSON.parse(await page.locator('#review-content').textContent());
  assert.deepEqual(Object.keys(publicIdentity).sort(),['agent_id','exchange_key','owner_id','signing_key']);await closeReview();
  await nav('outbox');
  await page.locator('#new-proposal').click();
  await page.locator('#proposal-kind').selectOption('mission');
  await page.getByLabel('Title',{exact:true}).fill('Fictional studio brief');
  await page.getByLabel('Deliverable',{exact:true}).fill('One note');
  await page.getByLabel('Expected value',{exact:true}).fill('studio');
  await page.getByLabel('Exact content',{exact:true}).fill('Prepare one fictional studio note.');
  await page.locator('input[name="synthetic"]').check();
  await page.getByRole('button',{name:'Create for review',exact:true}).click();
  await article('Fictional studio brief').getByRole('button',{name:'Review Fictional studio brief',exact:true}).click();
  await page.getByRole('dialog',{name:'Fictional studio brief',exact:true}).waitFor();
  assert.match(await page.locator('#review-decide .decide-question').textContent(),/^Send “Fictional studio brief” to /);
  assert.match(await page.locator('#review-decide dd').first().textContent(),/^Up to .+ from this mission's limit if \S+ agrees\. Simulated, no real payment\.$/,'a mission shows its signed limit');
  const offerText = await page.locator('#review-content').textContent();
  assert.match(offerText,/Fictional studio brief/);
  assert.match(offerText,/Prepare one fictional studio note/);
  assert.equal(writes.at(-1).path,'/api/mission-offers');
  assert.equal(writes.at(-1).body.permit_fixture,false);
  await closeReview();
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
  // In the evening, with nothing left to decide, a story about the day replaces the stack.
  const pendingLeft=Number(await page.locator('#home-count').textContent());
  assert.equal(await page.locator('#home-count').isVisible(),false,'nothing waiting means no count');
  if(pendingLeft===0){
    const evening=new Date();evening.setHours(19,30,0,0);if(evening<Date.now())evening.setTime(Date.now()+60000);await page.clock.setFixedTime(evening);
    await nav('inbox');await nav('overview');
    assert.match(await page.locator('#home-paragraph').textContent(),/^Evening Blair\. \d+ pieces? of work (was|were) agreed today/);
    assert.equal(await page.locator('#home-cards .story-card').count(),1);
    assert.equal(await page.locator('#home-cards .story-card .person-dot').count(),1);
    const before=writes.length;
    await page.locator('#home-cards .home-good').click();
    assert.equal(writes.length,before,'reacting to a story never writes or changes permission');
    await page.locator('#home-cards .home-later').click();
    await page.locator('#review-dialog').waitFor({state:'visible'});
    assert.match(await page.locator('#notice').textContent(),/without your yes/);
    assert.equal(writes.length,before,'reopening what was agreed never writes');
    await page.keyboard.press('Escape');await page.locator('#review-dialog').waitFor({state:'hidden'});
  }else assert.fail('the decisions above should leave nothing pending');
  assert.equal(await page.locator('#mobile-logout').isVisible(),true);
  await page.locator('#mobile-logout').click();await page.locator('#login-screen').waitFor({state:'visible'});
  assert.equal(await page.locator('#item-list').textContent(),'');assert.equal(await page.locator('#review-content').textContent(),'');
  for(const id of ['done-line','money-panel','mission-rows','home-cards','home-paragraph','section-tabs','section-filters','inspect-body'])assert.equal(await page.locator('#'+id).textContent(),'','clear home data on sign-out: '+id);
  for(const id of ['review-title','review-eyebrow','review-state','review-scope','review-message','review-details','review-commitments','owner-name','agent-name','owner-avatar','notice','connection-status'])assert.equal(await page.locator('#'+id).textContent(),'','clear hidden owner data: '+id);
  await page.reload();await page.locator('#login-screen').waitFor({state:'visible'});
  assert.equal(await page.locator('#workspace').isVisible(),false);
  assert.deepEqual(errors,[]);
  assert.deepEqual(externalRequests,[],'the font and all workspace assets must stay same-origin');
  console.log('PASS workspace browser: exact local Plus Jakarta Sans bytes and loaded face, measured Linear nav and heading typography, no external asset requests, every state-backed view, search and layouts without writes, keyboard navigation, exact accept/reject, separately approved synthetic work and artifact release, committed-but-lost response without duplicate retry, public-only identity, desktop/tablet/mobile layouts and session cleanup.');
} catch(error) {
  if(screenshots)await page.screenshot({path:path.join(screenshots,'central-platform-failure.png'),fullPage:true}).catch(()=>{});
  throw error;
} finally { await browser.close(); }
