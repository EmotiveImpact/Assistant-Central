import { DatabaseSync } from 'node:sqlite';
import { constants, closeSync, openSync, lstatSync } from 'node:fs';
import { dirname, isAbsolute } from 'node:path';
import { createCipheriv, createDecipheriv, createHmac, hkdfSync, randomBytes, randomUUID } from 'node:crypto';
import { Binding, BoundaryError, DraftInput, StatusInput, Status, type ErrorCode } from './contract.ts';

const SCHEMA = [
  'CREATE TABLE bridge_meta (version INTEGER NOT NULL, key_check TEXT NOT NULL)',
  'CREATE TABLE scopes (scope TEXT PRIMARY KEY, binding TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL, operations INTEGER NOT NULL DEFAULT 0, last_seen INTEGER NOT NULL)',
  'CREATE TABLE drafts (scope TEXT NOT NULL, request TEXT NOT NULL, id TEXT NOT NULL UNIQUE, commitment TEXT NOT NULL, sealed TEXT NOT NULL, PRIMARY KEY(scope, request))',
  'CREATE TABLE audit (sequence INTEGER PRIMARY KEY, scope TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL, observed_at INTEGER NOT NULL)',
];
const MAX_OPERATIONS = 256;
const MAX_DRAFTS = 32;
const MAX_SCOPES = 64;
const MAX_LIFETIME_MS = 15 * 60 * 1000;
export const Audit = Object.freeze({ version: 1, actions: ['create', 'status', 'reject'], outcomes: ['ok', 'invalid_input', 'unavailable', 'conflict', 'limit_reached', 'internal_error'] });
const status = (draftId: string): Status => Status.parse({ draftId, state: 'awaiting_owner_review', ownerConsent: 'not_requested', transportReceipt: 'none', execution: 'not_started' });

