import { mkdtempSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { DraftStore } from '../src/store.ts';
export const root = fileURLToPath(new URL('../', import.meta.url));
export const serverPath = resolve(root, 'src/stdio.ts');
export const draft = { requestId: 'fixture_request', title: 'Fictional planning task', instruction: 'Draft a fictional picnic checklist. Do not contact anyone.' };
export function fixture(label = 'fixture', options = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'ac-bridge-'));
  const key = randomBytes(32);
  const binding = { ownerId: `${label}_owner`, hostId: `${label}_host`, sessionId: 'session_one', conversationId: 'conversation_one', recipientId: 'fictional_peer', expiresAt: Date.now() + 600_000, ...options };
  const storePath = join(dir, 'drafts.sqlite');
  const store = new DraftStore(storePath, key); store.provision(binding);
  const launch = { storePath, keyHex: key.toString('hex'), binding };
  const env = { AC_BRIDGE_LAUNCH: JSON.stringify(launch), NODE_NO_WARNINGS: '1', HOME: dir, PATH: process.env.PATH ?? '', NODE_OPTIONS: `--import=${resolve(root, 'tests/no-network.mjs')}` };
  return { dir, key, binding, store, launch, env, cleanup() { store.close(); rmSync(dir, { recursive: true, force: true }); } };
}
