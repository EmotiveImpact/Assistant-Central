"""Independent TLS-carrier checks, using only disposable loopback test owners."""
import hashlib
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from pilot.crypto import TransportDenied
from pilot.file_exchange import FileExchangeDenied, read_packet, write_packet
from pilot.https_carrier import CarrierOutcomeUnknown, send_file
from pilot.https_mailbox import ACK
from pilot.tests import test_https_carrier as https_tests


class HTTPSCarrierReviewTests(unittest.TestCase):
    setUp = https_tests.HTTPSCarrierTests.setUp
    tearDown = https_tests.HTTPSCarrierTests.tearDown
    start = https_tests.HTTPSCarrierTests.start
    send = https_tests.HTTPSCarrierTests.send
    wire = https_tests.HTTPSCarrierTests.wire
    request = https_tests.HTTPSCarrierTests.request

    def test_port_zero_is_rejected_without_falling_back_to_https_default(self):
        with patch('pilot.https_carrier.socket.create_connection') as connect:
            with self.assertRaises(FileExchangeDenied):
                send_file(self.packet, 'https://localhost:0/v1/quarantine', self.b[2].fingerprint, ca_file=self.ca)
            connect.assert_not_called()
        self.assertEqual(list(self.spool.glob('*.json')), [])

    def test_malicious_mailbox_ack_does_not_create_transport_receipt_or_acceptance(self):
        # Even a correctly authenticated TLS endpoint can lie about storage.
        # Its response must never become the receiver's signed receipt.
        with patch.object(self.q, 'store', return_value='not-really-stored') as store:
            result = self.send()
        self.assertEqual(store.call_count, 1)
        self.assertTrue(result['transport_acknowledged'])
        self.assertEqual(result['delivery'], 'uncertain')
        self.assertEqual(result['owner_acceptance'], 'not_established')
        self.assertEqual(list(self.spool.glob('*.json')), [])
        status = self.a[2].exchange.outbox_status(self.message_id)
        self.assertEqual(status['state'], 'uncertain')
        self.assertIsNone(status['receipt_id'])
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])

    def test_stored_forged_signature_is_rejected_by_authenticated_import(self):
        packet = read_packet(self.packet)
        packet['signature'] = ('A' if packet['signature'][0] != 'A' else 'B') + packet['signature'][1:]
        forged = self.root / 'forged.json'
        write_packet(forged, packet)
        result = send_file(forged, self.target, self.b[2].fingerprint, ca_file=self.ca)
        self.assertTrue(result['transport_acknowledged'])
        stored = next(self.spool.glob('*.json'))
        with self.assertRaises(TransportDenied):
            self.b[3].receive(self.b[1], stored, self.receipt)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])

    def test_late_storage_result_is_uncertain_and_never_retried(self):
        store = self.q.store
        def delayed(raw):
            result = store(raw)
            time.sleep(3.2)
            return result
        with patch.object(self.q, 'store', side_effect=delayed) as call:
            with self.assertRaises(CarrierOutcomeUnknown): self.send()
            self.assertEqual(call.call_count, 1)
        stored = self.spool / (hashlib.sha256(self.raw).hexdigest() + '.json')
        self.assertEqual(stored.read_bytes(), self.raw)
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['state'], 'uncertain')
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])


if __name__ == '__main__':
    unittest.main()
