"""Real loopback relay, real exported packets, authenticated import on each side."""
import hashlib
import threading
import unittest

from pilot.file_exchange import FileExchangeDenied
from pilot.https_mailbox import Quarantine
from pilot.relay_carrier import RelayOutcomeUnknown, fetch_into, send_file
from pilot.tests import test_file_exchange as file_tests
from relay.acrelay.client import RelayClient
from relay.acrelay.local import serve
from relay.acrelay.protocol import RelayError
from relay.acrelay.service import Relay
from relay.acrelay.store import SqlStore


class RelayCarrierTests(unittest.TestCase):
    def setUp(self):
        file_tests.FileExchangeTests.setUp(self)
        self.store = SqlStore.sqlite(str(self.root / 'relay.db'))
        self.server = serve(Relay(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()
        url = f'http://127.0.0.1:{self.server.server_port}'
        self.alice_box, self.bob_box = RelayClient(url), RelayClient(url)
        self.alice_box.register(); self.bob_box.register()
        # Each owner gives the other an invite naming their own identity fingerprint.
        self.to_bob = self.bob_box.create_invite(self.b[2].fingerprint, packets=5)['link']
        self.to_alice = self.alice_box.create_invite(self.a[2].fingerprint, packets=5)['link']
        self.queues = {}
        for name, owner in (('alice', self.a), ('bob', self.b)):
            spool = self.root / ('quarantine-' + name)
            spool.mkdir(mode=0o700)
            self.queues[name] = (spool, Quarantine(spool, owner[2].fingerprint, max_files=2))
        self.a[3].export(self.a[1], self.message_id, self.packet)
        self.raw = self.packet.read_bytes()

    def tearDown(self):
        for _, q in self.queues.values():
            q.close()
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.store.close()
        file_tests.FileExchangeTests.tearDown(self)

    def test_round_trip_through_relay_with_original_receipt(self):
        sent = send_file(self.packet, self.to_bob, self.b[2].fingerprint)
        self.assertTrue(sent['relay_stored'])
        self.assertEqual(sent['delivery'], 'uncertain')
        self.assertFalse(sent['authorises_execution'])
        # Nothing reaches Bob's state until he fetches and imports.
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])
        spool, q = self.queues['bob']
        fetched = fetch_into(self.bob_box, q)
        self.assertEqual(fetched['stored'], [hashlib.sha256(self.raw).hexdigest() + '.json'])
        self.assertEqual(self.bob_box.fetch()['packets'], [])  # Acknowledged only after storing.
        self.b[3].receive(self.b[1], spool / fetched['stored'][0], self.receipt)
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        # The signed receipt goes back the same way.
        self.assertTrue(send_file(self.receipt, self.to_alice, self.a[2].fingerprint)['relay_stored'])
        alice_spool, alice_q = self.queues['alice']
        back = fetch_into(self.alice_box, alice_q)
        self.assertEqual(len(back['stored']), 1)
        self.a[3].receive(self.a[1], alice_spool / back['stored'][0])
        self.assertEqual(self.a[2].status(self.a[1], self.item_id)['state'], 'released')

    def test_invite_must_name_the_compared_recipient(self):
        with self.assertRaises(FileExchangeDenied):
            send_file(self.packet, self.to_alice, self.b[2].fingerprint)  # Invite is for Alice.
        with self.assertRaises(FileExchangeDenied):
            send_file(self.packet, self.to_alice, self.a[2].fingerprint)  # Packet is for Bob.
        with self.assertRaises(FileExchangeDenied):
            send_file(self.packet, 'https://example.invalid/invite#bad', self.b[2].fingerprint)

    def test_used_up_or_revoked_invite_is_refused_without_retry(self):
        link = self.bob_box.create_invite(self.b[2].fingerprint, packets=1)
        self.assertTrue(send_file(self.packet, link['link'], self.b[2].fingerprint)['relay_stored'])
        again = send_file(self.packet, link['link'], self.b[2].fingerprint)
        self.assertEqual((again['relay_stored'], again['delivery']), (False, 'not_sent'))
        self.bob_box.revoke(self.bob_box.create_invite(self.b[2].fingerprint)['grant_id'])

    def test_relay_failure_is_uncertain(self):
        def broken(*_):
            raise OSError('connection reset')
        with self.assertRaises(RelayOutcomeUnknown):
            send_file(self.packet, self.to_bob, self.b[2].fingerprint, transport=broken)
        def server_error(*_):
            raise RelayError(500, 'unavailable')
        with self.assertRaises(RelayOutcomeUnknown):
            send_file(self.packet, self.to_bob, self.b[2].fingerprint, transport=server_error)

    def test_junk_is_dropped_and_repeats_are_stored_once(self):
        from relay.acrelay.client import send_with_invite
        from relay.acrelay.protocol import parse_invite
        target = parse_invite(self.to_bob)
        send_with_invite(target, b'not a packet')
        for _ in range(3):
            send_with_invite(target, self.raw)
        spool, q = self.queues['bob']
        result = fetch_into(self.bob_box, q)
        self.assertEqual(result['rejected'], 1)
        self.assertEqual(len(result['stored']), 3)  # Same bytes, one file, stored idempotently.
        self.assertEqual(len(list(spool.glob('*.json'))), 1)
        self.assertEqual(self.bob_box.fetch()['packets'], [])

    def test_command_line_round_trip(self):
        import contextlib, io, json
        from pilot import relay_cli
        url = f'http://127.0.0.1:{self.server.server_port}'
        def run(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = relay_cli.main(list(argv))
            return code, out.getvalue()
        key = str(self.root / 'bob.key')
        self.assertEqual(run('init', '--relay', url, '--key', key)[0], 0)
        self.assertEqual((self.root / 'bob.key').stat().st_mode & 0o777, 0o600)
        self.assertEqual(run('init', '--relay', url, '--key', key)[0], 0)  # Repeatable.
        code, out = run('invite', '--relay', url, '--key', key, '--fingerprint', self.b[2].fingerprint)
        link = json.loads(out)['invite']
        code, out = run('send', '--invite', link, '--recipient', self.b[2].fingerprint, '--file', str(self.packet))
        self.assertEqual((code, json.loads(out)['delivery']), (0, 'uncertain'))
        spool = self.root / 'cli-spool'
        code, out = run('fetch', '--relay', url, '--key', key, '--quarantine', str(spool),
                        '--recipient', self.b[2].fingerprint)
        self.assertEqual(len(json.loads(out)['stored']), 1)
        self.b[3].receive(self.b[1], spool / json.loads(out)['stored'][0], self.receipt)
        self.assertEqual(run('send', '--invite', link, '--recipient', self.a[2].fingerprint,
                             '--file', str(self.packet))[0], 1)

    def test_live_check_against_local_relay(self):
        from pilot import relay_live_check
        lines = []
        url = f'http://127.0.0.1:{self.server.server_port}'
        self.assertTrue(relay_live_check.run(url, say=lines.append))
        self.assertEqual(lines[-1], 'Relay check passed.')
        self.assertEqual(relay_live_check.main(['ftp://nowhere']), 2)


if __name__ == '__main__':
    unittest.main()
