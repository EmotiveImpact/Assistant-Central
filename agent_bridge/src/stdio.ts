import { createBridge, Launch } from './server.ts';
import { DraftStore } from './store.ts';
import { BoundedStdioTransport } from './transport.ts';

// This environment is populated only by the trusted embedding host. It is NOT
// a public identity/authentication API. No auto-provisioning and no default owner.
let store: DraftStore | undefined;
try {
  const raw = process.env.AC_BRIDGE_LAUNCH;
  delete process.env.AC_BRIDGE_LAUNCH;
  if (!raw || Buffer.byteLength(raw) > 8192) throw new Error('missing_binding');
  const launch = Launch.parse(JSON.parse(raw));
  store = new DraftStore(launch.storePath, Buffer.from(launch.keyHex, 'hex'));
  const server = createBridge(store, launch.binding);
  const transport = new BoundedStdioTransport(process.stdin, process.stdout);
  server.onclose = () => { store?.close(); store = undefined; process.stdin.destroy(); };
  await server.connect(transport);
} catch {
  store?.close(); process.stderr.write('Assistant Central bridge unavailable\n'); process.exitCode = 1;
}
