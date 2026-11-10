"""Real official-SDK/MCP draft creation then current authenticated owner HTTP."""
import copy
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.server import RequestDenied
from workspace_ui.host_draft_fixture import DRAFT, PASSWORD, seed_host_review, sdk_seed, install_review
from workspace_ui.host_draft_service import HostDraftConfig, HostDraftService, run_review_helper
from workspace_ui.server import WorkspaceHTTPServer


class HostDraftHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='host-draft-http-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.owner_dir, self.config, self.launch, self.seeded = seed_host_review(self.root)
        self.open_server()
        self.addCleanup(self.close)
        self.route = '/api/host-drafts/fixture/' + self.seeded['draftId']

    def open_server(self):
        self.server = WorkspaceHTTPServer(self.owner_dir, 0, host_draft_config=HostDraftConfig(self.config))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if self.server:
            self.server.shutdown()
            self.thread.join(5)
            self.server.server_close()
            self.server = None

    def request(self, method, path, value=None, token=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        h = dict(headers or {})
        if token:
            h['Authorization'] = 'Bearer ' + token
        if value is not None:
            h['Content-Type'] = 'application/json'
        try:
            conn.request(method, path, body=None if value is None else json.dumps(value), headers=h)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def login(self):
        code, raw = self.request('POST', '/api/session', {'password': PASSWORD})
        self.assertEqual(code, 200)
        return json.loads(raw)['token']

    def review(self, token):
        code, raw = self.request('GET', self.route + '/review', token=token)
        self.assertEqual(code, 200)
        return json.loads(raw)

    def test_sdk_to_current_owner_exact_http_review_and_no_action(self):
        self.assertTrue(self.seeded['officialRunner'] and self.seeded['mcp'])
        self.assertEqual(self.request('GET', '/api/host-drafts')[0], 401)
        token = self.login()
        code, raw = self.request('GET', '/api/host-drafts', token=token)
        self.assertEqual(code, 200)
        queue = json.loads(raw)
        self.assertEqual(queue['connections'][0]['items'][0]['draftId'], self.seeded['draftId'])
        r = self.review(token)
        self.assertEqual(r['draft'], DRAFT)
        self.assertEqual(r['binding'], self.launch['binding'])
        self.assertEqual(r['status']['execution'], 'not_started')
        self.assertEqual(r['status']['transportReceipt'], 'none')
        state = json.loads(self.request('GET', '/api/state', token=token)[1])
        self.assertFalse(state['provider']['live_enabled'])
        self.assertEqual(state['items'], [])
        self.assertEqual(state['outbox'], [])

    def test_duplicate_dismiss_abandoned_response_restart_and_new_session_review(self):
        token = self.login()
        r = self.review(token)
        decision = {'digest': r['digest'], 'reviewToken': r['reviewToken']}
        code, raw = self.request('POST', self.route + '/dismiss', decision, token)
        self.assertEqual(code, 200)
        saved = json.loads(raw)
        self.assertEqual(saved['status']['state'], 'dismissed')
        self.assertEqual(self.request('POST', self.route + '/dismiss', decision, token), (code, raw))
        # A committed response is deliberately discarded; only inspection follows.
        self.request('POST', self.route + '/dismiss', decision, token)
        old_token = token
        self.close()
        self.open_server()
        self.assertEqual(self.request('GET', self.route + '/review', token=old_token)[0], 401)
        token = self.login()
        self.assertEqual(self.request('POST', self.route + '/dismiss', decision, token)[0], 400)
        fresh = self.review(token)
        self.assertEqual(fresh['decision'], saved['decision'])
        new = {'digest': fresh['digest'], 'reviewToken': fresh['reviewToken']}
        self.assertEqual(json.loads(self.request('POST', self.route + '/dismiss', new, token)[1]), saved)
        with sqlite3.connect(self.launch['storePath']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 1)

    def test_wrong_session_owner_scope_digest_and_unanticipated_schema_denied(self):
        token, other_session = self.login(), self.login()
        r = self.review(token)
        body = {'digest': r['digest'], 'reviewToken': r['reviewToken']}
        self.assertEqual(self.request('POST', self.route + '/dismiss', body, other_session)[0], 400)
        for change in ({'digest': '0' * 64}, {'reviewToken': r['reviewToken'] + 'x'}, {'decision': 'approve'}, {'storePath': '/tmp/evil'}):
            altered = dict(body, **change)
            self.assertEqual(self.request('POST', self.route + '/dismiss', altered, token)[0], 400)
        for route in ('/api/host-drafts/unknown/'+self.seeded['draftId']+'/review', '/api/host-drafts/fixture/missing/review', self.route+'/execute'):
            self.assertEqual(self.request('GET', route, token=token)[0], 400)
        other_dir = self.root / ('other_' + str(time.monotonic_ns()))
        other = LocalOwnerAuth(other_dir)
        try:
            other.bootstrap('other', 'other_agent', PASSWORD)
            foreign = other.login(PASSWORD)
            self.assertEqual(self.request('GET', self.route + '/review', token=foreign)[0], 401)
        finally:
            other.close()
        self.request('DELETE', '/api/session', {}, token)
        self.assertEqual(self.request('GET', self.route + '/review', token=token)[0], 401)

    def test_helper_commits_then_loses_response_is_uncertain_and_saved_once(self):
        token = self.login()
        r = self.review(token)
        body = {'digest': r['digest'], 'reviewToken': r['reviewToken']}
        def committed_but_lost(request):
            run_review_helper(request)
            raise TimeoutError('fixture lost helper response')
        with patch('workspace_ui.host_draft_service.run_review_helper', side_effect=committed_but_lost):
            self.assertEqual(self.request('POST', self.route + '/dismiss', body, token)[0], 503)
        self.assertEqual(self.review(token)['status']['state'], 'dismissed')
        with sqlite3.connect(self.launch['storePath']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 1)

    def test_current_launch_replacement_and_expiry_refuse_old_review_without_paths_or_secrets(self):
        token = self.login()
        r = self.review(token)
        body = {'digest': r['digest'], 'reviewToken': r['reviewToken']}
        path = Path(self.config['connections'][0]['launch_file'])
        original = path.read_text()
        for field, value in (('recipientId', 'new_recipient'), ('ownerId', '0'*64), ('expiresAt', 1)):
            changed = copy.deepcopy(self.launch)
            changed['binding'][field] = value
            try:
                path.write_text(json.dumps(changed))
                code, raw = self.request('POST', self.route + '/dismiss', body, token)
                self.assertEqual(code, 400)
                self.assertNotIn(self.launch['keyHex'].encode(), raw)
                self.assertNotIn(str(path).encode(), raw)
                self.assertFalse(json.loads(self.request('GET', '/api/host-drafts', token=token)[1])['connections'][0]['available'])
            finally:
                path.write_text(original)

    def test_host_revocation_blocks_reads_and_old_owner_decision(self):
        token = self.login()
        r = self.review(token)
        sdk_seed(self.launch, self.root, operation='revoke')
        self.assertEqual(self.request('GET', self.route+'/review', token=token)[0], 400)
        self.assertEqual(self.request('POST', self.route+'/dismiss', {'digest':r['digest'], 'reviewToken':r['reviewToken']}, token)[0], 400)
        catalogue = json.loads(self.request('GET', '/api/host-drafts', token=token)[1])
        self.assertEqual(catalogue['connections'], [{'id':'fixture', 'available':False, 'items':[]}])
        with sqlite3.connect(self.launch['storePath']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 0)

    def test_owner_expiry_during_helper_denies_before_dismiss_commit(self):
        def short_session():
            return self.server.owner.underlying.auth.login(PASSWORD, ttl=2)
        token = self.server.owner_worker.submit(short_session).result()
        r = self.review(token)
        def delay(request):
            time.sleep(2.1)
            return run_review_helper(request)
        with patch('workspace_ui.host_draft_service.run_review_helper', side_effect=delay):
            self.assertEqual(self.request('POST', self.route+'/dismiss', {'digest':r['digest'], 'reviewToken':r['reviewToken']}, token)[0], 400)
        with sqlite3.connect(self.launch['storePath']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 0)
        self.assertEqual(self.request('GET', '/api/host-drafts', token=token)[0], 401)

    def test_private_launch_config_owner_mapping_and_symlinks_refused(self):
        invalid = copy.deepcopy(self.config)
        invalid['connections'][0]['owner_fingerprint'] = '0'*64
        def construct():
            HostDraftService(self.server.owner.underlying, HostDraftConfig(invalid))
        with self.assertRaises(RequestDenied):
            self.server.owner_worker.submit(construct).result()
        path = Path(self.config['connections'][0]['launch_file'])
        os.chmod(path, 0o644)
        try:
            with self.assertRaises(PermissionError): HostDraftConfig(self.config)
        finally:
            os.chmod(path, 0o600)
        link = self.root / ('symlink_' + str(time.monotonic_ns()))
        link.symlink_to(path)
        invalid['connections'][0]['launch_file'] = str(link)
        with self.assertRaises(RequestDenied): HostDraftConfig(invalid)

    def test_cross_origin_wrong_host_and_no_plaintext_on_disk(self):
        token = self.login()
        for headers in ({'Origin': 'https://evil.invalid'}, {'Host':'evil.invalid'}):
            self.assertEqual(self.request('GET', '/api/host-drafts', token=token, headers=headers)[0], 400)
            self.assertEqual(self.request('POST', self.route+'/dismiss', {}, token, headers)[0], 400)
        self.assertEqual(self.request('OPTIONS', '/api/host-drafts')[0], 403)
        raw = Path(self.launch['storePath']).read_bytes()
        for content in (DRAFT['title'], DRAFT['instruction'], token):
            self.assertNotIn(content.encode(), raw)


if __name__ == '__main__':
    unittest.main()
