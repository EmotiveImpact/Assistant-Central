import copy
import json
import os
import select
import sqlite3
import struct
import tempfile
import time
import unittest

from independent_peer.endpoint import Endpoint
from independent_peer.fixture import Experiment, PeerProcess, UncertainOutcome
from independent_peer.pipes import frame
from independent_peer.protocol import (CAPABILITY, MAX_FRAME, Rejected, b64, canonical, digest,
                                      parse, token, unb64)
from tests.test_experiment import setup_request


def write_all(fd, data, deadline):
    while data:
        if time.monotonic() >= deadline:
            raise TimeoutError('test input write deadline')
        _, writable, _ = select.select([], [fd], [], max(0, deadline - time.monotonic()))
        if writable:
            sent = os.write(fd, data[:4096])
            data = data[sent:]


class ParserTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_floats_and_large_integer(self):
        for raw in (b'{"op":"inspect","op":"cancel"}', b'{"a":NaN}', b'{"a":Infinity}',
                    b'{"a":1.5}', b'{"a":9007199254740993}'):
            with self.subTest(raw=raw), self.assertRaises(Rejected):
                parse(raw)

    def test_utf8_only_scalar_unicode(self):
        for raw in ('{"x":"a"}'.encode('utf-16'), '{"x":"a"}'.encode('utf-32'), b'{"x":"\xff"}',
                    b'{"x":"\\ud800"}', b'{"\\udfff":1}'):
            with self.subTest(raw=raw), self.assertRaises(Rejected):
                parse(raw)
        self.assertEqual(parse('{"x":"💙"}'.encode()), {'x': '💙'})

    def test_depth_before_json_construction_and_quoted_braces(self):
        with self.assertRaisesRegex(Rejected, 'depth'):
            parse(b'[' * 25 + b'0' + b']' * 25)
        self.assertEqual(parse(b'{"x":"[[[\\\"{{{]"}'), {'x': '[[["{{{]'})

    def test_frame_byte_limit_and_base64_canonical_size(self):
        for raw in (b'', b'a' * (MAX_FRAME + 1)):
            with self.assertRaises(Rejected):
                parse(raw)
        with self.assertRaises(Rejected):
            frame({'a': 'x' * MAX_FRAME})
        with self.assertRaises(Rejected):
            unb64('AA===')
        with self.assertRaises(Rejected):
            unb64('AA==', 32)


