"""Authenticated synthetic owners and real loopback TLS, including crash gaps."""
import contextlib
import getpass
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch
import warnings

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import TransportDenied, canonical
from pilot.https_carrier import CarrierOutcomeUnknown, send_file
from pilot.https_exchange import HTTPSExchange, HTTPSOutcomeUnknown, main
from pilot.https_mailbox import MailboxServer, Quarantine, ROUTE
from pilot.runtime import PilotRuntime, RuntimeDenied
from pilot.tests import test_file_exchange as file_tests
from pilot.tests.test_https_carrier import certificates


class HTTPSExchangeTests(unittest.TestCase):
    def setUp(self):
        file_tests.FileExchangeTests.setUp(self)
        self.first, self.second = HTTPSExchange(self.a[2]), HTTPSExchange(self.b[2])
        self.ca, cert, key = certificates(self.root)
        self.mailboxes = []
        self.spools = []
        self.targets = []
        for owner in self.owners:
            spool = self.root / (owner[2].identity['owner_id'] + '-quarantine')
            spool.mkdir(mode=0o700)
            q = Quarantine(spool, owner[2].fingerprint)
            server = MailboxServer(q, cert, key, enabled=True)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
            thread.start()
            self.mailboxes.append((q, server, thread))
            self.spools.append(spool)
            self.targets.append(f'https://localhost:{server.server_address[1]}{ROUTE}')

    def tearDown(self):
        for q, server, thread in self.mailboxes:
            server.shutdown(); server.server_close(); thread.join(); q.close()
        file_tests.FileExchangeTests.tearDown(self)

    def send(self, **kwargs):
        return self.first.send(self.a[1], self.message_id, self.targets[1], self.b[2].fingerprint,
                               ca_file=self.ca, **kwargs)

    def receive(self, result, receiver=1, sender=0):
        owner = self.owners[receiver]
        return HTTPSExchange(owner[2]).receive(owner[1], self.spools[receiver] / (result['file_digest'] + '.json'),
                                               self.owners[sender][2].fingerprint, result['file_digest'])

    def outbox(self):
        return self.a[2].exchange.outbox_status(self.message_id)

    def test_real_tls_auth_import_explicit_retry_original_receipt_and_decision(self):
        original = self.a[2].exchange._outbox(self.message_id)['packet'].encode()
        first = self.send()
        self.assertTrue(first['transport_acknowledged'])
        self.assertEqual(first['delivery'], 'uncertain')
        self.assertEqual(self.outbox()['state'], 'uncertain')
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        stored = self.spools[1] / (first['file_digest'] + '.json')
        self.assertEqual(stored.read_bytes(), original)
        with self.assertRaises(RuntimeDenied): self.send()
        second = self.send(retry=True)
        self.assertEqual(first['packet_digest'], second['packet_digest'])
        self.assertEqual(self.outbox()['attempts'], 2)
        self.assertFalse(self.receive(first)['duplicate'])
        self.assertTrue(self.receive(first)['duplicate'])
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        receipt = self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, ca_file=self.ca)
        self.assertEqual(receipt['delivery'], 'uncertain')
        with self.assertRaises(RuntimeDenied):
            self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, ca_file=self.ca)
        repeated = self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, retry=True, ca_file=self.ca)
        self.assertEqual(receipt['file_digest'], repeated['file_digest'])
        self.assertFalse(self.receive(receipt, receiver=0, sender=1)['receipt_available'])
        self.assertEqual(self.outbox()['state'], 'received')
        self.assertEqual(self.a[2].status(self.a[1], self.item_id)['state'], 'released')
        with self.assertRaises((TransportDenied, RuntimeDenied)):
            self.first.send_receipt(self.a[1], receipt['message_id'], self.targets[1], self.b[2].fingerprint, ca_file=self.ca)
        decision = self.b[2].decide(self.b[1], self.item_id, self.b[2].review(self.b[1], self.item_id)['review_digest'], 'accept')
        sent = self.second.send(self.b[1], 'decision-' + decision['decision_digest'], self.targets[0], self.a[2].fingerprint, ca_file=self.ca)
        self.assertEqual(self.receive(sent, receiver=0, sender=1)['owner_acceptance'], 'accepted')
        self.assertFalse(sent['authorises_execution'])

    def test_accounting_commits_before_network_without_open_transaction(self):
        real_send = send_file
        def inspect(source, target, recipient, **kwargs):
            self.assertFalse(self.a[2].db.in_transaction)
            with sqlite3.connect(self.root / 'alice' / 'runtime.sqlite') as db:
                self.assertEqual(db.execute('SELECT attempts,state FROM peer_outbox WHERE id=?', (self.message_id,)).fetchone(), (1, 'uncertain'))
                self.assertEqual(db.execute('SELECT state FROM https_send_attempts').fetchone(), ('uncertain',))
            self.assertEqual(Path(source).read_bytes(), self.a[2].exchange._outbox(self.message_id)['packet'].encode())
            return real_send(source, target, recipient, **kwargs)
        with patch('pilot.https_exchange.send_file', side_effect=inspect) as call:
            self.send()
            self.assertEqual(call.call_count, 1)

    def test_no_auth_or_runtime_lock_held_during_carrier_and_late_cancel_is_retained(self):
        real_send = send_file
        def inspect(source, target, recipient, **kwargs):
            acquired = []
            def locks():
                for lock in (self.a[0]._lock, self.a[2]._lock):
                    success = lock.acquire(timeout=0.5)
                    acquired.append(success)
                    if success: lock.release()
            worker = threading.Thread(target=locks)
            worker.start(); worker.join(timeout=2)
            self.assertEqual(acquired, [True, True])
            self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
            # The final gate has passed: subsequent cancellation cannot recall bytes.
            return real_send(source, target, recipient, **kwargs)
        with patch('pilot.https_exchange.send_file', side_effect=inspect):
            result = self.send()
        self.assertTrue(result['transport_acknowledged'])
        self.assertEqual(result['delivery'], 'uncertain')
        self.assertEqual(self.outbox()['state'], 'cancelled')
        with self.assertRaises((RuntimeDenied, TransportDenied)): self.send(retry=True)

    def test_journal_failure_rolls_back_outbox_attempt_and_never_sends(self):
        with self.a[2]._transaction(self.a[1]):
            self.first._schema()
            self.a[2].db.execute("CREATE TRIGGER fail_journal BEFORE INSERT ON https_send_attempts BEGIN SELECT RAISE(ABORT,'fictional failure'); END")
        with patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown): self.send()
            carrier.assert_not_called()
        self.assertEqual((self.outbox()['attempts'], self.outbox()['state']), (0, 'queued'))
        self.assertEqual(self.first.status(self.a[1], self.message_id)['attempts'], [])

    def test_interrupt_after_commit_retains_one_attempt_and_requires_retry(self):
        prepare = self.first._prepare
        def interrupted(*args):
            prepare(*args)
            raise KeyboardInterrupt
        with patch.object(self.first, '_prepare', side_effect=interrupted), patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown): self.send()
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 1)
        self.assertEqual(len(self.first.status(self.a[1], self.message_id)['attempts']), 1)
        with self.assertRaises(RuntimeDenied): self.send()
        self.assertTrue(self.send(retry=True)['transport_acknowledged'])

    def test_lost_connection_dishonest_ack_and_failure_never_authorise(self):
        with patch('pilot.https_exchange.send_file', side_effect=CarrierOutcomeUnknown) as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown): self.send()
            self.assertEqual(carrier.call_count, 1)
        q = self.mailboxes[1][0]
        with patch.object(q, 'store', return_value='not-stored'):
            result = self.send(retry=True)
        self.assertTrue(result['transport_acknowledged'])
        self.assertFalse(list(self.spools[1].glob('*.json')))
        self.assertEqual(self.outbox()['state'], 'uncertain')
        self.assertIsNone(self.outbox()['receipt_id'])
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        self.assertEqual([row['state'] for row in self.first.status(self.a[1], self.message_id)['attempts']], ['uncertain'] * 2)

    def test_wrong_session_destination_recipient_and_unreleased_id_do_not_send(self):
        with patch('pilot.https_exchange.send_file') as carrier:
            for session in (self.b[1], 'bad'):
                with self.assertRaises(AuthError):
                    self.first.send(session, self.message_id, self.targets[1], self.b[2].fingerprint)
            for target in ('http://localhost/v1/quarantine', 'https://localhost:0/v1/quarantine',
                           self.targets[1] + '?password=x', self.targets[1] + '#x',
                           'https://user:secret@localhost/v1/quarantine', 'https://localhost:broken/v1/quarantine'):
                with self.assertRaises(RuntimeDenied):
                    self.first.send(self.a[1], self.message_id, target, self.b[2].fingerprint)
            with self.assertRaises(RuntimeDenied):
                self.first.send(self.a[1], self.message_id, self.targets[1], self.a[2].fingerprint)
            with self.assertRaises(TransportDenied):
                self.first.send(self.a[1], 'unreleased', self.targets[1], self.b[2].fingerprint)
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 0)

    def test_logout_expiry_and_revoked_peer_stop_new_attempt(self):
        self.a[0].logout(self.a[1])
        with self.assertRaises(AuthError): self.send()
        self.a[1] = self.a[0].login('fictional-password-alice')
        self.a[2].revoke_peer(self.a[1], self.b[2].fingerprint)
        with patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(TransportDenied): self.send()
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 0)

    def test_expiry_after_preparation_stops_carrier_but_retains_attempt(self):
        from pilot.file_exchange import write_packet
        def expire(path, packet):
            write_packet(path, packet)
            self.now = 1501
        with patch('pilot.https_exchange.write_packet', side_effect=expire), patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown): self.send()
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 1)

    def test_cancel_blocks_original_but_explicit_cancel_packet_can_be_sent(self):
        original = self.send()
        cancelled = self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
        with self.assertRaises((TransportDenied, RuntimeDenied)): self.send(retry=True)
        notice = self.first.send(self.a[1], cancelled['cancel_message_id'], self.targets[1], self.b[2].fingerprint, ca_file=self.ca)
        self.receive(notice)
        self.receive(original)
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'cancelled')
        self.assertFalse(notice['authorises_execution'])

    def test_source_cancellation_stops_already_queued_artifact(self):
        self.receive(self.send())
        self.b[2].decide(self.b[1], self.item_id, self.b[2].review(self.b[1], self.item_id)['review_digest'], 'accept')
        artifact = self.b[2].propose(self.b[1], self.a[2].fingerprint, 'artifact', 'Fictional result',
                                   'Synthetic result only', 'a' * 64, 'garden', 1400, self.item_id)
        released = self.b[2].release(self.b[1], artifact['id'], self.b[2].review(self.b[1], artifact['id'])['review_digest'])
        self.b[2].cancel(self.b[1], self.item_id, self.b[2].review(self.b[1], self.item_id)['review_digest'])
        with patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(RuntimeDenied):
                self.second.send(self.b[1], released['message_id'], self.targets[0], self.a[2].fingerprint, ca_file=self.ca)
            carrier.assert_not_called()
        self.assertEqual(self.b[2].exchange.outbox_status(released['message_id'])['attempts'], 0)

    def test_attempt_cap_includes_previous_file_exports_and_journal_capacity(self):
        self.a[3].export(self.a[1], self.message_id, self.packet)
        with self.assertRaises(RuntimeDenied): self.send()
        for _ in range(4): self.send(retry=True)
        with self.assertRaises(TransportDenied): self.send(retry=True)
        self.assertEqual(self.outbox()['attempts'], 5)
        self.assertEqual(len(self.first.status(self.a[1], self.message_id)['attempts']), 4)

    def test_selected_digest_sender_and_tampered_signature_fail_without_apply(self):
        result = self.send()
        path = self.spools[1] / (result['file_digest'] + '.json')
        with self.assertRaises(RuntimeDenied):
            self.second.receive(self.b[1], path, self.a[2].fingerprint, 'f' * 64)
        with self.assertRaises(RuntimeDenied):
            self.second.receive(self.b[1], path, self.b[2].fingerprint, result['file_digest'])
        packet = json.loads(path.read_bytes())
        packet['signature'] = ('A' if packet['signature'][0] != 'A' else 'B') + packet['signature'][1:]
        forged = canonical(packet)
        name = self.mailboxes[1][0].store(forged)
        with self.assertRaises(TransportDenied):
            self.second.receive(self.b[1], self.spools[1] / name, self.a[2].fingerprint, name[:-5])
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        self.assertEqual(self.b[2].db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)

    def test_import_interruption_leaves_cached_receipt_and_duplicate_is_explicit(self):
        sent = self.send()
        receive = self.b[2].receive
        def interrupt(*args):
            receive(*args)
            raise KeyboardInterrupt
        with patch.object(self.b[2], 'receive', side_effect=interrupt) as call:
            with self.assertRaises(HTTPSOutcomeUnknown): self.receive(sent)
            self.assertEqual(call.call_count, 1)
        self.assertTrue(self.receive(sent)['duplicate'])
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')

    def test_missing_cached_receipt_fails_closed_without_regeneration(self):
        self.receive(self.send())
        self.b[2].db.execute('DELETE FROM peer_receipts WHERE id=?', (self.message_id,))
        with patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(RuntimeDenied):
                self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, ca_file=self.ca)
            carrier.assert_not_called()
        self.assertEqual(self.b[2].db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0], 0)
        self.assertEqual(self.second.status(self.b[1], 'receipt-' + self.message_id)['attempts'], [])

    def test_receipt_attempt_bound_expiry_and_total_journal_capacity(self):
        self.receive(self.send())
        for attempt in range(5):
            receipt = self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint,
                                               retry=attempt > 0, ca_file=self.ca)
        with self.assertRaises(RuntimeDenied):
            self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, retry=True, ca_file=self.ca)
        with patch('pilot.https_exchange.MAX_HISTORY', 1):
            with self.assertRaises(RuntimeDenied): self.send(retry=True)
        self.assertEqual(self.outbox()['attempts'], 1)
        self.now = 4601
        # Login again: packet expiry, rather than an expired owner session, gates this operation.
        self.b[1] = self.b[0].login('fictional-password-bob')
        with self.assertRaises(RuntimeDenied):
            self.second.send_receipt(self.b[1], self.message_id, self.targets[0], self.a[2].fingerprint, retry=True, ca_file=self.ca)
        self.assertEqual(len(self.second.status(self.b[1], receipt['message_id'])['attempts']), 5)

    def test_restart_retains_uncertainty_original_bytes_and_receipt_attempts(self):
        first = self.send()
        old_session = self.a[1]
        self.a[2].close(); self.a[0].close()
        auth = LocalOwnerAuth(self.root / 'alice', clock=lambda: self.now)
        runtime = PilotRuntime(self.root / 'alice', auth, clock=lambda: self.now)
        self.a[:] = [auth, auth.login('fictional-password-alice'), runtime, None]
        self.first = HTTPSExchange(runtime)
        with self.assertRaises(AuthError): self.first.status(old_session, self.message_id)
        self.assertEqual(len(self.first.status(self.a[1], self.message_id)['attempts']), 1)
        with self.assertRaises(RuntimeDenied): self.send()
        self.assertEqual(first['file_digest'], self.send(retry=True)['file_digest'])

    def test_cli_missing_runtime_and_busy_service_do_not_prompt(self):
        with patch('pilot.https_exchange.getpass.getpass') as prompt:
            for directory in (self.root / 'missing', self.root / 'alice'):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--directory', str(directory), 'status', '--message-id', self.message_id]), 1)
            prompt.assert_not_called()
        self.assertFalse((self.root / 'missing').exists())

    def test_cli_private_prompt_and_redacted_send(self):
        self.a[2].close(); self.a[0].close()
        argv = ['--directory', str(self.root / 'alice'), 'send', '--message-id', self.message_id,
                '--destination', self.targets[1], '--recipient', self.b[2].fingerprint, '--ca-file', str(self.ca)]
        def unsafe(_): warnings.warn('Cannot hide', getpass.GetPassWarning)
        with patch('pilot.https_exchange.getpass.getpass', side_effect=unsafe), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(argv), 1)
        with patch('pilot.https_exchange.getpass.getpass', return_value='fictional-password-alice'), \
             patch('pilot.https_exchange.LocalOwnerAuth', side_effect=lambda path: LocalOwnerAuth(path, clock=lambda: self.now)), \
             patch('pilot.https_exchange.PilotRuntime', side_effect=lambda path, auth: PilotRuntime(path, auth, clock=lambda: self.now)), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(argv), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['delivery'], 'uncertain')
        for secret in ('fictional-password', 'SYNTHETIC PRIVATE TEXT', self.a[1]):
            self.assertNotIn(secret, output.getvalue())


if __name__ == '__main__':
    unittest.main()
