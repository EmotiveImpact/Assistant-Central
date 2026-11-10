"""Recovery exports only retained receipt bytes, including after cache damage."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.crypto import TransportDenied, canonical, digest
from pilot.file_exchange import FileExchange, read_packet, write_packet
from pilot.https_exchange import HTTPSExchange
from pilot.runtime import PilotRuntime, RuntimeDenied


class FileReceiptRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 1000
        self.owners = []
        for name in ('alice', 'bob'):
            auth = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            auth.bootstrap(name, name + '-assistant', 'fictional-password-' + name)
            session = auth.login('fictional-password-' + name)
            runtime = PilotRuntime(self.root / name, auth, clock=lambda: self.now)
            self.owners.append([auth, session, runtime, FileExchange(runtime)])
        self.a, self.b = self.owners
        for owner, peer in ((self.a, self.b), (self.b, self.a)):
            owner[2].enrol_peer(owner[1], peer[2].identity, peer[2].fingerprint)
        item = self.a[2].propose(self.a[1], self.b[2].fingerprint, 'task', 'Fictional garden',
                               'SYNTHETIC PRIVATE TEXT', 'a' * 64, 'garden', 1500)
        self.message_id = self.a[2].release(self.a[1], item['id'],
            self.a[2].review(self.a[1], item['id'])['review_digest'])['message_id']
        self.source = self.root / 'proposal.json'
        self.original = self.root / 'original-receipt.json'
        self.output = self.root / 'recovered-receipt.json'
        self.a[3].export(self.a[1], self.message_id, self.source)
        self.packet = read_packet(self.source)
        self.b[3].receive(self.b[1], self.source, self.original)

    def tearDown(self):
        for auth, session, runtime, exchange in self.owners:
            runtime.close()
            auth.close()
        self.temp.cleanup()

    def snapshot(self):
        return '\n'.join(self.b[2].db.iterdump())

    def recover(self):
        return self.b[3].receipt(self.b[1], self.message_id, self.output)

    def reopen_recipient(self):
        self.b[2].close()
        self.b[0].close()
        auth = LocalOwnerAuth(self.root / 'bob', clock=lambda: self.now)
        session = auth.login('fictional-password-bob')
        runtime = PilotRuntime(self.root / 'bob', auth, clock=lambda: self.now)
        self.b[:] = [auth, session, runtime, FileExchange(runtime)]

    def test_missing_cache_after_restart_cannot_mint_receipt_or_create_file(self):
        self.b[2].db.execute('DELETE FROM peer_receipts WHERE id=?', (self.message_id,))
        self.now = read_packet(self.original)['header']['expires'] + 1
        self.reopen_recipient()
        before = self.snapshot()
        self.assertIsNotNone(self.b[2].db.execute(
            'SELECT 1 FROM peer_inbox WHERE id=?', (self.message_id,)).fetchone())
        with self.assertRaisesRegex(TransportDenied, 'Original cached receipt required'):
            self.recover()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.b[2].db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0], 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.b[2].db.in_transaction)

    def test_cache_precondition_is_inside_the_runtime_transaction(self):
        transaction = self.b[2]._transaction
        before = self.snapshot()

        @contextmanager
        def remove_cache_on_entry(session):
            with transaction(session) as checks:
                self.b[2].db.execute('DELETE FROM peer_receipts WHERE id=?', (self.message_id,))
                yield checks

        with patch.object(self.b[2], '_transaction', remove_cache_on_entry), \
                patch.object(self.b[2].exchange, 'receipt_for', wraps=self.b[2].exchange.receipt_for) as receipt_for:
            with self.assertRaisesRegex(TransportDenied, 'Original cached receipt required'):
                self.recover()
        receipt_for.assert_not_called()
        self.assertEqual(self.snapshot(), before)  # Transactional removal was rolled back.
        self.assertFalse(self.output.exists())

    def test_expired_cached_receipt_is_recovered_byte_identically_after_restart(self):
        original = self.original.read_bytes()
        self.now = read_packet(self.original)['header']['expires'] + 1
        self.reopen_recipient()
        before = self.snapshot()
        result = self.recover()
        self.assertEqual(result, {'message_id': self.message_id, 'transport_receipt_only': True})
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.snapshot(), before)

    def test_revoked_peer_cannot_export_cached_receipt(self):
        self.b[2].revoke_peer(self.b[1], self.a[2].fingerprint)
        before = self.snapshot()
        with self.assertRaises(TransportDenied):
            self.recover()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.output.exists())

    def test_damaged_cached_receipt_is_not_replaced(self):
        packet = read_packet(self.original)
        packet['header']['expires'] += 1
        self.b[2].db.execute('UPDATE peer_receipts SET packet=?,digest=? WHERE id=?',
                            (canonical(packet).decode(), digest(packet), self.message_id))
        before = self.snapshot()
        with self.assertRaises(TransportDenied):
            self.recover()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.output.exists())

    def assert_duplicate_missing_cache_denied(self, receive):
        self.b[2].db.execute('DELETE FROM peer_receipts WHERE id=?', (self.message_id,))
        self.now = read_packet(self.original)['header']['expires'] + 1
        self.reopen_recipient()
        before = self.snapshot()
        paths_before = sorted(self.root.iterdir())
        with patch.object(self.b[2].exchange, 'receipt_for', wraps=self.b[2].exchange.receipt_for) as receipt_for:
            with self.assertRaisesRegex((RuntimeDenied, TransportDenied), 'Original cached receipt required'):
                receive()
        receipt_for.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(self.root.iterdir()), paths_before)
        self.assertEqual(read_packet(self.source), self.packet)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.b[2].db.in_transaction)

    def test_runtime_duplicate_import_cannot_replace_missing_cache(self):
        self.assert_duplicate_missing_cache_denied(
            lambda: self.b[2].receive(self.b[1], self.packet))

    def test_file_duplicate_import_cannot_replace_missing_cache_or_create_file(self):
        self.assert_duplicate_missing_cache_denied(
            lambda: self.b[3].receive(self.b[1], self.source, self.output))

    def test_https_duplicate_import_cannot_replace_missing_cache(self):
        file_digest = hashlib.sha256(canonical(self.packet)).hexdigest()
        quarantine_entry = self.root / (file_digest + '.json')
        write_packet(quarantine_entry, self.packet)
        self.assert_duplicate_missing_cache_denied(lambda: HTTPSExchange(self.b[2]).receive(
            self.b[1], quarantine_entry, self.a[2].fingerprint, file_digest))

    def test_duplicate_imports_preserve_original_expired_cached_receipt(self):
        original = self.original.read_bytes()
        self.now = read_packet(self.original)['header']['expires'] + 1
        self.reopen_recipient()
        before = self.snapshot()
        direct = self.b[2].receive(self.b[1], self.packet)
        self.assertTrue(direct['duplicate'])
        self.assertEqual(canonical(direct['receipt']), original)
        file_result = self.b[3].receive(self.b[1], self.source, self.output)
        self.assertTrue(file_result['duplicate'])
        self.assertEqual(self.output.read_bytes(), original)
        file_digest = hashlib.sha256(canonical(self.packet)).hexdigest()
        quarantine_entry = self.root / (file_digest + '.json')
        write_packet(quarantine_entry, self.packet)
        https_result = HTTPSExchange(self.b[2]).receive(
            self.b[1], quarantine_entry, self.a[2].fingerprint, file_digest)
        self.assertTrue(https_result['duplicate'])
        self.assertTrue(https_result['receipt_available'])
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_receipt_does_not_require_or_create_its_own_receipt_cache(self):
        packet = read_packet(self.original)
        first = self.a[2].receive(self.a[1], packet)
        before = '\n'.join(self.a[2].db.iterdump())
        duplicate = self.a[2].receive(self.a[1], packet)
        self.assertFalse(first['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        self.assertIsNone(first['receipt'])
        self.assertIsNone(duplicate['receipt'])
        self.assertEqual(self.a[2].db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0], 0)
        self.assertEqual('\n'.join(self.a[2].db.iterdump()), before)


if __name__ == '__main__':
    unittest.main()
