"""Independent file-handoff regressions. All owners and payloads are fictional."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import TransportDenied
from pilot.file_exchange import FileExchange, FileExchangeDenied, FileOutcomeUnknown, read_packet, write_packet
from pilot.runtime import PilotRuntime


class FileExchangeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.owners = []
        for name in ('sender', 'receiver'):
            auth = LocalOwnerAuth(self.root / name, clock=lambda: self.now)
            self.addCleanup(auth.close)
            auth.bootstrap(name, name + '-assistant', 'fictional-review-password')
            token = auth.login('fictional-review-password')
            runtime = PilotRuntime(self.root / name, auth, clock=lambda: self.now)
            self.addCleanup(runtime.close)
            self.owners.append((auth, token, runtime, FileExchange(runtime)))
        self.a, self.b = self.owners
        self.a[2].enrol_peer(self.a[1], self.b[2].identity, self.b[2].fingerprint)
        self.b[2].enrol_peer(self.b[1], self.a[2].identity, self.a[2].fingerprint)
        item = self.a[2].propose(self.a[1], self.b[2].fingerprint, 'task', 'Synthetic transfer',
                               'SYNTHETIC ONLY: an imaginary garden', 'c' * 64, 'review-transfer', 1500)
        self.item_id = item['id']
        self.message_id = self.a[2].release(self.a[1], self.item_id,
                                          self.a[2].review(self.a[1], self.item_id)['review_digest'])['message_id']
        self.source = self.root / 'original.json'
        self.receipt = self.root / 'receipt.json'

    def export(self):
        self.a[3].export(self.a[1], self.message_id, self.source)

    def test_import_ack_loss_cannot_reapply_or_lose_original_receipt(self):
        self.export()
        receive = self.b[2].receive
        captured = {}
        def lost_ack(*args):
            result = receive(*args)
            captured.update(result)
            raise KeyboardInterrupt('fictional acknowledgement interruption')
        with patch.object(self.b[2], 'receive', side_effect=lost_ack), self.assertRaises(FileOutcomeUnknown):
            self.b[3].receive(self.b[1], self.source, self.receipt)
        self.assertFalse(self.receipt.exists())
        before = self.b[2].state(self.b[1])
        result = self.b[3].receive(self.b[1], self.source, self.receipt)
        self.assertTrue(result['duplicate'])
        self.assertEqual(self.b[2].state(self.b[1])['history'], before['history'])
        self.assertEqual(read_packet(self.receipt), captured['receipt'])

    def test_tampered_ciphertext_never_commits_or_emits_a_receipt(self):
        self.export()
        packet = read_packet(self.source)
        packet['ciphertext'] = ('A' if packet['ciphertext'][0] != 'A' else 'B') + packet['ciphertext'][1:]
        tampered = self.root / 'tampered.json'
        write_packet(tampered, packet)
        before = self.b[2].state(self.b[1])
        with self.assertRaises(TransportDenied): self.b[3].receive(self.b[1], tampered, self.receipt)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.b[2].state(self.b[1]), before)

    def test_revoked_peer_blocks_new_export_and_previously_exported_import(self):
        self.export()
        self.a[2].revoke_peer(self.a[1], self.b[2].fingerprint)
        self.b[2].revoke_peer(self.b[1], self.a[2].fingerprint)
        extra = self.root / 'after-revocation.json'
        with self.assertRaises(TransportDenied): self.a[3].export(self.a[1], self.message_id, extra)
        with self.assertRaises(TransportDenied): self.b[3].receive(self.b[1], self.source, self.receipt)
        self.assertFalse(extra.exists()); self.assertFalse(self.receipt.exists())
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])

    def test_expiry_during_file_read_denies_import_before_any_application(self):
        self.export()
        def delayed(path):
            value = read_packet(path)
            self.now = 1900
            return value
        with patch('pilot.file_exchange.read_packet', side_effect=delayed), self.assertRaises(AuthError):
            self.b[3].receive(self.b[1], self.source, self.receipt)
        self.assertFalse(self.receipt.exists())
        fresh = self.b[0].login('fictional-review-password')
        self.assertEqual(self.b[2].state(fresh)['items'], [])

    def test_nonsticky_writable_ancestor_and_output_link_are_refused(self):
        self.export()
        writable = self.root / 'writable'
        writable.mkdir(mode=0o700)
        writable.chmod(0o777)
        private = writable / 'private'
        private.mkdir(mode=0o700)
        with self.assertRaises(FileExchangeDenied): write_packet(private / 'packet.json', read_packet(self.source))
        self.assertFalse((private / 'packet.json').exists())
        target = self.root / 'target'; target.write_bytes(b'never overwrite'); target.chmod(0o600)
        link = self.root / 'output-link'; link.symlink_to(target)
        with self.assertRaises(FileOutcomeUnknown): self.a[3].export(self.a[1], self.message_id, link)
        self.assertEqual(target.read_bytes(), b'never overwrite')


if __name__ == '__main__':
    unittest.main()
