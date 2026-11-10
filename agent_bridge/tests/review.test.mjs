import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { DatabaseSync } from 'node:sqlite';
import { fixture, draft, serverPath } from './helpers.mjs';

test('independent review: rejected initialization cannot unlock tool dispatch', async () => {
  const f = fixture('review');
  const child = spawn(process.execPath, [serverPath], { env: f.env, stdio: ['pipe', 'pipe', 'pipe'] });
  let output = '';
  child.stdout.on('data', data => { output += data; });
  try {
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} }) + '\n');
    for (let i = 0; i < 100 && !output && child.exitCode === null; i++) await delay(10);
    if (child.exitCode === null) {
      child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
      child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'create_task_draft', arguments: draft } }) + '\n');
      await delay(150);
    }
    const db = new DatabaseSync(f.launch.storePath);
    try { assert.equal(db.prepare('SELECT count(*) AS n FROM drafts').get().n, 0, 'Malformed initialization must not enable a later write'); }
    finally { db.close(); }
  } finally {
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill(); await exited; }
    f.cleanup();
  }
});
