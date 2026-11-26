// Record docs/demo.gif from a running local demo. Fictional content only.
// Usage: python -B -m workspace_ui.demo --port 8775 &   then
//        node tools/demo/record.mjs http://127.0.0.1:8775 "Fictional browser test password" <frame dir>
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';
const require=createRequire(import.meta.url);let chromium;
try{({chromium}=require('playwright'));}catch{({chromium}=createRequire('/opt/')('playwright'));}
const [url,password,dir]=process.argv.slice(2);
if(!url||!password||!dir)throw new Error('Usage: record.mjs <url> <password> <frame dir>');
await mkdir(dir,{recursive:true});
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1280,height:800},deviceScaleFactor:1});
let n=0;const shot=async(hold=1)=>{for(let i=0;i<hold;i++)await page.screenshot({path:path.join(dir,`f${String(n++).padStart(3,'0')}.png`)});};
const view=async v=>{await page.locator(`#navigation [data-view="${v}"]`).click();await page.waitForFunction(value=>document.querySelector(`#navigation [data-view="${value}"]`)?.getAttribute('aria-current')==='page',v);await page.waitForTimeout(400);};
try{
  await page.goto(url);await shot(3);
  await page.locator('#password').pressSequentially(password,{delay:15});await shot(1);
  await page.getByRole('button',{name:/Unlock workspace/}).click();await page.locator('#workspace').waitFor({state:'visible'});await page.waitForTimeout(600);await shot(4);
  for(const v of ['inbox','tasks','artifacts','peers','activity']){await view(v);await shot(3);}
  await view('overview');await shot(3);
}finally{await browser.close();}
console.log(`${n} frames`);
