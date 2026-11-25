// Browser check for the mission card MCP App (run locally: node mission_cards/tests/card_app_check.mjs).
// Simulates the host's ui/notifications/tool-result message and inspects the DOM.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import assert from 'node:assert/strict';

const browser = await chromium.launch();
const page = await browser.newPage();
const sent = [];
await page.exposeFunction('__record', (m) => sent.push(m));
await page.addInitScript(() => { const orig = window.postMessage.bind(window);
  window.postMessage = (m, o) => { window.__record(m); return orig(m, o); }; });
await page.goto(new URL('../card_app.html', import.meta.url).href);
await page.waitForFunction(() => typeof window.__render === 'function');
for (let i = 0; i < 50 && !sent.length; i++) await page.waitForTimeout(20);
assert.equal(sent[0]?.method, 'ui/initialize');
await page.evaluate(() => window.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: {
  structuredContent: { mission_id: 'offsite-1', card_digest: 'ab'.repeat(32), state: 'drafting',
    waiting_on_you: ['Review and acknowledge the mission card'],
    snapshot: { mission_id: 'offsite-1', goal: 'Pick a venue', owners: { edem: 'Edem', sam: 'Sam' },
      constraints: [{ id: 'c1', owner: 'sam', kind: 'must', text: '<img src=x onerror="window.pwned=1"> Step-free access' }] } } } }, '*'));
await page.waitForSelector('#card:not([hidden])');
assert.equal(await page.textContent('#goal'), 'Pick a venue');
assert.match(await page.textContent('#owners'), /From Sam.*c1\. Must: <img src=x onerror="window.pwned=1"> Step-free access/s);
assert.equal(await page.locator('#owners img').count(), 0);
assert.equal(await page.evaluate(() => window.pwned), undefined);
assert.match(await page.textContent('#waiting'), /Review and acknowledge/);
await page.screenshot({ path: process.argv[2] || '/dev/null' });
await browser.close();
console.log('mission card app: 6/6 browser checks passed');
