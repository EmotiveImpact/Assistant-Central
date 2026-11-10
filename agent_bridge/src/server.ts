import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { Binding, BoundaryError, tools } from './contract.ts';
import { DraftStore } from './store.ts';
import { z } from 'zod';

/** No owner decision, provider dispatch, transport send, history or arbitrary router is supplied. */
export function createBridge(store: DraftStore, binding: Binding) {
  const trustedBinding = Object.freeze(Binding.parse(binding));
  const server = new Server({ name: 'assistant-central-inert-drafts', version: '0.1.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async request => {
    if (request.params?.cursor !== undefined) throw new Error('Request rejected');
    return { tools: structuredClone(tools) as never };
  });
  server.setRequestHandler(CallToolRequestSchema, async request => {
    try {
      const value = store.dispatch(trustedBinding, request.params.name, request.params.arguments);
      return { content: [{ type: 'text' as const, text: JSON.stringify(value) }], structuredContent: value };
    } catch (error) {
      const value = { error: error instanceof BoundaryError ? error.code : 'internal_error' };
      return { isError: true, content: [{ type: 'text' as const, text: JSON.stringify(value) }] };
    }
  });
  return server;
}
export const Launch = z.object({
  storePath: z.string().min(1).max(4096), keyHex: z.string().regex(/^[a-f0-9]{64}$/), binding: Binding,
}).strict();
