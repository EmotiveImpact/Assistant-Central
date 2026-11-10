"""Independent final-gate and no-reissue checks for explicit HTTPS exchange."""
import unittest
from unittest.mock import patch

from pilot import file_exchange
from pilot.crypto import TransportDenied
from pilot.https_exchange import HTTPSOutcomeUnknown
from pilot.runtime import RuntimeDenied
from pilot.tests import test_https_exchange as fixtures


class IndependentHTTPSReview(unittest.TestCase):
    setUp = fixtures.HTTPSExchangeTests.setUp
    tearDown = fixtures.HTTPSExchangeTests.tearDown
    send = fixtures.HTTPSExchangeTests.send
    receive = fixtures.HTTPSExchangeTests.receive
    outbox = fixtures.HTTPSExchangeTests.outbox

    def test_session_expiry_after_staging_never_contacts_carrier(self):
        def expire(path, packet):
            file_exchange.write_packet(path, packet)
            self.a[0].clock = lambda: 10000
        with patch('pilot.https_exchange.write_packet', side_effect=expire), \
                patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown):
                self.send()
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 1)
        self.assertEqual(self.a[2].db.execute('SELECT COUNT(*) FROM https_send_attempts').fetchone()[0], 1)
        self.assertEqual(list(self.spools[1].glob('*.json')), [])

    def test_peer_revocation_after_staging_never_contacts_carrier(self):
        def revoke(path, packet):
            file_exchange.write_packet(path, packet)
            self.a[2].revoke_peer(self.a[1], self.b[2].fingerprint)
        with patch('pilot.https_exchange.write_packet', side_effect=revoke), \
                patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises(HTTPSOutcomeUnknown):
                self.send()
            carrier.assert_not_called()
        self.assertEqual(self.outbox()['attempts'], 1)
        self.assertEqual(list(self.spools[1].glob('*.json')), [])

    def test_absent_cached_receipt_cannot_mint_replacement(self):
        self.receive(self.send())
        with self.b[2]._transaction(self.b[1]):
            self.b[2].db.execute('DELETE FROM peer_receipts WHERE id=?', (self.message_id,))
        with patch('pilot.https_exchange.send_file') as carrier:
            with self.assertRaises((RuntimeDenied, TransportDenied)):
                self.second.send_receipt(self.b[1], self.message_id, self.targets[0],
                                         self.a[2].fingerprint, ca_file=self.ca)
            carrier.assert_not_called()
        self.assertEqual(self.b[2].db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0], 0)
        self.assertEqual(self.second.status(self.b[1], self.message_id)['attempts'], [])


if __name__ == '__main__':
    unittest.main()
