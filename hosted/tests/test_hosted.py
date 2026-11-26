"""The hosted demo only re-addresses requests; the owner server still decides."""
import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer

os.environ.setdefault('PARLU_DEMO_SCHEME', 'https')
from hosted.index import PAGE_EDITS, PASSWORD, handler, original_target  # noqa: E402
from pathlib import Path  # noqa: E402

HOST = 'parlu-demo.example'


class HostedDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, token=None, origin='https://' + HOST):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        headers = {'Host': HOST}
        if origin:
            headers['Origin'] = origin
        if token:
            headers['Authorization'] = 'Bearer ' + token
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, body=raw, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data, dict(response.getheaders())

    def test_routed_paths(self):
        self.assertEqual(original_target('/hosted/index.py?parlu_path='), '/')
        self.assertEqual(original_target('/hosted/index.py?parlu_path=app.mjs'), '/app.mjs')
        self.assertEqual(original_target('/hosted/index.py?parlu_path=api/state&x=1'), '/api/state?x=1')
        self.assertEqual(original_target('/api/state?parlu_path=api/state'), '/api/state')
        self.assertIsNone(original_target('/hosted/index.py'))
        self.assertIsNone(original_target('/hosted/index.py?parlu_path=a%3Fb'))

    def test_page_shows_demo_password_and_keeps_headers(self):
        status, body, headers = self.request('GET', '/hosted/index.py?parlu_path=', origin=None)
        self.assertEqual(status, 200)
        self.assertIn(PASSWORD.encode(), body)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])

    def test_every_page_edit_still_matches_the_app(self):
        page = (Path(__file__).resolve().parents[2] / 'workspace_ui' / 'index.html').read_bytes()
        for before, _ in PAGE_EDITS:
            self.assertEqual(page.count(before), 1, before[:60])
        status, body, _ = self.request('GET', '/', origin=None)
        self.assertEqual(status, 200)
        self.assertEqual(body.count(b'data-demo-enter'), 2)
        self.assertIn(b'/hosted-demo.mjs', body)

    def test_demo_files_are_served(self):
        status, body, headers = self.request('GET', '/hosted-demo.mjs', origin=None)
        self.assertEqual(status, 200)
        self.assertIn(PASSWORD.encode(), body)
        self.assertTrue(headers['Content-Type'].startswith('text/javascript'))
        self.assertEqual(self.request('GET', '/hosted-demo.css', origin=None)[0], 200)

    def test_sign_in_and_state(self):
        status, body, _ = self.request('POST', '/api/session', {'password': PASSWORD})
        self.assertEqual(status, 200)
        token = json.loads(body)['token']
        status, body, _ = self.request('GET', '/api/state', token=token, origin=None)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['identity']['agent_id'], 'Beacon')

    def test_wrong_password_and_foreign_origin_are_refused(self):
        self.assertEqual(self.request('POST', '/api/session', {'password': 'wrong'})[0], 401)
        self.assertEqual(self.request('POST', '/api/session', {'password': PASSWORD},
                                      origin='https://elsewhere.example')[0], 400)
        self.assertEqual(self.request('POST', '/api/session', {'password': PASSWORD},
                                      origin='http://' + HOST)[0], 400)

    def test_peer_mailbox_is_not_public(self):
        self.assertEqual(self.request('POST', '/peer/inbox', {'packet': {}})[0], 404)

    def test_demo_has_the_story_money_and_a_team_mission(self):
        token = json.loads(self.request('POST', '/api/session', {'password': PASSWORD})[1])['token']
        items = json.loads(self.request('GET', '/api/state', token=token, origin=None)[1])['items']
        caps = [item['mission_cap'] for item in items if item.get('mission_cap')]
        self.assertIn({'cap_micro': 400_000_000, 'currency': 'GBP'}, caps)
        parts = [item for item in items if item['title'].startswith('Launch website: ') and item['kind'] == 'task']
        self.assertEqual(len({item['peer_id'] for item in parts}), 3)
        self.assertEqual(len({item['context'] for item in parts}), 1)

    def test_a_long_warm_instance_starts_a_fresh_workspace(self):
        import hosted.index as hosted
        first = hosted._owner_server()
        saved = hosted._seeded_at
        try:
            hosted._seeded_at = saved - hosted.MAX_AGE - 1
            second = hosted._owner_server()
            self.assertIsNot(first, second)
            self.assertIs(hosted._owner_server(), second)
        finally:
            hosted._seeded_at = max(hosted._seeded_at, saved)


if __name__ == '__main__':
    unittest.main()
