// Diagnostic tripwire, not an OS sandbox. Hosted CI additionally uses Docker's
// network=none. No host integration in these tests needs outbound networking.
import net from 'node:net';
import http from 'node:http';
import https from 'node:https';
import tls from 'node:tls';
import { syncBuiltinESMExports } from 'node:module';
const reject = () => { throw new Error('Acceptance fixtures forbid outbound networking'); };
net.Socket.prototype.connect = reject;
net.connect = reject; net.createConnection = reject; tls.connect = reject;
http.request = reject; http.get = reject; https.request = reject; https.get = reject;
globalThis.fetch = reject;
syncBuiltinESMExports();
