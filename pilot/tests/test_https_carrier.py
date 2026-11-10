"""Disposable local TLS PKI and real sockets only; never remote traffic."""
import concurrent.futures
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from pilot.crypto import MAX_PACKET
from pilot.file_exchange import FileExchangeDenied, read_packet
from pilot.https_carrier import CarrierOutcomeUnknown, send_file
from pilot.https_mailbox import ACK, MEDIA, ROUTE, MailboxServer, Quarantine
from pilot.tests import test_file_exchange as file_tests


def certificates(root, name='trusted', hostname='localhost', expired=False):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fictional disposable CA')])
    ca = (x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(issuer).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    paths = []
    for suffix, data in [('ca', ca.public_bytes(serialization.Encoding.PEM)),
                         ('cert', leaf.public_bytes(serialization.Encoding.PEM)),
                         ('key', leaf_key.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))]:
        path = root / (name + '.' + suffix)
        path.write_bytes(data)
        path.chmod(0o600)
        paths.append(path)
    return paths


class HTTPSCarrierTests(unittest.TestCase):
    def setUp(self):
        file_tests.FileExchangeTests.setUp(self)
        self.a[3].export(self.a[1], self.message_id, self.packet)
        self.raw = self.packet.read_bytes()
        self.spool = self.root / 'quarantine'
        self.spool.mkdir(mode=0o700)
        self.q = Quarantine(self.spool, self.b[2].fingerprint)
        self.ca, self.cert, self.key = certificates(self.root)
        self.servers = []
        self.server, self.target = self.start(self.q, self.cert, self.key)

    def start(self, q, cert, key):
        server = MailboxServer(q, cert, key, enabled=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
        thread.start()
        self.servers.append((server, thread))
        return server, f'https://localhost:{server.server_address[1]}{ROUTE}'

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()
        self.q.close()
        file_tests.FileExchangeTests.tearDown(self)

    def send(self, **kwargs):
        return send_file(self.packet, self.target, self.b[2].fingerprint,
                         ca_file=kwargs.pop('ca_file', self.ca), **kwargs)

    def wire(self, request):
        context = ssl.create_default_context(cafile=self.ca)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        with socket.create_connection(self.server.server_address, timeout=4) as tcp:
            with context.wrap_socket(tcp, server_hostname='localhost') as tls:
                tls.sendall(request)
                result = bytearray()
                while len(result) < 1024:
                    value = tls.recv(1024)
                    if not value:
                        break
                    result.extend(value)
                return bytes(result)

    def request(self, raw=None, *, method='POST', path=ROUTE, extra='', media=MEDIA, length=None):
        raw = self.raw if raw is None else raw
        return (f'{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: {media}\r\n'
                f'Content-Length: {len(raw) if length is None else length}\r\nConnection: close\r\n'
                f'{extra}\r\n').encode() + raw

    def test_real_tls_quarantine_then_authenticated_import_and_original_receipt(self):
        result = self.send()
        self.assertTrue(result['transport_acknowledged'])
        self.assertEqual(result['delivery'], 'uncertain')
        self.assertFalse(result['authorises_execution'])
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        name = hashlib.sha256(self.raw).hexdigest() + '.json'
        stored = self.spool / name
        self.assertEqual(stored.read_bytes(), self.raw)
        self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.send()['transport_acknowledged'])
        self.assertEqual(len(list(self.spool.glob('*.json'))), 1)
        self.b[3].receive(self.b[1], stored, self.receipt)
        duplicate_receipt = self.root / 'duplicate-receipt.json'
        self.b[3].receive(self.b[1], stored, duplicate_receipt)
        self.assertEqual(self.receipt.read_bytes(), duplicate_receipt.read_bytes())
        self.a[3].receive(self.a[1], self.receipt)
        self.assertEqual(self.a[2].status(self.a[1], self.item_id)['state'], 'released')
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['attempts'], 1)

    def test_wrong_hostname_ca_expired_and_plaintext(self):
        with self.assertRaises(CarrierOutcomeUnknown):
            send_file(self.packet, self.target.replace('localhost', '127.0.0.1'),
                      self.b[2].fingerprint, ca_file=self.ca)
        other_ca, _, _ = certificates(self.root, 'other')
        with self.assertRaises(CarrierOutcomeUnknown): self.send(ca_file=other_ca)
        ca, cert, key = certificates(self.root, 'expired', expired=True)
        _, target = self.start(self.q, cert, key)
        with self.assertRaises(CarrierOutcomeUnknown):
            send_file(self.packet, target, self.b[2].fingerprint, ca_file=ca)
        with socket.create_connection(self.server.server_address, timeout=4) as tcp:
            tcp.sendall(self.request())
            try: self.assertNotEqual(tcp.recv(1024), ACK)
            except ConnectionResetError: pass
        self.assertEqual(list(self.spool.glob('*.json')), [])

    def test_tls12_refused(self):
        context = ssl.create_default_context(cafile=self.ca)
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        with socket.create_connection(self.server.server_address, timeout=4) as tcp:
            with self.assertRaises(ssl.SSLError):
                context.wrap_socket(tcp, server_hostname='localhost')

    def test_strict_request_and_json(self):
        duplicates = b'{"header":{},"header":{}}'
        cases = [self.request(method='GET'), self.request(path='/owner/login'),
                 self.request(media='application/json'), self.request(length=MAX_PACKET + 1),
                 self.request(extra='Transfer-Encoding: chunked\r\n'),
                 self.request(extra='Authorization: Bearer fictional\r\n'),
                 self.request(extra='Cookie: fictional-session\r\n'),
                 self.request(extra='Content-Length: 1\r\n'), self.request(raw=duplicates),
                 self.request(raw=b'not json'), self.request(raw=b'NaN'),
                 self.request(raw=b'[' * 2000), self.request(raw=b'\xff'),
                 self.request(extra='X-Padding: ' + 'a'*2048 + '\r\n')]
        for request in cases:
            with self.subTest(request=request[:30]):
                try: self.assertNotEqual(self.wire(request), ACK)
                except (ConnectionResetError, ssl.SSLError): pass
        self.assertEqual(list(self.spool.glob('*.json')), [])

    def test_disabled_and_private_certificate_files(self):
        with self.assertRaises(FileExchangeDenied): MailboxServer(self.q, self.cert, self.key)
        self.key.chmod(0o644)
        with self.assertRaises(FileExchangeDenied):
            MailboxServer(self.q, self.cert, self.key, enabled=True)
        self.key.chmod(0o600)
        link = self.root / 'linked-key'
        link.symlink_to(self.key)
        with self.assertRaises(OSError): MailboxServer(self.q, self.cert, link, enabled=True)

    def test_capacity_concurrency_and_exact_duplicates(self):
        self.q.max_files = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            names = list(executor.map(self.q.store, [self.raw]*16))
        self.assertEqual(len(set(names)), 1)
        changed = json.loads(self.raw)
        changed['header']['message_id'] = 'different'
        with self.assertRaises(FileExchangeDenied): self.q.store(json.dumps(changed).encode())
        stored = self.spool / names[0]
        stored.write_bytes(b'changed')
        with self.assertRaises(FileExchangeDenied): self.q.store(self.raw)
        self.assertEqual(stored.read_bytes(), b'changed')

    def test_spool_lock_permissions_links_and_capacity_bytes(self):
        with self.assertRaises(BlockingIOError): Quarantine(self.spool, self.b[2].fingerprint)
        self.q.max_bytes = len(self.raw) - 1
        with self.assertRaises(FileExchangeDenied): self.q.store(self.raw)
        self.q.max_bytes = len(self.raw)
        name = self.q.store(self.raw)
        path = self.spool / name
        path.chmod(0o644)
        with self.assertRaises(FileExchangeDenied): self.q.store(self.raw)
        path.chmod(0o600)
        link = self.root / 'hardlinked'
        os.link(path, link)
        with self.assertRaises(FileExchangeDenied): self.q.store(self.raw)
        link.unlink()
        path.unlink()
        path.symlink_to(self.packet)
        with self.assertRaises(OSError): self.q.store(self.raw)

    def test_interrupted_storage_never_overwrites_and_ack_is_uncertain(self):
        with patch('pilot.https_mailbox.os.write', side_effect=OSError('fictional interruption')):
            self.assertFalse(self.send()['transport_acknowledged'])
        stored = next(self.spool.glob('*.json'))
        self.assertEqual(stored.read_bytes(), b'')
        self.assertFalse(self.send()['transport_acknowledged'])
        self.assertEqual(stored.read_bytes(), b'')
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['state'], 'uncertain')

    def test_ack_loss_no_retry_no_acceptance(self):
        with patch('pilot.https_mailbox.ACK', b'HTTP/1.1 302 Found\r\nLocation: https://example.invalid/\r\n\r\n'):
            with patch.object(self.q, 'store', wraps=self.q.store) as store:
                result = self.send()
                self.assertEqual(store.call_count, 1)
        self.assertFalse(result['transport_acknowledged'])
        self.assertEqual(result['delivery'], 'uncertain')
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        self.assertEqual(len(list(self.spool.glob('*.json'))), 1)

    def test_distinct_concurrent_packets_cannot_overfill(self):
        self.q.max_files = 2
        packets = []
        for index in range(16):
            packet = json.loads(self.raw)
            packet['header']['message_id'] = f'fictional-{index}'
            packets.append(json.dumps(packet).encode())
        def store(raw):
            try:
                self.q.store(raw)
                return True
            except FileExchangeDenied:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(sum(executor.map(store, packets)), 2)
        self.assertEqual(len(list(self.spool.glob('*.json'))), 2)

    def test_fsync_failure_retains_complete_file_without_claiming_ack(self):
        with patch('pilot.https_mailbox.os.fsync', side_effect=OSError('fictional fsync')):
            result = self.send()
        self.assertFalse(result['transport_acknowledged'])
        self.assertEqual(next(self.spool.glob('*.json')).read_bytes(), self.raw)
        # This is a new explicit attempt. Exact bytes are resynced, not rewritten.
        with patch('pilot.https_mailbox.os.write', side_effect=AssertionError('rewrite')):
            self.assertTrue(self.send()['transport_acknowledged'])

    def test_failed_connection_is_attempted_once(self):
        with patch('pilot.https_carrier.socket.create_connection', side_effect=OSError) as connect:
            with self.assertRaises(CarrierOutcomeUnknown): self.send()
            self.assertEqual(connect.call_count, 1)

    def test_target_and_recipient_must_be_explicit(self):
        for target in [self.target.replace('https:', 'http:'), self.target + '?token=x',
                       self.target + '#x', '\n' + self.target,
                       self.target.replace('localhost', 'local\nhost'),
                       self.target.replace('localhost', 'u:p@localhost')]:
            with self.assertRaises(FileExchangeDenied):
                send_file(self.packet, target, self.b[2].fingerprint, ca_file=self.ca)
        with self.assertRaises(FileExchangeDenied):
            send_file(self.packet, self.target, self.a[2].fingerprint, ca_file=self.ca)
