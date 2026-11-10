// Real Chromium, mocked HTTP boundary. Server/TLS behaviour is tested in Python.
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const root=fileURLToPath(new URL('../',import.meta.url));
const server=createServer(async(req,res)=>{const name=req.url==='/'?'index.html':req.url.slice(1);if(!['index.html','style.css','app.mjs','model.mjs','transfers.mjs'].includes(name)){res.writeHead(404);res.end();return;}res.writeHead(200,{'Content-Type':name.endsWith('.mjs')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});res.end(await readFile(path.join(root,name)));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const a='a'.repeat(64),b='b'.repeat(64),packet='proposal-'+b,auth='FICTIONAL-TRANSFER-SESSION';
const connection={id:'peer',label:'Fictional mailbox',peer_fingerprint:b,destination:'https://mailbox.invalid/v1/quarantine'};
const outbox={message_id:packet,packet_digest:a,peer:b,state:'queued',attempts:0,expires:Date.now()/1000+3600,receipt_id:null,receipt_digest:null,transport_receipt_only:true,owner_acceptance:'not_established',work_execution:'not_established'};
const fixture={identity:{owner_id:'fictional-owner',agent_id:'Atlas',fingerprint:a},peers:[{peer_id:b,owner_id:'fictional-peer',agent_id:'Mira',fingerprint:b,state:'active'}],items:[],history:[],transfers:{enabled:true,connections:[connection],outbox:[outbox],receipts:[],quarantine:[a],dispatch:null,authorises_execution:false,automatic_delivery:false}};
let writes=[],lost=true,refreshFails=false;
const attempts=[];
function reviewed(kind,identifier){return {connection,kind,identifier,message_id:packet,packet_kind:'proposal',packet_digest:a,review_digest:attempts.length?b:a,expires:outbox.expires,outbox:kind==='outbox'?outbox:null,attempts:kind==='outbox'?attempts:[],allowed_actions:kind==='quarantine'?['import']:outbox.attempts?['retry']:['send'],authorises_execution:false,owner_acceptance:'not_established',authenticated:kind!=='quarantine'};}
await page.route('**/api/**',async route=>{
 const req=route.request(),url=new URL(req.url()),method=req.method();const reply=(v,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(v)});
 if(url.pathname==='/api/session'&&method==='POST')return reply({token:auth,identity:fixture.identity});
 assert.equal(req.headers().authorization,'Bearer '+auth);
 if(url.pathname==='/api/session'&&method==='DELETE')return reply({signed_out:true});
 if(url.pathname==='/api/state'){if(refreshFails)return reply({error:'offline'},503);return reply(fixture);}
 const match=url.pathname.match(/^\/api\/transfers\/peer\/(outbox|quarantine)\/([^/]+)(?:\/(send|import))?$/);
 if(match){if(method==='GET')return reply(reviewed(match[1],match[2]));
  writes.push({path:url.pathname,body:req.postDataJSON()});
  if(match[3]==='import')return reply({duplicate:false,authorises_execution:false});
  assert.deepEqual(req.postDataJSON(),{review_digest:outbox.attempts?b:a,retry:outbox.attempts>0});
  outbox.attempts++;outbox.state='uncertain';attempts.push({sequence:outbox.attempts,message_id:packet,packet_digest:a,file_digest:b,recipient:b,destination:connection.destination,kind:'proposal',state:'uncertain'});
  if(lost){lost=false;refreshFails=true;return route.abort();}
  fixture.transfers.dispatch={message_id:packet,connection_id:'peer',state:'in_flight',transport_acknowledged:false,delivery:'uncertain',authorises_execution:false};return reply({dispatch_started:true,delivery:'uncertain'});
 }
 return reply({error:'unexpected'},400);
});
try{
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.locator('#password').fill('fictional-password');await page.getByRole('button',{name:'Unlock workspace'}).click();await page.locator('#workspace').waitFor({state:'visible'});
 await page.locator('[data-view=transfers]').click();assert.equal(writes.length,0);
 await page.getByRole('button',{name:'Inspect via Fictional mailbox'}).click();await page.locator('#review-dialog').waitFor({state:'visible'});
 await page.getByRole('button',{name:'Send original packet once',exact:true}).click();assert.equal(writes.length,0);assert.match(await page.locator('#review-message').textContent(),/Confirm/);
 await page.getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('button',{name:'Inspect via Fictional mailbox'}).click();assert.equal(await page.locator('#transfer-confirm').isChecked(),false);
 await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Send original packet once',exact:true}).click();await page.locator('#review-message').filter({hasText:'could not be confirmed'}).waitFor();
 await page.getByRole('button',{name:'Send original packet once',exact:true}).click();assert.equal(writes.length,1);
 await page.getByRole('button',{name:'Close review'}).click();await page.locator('#refresh').click();assert.equal(writes.length,1);await page.locator('#notice').filter({hasText:'could not be confirmed'}).waitFor();
 refreshFails=false;await page.locator('#refresh').click();await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();
 await page.getByRole('button',{name:'Inspect via Fictional mailbox'}).click();await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Send one explicit retry',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});assert.equal(writes.length,2);
 await page.getByRole('button',{name:'Inspect via Fictional mailbox'}).click();assert.equal(await page.getByRole('button',{name:'Send one explicit retry',exact:true}).count(),0);assert.match(await page.locator('#review-message').textContent(),/in flight/);await page.getByRole('button',{name:'Close',exact:true}).click();
 fixture.transfers.dispatch.state='finished';fixture.transfers.dispatch.transport_acknowledged=true;await page.locator('#refresh').click();await page.locator('#notice').filter({hasText:'Saved state inspected'}).waitFor();assert.match(await page.locator('#item-list').textContent(),/untrusted quarantine acknowledgement/);
 const selects=page.locator('.transfer-import select');await selects.nth(0).selectOption('peer');await page.getByRole('button',{name:'Inspect selected import'}).click();await page.locator('#transfer-confirm').check();await page.getByRole('button',{name:'Import selected packet',exact:true}).click();await page.locator('#review-dialog').waitFor({state:'hidden'});assert.equal(writes.length,3);assert.ok(writes[2].path.endsWith('/import'));
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(process.env.PILOT_SCREENSHOT_DIR){await mkdir(process.env.PILOT_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-mobile.png'),fullPage:true});}
 await page.getByRole('button',{name:'Inspect via Fictional mailbox'}).click();await page.locator('.commitment-details summary').click();assert.match(await page.locator('#review-commitments').textContent(),/Attempt 1/);assert.match(await page.locator('#review-commitments').textContent(),/Attempt 2/);
 if(process.env.PILOT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-review-mobile.png'),fullPage:true});
 await page.keyboard.press('Escape');await page.locator('#review-dialog').waitFor({state:'hidden'});assert.equal(writes.length,3);
 await page.setViewportSize({width:1440,height:1000});if(process.env.PILOT_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.PILOT_SCREENSHOT_DIR,'transfers-desktop.png'),fullPage:true});
 await page.locator('#logout').click();await page.locator('#login-screen').waitFor({state:'visible'});assert.equal(await page.locator('#item-list').textContent(),'');assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(errors,[]);
 console.log('PASS transfer Chromium: exact confirmation, no automatic send, lost response fence, failed refresh, explicit retry, in-flight block, selected import, immutable history, mobile layout, dismissal, logout.');
}finally{await browser.close();await new Promise(r=>server.close(r));}
