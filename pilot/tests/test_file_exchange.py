"""Real temporary owners, ciphertext files, and adversarial offline boundaries."""
import contextlib
import io
import getpass
import warnings
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import MAX_PACKET, TransportDenied
from pilot.file_exchange import FileExchange, FileExchangeDenied, FileOutcomeUnknown, main, read_packet, write_packet
from pilot.runtime import PilotRuntime


class FileExchangeTests(unittest.TestCase):
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
                                'SYNTHETIC PRIVATE TEXT', 'a'*64, 'garden', 1500)
        self.item_id = item['id']
        self.message_id = self.a[2].release(self.a[1], self.item_id,
            self.a[2].review(self.a[1], self.item_id)['review_digest'])['message_id']
        self.packet = self.root / 'packet.json'
        self.receipt = self.root / 'receipt.json'

    def tearDown(self):
        for auth, session, runtime, exchange in self.owners:
            runtime.close()
            auth.close()
        self.temp.cleanup()

    def export(self):
        return self.a[3].export(self.a[1], self.message_id, self.packet)

    def test_end_to_end_duplicate_receipt_no_acceptance_or_receipt_loop(self):
        self.export()
        self.assertNotIn(b'SYNTHETIC PRIVATE TEXT', self.packet.read_bytes())
        self.assertEqual(self.packet.stat().st_mode & 0o777, 0o600)
        result = self.b[3].receive(self.b[1], self.packet, self.receipt)
        self.assertFalse(result['duplicate'])
        self.assertEqual(result['owner_acceptance'], 'not_established')
        other = self.root/'duplicate.json'
        self.assertTrue(self.b[3].receive(self.b[1], self.packet, other)['duplicate'])
        self.assertEqual(self.receipt.read_bytes(), other.read_bytes())
        loop = self.root/'loop.json'
        self.assertFalse(self.a[3].receive(self.a[1], self.receipt, loop)['receipt_available'])
        self.assertFalse(loop.exists())
        self.assertEqual(self.a[2].status(self.a[1], self.item_id)['state'], 'released')
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        with self.assertRaises(TransportDenied):
            self.a[3].receipt(self.a[1], read_packet(self.receipt)['header']['message_id'], loop)

    def test_failed_output_retains_uncertainty_and_attempt_bound(self):
        self.packet.write_bytes(b'never overwrite')
        for _ in range(5):
            with self.assertRaises(FileOutcomeUnknown): self.export()
        self.assertEqual(self.packet.read_bytes(), b'never overwrite')
        state = self.a[2].exchange.outbox_status(self.message_id)
        self.assertEqual((state['attempts'], state['state']), (5, 'uncertain'))
        with self.assertRaises(TransportDenied): self.export()

    def test_interrupted_write_and_receipt_recovery_after_restart(self):
        with patch('pilot.file_exchange.os.write', side_effect=KeyboardInterrupt):
            with self.assertRaises(FileOutcomeUnknown): self.export()
        self.assertTrue(self.packet.exists())
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['attempts'], 1)
        self.packet.unlink()  # test cleanup, never automatic application retry
        self.export()
        with patch('pilot.file_exchange.os.fsync', side_effect=OSError):
            with self.assertRaises(FileOutcomeUnknown):
                self.b[3].receive(self.b[1], self.packet, self.receipt)
        original = self.receipt.read_bytes()
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        self.b[2].close(); self.b[0].close()
        auth = LocalOwnerAuth(self.root/'bob', clock=lambda: self.now)
        runtime = PilotRuntime(self.root/'bob', auth, clock=lambda: self.now)
        self.b[:] = [auth, auth.login('fictional-password-bob'), runtime, FileExchange(runtime)]
        recovered = self.root/'recovered.json'
        self.b[3].receipt(self.b[1], self.message_id, recovered)
        self.assertEqual(original, recovered.read_bytes())

    def test_cancel_and_expiry_stop_export(self):
        self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
        with self.assertRaises(TransportDenied): self.export()
        cancel = self.a[2].status(self.a[1], self.item_id)['cancel_message_id']
        self.a[3].export(self.a[1], cancel, self.packet)
        self.b[3].receive(self.b[1], self.packet)
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])

    def test_cancel_before_original_arrives_and_tamper_is_atomic(self):
        self.export()
        original = self.packet.read_bytes()
        tampered = json.loads(original)
        value = tampered['signature']
        tampered['signature'] = ('A' if value[0] != 'A' else 'B') + value[1:]
        self.packet.write_text(json.dumps(tampered))
        with self.assertRaises(TransportDenied): self.b[3].receive(self.b[1], self.packet)
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        self.assertEqual(self.b[2].db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)
        self.packet.write_bytes(original)
        cancelled = self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
        cancel_path = self.root/'cancel.json'
        self.a[3].export(self.a[1], cancelled['cancel_message_id'], cancel_path)
        self.b[3].receive(self.b[1], cancel_path)
        self.b[3].receive(self.b[1], self.packet)
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'cancelled')

    def test_expired_packet_not_applied(self):
        self.export(); self.now = 1501
        with self.assertRaises(TransportDenied): self.b[3].receive(self.b[1], self.packet)
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        with self.assertRaises(TransportDenied): self.a[3].export(self.a[1], self.message_id, self.root/'expired')

    def test_stale_cross_owner_sessions_touch_no_files(self):
        for session in (self.b[1], 'alice'):
            with self.assertRaises(AuthError): self.a[3].export(session, self.message_id, self.packet)
        self.a[0].logout(self.a[1])
        with self.assertRaises(AuthError): self.export()
        self.assertFalse(self.packet.exists())
        with self.assertRaises(AuthError): self.a[3].receive(self.a[1], self.root/'missing')

    def test_filesystem_links_modes_types_and_ancestors(self):
        self.export()
        alias = self.root/'alias'
        alias.symlink_to(self.packet)
        with self.assertRaises(OSError): read_packet(alias)
        alias.unlink(); os.link(self.packet, alias)
        with self.assertRaises(FileExchangeDenied): read_packet(alias)
        alias.unlink(); self.packet.chmod(0o644)
        with self.assertRaises(FileExchangeDenied): read_packet(self.packet)
        self.packet.chmod(0o600)
        fifo = self.root/'fifo'; os.mkfifo(fifo, 0o600)
        with self.assertRaises(FileExchangeDenied): read_packet(fifo)
        linkdir = self.root/'linkdir'; linkdir.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError): read_packet(linkdir/'packet.json')
        public = self.root/'public'; public.mkdir(mode=0o755)
        with self.assertRaises(FileExchangeDenied): write_packet(public/'new', read_packet(self.packet))
        with self.assertRaises(FileExistsError): write_packet(alias if alias.exists() else self.packet, read_packet(self.packet))

    def test_actual_byte_bounds_strict_json_and_source_changes(self):
        self.export(); original = self.packet.read_bytes()
        for raw in (b' '*MAX_PACKET + original, b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'\xff', b'['*2000):
            self.packet.write_bytes(raw)
            with self.assertRaises(FileExchangeDenied): read_packet(self.packet)
        self.packet.write_bytes(original)
        real_read = os.read
        def mutate(fd, count):
            chunk = real_read(fd, count)
            self.packet.write_bytes(original + b' ')
            return chunk
        with patch('pilot.file_exchange.os.read', side_effect=mutate):
            with self.assertRaises(FileExchangeDenied): read_packet(self.packet)

    def test_unsafe_ancestor_and_existing_output_symlink(self):
        self.export()
        unsafe = self.root/'unsafe'; unsafe.mkdir(mode=0o777); unsafe.chmod(0o777)
        private = unsafe/'private'; private.mkdir(mode=0o700)
        with self.assertRaises(FileExchangeDenied): write_packet(private/'new', read_packet(self.packet))
        link = self.root/'output-link'; link.symlink_to(self.packet)
        original = self.packet.read_bytes()
        with self.assertRaises(FileExistsError): write_packet(link, read_packet(self.packet))
        self.assertEqual(self.packet.read_bytes(), original)

    def test_runtime_interruption_after_commit_never_retries(self):
        prepare = self.a[2].prepare_delivery
        def interrupted_prepare(*args):
            prepare(*args)
            raise KeyboardInterrupt
        with patch.object(self.a[2], 'prepare_delivery', side_effect=interrupted_prepare) as call:
            with self.assertRaises(FileOutcomeUnknown): self.export()
        self.assertEqual(call.call_count, 1)
        self.assertFalse(self.packet.exists())
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['attempts'], 1)
        self.export()
        receive = self.b[2].receive
        def interrupted_receive(*args):
            receive(*args)
            raise KeyboardInterrupt
        with patch.object(self.b[2], 'receive', side_effect=interrupted_receive) as call:
            with self.assertRaises(FileOutcomeUnknown): self.b[3].receive(self.b[1], self.packet)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        self.b[3].receipt(self.b[1], self.message_id, self.receipt)

    def test_cli_private_prompt_and_redacted_success(self):
        self.a[2].close(); self.a[0].close()
        argv = ['--directory', str(self.root/'alice'), 'export', '--message-id', self.message_id, '--output', str(self.packet)]
        def insecure_prompt(_):
            warnings.warn('Cannot hide input', getpass.GetPassWarning)
            self.fail('Must not fall back to echoed input')
        with patch('pilot.file_exchange.getpass.getpass', side_effect=insecure_prompt), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(argv), 1)
        self.assertNotIn('fictional-password', output.getvalue())
        self.assertFalse(self.packet.exists())
        with patch('pilot.file_exchange.getpass.getpass', return_value='fictional-password-alice'), \
                patch('pilot.file_exchange.LocalOwnerAuth', side_effect=lambda path: LocalOwnerAuth(path, clock=lambda: self.now)), \
                patch('pilot.file_exchange.PilotRuntime', side_effect=lambda path, auth: PilotRuntime(path, auth, clock=lambda: self.now)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(argv), 0)
        self.assertEqual(json.loads(output.getvalue())['delivery'], 'uncertain')
        self.assertNotIn('SYNTHETIC PRIVATE TEXT', output.getvalue())
        self.assertNotIn('fictional-password', output.getvalue())

    def test_cli_missing_runtime_does_not_prompt_or_initialise(self):
        directory = self.root/'provisioned-only'
        auth = LocalOwnerAuth(directory)
        auth.bootstrap('fictional-third', 'third-assistant', 'fictional-third-password')
        auth.close()
        with patch('pilot.file_exchange.getpass.getpass') as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--directory', str(directory), 'export', '--message-id', self.message_id, '--output', str(self.packet)]), 1)
        prompt.assert_not_called()
        self.assertFalse((directory/'runtime.sqlite').exists())
        self.assertFalse(self.packet.exists())

    def test_cli_exclusive_lock_and_no_insecure_password_fallback(self):
        with patch('pilot.file_exchange.getpass.getpass') as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--directory', str(self.root/'alice'), 'export', '--message-id', self.message_id, '--output', str(self.packet)]), 1)
        prompt.assert_not_called()
        self.assertFalse(self.packet.exists())


if __name__ == '__main__':
    unittest.main()
