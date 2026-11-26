"""The opt-in phone address: one more exact Host name for the owner API, nothing wider."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from workspace_ui.demo import PASSWORD, seed_workspace
from workspace_ui.server import WorkspaceHTTPServer, main, phone_host

PHONE = 'my-mac.tail1234.ts.net'


class PhoneHostTests(unittest.TestCase):
    def start(self, phone):
        temporary = tempfile.TemporaryDirectory(prefix='central-phone-test-')
        self.addCleanup(temporary.cleanup)
        server = WorkspaceHTTPServer(seed_workspace(Path(temporary.name)), 0, phone_host=phone)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def close():
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.addCleanup(close)
        return server

    def request(self, server, method, path, value=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.putrequest(method, path, skip_host=True)
        for name, content in (headers or {}).items():
            connection.putheader(name, content)
        body = None
        if value is not None:
            body = json.dumps(value).encode()
            connection.putheader('Content-Type', 'application/json')
            connection.putheader('Content-Length', str(len(body)))
        connection.endheaders(body)
        try:
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_phone_signs_in_and_reads_state_through_its_own_host(self):
        server = self.start(PHONE)
        status, body = self.request(server, 'POST', '/api/session', {'password': PASSWORD}, {'Host': PHONE})
        self.assertEqual(status, 200)
        token = json.loads(body)['token']
        status, body = self.request(server, 'GET', '/api/state', headers={'Host': PHONE, 'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200)
        self.assertIn('items', json.loads(body))
        # The ordinary loopback host keeps working beside it.
        status, _ = self.request(server, 'GET', '/api/state', headers={'Host': server.host_header, 'Authorization': 'Bearer ' + token})
        self.assertEqual(status, 200)

    def test_a_web_page_cannot_use_the_phone_host(self):
        server = self.start(PHONE)
        for origin in ('https://' + PHONE, 'https://evil.example', 'null'):
            status, _ = self.request(server, 'POST', '/api/session', {'password': PASSWORD}, {'Host': PHONE, 'Origin': origin})
            self.assertEqual(status, 400, origin)

    def test_only_the_owner_api_is_reachable_through_the_phone_host(self):
        server = self.start(PHONE)
        for path in ('/', '/index.html', '/app.mjs'):
            status, _ = self.request(server, 'GET', path, headers={'Host': PHONE})
            self.assertEqual(status, 400, path)
        status, _ = self.request(server, 'POST', '/peer/inbox', {'packet': 'x'}, {'Host': PHONE, 'X-Assistant-Central-Peer': '1'})
        self.assertEqual(status, 400)

    def test_without_the_option_the_phone_host_is_refused(self):
        server = self.start(None)
        status, _ = self.request(server, 'POST', '/api/session', {'password': PASSWORD}, {'Host': PHONE})
        self.assertEqual(status, 400)

    def test_other_hosts_stay_refused(self):
        server = self.start(PHONE)
        for host in ('other.tail1234.ts.net', PHONE + ':8877', 'evil.example'):
            status, _ = self.request(server, 'POST', '/api/session', {'password': PASSWORD}, {'Host': host})
            self.assertEqual(status, 400, host)
        status, _ = self.request(server, 'POST', '/api/session', {'password': PASSWORD}, {})
        self.assertEqual(status, 400)

    def test_the_name_is_checked(self):
        self.assertEqual(phone_host('My-Mac.Tail1234.ts.net'), 'my-mac.tail1234.ts.net')
        self.assertEqual(phone_host('my-mac.tail1234.ts.net:8443'), 'my-mac.tail1234.ts.net:8443')
        for bad in ('', 'localhost', '127.0.0.1', '192.168.1.20:8877', 'mac', 'a..b', 'x.com/path', 'x.com?y', '-x.com', 'x.com:', 'two words.com'):
            with self.assertRaises(ValueError, msg=bad):
                phone_host(bad)

    def test_launcher_refuses_a_bad_name(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                main(['serve', '--directory', directory, '--phone-host', '192.168.1.20'])


if __name__ == '__main__':
    unittest.main()
