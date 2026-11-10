import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { BoundedStdioTransport } from '../src/transport.ts';
import { strictJson } from '../src/json.ts';
import { fixture, draft, serverPath } from './helpers.mjs';

const initialise = { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'not-identity', version: '1.0' } } };
const initResponse = { jsonrpc: '2.0', id: 1, result: { protocolVersion: '2025-11-25', capabilities: { tools: {} }, serverInfo: { name: 'fixture', version: '1' } } };
const ready = { jsonrpc: '2.0', method: 'notifications/initialized' };
const frame = value => JSON.stringify(value) + '\n';
async function rawTransport() {
  const input = new PassThrough(), output = new PassThrough(), received = []; let closed = false;
  const transport = new BoundedStdioTransport(input, output);
  transport.onmessage = message => received.push(message);
  transport.onclose = () => { closed = true; };
  await transport.start();
  return { input, output, received, transport, get closed() { return closed; } };
}
async function admit(t) { t.input.write(frame(initialise)); await t.transport.send(initResponse); t.input.write(frame(ready)); }
async function clientFor(f) {
  const client = new Client({ name: 'fictional-conformance-host', version: '1' }, { capabilities: {} });
  const transport = new StdioClientTransport({ command: process.execPath, args: [serverPath], env: f.env, stderr: 'pipe' });
  let stderr = ''; transport.stderr?.on('data', chunk => { stderr += chunk; });
  await client.connect(transport);
  return { client, transport, stderr: () => stderr };
}

