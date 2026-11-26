"""Self-contained checks for the SDK: no Parlu app code needed."""
from pathlib import Path
import unittest

from parlu import ParluError
from parlu.relay import DEFAULT_RELAY, MailboxKey, RelayError, invite_link, parse_invite
from parlu.web import ParluWeb, request_for

ROOT = Path(__file__).resolve().parents[1]


class WebRequestShape(unittest.TestCase):
    def test_request_carries_protocol_envelope_and_headers(self):
        body, headers = request_for('tools/call', {'name': 'check_inbox', 'arguments': {}}, 7, 'check_inbox')
        self.assertEqual(body['id'], 7)
        self.assertEqual(body['params']['_meta']['io.modelcontextprotocol/protocolVersion'], '2026-07-28')
        self.assertEqual(body['params']['_meta']['io.modelcontextprotocol/clientCapabilities'], {})
        self.assertEqual((headers['Mcp-Method'], headers['Mcp-Name']), ('tools/call', 'check_inbox'))

    def test_only_https_or_this_computer(self):
        for bad in ('http://example.com/mcp', 'ftp://127.0.0.1/mcp', 'file:///etc/passwd'):
            with self.subTest(bad=bad), self.assertRaises(ParluError):
                ParluWeb(bad)
        ParluWeb('https://central.example/mcp')
        ParluWeb('http://127.0.0.1:8890/mcp')

    def test_unreachable_central_is_a_plain_error(self):
        with self.assertRaises(ParluError):
            ParluWeb('http://127.0.0.1:9/mcp', timeout=2).pending()


class RelayProtocol(unittest.TestCase):
    def test_invite_round_trip_and_tamper(self):
        key = MailboxKey.from_seed(b'\x01' * 32)
        link = invite_link(DEFAULT_RELAY, key.mailbox, 'tok' * 11, 'a' * 64, 'Fictional')
        parsed = parse_invite(link)
        self.assertEqual(parsed['identity_fingerprint'], 'a' * 64)
        with self.assertRaises(RelayError):
            parse_invite(link.replace('#', '#x'))

    def test_copy_matches_the_relay_service(self):
        service = ROOT.parents[1] / 'relay' / 'acrelay'
        if not service.exists():
            self.skipTest('Relay service is not in this checkout.')
        for name in ('protocol.py', 'client.py'):
            self.assertEqual((ROOT / 'parlu' / 'relay' / name).read_bytes(), (service / name).read_bytes(), name)


if __name__ == '__main__':
    unittest.main()