class PipeTests(unittest.TestCase):
    def spawn(self):
        directory = tempfile.TemporaryDirectory(prefix='pipe-tests-')
        peer = PeerProcess('alice', directory.name)
        self.addCleanup(directory.cleanup)
        self.addCleanup(peer.close)
        peer.owner('describe')
        return peer

    def test_oversized_zero_and_malformed_frames_terminate_without_mutation(self):
        for raw in (struct.pack('!I', MAX_FRAME + 1), struct.pack('!I', 0),
                    struct.pack('!I', 3) + b'bad', struct.pack('!I', 1) + b'\xff'):
            with self.subTest(raw=raw):
                peer = self.spawn()
                os.write(peer.peer_w, raw)
                peer.process.wait(timeout=2)
                self.assertNotEqual(peer.process.returncode, 0)
                with sqlite3.connect(peer.database) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM owner_operations').fetchone()[0], 0)

    def test_partial_peer_frame_does_not_block_owner_then_expires(self):
        peer = self.spawn()
        started = time.monotonic()
        os.write(peer.peer_w, b'\x00')
        self.assertEqual(peer.owner('inspect')['actor'], 'alice')
        peer.process.wait(timeout=3)
        self.assertGreaterEqual(time.monotonic() - started, 0.8)
        self.assertLess(time.monotonic() - started, 3)
        self.assertNotEqual(peer.process.returncode, 0)

    def test_eof_terminates_and_reaps(self):
        peer = self.spawn()
        os.close(peer.peer_w)
        peer.peer_w = -1
        peer.process.wait(timeout=2)
        self.assertEqual(peer.process.returncode, 0)
        with self.assertRaises(UncertainOutcome):
            peer.owner('inspect')

    def test_truncated_body_absolute_deadline_not_reset_by_drip(self):
        peer = self.spawn()
        started = time.monotonic()
        os.write(peer.peer_w, struct.pack('!I', 200))
        for _ in range(3):
            time.sleep(0.2)
            os.write(peer.peer_w, b' ')
        peer.process.wait(timeout=2)
        self.assertLess(time.monotonic() - started, 2)

    def test_unread_peer_responses_do_not_indefinitely_block_owner(self):
        try:
            import fcntl
        except ImportError:
            self.skipTest('Linux pipe capacity control required for deterministic backpressure')
        with Experiment() as experiment:
            _, _, request, _, _ = setup_request(experiment, deliver=False)
            peer = experiment.bob
            fcntl.fcntl(peer.peer_r, fcntl.F_SETPIPE_SZ, 4096)
            payload = frame({'op': 'deliver', 'value': request['packet']})
            # Four responses exceed the 4KiB output pipe. No peer replies are read.
            write_all(peer.peer_w, payload * 4, time.monotonic() + 0.6)
            time.sleep(0.08)
            response = peer.owner('cancel')
            self.assertEqual(response['terminal'], 'cancel')
            peer.process.wait(timeout=3)
            self.assertNotEqual(peer.process.returncode, 0)
            with sqlite3.connect(peer.database) as db:
                self.assertEqual(db.execute('SELECT terminal FROM policy').fetchone()[0], 'cancel')
                self.assertEqual(db.execute('SELECT count(*) FROM inbox').fetchone()[0], 1)
                self.assertIsNone(db.execute('SELECT processed FROM inbox').fetchone()[0])

    def test_client_uncertainty_poisoned_no_automatic_retry(self):
        peer = self.spawn()
        peer.process.terminate(); peer.process.wait(timeout=2)
        with self.assertRaises(UncertainOutcome):
            peer.owner('allow_receive')
        with self.assertRaisesRegex(UncertainOutcome, 'poisoned'):
            peer.owner('inspect')

    def test_postcommit_lost_owner_reply_is_uncertain_not_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            alice = PeerProcess('alice', directory, 'tests.postcommit_worker')
            bob = PeerProcess('bob', directory)
            try:
                a = alice.owner('describe')['descriptor']; b = bob.owner('describe')['descriptor']
                context = {'id': token(), 'context': '0' * 64, 'capability': CAPABILITY}
                alice.owner('configure', task=context, peer=b)
                bob.owner('configure', task=context, peer=a)
                grant = bob.owner('allow_receive')['grant']
                command = {'op': 'approve_send', 'operation_id': token(), 'payload': 'Fiction.', 'grant': grant}
                with self.assertRaises(UncertainOutcome):
                    alice.call('owner', command, timeout=0.15)
                with sqlite3.connect(alice.database) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
                    self.assertEqual(db.execute('SELECT count(*) FROM owner_operations').fetchone()[0], 2)
                with self.assertRaisesRegex(UncertainOutcome, 'poisoned'):
                    alice.call('owner', command)
            finally:
                alice.close(); bob.close()


class CryptoPacketTests(unittest.TestCase):
    def test_ciphertext_nonce_key_header_and_signature_tampering(self):
        with Experiment() as experiment:
            _, _, request, _, _ = setup_request(experiment, deliver=False)
            original = request['packet']
            attacks = []
            packet = copy.deepcopy(original); packet['ciphertext'] = b64(bytes([unb64(packet['ciphertext'])[0] ^ 1]) + unb64(packet['ciphertext'])[1:]); attacks.append(packet)
            for field, value in [('nonce', b64(b'0' * 12)), ('ephemeral', b64(b'0' * 32)),
                                 ('sender', 'alice-not-bound'), ('recipient', 'alice'),
                                 ('sender_binding', '0' * 64), ('recipient_binding', '1' * 64),
                                 ('protocol', 'other/1')]:
                packet = copy.deepcopy(original); packet['header'][field] = value; attacks.append(packet)
            packet = copy.deepcopy(original); packet['extra'] = 'owner'; attacks.append(packet)
            for packet in attacks:
                with self.subTest(packet=packet['header']), self.assertRaises(Rejected):
                    experiment.bob.peer('deliver', packet)
            self.assertEqual(experiment.bob.owner('inspect')['incoming'], [])
            experiment.bob.peer('deliver', original)


if __name__ == '__main__':
    unittest.main()
