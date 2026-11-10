import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fixture, draft, serverPath, root } from './helpers.mjs';
import { Agent, Runner, MCPServerStdio, setTracingDisabled } from '@openai/agents';

setTracingDisabled(true);

test('OpenAI Agents official Runner discovers and calls the real stdio bridge', async () => {
  const f = fixture('openai');
  const mcp = new MCPServerStdio({ name: 'central', command: process.execPath, args: [serverPath], env: f.env, cacheToolsList: false });
  const seen = [];
  // Only model decisions are doubles. Agent, Runner, discovery, dispatch, stdio,
  // validation, encrypted storage and tool responses are the actual implementations.
  const model = {
    async getResponse(request) {
      seen.push(request);
      if (seen.length === 1) {
        assert.deepEqual(request.tools.map(t => t.name).sort(), ['create_task_draft', 'task_draft_status']);
        return { usage: {}, output: [{ type: 'function_call', id: 'call_fixture', callId: 'call_fixture', name: 'create_task_draft', arguments: JSON.stringify(draft), status: 'completed' }] };
      }
      assert.ok(JSON.stringify(request.input).includes('awaiting_owner_review'));
      return { usage: {}, output: [{ type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: 'Inert draft saved, awaiting the owner.' }] }] };
    },
    async *getStreamedResponse() { throw new Error('streaming_not_used'); },
  };
  try {
    await mcp.connect();
    const agent = new Agent({ name: 'Fictional OpenAI SDK host', model, instructions: 'Prepare an inert draft only.', mcpServers: [mcp] });
    const result = await new Runner({ tracingDisabled: true }).run(agent, 'Prepare the fictional task.', { maxTurns: 3 });
    assert.equal(result.finalOutput, 'Inert draft saved, awaiting the owner.');
    assert.equal(seen.length, 2);
    const stored = f.store.dispatch(f.binding, 'create_task_draft', draft);
    assert.equal(stored.ownerConsent, 'not_requested');
    const remote = await mcp.callTool('task_draft_status', { draftId: stored.draftId });
    assert.ok(JSON.stringify(remote).includes(stored.draftId));
  } finally { await mcp.close(); f.cleanup(); }
});

test('Cursor/Grok Agent SDK official serve handle dispatches advertised MCP tools without a model', async () => {
  const f = fixture('cursor');
  const project = join(f.dir, 'project');
  mkdirSync(join(project, 'bot', 'mcp-connections'), { recursive: true });
  writeFileSync(join(project, 'package.json'), JSON.stringify({ type: 'module' }));
  // Trusted local fixture modules, with no tools/skills/egress/credential setup.
  writeFileSync(join(project, 'bot', 'instructions.md'), 'Only prepare inert drafts.');
  const sdkUrl = pathToFileURL(join(root, 'node_modules/@grok/agent-sdk/dist/index.js')).href;
  writeFileSync(join(project, 'bot', 'agent.ts'), `import { defineAgent, emptyFs } from ${JSON.stringify(sdkUrl)}; export default defineAgent({ name: 'Fictional Cursor SDK host', tools: [], skills: false, fs: emptyFs() });`);
  writeFileSync(join(project, 'bot', 'mcp-connections', 'central.ts'), `import { defineConnection } from ${JSON.stringify(sdkUrl)}; export default defineConnection(${JSON.stringify({ command: process.execPath, args: [serverPath], env: f.env, advertiseTools: true, tools: ['create_task_draft', 'task_draft_status'] })});`);
  const { serve } = await import('@grok/agent-sdk');
  let handle;
  try {
    handle = await serve(project, { host: '127.0.0.1', port: 0, stateRoot: join(f.dir, 'host-state'), schedules: false, reminders: false, playground: false, docs: false, mode: 'single', logger() {} });
    const result = await handle.callTool('create_task_draft', draft);
    assert.equal(result.isError, false);
    assert.ok(JSON.stringify(result.result).includes('awaiting_owner_review'));
    const stored = f.store.dispatch(f.binding, 'create_task_draft', draft);
    const response = await handle.callTool('task_draft_status', { draftId: stored.draftId });
    assert.equal(response.isError, false);
    assert.ok(JSON.stringify(response.result).includes(stored.draftId));
    const rejected = await handle.callTool('create_task_draft', { ...draft, requestId: 'spoof', ownerId: 'attacker' });
    assert.equal(rejected.isError, true);
    await assert.rejects(() => handle.callTool('release', { draftId: stored.draftId }));
    f.store.revoke(f.binding);
    const revoked = await handle.callTool('task_draft_status', { draftId: stored.draftId });
    assert.equal(revoked.isError, true);
  } finally { await handle?.close(); f.cleanup(); }
});