/** Trusted-host API. Never expose this object, database path or key to an agent. */
export class DraftStore {
  #db: DatabaseSync;
  #key: Buffer;
  #macKey: Buffer;
  #now: () => number;
  constructor(path: string, key: Uint8Array, now: () => number = Date.now) {
    if (key.byteLength !== 32) throw new BoundaryError('unavailable');
    if (!isAbsolute(path)) throw new BoundaryError('unavailable');
    const parent = lstatSync(dirname(path));
    if (!parent.isDirectory() || parent.isSymbolicLink() || (parent.mode & 0o077) !== 0 || parent.uid !== process.getuid?.()) throw new BoundaryError('unavailable');
    // Create privately before SQLite opens it. Same-user malicious processes,
    // directory replacement, privileged OS access and backup rollback are excluded.
    let created = false;
    try { closeSync(openSync(path, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW, 0o600)); created = true; }
    catch (e) { if ((e as NodeJS.ErrnoException).code !== 'EEXIST') throw e; }
    const file = lstatSync(path);
    if (!file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || (file.mode & 0o077) !== 0 || file.uid !== process.getuid?.()) throw new BoundaryError('unavailable');
    this.#key = Buffer.from(hkdfSync('sha256', key, 'ac-agent-bridge-v1', 'draft-encryption', 32));
    this.#macKey = Buffer.from(hkdfSync('sha256', key, 'ac-agent-bridge-v1', 'scope-commitments', 32)); this.#now = now;
    this.#db = new DatabaseSync(path);
    try {
      this.#db.exec('PRAGMA busy_timeout=1000; PRAGMA journal_mode=DELETE; PRAGMA secure_delete=ON; PRAGMA trusted_schema=OFF');
      if (created) this.#transaction(() => {
        for (const sql of SCHEMA) this.#db.exec(sql);
        this.#db.prepare('INSERT INTO bridge_meta VALUES(1,?)').run(this.#mac('store-key-check-v1'));
      });
      const schema = this.#db.prepare("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql").all().map(row => row.sql);
      if (JSON.stringify(schema) !== JSON.stringify([...SCHEMA].sort())) throw new BoundaryError('unavailable');
      const metadata = this.#db.prepare('SELECT * FROM bridge_meta').all();
      if (metadata.length !== 1 || metadata[0].version !== 1 || metadata[0].key_check !== this.#mac('store-key-check-v1')) throw new BoundaryError('unavailable');
    } catch { this.close(); throw new BoundaryError('unavailable'); }
  }
  close() { this.#db.close(); this.#key.fill(0); this.#macKey.fill(0); }
  #mac(value: string) { return createHmac('sha256', this.#macKey).update('assistant-central-agent-bridge-v1\0').update(value).digest('hex'); }
  #scope(binding: Binding) {
    // Expiry is immutable per provisioned session. It is not a new scope.
    const { expiresAt: _, ...identity } = Binding.parse(binding);
    return this.#mac(JSON.stringify(identity));
  }
  #transaction<T>(fn: () => T): T {
    this.#db.exec('BEGIN IMMEDIATE');
    try { const value = fn(); this.#db.exec('COMMIT'); return value; }
    catch (error) { this.#db.exec('ROLLBACK'); throw error; }
  }
  /** Provision only after the embedding host has authenticated the real owner.
   * This is a fictional binding in the acceptance demo, not human consent. */
  provision(binding: Binding) {
    const b = Binding.parse(binding); const scope = this.#scope(b); const now = this.#now();
    if (b.expiresAt <= now || b.expiresAt > now + MAX_LIFETIME_MS) throw new BoundaryError('unavailable');
    this.#transaction(() => {
      const old = this.#db.prepare('SELECT binding, revoked FROM scopes WHERE scope=?').get(scope);
      const commitment = this.#mac(JSON.stringify(b));
      if (old) {
        if (old.binding !== commitment || old.revoked) throw new BoundaryError('unavailable');
        return;
      }
      const count = this.#db.prepare('SELECT count(*) AS n FROM scopes').get()!;
      if (Number(count.n) >= MAX_SCOPES) throw new BoundaryError('limit_reached');
      this.#db.prepare('INSERT INTO scopes(scope,binding,expires,last_seen) VALUES(?,?,?,?)').run(scope, commitment, b.expiresAt, now);
    });
  }
  revoke(binding: Binding) {
    const result = this.#db.prepare('UPDATE scopes SET revoked=1 WHERE scope=? AND binding=?').run(this.#scope(binding), this.#mac(JSON.stringify(Binding.parse(binding))));
    // An unknown binding cannot be reported as successfully fenced.
    if (Number(result.changes) !== 1) throw new BoundaryError('unavailable');
  }
  #seal(value: string, aad: string) {
    const nonce = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', this.#key, nonce);
    cipher.setAAD(Buffer.from(aad));
    const encrypted = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]);
    return Buffer.concat([nonce, cipher.getAuthTag(), encrypted]).toString('base64');
  }
  #open(value: string, aad: string) {
    const raw = Buffer.from(value, 'base64');
    const cipher = createDecipheriv('aes-256-gcm', this.#key, raw.subarray(0, 12));
    cipher.setAAD(Buffer.from(aad)); cipher.setAuthTag(raw.subarray(12, 28));
    return Buffer.concat([cipher.update(raw.subarray(28)), cipher.final()]).toString('utf8');
  }
  /** Trusted owner-review composition ONLY. Caller must authenticate the owner
   * independently. This is deliberately not registered as an MCP tool. Revoking
   * agent access does not delete the owner's review record. Content is untrusted. */
  inspectForOwner(binding: Binding, draftId: string): { draft: DraftInput, status: Status } {
    const scope = this.#scope(binding);
    const row = this.#db.prepare('SELECT binding FROM scopes WHERE scope=?').get(scope);
    if (!row || row.binding !== this.#mac(JSON.stringify(Binding.parse(binding)))) throw new BoundaryError('unavailable');
    const found = this.#db.prepare('SELECT * FROM drafts WHERE scope=? AND id=?').get(scope, draftId);
    if (!found) throw new BoundaryError('unavailable');
    const draft = DraftInput.parse(JSON.parse(this.#open(String(found.sealed), `${scope}:${found.id}`)));
    if (found.commitment !== this.#mac(JSON.stringify(draft))) throw new BoundaryError('unavailable');
    return { draft, status: status(String(found.id)) };
  }
  /** The only model-facing operation, with one fixed trusted binding. */
  dispatch(binding: Binding, name: string, input: unknown): Status {
    const scope = this.#scope(binding); const now = this.#now();
    // Audit rejection commits too. No user strings, content, keys or session IDs in audit.
    const outcome = this.#transaction((): { value?: Status, error?: ErrorCode } => {
      const row = this.#db.prepare('SELECT * FROM scopes WHERE scope=?').get(scope);
      if (!row || row.revoked || row.binding !== this.#mac(JSON.stringify(Binding.parse(binding)))) return { error: 'unavailable' };
      if (now < Number(row.last_seen) || now >= Number(row.expires)) {
        this.#db.prepare('UPDATE scopes SET revoked=1 WHERE scope=?').run(scope);
        return { error: 'unavailable' };
      }
      if (Number(row.operations) >= MAX_OPERATIONS) return { error: 'limit_reached' };
      this.#db.prepare('UPDATE scopes SET operations=operations+1,last_seen=? WHERE scope=?').run(now, scope);
      const action = name === 'create_task_draft' ? 'create' : name === 'task_draft_status' ? 'status' : 'reject';
      let value: Status | undefined; let error: ErrorCode | undefined;
      this.#db.exec('SAVEPOINT draft_operation');
      try {
        if (name === 'create_task_draft') {
          const parsed = DraftInput.safeParse(input);
          if (!parsed.success) throw new BoundaryError('invalid_input');
          const payload = JSON.stringify(parsed.data); const request = this.#mac(parsed.data.requestId);
          const commitment = this.#mac(payload);
          const previous = this.#db.prepare('SELECT * FROM drafts WHERE scope=? AND request=?').get(scope, request);
          if (previous) {
            if (previous.commitment !== commitment) throw new BoundaryError('conflict');
            // A corrupted record never yields a successful duplicate acknowledgement.
            if (this.#open(String(previous.sealed), `${scope}:${previous.id}`) !== payload) throw new BoundaryError('unavailable');
            value = status(String(previous.id));
          } else {
            const count = this.#db.prepare('SELECT count(*) AS n FROM drafts WHERE scope=?').get(scope)!;
            if (Number(count.n) >= MAX_DRAFTS) throw new BoundaryError('limit_reached');
            const id = randomUUID(); const sealed = this.#seal(payload, `${scope}:${id}`);
            this.#db.prepare('INSERT INTO drafts VALUES(?,?,?,?,?)').run(scope, request, id, commitment, sealed);
            value = status(id);
          }
        } else if (name === 'task_draft_status') {
          const parsed = StatusInput.safeParse(input);
          if (!parsed.success) throw new BoundaryError('invalid_input');
          const found = this.#db.prepare('SELECT * FROM drafts WHERE scope=? AND id=?').get(scope, parsed.data.draftId);
          if (!found) throw new BoundaryError('unavailable');
          // Verify the encrypted record before projecting its inert status.
          DraftInput.parse(JSON.parse(this.#open(String(found.sealed), `${scope}:${found.id}`)));
          value = status(String(found.id));
        } else throw new BoundaryError('invalid_input');
      } catch (e) { error = e instanceof BoundaryError ? e.code : 'internal_error'; }
      const finished = this.#now();
      if (finished < now || finished >= Number(row.expires)) {
        error = 'unavailable';
        this.#db.exec('ROLLBACK TO draft_operation');
        this.#db.prepare('UPDATE scopes SET revoked=1 WHERE scope=?').run(scope);
      } else if (error) this.#db.exec('ROLLBACK TO draft_operation');
      else this.#db.prepare('UPDATE scopes SET last_seen=? WHERE scope=?').run(finished, scope);
      this.#db.exec('RELEASE draft_operation');
      this.#db.prepare('INSERT INTO audit(scope,action,outcome,observed_at) VALUES(?,?,?,?)').run(scope, action, error ?? 'ok', now);
      return error ? { error } : { value };
    });
    if (outcome.error) throw new BoundaryError(outcome.error);
    return Status.parse(outcome.value);
  }
}
