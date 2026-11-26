# SPDX-License-Identifier: AGPL-3.0-only
"""Relay end to end over a real local HTTP server. Fictional owners, opaque test packets."""
from pathlib import Path
import base64
import hashlib
import json
import re
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing

from acrelay.client import RelayClient, send_with_invite
from acrelay.local import serve
from acrelay.protocol import MailboxKey, RelayError, parse_invite
from acrelay.service import MAX_BODY, RETENTION, Relay
from acrelay.store import SqlStore

ALICE_FP = 'a' * 64


class RelayCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 2_000_000_000
        self.db = Path(self.tmp.name) / 'relay.sqlite'
        self.store = SqlStore.sqlite(str(self.db))
        self.relay = Relay(self.store, clock=lambda: self.now)
        self.server = serve(self.relay)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.alice = RelayClient(self.url, clock=lambda: self.now)
        self.alice.register()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.close()
        self.tmp.cleanup()

    def invite(self, **kwargs):
        return self.alice.create_invite(ALICE_FP, label='Fictional Alice', **kwargs)


class RelayTests(RelayCase):
    def test_invite_send_fetch_acknowledge(self):
        invite = self.invite()
        parsed = parse_invite(invite['link'])
        self.assertEqual((parsed['mailbox'], parsed['identity_fingerprint']), (self.alice.mailbox, ALICE_FP))
        send_with_invite(invite['link'], b'opaque-ciphertext-1')
        send_with_invite(invite['link'], b'opaque-ciphertext-2')
        batch = self.alice.fetch()
        self.assertEqual([p['body'] for p in batch['packets']], [b'opaque-ciphertext-1', b'opaque-ciphertext-2'])
        self.assertEqual({p['grant_id'] for p in batch['packets']}, {invite['grant_id']})
        self.alice.acknowledge(batch['packets'][0]['seq'])
        self.assertEqual([p['body'] for p in self.alice.fetch()['packets']], [b'opaque-ciphertext-2'])
        page = self.alice.fetch(after=batch['packets'][0]['seq'], limit=1)
        self.assertEqual(len(page['packets']), 1)

    def test_token_never_reaches_the_server_in_the_link(self):
        link = self.invite()['link']
        base, fragment = link.split('#', 1)
        self.assertEqual(base, self.url + '/invite')
        token = parse_invite(link)['send_token']
        with closing(sqlite3.connect(self.db)) as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn(token, dump)

    def test_grant_limits_expiry_and_revocation(self):
        invite = self.invite(packets=1)
        send_with_invite(invite['link'], b'one')
        with self.assertRaises(RelayError) as used:
            send_with_invite(invite['link'], b'two')
        self.assertEqual(used.exception.code, 'no_grant')
        short = self.invite(seconds=60)
        self.now += 61
        with self.assertRaises(RelayError):
            send_with_invite(short['link'], b'late')
        live = self.invite()
        self.alice.revoke(live['grant_id'])
        with self.assertRaises(RelayError):
            send_with_invite(live['link'], b'revoked')

    def test_wrong_token_and_wrong_mailbox_are_refused(self):
        invite = parse_invite(self.invite()['link'])
        bob = RelayClient(self.url, clock=lambda: self.now)
        bob.register()
        for forged in ({**invite, 'send_token': 'x' * 43}, {**invite, 'mailbox': bob.mailbox}):
            with self.subTest(forged=forged['mailbox'][:4]), self.assertRaises(RelayError):
                send_with_invite(forged, b'nope')

    def test_only_the_mailbox_key_can_read_grant_or_ack(self):
        send_with_invite(self.invite()['link'], b'secret-shaped')
        stranger = RelayClient(self.url, MailboxKey(), clock=lambda: self.now)
        stranger.key.mailbox = self.alice.mailbox  # Claims Alice's mailbox with another key.
        for call in (stranger.fetch, lambda: stranger.acknowledge(1), lambda: stranger.grant('t' * 43, seconds=60, packets=1)):
            with self.assertRaises(RelayError) as caught:
                call()
            self.assertEqual(caught.exception.status, 401)
        self.assertEqual(len(self.alice.fetch()['packets']), 1)

    def test_replayed_or_stale_signatures_are_refused(self):
        path = f'/v1/mailboxes/{self.alice.mailbox}/packets?after=0&limit=50'
        headers = self.alice.key.headers('GET', path, b'', now=self.now)
        first = self.relay.handle('GET', path, headers, b'')
        self.assertEqual(first[0], 200)
        replay = self.relay.handle('GET', path, headers, b'')
        self.assertEqual((replay[0], json.loads(replay[2])['error']), (401, 'replayed'))
        stale = self.alice.key.headers('GET', path, b'', now=self.now - 301)
        self.assertEqual(self.relay.handle('GET', path, stale, b'')[0], 401)
        # A signature for one query cannot be reused for another.
        other = self.relay.handle('GET', path.replace('after=0', 'after=5'),
                                  self.alice.key.headers('GET', path, b'', now=self.now), b'')
        self.assertEqual(other[0], 401)

    def test_packets_expire_and_size_is_bounded(self):
        link = self.invite()['link']
        send_with_invite(link, b'old')
        self.now += RETENTION + 1
        self.assertEqual(self.alice.fetch()['packets'], [])
        status = self.relay.handle('POST', f'/v1/mailboxes/{self.alice.mailbox}/packets',
                                   {'Authorization': 'Bearer ' + parse_invite(link)['send_token']}, b'x' * (MAX_BODY + 1))
        self.assertEqual(status[0], 413)

    def test_register_is_idempotent_and_self_certifying(self):
        self.assertEqual(self.alice.register()['mailbox'], self.alice.mailbox)
        other = MailboxKey()
        body = json.dumps({'public_key': __import__('acrelay.protocol', fromlist=['b64e']).b64e(other.public_bytes)}).encode()
        forged = self.alice.key.headers('POST', '/v1/mailboxes', body, now=self.now)
        self.assertEqual(self.relay.handle('POST', '/v1/mailboxes', forged, body)[0], 401)

    def test_health_source_and_invite_page(self):
        self.assertEqual(json.loads(self.relay.handle('GET', '/v1/health', {}, b'')[2])['ok'], True)
        self.assertEqual(json.loads(self.relay.handle('GET', '/source', {}, b'')[2])['licence'], 'AGPL-3.0-only')
        status, headers, page = self.relay.handle('GET', '/invite', {}, b'')
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertIn(b'never sent here', page)
        # Only the one inline script runs, pinned by its hash: it hands the address to local Parlu.
        script = re.search(rb'<script>(.*?)</script>', page, re.S).group(1)
        pinned = 'sha256-' + base64.b64encode(hashlib.sha256(script).digest()).decode()
        self.assertIn(f"script-src '{pinned}'", headers['Content-Security-Policy'])
        self.assertIn(b"'#join='+encodeURIComponent(location.href)", script)
        self.assertIn(b'href="http://127.0.0.1:8877/" hidden', page)
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        status, headers, page = self.relay.handle('GET', '/', {}, b'')
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertIn(b'Parlu relay is running', page)
        self.assertEqual(self.relay.handle('POST', '/', {}, b'')[0], 404)

    def test_parse_invite_rejects_tampered_links(self):
        link = self.invite()['link']
        for bad in (link.replace('#', '#x'), link.split('#')[0], 'https://elsewhere.example/invite#' + link.split('#')[1]):
            with self.subTest(bad=bad[:30]), self.assertRaises(RelayError):
                parse_invite(bad)

    def test_client_refuses_plain_http_to_remote_hosts(self):
        with self.assertRaises(RelayError):
            RelayClient('http://relay.example')

    def test_restart_keeps_mailboxes_grants_and_packets(self):
        link = self.invite()['link']
        send_with_invite(link, b'durable')
        self.server.shutdown(); self.server.server_close(); self.store.close()
        self.store = SqlStore.sqlite(str(self.db))
        self.relay = Relay(self.store, clock=lambda: self.now)
        self.server = serve(self.relay)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.alice.url = f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual([p['body'] for p in self.alice.fetch()['packets']], [b'durable'])


if __name__ == '__main__':
    unittest.main()
