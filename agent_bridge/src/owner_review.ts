/** Fixed one-request local pipe. Not an MCP server, listener or shell interface.
 * Credentials arrive only on stdin from the authenticated workspace process. */
import { z } from 'zod';
import { Launch } from './server.ts';
import { DraftStore, OwnerContext } from './store.ts';
import { StatusInput, BoundaryError } from './contract.ts';
import { strictJson } from './json.ts';
const Request = z.object({ launch: Launch, owner: OwnerContext,
  operation: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('list') }).strict(),
    z.object({ kind: z.literal('review'), draftId: StatusInput.shape.draftId }).strict(),
    z.object({ kind: z.literal('dismiss'), draftId: StatusInput.shape.draftId,
      digest: z.string().regex(/^[a-f0-9]{64}$/), reviewToken: z.string().min(1).max(2048) }).strict(),
  ]) }).strict();
let store: DraftStore | undefined;
let dismissAdmitted = false;
const timer = setTimeout(() => process.exit(1), 4000);
try {
  const chunks: Buffer[] = []; let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length; if (size > 16384) throw new Error('bound'); chunks.push(chunk);
  }
  const request = Request.parse(strictJson(Buffer.concat(chunks).toString('utf8')));
  store = new DraftStore(request.launch.storePath, Buffer.from(request.launch.keyHex, 'hex'));
  const { binding } = request.launch; const op = request.operation; let result: unknown;
  dismissAdmitted = op.kind === 'dismiss';
  if (op.kind === 'list') result = { items: store.listForOwner(binding, request.owner) };
  else if (op.kind === 'review') result = store.reviewForOwner(binding, request.owner, op.draftId);
  else result = store.dismissForOwner(binding, request.owner, op.draftId, op.digest, op.reviewToken);
  const output = JSON.stringify({ result });
  if (Buffer.byteLength(output) > 32768) throw new Error('bound');
  process.stdout.write(output);
} catch (error) {
  // Only a proven boundary refusal can imply no dismissal was committed. An
  // unexpected failure after admission may follow COMMIT, so never label it a
  // definite refusal. Both envelopes are fixed and contain no exception data.
  const uncertain = dismissAdmitted && !(error instanceof BoundaryError);
  process.stdout.write(uncertain ? '{"error":"outcome_unknown"}' : '{"error":"unavailable"}');
  process.exitCode = uncertain ? 2 : 1;
} finally { clearTimeout(timer); store?.close(); }
