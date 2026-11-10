import type { Readable, Writable } from 'node:stream';
import type { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import { JSONRPCMessageSchema, InitializeRequestSchema, InitializeResultSchema, SUPPORTED_PROTOCOL_VERSIONS, type JSONRPCMessage } from '@modelcontextprotocol/sdk/types.js';
import { strictJson } from './json.ts';

const MAX_FRAME = 16384, MAX_OUTPUT = 32768, MAX_FRAMES = 512, MAX_REQUESTS = 256;
/** MCP newline-delimited stdio, with a deliberately smaller admission profile. */
export class BoundedStdioTransport implements Transport {
  onclose?: () => void;
  onerror?: (error: Error) => void;
  onmessage?: (message: JSONRPCMessage) => void;
  #input: Readable; #output: Writable; #buffer = Buffer.alloc(0);
  #closed = false; #started = false; #frames = 0;
  #ids = new Set<string>(); #phase = 0;
  #initializeId?: string | number;
  #partialTimer?: NodeJS.Timeout; #lifetime?: NodeJS.Timeout;
  constructor(input: Readable, output: Writable) { this.#input = input; this.#output = output; }
  async start() {
    if (this.#started) throw new Error('already_started'); this.#started = true;
    this.#input.on('data', this.#data); this.#input.on('end', this.#end); this.#input.on('error', this.#end);
    this.#lifetime = setTimeout(() => { void this.close(); }, 120_000); this.#lifetime.unref();
  }
  #end = () => { void this.close(); };
  #data = (chunk: Buffer) => {
    if (this.#closed) return;
    try {
      // Consume slices: a huge multi-line chunk never becomes one retained buffer.
      let offset = 0;
      while (offset < chunk.length && !this.#closed) {
        const end = chunk.indexOf(10, offset); const limit = end < 0 ? chunk.length : end;
        if (this.#buffer.length + limit - offset > MAX_FRAME) throw new Error('frame_limit');
        this.#buffer = Buffer.concat([this.#buffer, chunk.subarray(offset, limit)]);
        if (end < 0) break;
        const text = new TextDecoder('utf-8', { fatal: true }).decode(this.#buffer);
        this.#buffer = Buffer.alloc(0); clearTimeout(this.#partialTimer); this.#partialTimer = undefined;
        this.#accept(text); offset = end + 1;
      }
      if (this.#buffer.length && !this.#partialTimer) {
        this.#partialTimer = setTimeout(() => { void this.close(); }, 5_000); this.#partialTimer.unref();
      } else if (!this.#buffer.length) this.#partialTimer = undefined;
    } catch { void this.close(); }
  };
  #accept(text: string) {
    if (++this.#frames > MAX_FRAMES) throw new Error('frame_limit');
    const message = JSONRPCMessageSchema.parse(strictJson(text));
    if (!('method' in message)) throw new Error('unexpected_response');
    if ('id' in message) {
      if ((typeof message.id === 'string' && Buffer.byteLength(message.id) > 128)
        || (typeof message.id === 'number' && !Number.isSafeInteger(message.id))) throw new Error('invalid_id');
      const id = `${typeof message.id}:${message.id}`;
      if (this.#ids.has(id) || this.#ids.size >= MAX_REQUESTS) throw new Error('replayed_request');
      this.#ids.add(id);
      if (message.method === 'initialize') {
        if (this.#phase !== 0) throw new Error('reinitialise');
        InitializeRequestSchema.parse(message);
        this.#phase = 1; this.#initializeId = message.id;
      } else if (this.#phase !== 3) throw new Error('not_initialised');
    } else {
      if (message.method === 'notifications/initialized') {
        if (this.#phase !== 2) throw new Error('not_initialised');
        this.#phase = 3;
      } else if (message.method !== 'notifications/cancelled' || this.#phase !== 3) return;
    }
    this.onmessage?.(message);
  }
  async send(message: JSONRPCMessage) {
    if (this.#closed) throw new Error('closed');
    if (this.#phase === 1 && 'id' in message && message.id === this.#initializeId) {
      if (!('result' in message)) { await this.close(); return; }
      const result = InitializeResultSchema.parse(message.result);
      if (!SUPPORTED_PROTOCOL_VERSIONS.includes(result.protocolVersion)) { await this.close(); return; }
      this.#phase = 2;
    }
    // SDK errors can otherwise echo unknown methods or validation input.
    const clean = 'error' in message ? { jsonrpc: '2.0', id: message.id, error: { code: message.error.code, message: 'Request rejected' } } : message;
    const raw = JSON.stringify(clean) + '\n';
    if (Buffer.byteLength(raw) > MAX_OUTPUT || this.#output.writableLength > MAX_OUTPUT * 4) { await this.close(); return; }
    await new Promise<void>((resolve, reject) => this.#output.write(raw, error => error ? reject(new Error('write_failed')) : resolve()));
  }
  async close() {
    if (this.#closed) return; this.#closed = true;
    clearTimeout(this.#partialTimer); clearTimeout(this.#lifetime);
    this.#input.off('data', this.#data); this.#input.off('end', this.#end); this.#input.off('error', this.#end);
    this.#input.pause(); this.#buffer = Buffer.alloc(0); this.onclose?.();
  }
}
