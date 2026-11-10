"""Fictional at-rest, migration, locking and uncertainty regressions."""
import base64
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth, AuthError
from pilot.crypto import digest
from pilot.runtime import PilotRuntime
from pilot.storage import FIELDS, PREFIX, RecordStorage, StorageDenied
from pilot.storage_migrate import migrate, PENDING, MigrationOutcomeUnknown
from pilot.workflow import SyntheticWorkLoop, FIXTURE_GRANT


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.auths, self.runtimes, self.sessions = {}, {}, {}
        for owner in ('alice', 'bob'):
            directory = self.root / owner
            directory.mkdir(mode=0o700)
            auth = LocalOwnerAuth(directory / 'auth', clock=lambda: self.now)
            auth.bootstrap(owner, owner + '-agent', 'Fictional password ' + owner)
            self.auths[owner] = auth
            self.sessions[owner] = auth.login('Fictional password ' + owner)
            self.runtimes[owner] = PilotRuntime(directory / 'runtime', auth, clock=lambda: self.now)
        self.addCleanup(self.close)
        self.a, self.b = self.runtimes.values()
        self.sa, self.sb = self.sessions.values()
        self.a.enrol_peer(self.sa, self.b.identity, self.b.fingerprint)
        self.b.enrol_peer(self.sb, self.a.identity, self.a.fingerprint)
        self.secret = 'FICTIONAL private garden content never stored unencrypted 6712'

    def close(self):
        for runtime in self.runtimes.values():
            runtime.close()
        for auth in self.auths.values():
            auth.close()

    def item(self, name='one'):
        return self.a.propose(self.sa, self.b.fingerprint, 'task', 'FICTIONAL private title 8251',
            self.secret, digest({'name': name}), name, 1500, provider_disclosure=FIXTURE_GRANT)['id']

    def workflow(self):
        item = self.item()
        self.a.release(self.sa, item, self.a.review(self.sa, item)['review_digest'])
        packet = self.a.prepare_delivery(self.sa, 'proposal-' + item)
        self.b.receive(self.sb, packet)
        self.b.decide(self.sb, item, self.b.review(self.sb, item)['review_digest'], 'accept')
        workflow = SyntheticWorkLoop(self.b, enabled=True)
        prepared = workflow.prepare(self.sb, item)
        workflow.approve(self.sb, prepared['run_id'], prepared['review_digest'], 1400)
        return item, packet, workflow, prepared

    def legacy(self, owner='alice'):
        """Fictional old-format fixture only; production has no plaintext switch."""
        runtime = self.runtimes[owner]
        runtime.db.execute('PRAGMA secure_delete=ON')
        for table, (key, columns) in FIELDS.items():
            if not runtime.db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                continue
            rows = list(runtime.db.execute('SELECT * FROM ' + table))
            for raw in rows:
                plain = runtime.storage.row(table, raw)
                for column in columns:
                    runtime.db.execute('UPDATE ' + table + ' SET ' + column + '=? WHERE ' + key + '=?', (plain[column], plain[key]))
        runtime.db.execute('DROP TABLE application_storage')
        runtime.db.execute('VACUUM')
        runtime.close()
        return runtime.directory

    def restart(self, owner='alice'):
        runtime = self.runtimes[owner]
        runtime.close()
        replacement = PilotRuntime(runtime.directory, self.auths[owner], clock=lambda: self.now)
        self.runtimes[owner] = replacement
        if owner == 'alice': self.a = replacement
        else: self.b = replacement
        return replacement

    def test_all_payload_columns_encrypt_and_raw_file_has_no_text(self):
        item, packet, workflow, prepared = self.workflow()
        status = workflow.dispatch(self.sb, prepared['run_id'], prepared['review_digest'])
        review = workflow.review_result(self.sb, status['run_id'])
        workflow.stage_result(self.sb, status['run_id'], review['review_digest'])
        for runtime in (self.a, self.b):
            for table, (_, columns) in FIELDS.items():
                if runtime.db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                    for row in runtime.db.execute('SELECT * FROM ' + table):
                        for column in columns:
                            if row[column] is not None:
                                self.assertTrue(row[column].startswith(PREFIX), (table, column))
            for file in runtime.directory.iterdir():
                if file.is_file():
                    raw = file.read_bytes()
                    for needle in (self.secret, 'FICTIONAL private title 8251', review['content']):
                        self.assertNotIn(needle.encode(), raw)
        self.assertEqual(self.a.prepare_delivery(self.sa, 'proposal-' + item), packet)

    def test_row_column_table_and_owner_substitution_fail_closed(self):
        codec = self.a.storage
        encrypted = codec.seal('pilot_provider_runs', 'first', 'review', self.secret)
        for table, key, column in (('pilot_provider_runs', 'second', 'review'),
                                  ('pilot_provider_runs', 'first', 'request'),
                                  ('pilot_workflow_artifacts', 'first', 'review')):
            with self.assertRaises(StorageDenied): codec.open(table, key, column, encrypted)
        with self.assertRaises(StorageDenied): self.b.storage.open('pilot_provider_runs', 'first', 'review', encrypted)

    def test_nonce_ciphertext_ephemeral_and_plaintext_corruption_refused(self):
        codec = self.a.storage
        encrypted = codec.seal('runtime_items', 'test', 'body', self.secret)
        raw = base64.b64decode(encrypted[len(PREFIX):])
        for offset in (0, 32, 44, len(raw) - 1):
            corrupted = bytearray(raw); corrupted[offset] ^= 1
            with self.assertRaises(StorageDenied):
                codec.open('runtime_items', 'test', 'body', PREFIX + base64.b64encode(corrupted).decode())
        for value in (self.secret, PREFIX + '!', PREFIX, PREFIX + base64.b64encode(b'x' * 59).decode()):
            with self.assertRaises(StorageDenied): codec.open('runtime_items', 'test', 'body', value)
        self.assertNotEqual(encrypted, codec.seal('runtime_items', 'test', 'body', self.secret))

    def test_lock_denies_open_but_allows_sealing_for_late_results(self):
        codec = self.a.storage
        encrypted = codec.seal('runtime_items', 'test', 'body', self.secret)
        self.a.auth.lock()
        with self.assertRaises(AuthError): codec.open('runtime_items', 'test', 'body', encrypted)
        late = codec.seal('runtime_items', 'test', 'body', self.secret)
        self.sa = self.a.auth.login('Fictional password alice')
        self.assertEqual(codec.open('runtime_items', 'test', 'body', late), self.secret)

    def test_password_rotation_preserves_ciphertext_and_original_packets(self):
        item, packet, _, _ = self.workflow()
        before = (self.a.directory / 'runtime.sqlite').read_bytes()
        self.a.auth.change_password(self.sa, 'Fictional password alice', 'New fictional password alice')
        self.assertEqual(before, (self.a.directory / 'runtime.sqlite').read_bytes())
        with self.assertRaises(AuthError): self.a.review(self.sa, item)
        self.sa = self.a.auth.login('New fictional password alice')
        self.restart()
        self.assertEqual(self.a.review(self.sa, item)['content'], self.secret)
        self.assertEqual(self.a.prepare_delivery(self.sa, 'proposal-' + item), packet)

    def test_provider_late_result_is_retained_encrypted_after_logout(self):
        _, _, workflow, prepared = self.workflow()
        original = workflow.adapter.transport.send
        def lock_then_return(encoded):
            self.b.auth.lock()
            return original(encoded)
        workflow.adapter.transport.send = lock_then_return
        status = workflow.adapter.dispatch(self.sb, prepared['run_id'])
        self.assertEqual(status['state'], 'completed')
        ciphertext = self.b.db.execute('SELECT result FROM pilot_provider_runs').fetchone()[0]
        self.assertTrue(ciphertext.startswith(PREFIX))
        self.sb = self.b.auth.login('Fictional password bob')
        self.assertIn('SYNTHETIC FIXTURE RESULT', workflow.adapter.result(self.sb, prepared['run_id'])['text'])

    def test_missing_or_changed_metadata_cannot_fallback_to_plaintext(self):
        self.item()
        self.a.db.execute('DROP TABLE application_storage')
        with self.assertRaises(StorageDenied): self.item('two')
        with self.assertRaises(StorageDenied): self.restart()
        with self.assertRaises(StorageDenied):
            RecordStorage(self.b.db, self.a.auth)

    def test_shared_runtime_lease_refuses_exclusive_migration(self):
        other = PilotRuntime(self.a.directory, self.a.auth)
        try:
            with self.assertRaises(StorageDenied): migrate(self.a.directory, self.a.auth, self.sa)
        finally:
            other.close()

    def test_legacy_requires_explicit_migration_and_roundtrips_exact_state(self):
        item, packet, workflow, prepared = self.workflow()
        status = workflow.dispatch(self.sb, prepared['run_id'], prepared['review_digest'])
        review = workflow.review_result(self.sb, status['run_id'])
        workflow.stage_result(self.sb, status['run_id'], review['review_digest'])
        before_a, before_b = self.a.state(self.sa), self.b.state(self.sb)
        self.legacy('alice'); self.legacy('bob')
        with self.assertRaises(StorageDenied): self.restart()
        for owner in ('alice', 'bob'):
            result = migrate(self.runtimes[owner].directory, self.auths[owner], self.sessions[owner])
            self.assertTrue(result['migrated'])
            self.assertFalse(result['plaintext_backup_created'])
            self.restart(owner)
        self.assertEqual(self.a.state(self.sa), before_a)
        self.assertEqual(self.b.state(self.sb), before_b)
        self.assertEqual(self.a.prepare_delivery(self.sa, 'proposal-' + item), packet)
        self.assertEqual(SyntheticWorkLoop(self.b, enabled=True).review_result(self.sb, status['run_id']), review)
        for runtime in (self.a, self.b):
            self.assertNotIn(self.secret.encode(), (runtime.directory / 'runtime.sqlite').read_bytes())
        with self.assertRaises(StorageDenied): migrate(self.a.directory, self.a.auth, self.sa)

    def test_failed_encryption_preserves_original_and_creates_no_output(self):
        self.item(); directory = self.legacy()
        original = (directory / 'runtime.sqlite').read_bytes()
        with patch.object(RecordStorage, 'seal', side_effect=StorageDenied('synthetic refusal')):
            with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)
        self.assertEqual((directory / 'runtime.sqlite').read_bytes(), original)
        self.assertFalse((directory / PENDING).exists())

    def test_write_interruption_preserves_original_and_blocks_automatic_retry(self):
        self.item(); directory = self.legacy()
        original = (directory / 'runtime.sqlite').read_bytes()
        with patch('pilot.storage_migrate.os.fsync', side_effect=OSError('FICTIONAL secret OS error')):
            with self.assertRaises(MigrationOutcomeUnknown) as outcome: migrate(directory, self.a.auth, self.sa)
        self.assertNotIn('secret', str(outcome.exception))
        self.assertEqual((directory / 'runtime.sqlite').read_bytes(), original)
        self.assertTrue((directory / PENDING).exists())
        self.assertNotIn(self.secret.encode(), (directory / PENDING).read_bytes())
        with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)

    def test_directory_sync_failure_requires_inspection_but_restart_reads_encrypted_state(self):
        item = self.item(); directory = self.legacy()
        original_fsync = os.fsync
        calls = []
        def fail_second(fd):
            calls.append(fd)
            if len(calls) == 2: raise OSError('synthetic directory fsync')
            return original_fsync(fd)
        with patch('pilot.storage_migrate.os.fsync', side_effect=fail_second):
            with self.assertRaises(MigrationOutcomeUnknown): migrate(directory, self.a.auth, self.sa)
        self.assertFalse((directory / PENDING).exists())
        self.restart()
        self.assertEqual(self.a.review(self.sa, item)['content'], self.secret)

    def test_sidecar_symlink_hardlink_and_wrong_owner_refused(self):
        self.item(); directory = self.legacy()
        source = directory / 'runtime.sqlite'
        original = source.read_bytes()
        with self.assertRaises(StorageDenied): migrate(directory, self.b.auth, self.sb)
        for name in ('runtime.sqlite-journal', 'runtime.sqlite-wal', 'runtime.sqlite-shm', PENDING):
            sidecar = directory / name
            sidecar.symlink_to('/nonexistent')
            with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)
            sidecar.unlink()
        link = directory / 'hardlink'; os.link(source, link)
        with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)
        link.unlink()
        saved = directory / 'original'; source.rename(saved); source.symlink_to(saved)
        with self.assertRaises(OSError): migrate(directory, self.a.auth, self.sa)
        source.unlink(); saved.rename(source)
        self.assertEqual(source.read_bytes(), original)

    def test_expired_session_cannot_publish_migration(self):
        self.item(); directory = self.legacy()
        original = (directory / 'runtime.sqlite').read_bytes()
        self.now = 2000
        with self.assertRaises(AuthError): migrate(directory, self.a.auth, self.sa)
        self.assertEqual((directory / 'runtime.sqlite').read_bytes(), original)

    def test_unknown_table_or_trigger_migration_refused(self):
        self.item(); directory = self.legacy()
        db = sqlite3.connect(directory / 'runtime.sqlite')
        db.execute('CREATE TABLE unexpected_secret(payload TEXT)'); db.commit(); db.close()
        with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)

    def test_lost_format_marker_is_not_double_encrypted_by_migration(self):
        self.item()
        self.a.db.execute('DROP TABLE application_storage')
        self.a.close()
        before = (self.a.directory / 'runtime.sqlite').read_bytes()
        with self.assertRaises(StorageDenied): migrate(self.a.directory, self.a.auth, self.sa)
        self.assertEqual(before, (self.a.directory / 'runtime.sqlite').read_bytes())
        self.assertFalse((self.a.directory / PENDING).exists())

    def test_source_mutation_before_replace_leaves_original_change_and_pending(self):
        self.item(); directory = self.legacy()
        original_fsync = os.fsync
        changed = []
        def change_source(fd):
            original_fsync(fd)
            if not changed:
                db = sqlite3.connect(directory / 'runtime.sqlite')
                db.execute("UPDATE runtime_items SET cancelled=1")
                db.commit(); db.close()
                changed.append((directory / 'runtime.sqlite').read_bytes())
        with patch('pilot.storage_migrate.os.fsync', side_effect=change_source):
            with self.assertRaises(MigrationOutcomeUnknown): migrate(directory, self.a.auth, self.sa)
        self.assertEqual((directory / 'runtime.sqlite').read_bytes(), changed[0])
        self.assertTrue((directory / PENDING).exists())

    def test_generated_columns_are_not_silently_copied(self):
        self.item(); directory = self.legacy()
        with sqlite3.connect(directory / 'runtime.sqlite') as db:
            db.execute("ALTER TABLE runtime_items ADD COLUMN generated_secret TEXT GENERATED ALWAYS AS ('FICTIONAL PRIVATE GENERATED TEXT') VIRTUAL")
        before = (directory / 'runtime.sqlite').read_bytes()
        with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)
        self.assertEqual(before, (directory / 'runtime.sqlite').read_bytes())
        self.assertFalse((directory / PENDING).exists())

    def test_missing_known_column_refuses_before_output(self):
        self.item(); directory = self.legacy()
        with sqlite3.connect(directory / 'runtime.sqlite') as db:
            db.execute('ALTER TABLE runtime_items DROP COLUMN cancel_acknowledged')
        before = (directory / 'runtime.sqlite').read_bytes()
        with self.assertRaises(StorageDenied): migrate(directory, self.a.auth, self.sa)
        self.assertEqual(before, (directory / 'runtime.sqlite').read_bytes())
        self.assertFalse((directory / PENDING).exists())

    def test_optional_https_journal_is_preserved_exactly(self):
        from pilot.https_exchange import HTTPSExchange
        self.item()
        HTTPSExchange(self.a)._schema()
        self.a.db.execute("INSERT INTO https_send_attempts(message_id,packet_digest,file_digest,recipient,destination,kind,state) VALUES(?,?,?,?,?,?,'uncertain')",
                          ('synthetic-message', 'a' * 64, 'b' * 64, self.b.fingerprint,
                           'https://fictional.invalid/v1/packets', 'proposal'))
        before = [dict(row) for row in self.a.db.execute('SELECT * FROM https_send_attempts')]
        directory = self.legacy()
        migrate(directory, self.a.auth, self.sa)
        self.restart()
        self.assertEqual([dict(row) for row in self.a.db.execute('SELECT * FROM https_send_attempts')], before)

    def test_failed_runtime_close_keeps_migration_excluded(self):
        from pilot.storage import StoreLease
        errors = []
        def wrong_thread_close():
            try:
                self.a.close()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=wrong_thread_close)
        thread.start(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], sqlite3.ProgrammingError)
        self.assertEqual(self.a.db.execute('SELECT 1').fetchone()[0], 1)
        with self.assertRaises(StorageDenied): StoreLease(self.a.directory, exclusive=True)
        self.a.close()
        lease = StoreLease(self.a.directory, exclusive=True)
        lease.close()

    def test_transaction_rollback_leaves_no_plaintext_or_partial_item(self):
        count = self.a.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0]
        with patch.object(self.a, '_event', side_effect=StorageDenied('synthetic audit failure')):
            with self.assertRaises(StorageDenied): self.item()
        self.assertEqual(self.a.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0], count)
        self.assertNotIn(self.secret.encode(), (self.a.directory / 'runtime.sqlite').read_bytes())