test('strict JSON rejects duplicates, escaped duplicate keys, invalid UTF scalar, depth and numeric overflow', () => {
  for (const text of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"s":"\\ud800"}', '1e999', '[1,]', '{"a":1,}', 'true false', '\u00a0null', '['.repeat(18) + '0' + ']'.repeat(18), '[' + '0,'.repeat(1024) + '0]']) assert.throws(() => strictJson(text));
  assert.deepEqual(JSON.parse(JSON.stringify(strictJson('{"a":[1,true,null,"🙂"],"__proto__":{"test":1}}'))), { a: [1, true, null, '🙂'], ['__proto__']: { test: 1 } });
  assert.equal({}.test, undefined);
});
test('fragmented UTF-8 and multiple MCP frames conform to LF stdio', async () => {
  const t = await rawTransport();
  t.input.write(frame(initialise)); await t.transport.send(initResponse);
  const bytes = Buffer.from(frame(ready) + frame({ jsonrpc: '2.0', id: '🙂', method: 'ping' }));
  for (const byte of bytes) t.input.write(Buffer.from([byte]));
  assert.equal(t.received.length, 3); assert.equal(t.closed, false); await t.transport.close();
});
for (const [label, raw] of [
  ['oversized frame', 'x'.repeat(16385)], ['duplicate keys', '{"jsonrpc":"2.0","id":1,"id":2,"method":"initialize"}\n'],
  ['invalid UTF-8', Buffer.from([0xff, 10])], ['batch', '[{"jsonrpc":"2.0","id":1,"method":"initialize"}]\n'],
  ['unsafe RPC id', frame({ ...initialise, id: 2 ** 54 })], ['early tool', frame({ jsonrpc: '2.0', id: 2, method: 'tools/list' })],
]) test(`transport closes without forwarding ${label}`, async () => {
  const t = await rawTransport(); t.input.write(raw); assert.equal(t.closed, true); assert.equal(t.received.length, 0);
});
test('RPC id replay and reinitialisation close; numeric and textual ids are distinct', async () => {
  const t = await rawTransport();
  await admit(t); t.input.write(frame({ jsonrpc: '2.0', id: '1', method: 'ping' }));
  assert.equal(t.received.length, 3); assert.equal(t.closed, false);
  t.input.write(frame({ jsonrpc: '2.0', id: 1, method: 'tools/list' })); assert.equal(t.closed, true);
  const second = await rawTransport(); await admit(second); second.input.write(frame({ ...initialise, id: 3 })); assert.equal(second.closed, true);
});
test('RPC request budget is bounded; SDK errors cannot echo hostile values', async () => {
  const t = await rawTransport(); await admit(t);
  for (let id = 2; id <= 257; id++) t.input.write(frame({ jsonrpc: '2.0', id, method: 'ping' }));
  assert.equal(t.closed, true); assert.equal(t.received.length, 257); // 256 requests and initialized.
  const second = await rawTransport(); let output = ''; second.output.on('data', data => { output += data; });
  await second.transport.send({ jsonrpc: '2.0', id: 1, error: { code: -32602, message: 'secret-canary', data: 'secret-canary' } });
  assert.equal(output.includes('secret-canary'), false); assert.ok(output.includes('Request rejected')); await second.transport.close();
});
test('official MCP client lists exact tools, rejects hostile args, redacts errors and survives reconnect', async () => {
  const f = fixture(); let c;
  try {
    c = await clientFor(f);
    const listed = await c.client.listTools(); assert.deepEqual(listed.tools.map(t => t.name), ['create_task_draft', 'task_draft_status']);
    const first = await c.client.callTool({ name: 'create_task_draft', arguments: draft, _meta: { ownerId: 'attacker', conversationId: 'attacker' } });
    assert.equal(first.isError, undefined);
    const value = first.structuredContent;
    const bad = await c.client.callTool({ name: 'create_task_draft', arguments: { ...draft, ownerId: 'secret-canary' } });
    assert.equal(bad.isError, true); assert.equal(JSON.stringify(bad).includes('secret-canary'), false);
    const unknown = await c.client.callTool({ name: 'release', arguments: { secret: 'secret-canary' } }); assert.equal(unknown.isError, true);
    assert.equal(JSON.stringify(unknown).includes('secret-canary'), false);
    await c.client.close(); c = await clientFor(f);
    const retry = await c.client.callTool({ name: 'create_task_draft', arguments: draft }); assert.deepEqual(retry.structuredContent, value);
    f.store.revoke(f.binding);
    const revoked = await c.client.callTool({ name: 'task_draft_status', arguments: { draftId: value.draftId } }); assert.equal(revoked.isError, true);
    assert.equal(c.stderr().includes('secret-canary'), false);
  } finally { await c?.client.close(); f.cleanup(); }
});
test('a committed draft with an abandoned response recovers by exact request, never creates a replacement', async () => {
  const f = fixture(); let process;
  try {
    process = spawn(globalThis.process.execPath, [serverPath], { env: f.env, stdio: ['pipe', 'pipe', 'pipe'] });
    process.stdin.write(frame(initialise));
    await once(process.stdout, 'data');
    process.stdin.write(frame(ready) + frame({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'create_task_draft', arguments: draft } }));
    // Deliberately never parse/retain the call response. Observe commitment only
    // via the trusted store, then terminate the transport and retry explicitly.
    let stored;
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline) {
      const { DatabaseSync } = await import('node:sqlite'); const db = new DatabaseSync(f.launch.storePath);
      try {
        // Observation can race the real SQLite commit. A bounded busy wait is
        // not a mutation retry, nor evidence that a draft has been committed.
        db.exec('PRAGMA busy_timeout=100');
        const row = db.prepare('SELECT id FROM drafts').get();
        if (row) { stored = row.id; break; }
      } catch (error) {
        if (error?.errcode !== 5) throw error;
      } finally { db.close(); }
      await delay(10);
    }
    assert.ok(stored); process.kill(); await once(process, 'exit'); process = undefined;
    const c = await clientFor(f);
    try { const retry = await c.client.callTool({ name: 'create_task_draft', arguments: draft }); assert.equal(retry.structuredContent.draftId, stored); }
    finally { await c.client.close(); }
  } finally { process?.kill(); f.cleanup(); }
});
test('initialized before a successful SDK response cannot unlock tools, and handshake cannot repeat', async () => {
  const t = await rawTransport();
  t.input.write(frame(initialise) + frame(ready));
  assert.equal(t.closed, true); assert.equal(t.received.length, 1);
  const second = await rawTransport(); await admit(second); second.input.write(frame(ready)); assert.equal(second.closed, true);
});
test('initialization schema and negotiated SDK result are both validated', async () => {
  const t = await rawTransport(); t.input.write(frame({ ...initialise, params: {} }));
  assert.equal(t.closed, true); assert.equal(t.received.length, 0);
  const second = await rawTransport(); second.input.write(frame(initialise));
  await second.transport.send({ ...initResponse, result: { ...initResponse.result, protocolVersion: 'invented-profile' } });
  assert.equal(second.closed, true);
});
