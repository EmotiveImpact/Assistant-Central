import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const home = mkdtempSync(join(tmpdir(), 'ac-host-home-'));
const root = fileURLToPath(new URL('../', import.meta.url));
// No inherited API keys, login state, shell configuration, or telemetry endpoints.
const env = { PATH: process.env.PATH ?? '', HOME: home, TMPDIR: tmpdir(),
  NODE_NO_WARNINGS: '1', OTEL_SDK_DISABLED: 'true', OPENAI_AGENTS_DISABLE_TRACING: '1' };
const child = spawn(process.execPath, ['--import', './tests/no-network.mjs', '--test', '--test-concurrency=1', './tests/*.test.mjs'], { cwd: root, env, stdio: 'inherit' });
child.on('exit', code => { rmSync(home, { recursive: true, force: true }); process.exitCode = code ?? 1; });
