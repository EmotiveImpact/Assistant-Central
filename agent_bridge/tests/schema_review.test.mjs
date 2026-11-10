// Independent exact-schema regression: SQL LIKE '_' is a wildcard, not an underscore.
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { DraftStore } from '../src/store.ts';
import { fixture } from './helpers.mjs';

for (const version of [1, 2]) {
  test(`v${version} schema refuses a user table resembling SQLite's reserved prefix`, () => {
    const f = fixture(`schema-prefix-v${version}`);
    let reopened;
    try {
      const db = new DatabaseSync(f.launch.storePath);
      try {
        db.exec('CREATE TABLE sqliteXhidden (private_note TEXT)');
        if (version === 1) db.exec('DROP TABLE owner_dismissals; UPDATE bridge_meta SET version=1');
      } finally { db.close(); }
      assert.throws(() => {
        reopened = new DraftStore(f.launch.storePath, f.key, Date.now,
          version === 1 ? { allowOfflineV1Upgrade: true } : {});
      }, 'An unknown user table must not be excluded as a SQLite internal table');
    } finally { reopened?.close(); f.cleanup(); }
  });
}
