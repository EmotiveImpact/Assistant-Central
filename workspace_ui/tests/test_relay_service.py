"""Invite routes over the real workspace HTTP server: off by default, owner session required."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from relay.acrelay.local import serve
from relay.acrelay.service import Relay
from relay.acrelay.store import SqlStore
from workspace_ui.demo import PASSWORD
from workspace_ui.server import STATIC_FILES, WorkspaceHTTPServer


def owner(root, name, agent):
    auth = LocalOwnerAuth(Path(root) / name)
    try:
        auth.bootstrap(name, agent, PASSWORD)
    finally:
        auth.close()
    return Path(root) / name


class RelayRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='parlu-relay-route-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = SqlStore.sqlite(str(self.root / 'relay.sqlite'))
        self.relay = serve(Relay(self.store))
        threading.Thread(target=self.relay.serve_forever, daemon=True).start()
        self.addCleanup(self.close_relay)

    def close_relay(self):
        self.relay.shutdown(); self.relay.server_close(); self.store.close()

    def start(self, directory, relay_url=None):
        server = WorkspaceHTTPServer(directory, 0, relay_url=relay_url)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join(timeout=5), server.server_close()))
        return server

    def call(self, server, method, path, value=None, token=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        headers = {}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        body = None
        if value is not None:
            body = json.dumps(value)
            headers['Content-Type'] = 'application/json'
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b'{}')
        finally:
            connection.close()

    def login(self, server):
        return self.call(server, 'POST', '/api/session', {'password': PASSWORD})[1]['token']

    def test_relay_is_off_unless_the_host_chooses_one(self):
        server = self.start(owner(self.root, 'edem', 'Juniper'))
        token = self.login(server)
        status, state = self.call(server, 'GET', '/api/state', token=token)
        self.assertEqual(status, 200)
        self.assertNotIn('relay', state)
        self.assertEqual(self.call(server, 'POST', '/api/invites', {}, token)[0], 400)
        self.assertIn('/qr.mjs', STATIC_FILES)
        self.assertIn('/invites.mjs', STATIC_FILES)

    def test_invite_routes_need_the_owner_and_exact_fields(self):
        server = self.start(owner(self.root, 'edem', 'Juniper'), f'http://127.0.0.1:{self.relay.server_port}')
        self.assertEqual(self.call(server, 'POST', '/api/invites', {})[0], 401)
        self.assertEqual(self.call(server, 'GET', '/api/state')[0], 401)
        token = self.login(server)
        state = self.call(server, 'GET', '/api/state', token=token)[1]
        self.assertEqual((state['relay']['enabled'], state['relay']['invites'], state['relay']['mailbox_ready']),
                         (True, [], False))
        status, made = self.call(server, 'POST', '/api/invites', {'label': 'Maya', 'hours': 24}, token)
        self.assertEqual((status, made['made'], made['label']), (200, True, 'Maya'))
        self.assertEqual(self.call(server, 'POST', '/api/invites', {'label': 'x', 'extra': 1}, token)[0], 400)
        self.assertEqual(self.call(server, 'POST', '/api/invites', {'hours': 9999}, token)[0], 400)
        self.assertEqual(self.call(server, 'GET', f"/api/invites/{made['id']}", token=token)[1]['link'], made['link'])
        # Opening your own invite is refused before anything is added or sent.
        self.assertEqual(self.call(server, 'POST', '/api/invites/open', {'link': made['link']}, token)[1]['reason'],
                         'own_invite')
        self.assertEqual(self.call(server, 'POST', '/api/invites/open', {'link': 'not a link'}, token)[0], 400)
        self.assertEqual(self.call(server, 'POST', '/api/relay/sync', {'send': 'yes'}, token)[0], 400)
        self.assertEqual(self.call(server, 'POST', '/api/relay/sync', {'send': False}, token)[1]['relay'], 'ok')
        self.assertEqual(self.call(server, 'POST', f"/api/invites/{made['id']}/revoke", {}, token)[1]['revoked'], True)
        self.assertEqual(self.call(server, 'GET', f"/api/invites/{made['id']}", token=token)[0], 400)
        # Everything else is still the owner's ordinary API.
        self.assertEqual(self.call(server, 'POST', '/api/exchange', {}, token)[0], 200)

    def maya(self, name):
        auth = LocalOwnerAuth(owner(self.root, name, 'Otto'))
        try:
            return auth.public_identity()
        finally:
            auth.close()

    def enrol(self, server, token, public):
        return self.call(server, 'POST', '/api/peers', {'public_identity': public, 'expected_fingerprint': fingerprint(public),
                                                        'endpoint': 'http://127.0.0.1:9999'}, token)[0]

    def test_revoking_an_assistant_is_final_and_needs_the_owner(self):
        for relay_url in (None, f'http://127.0.0.1:{self.relay.server_port}'):
            with self.subTest(relay=bool(relay_url)):
                server = self.start(owner(self.root, f'edem-{bool(relay_url)}', 'Juniper'), relay_url)
                token = self.login(server)
                public = self.maya(f'maya-{bool(relay_url)}')
                pin = fingerprint(public)
                self.assertEqual(self.enrol(server, token, public), 200)
                path = f'/api/peers/{pin}/revoke'
                self.assertEqual(self.call(server, 'POST', path, {})[0], 401)
                self.assertEqual(self.call(server, 'POST', path, {'extra': 1}, token)[0], 400)
                self.assertEqual(self.call(server, 'POST', '/api/peers/' + 'f' * 64 + '/revoke', {}, token)[0], 400)
                status, result = self.call(server, 'POST', path, {}, token)
                self.assertEqual((status, result['revoked'], result['peer_id']), (200, True, pin))
                self.assertEqual('relay' in result, bool(relay_url))
                peers = self.call(server, 'GET', '/api/state', token=token)[1]['peers']
                self.assertEqual([(p['peer_id'], p['state']) for p in peers], [(pin, 'revoked')])
                # A revoked key cannot be added back.
                self.assertEqual(self.enrol(server, token, public), 400)

if __name__ == '__main__':
    unittest.main()
