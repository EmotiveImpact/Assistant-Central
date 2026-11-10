"""Combined facades over actual loopback HTTP, not browser acceptance."""
import http.client
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib.parse import urljoin

from workspace_ui.conversation_service import ConversationService
from workspace_ui.host_draft_service import HostDraftConfig, HostDraftService, VERSION
from workspace_ui.owner_workspace_fixture import PASSWORD, seed_owner_workspace
from workspace_ui.server import WorkspaceHTTPServer


class OwnerWorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='combined-owner-http-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = seed_owner_workspace(self.root)
        self.server = None
        self.addCleanup(self.stop)
        self.start()
        self.tokens = {name: self.login(name) for name in self.fixture.principals}

    def start(self, conversations=True, drafts=True):
        # Standalone host mode knows only the primary owner.
        config = self.fixture.host_draft_config
        if drafts and not conversations:
            config = HostDraftConfig({'version': VERSION, 'connections': [{
                'id': 'alice_queue', 'owner_fingerprint': self.fixture.principals['alice'],
                'launch_file': str(self.root / 'alice_host' / 'launch.json')}]})
        self.server = WorkspaceHTTPServer(self.fixture.directory, 0,
            conversation_config=self.fixture.conversation_config if conversations else None,
            host_draft_config=config if drafts else None)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join(5)
            self.server.server_close()
            self.server = None

    def raw(self, method, path, value=None, token=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        if value is not None:
            headers['Content-Type'] = 'application/json'
        try:
            connection.request(method, path, None if value is None else json.dumps(value), headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def login(self, name, account=True):
        body = {'password': PASSWORD}
        if account:
            body['account'] = name
        status, raw = self.raw('POST', '/api/session', body)
        self.assertEqual(status, 200, raw)
        return json.loads(raw)['token']

    def call(self, name, path, value=None, method=None, expect=200):
        status, raw = self.raw(method or ('GET' if value is None else 'POST'), path, value, self.tokens[name])
        self.assertEqual(status, expect, raw)
        return json.loads(raw)

    def route(self, name):
        return '/api/host-drafts/' + name + '_queue/' + self.fixture.seeded[name]['draftId']

    def binding(self, name):
        binding = self.call(name, '/api/conversations/thread_1')['binding']
        return {key: binding[key] for key in ('member_epoch', 'policy_generation')}

    def history(self, name):
        return self.call(name, '/api/conversations/thread_1/history', {'binding': self.binding(name)})['messages']

    def join_carol(self):
        invitation = self.call('carol', '/api/conversations')['invitations'][0]
        self.call('carol', '/api/conversations/invitations/' + invitation['id'] + '/accept', {})

    def test_real_sdk_queues_follow_separate_authenticated_accounts(self):
        self.assertIsInstance(self.server.owner, HostDraftService)
        self.assertIsInstance(self.server.owner.underlying, ConversationService)
        self.assertEqual(len(set(self.tokens.values())), 3)
        self.assertEqual(self.raw('GET', '/api/host-drafts')[0], 401)
        for name in ('alice', 'bob'):
            with self.subTest(owner=name):
                seeded = self.fixture.seeded[name]
                self.assertTrue(seeded['officialRunner'] and seeded['mcp'])
                state = self.call(name, '/api/state')
                self.assertEqual(state['identity']['owner_id'], name)
                self.assertTrue(state['conversations']['enabled'] and state['host_drafts']['enabled'])
                self.assertFalse(state['provider']['live_enabled'])
                self.assertEqual((state['items'], state['outbox']), ([], []))
                queue = self.call(name, '/api/host-drafts')['connections']
                self.assertEqual([item['id'] for item in queue], [name + '_queue'])
                self.assertEqual(queue[0]['items'][0]['draftId'], seeded['draftId'])
                review = self.call(name, self.route(name) + '/review')
                self.assertEqual(review['draft'], self.fixture.drafts[name])
                self.assertEqual(review['binding']['ownerId'], self.fixture.principals[name])
        self.assertEqual(self.call('carol', '/api/host-drafts')['connections'], [])

    def test_other_owner_inspect_and_dismiss_denied_correct_owner_commits(self):
        for name, other in (('alice', 'bob'), ('bob', 'alice')):
            with self.subTest(owner=name):
                review = self.call(name, self.route(name) + '/review')
                decision = {key: review[key] for key in ('digest', 'reviewToken')}
                self.call(other, self.route(name) + '/review', expect=400)
                self.call(other, self.route(name) + '/dismiss', decision, expect=400)
                self.assertEqual(self.call(name, self.route(name) + '/review')['status']['state'], 'awaiting_owner_review')
                result = self.call(name, self.route(name) + '/dismiss', decision)
                self.assertEqual(result['status']['state'], 'dismissed')
                self.assertEqual(result['status']['execution'], 'not_started')
                self.assertEqual(result['status']['transportReceipt'], 'none')
                with sqlite3.connect(self.fixture.launches[name]['storePath']) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 1)

    def test_future_only_join_and_stale_membership_refusal(self):
        old = self.history('alice')[0]
        stale = self.binding('alice')
        self.join_carol()
        self.assertEqual(self.history('carol'), [])
        self.call('carol', '/api/conversations/thread_1/read',
                  {'binding': self.binding('carol'), 'event_id': old['id']}, expect=400)
        self.call('alice', '/api/conversations/thread_1/message',
                  {'binding': stale, 'request_id': 'stale', 'text': 'Old audience draft'}, expect=400)
        future = self.call('bob', '/api/conversations/thread_1/message',
                  {'binding': self.binding('bob'), 'request_id': 'future', 'text': 'New audience words'})
        self.assertEqual([item['id'] for item in self.history('carol')], [future['id']])
        self.assertEqual(len(self.call('bob', '/api/host-drafts')['connections']), 1)

    def test_exact_own_author_history_grant_and_revoke(self):
        old = self.history('alice')
        self.join_carol()
        body = {'binding': self.binding('alice'), 'recipient': self.fixture.principals['carol'],
                'event_ids': [old[0]['id']], 'purpose': 'Fictional exact context', 'expires_at': time.time() + 600}
        review = self.call('alice', '/api/conversations/thread_1/grant-review', body)
        self.assertEqual([item['id'] for item in review['messages']], [old[0]['id']])
        self.call('alice', '/api/conversations/thread_1/grant-review',
                  dict(body, event_ids=[old[2]['id']]), expect=400)
        route = '/api/conversations/grants/' + review['statement']['id']
        decision = {'review_digest': review['review_digest']}
        self.call('bob', route + '/approve', decision, expect=400)
        self.call('alice', route + '/approve', decision)
        self.assertEqual([item['id'] for item in self.history('carol')], [old[0]['id']])
        self.call('bob', route + '/revoke', {}, expect=400)
        self.call('alice', route + '/revoke', {})
        self.assertEqual(self.history('carol'), [])
        self.call('alice', route + '/approve', decision, expect=400)

    def test_coordinator_logout_does_not_borrow_other_accounts_vault(self):
        binding = self.binding('bob')
        self.call('alice', '/api/session', {}, method='DELETE')
        self.call('bob', '/api/conversations/thread_1/history', {'binding': binding}, expect=400)
        self.call('bob', '/api/conversations', expect=400)
        self.assertEqual(self.call('bob', '/api/state')['identity']['owner_id'], 'bob')
        self.assertEqual([item['id'] for item in self.call('bob', '/api/host-drafts')['connections']], ['bob_queue'])
        self.call('bob', self.route('alice') + '/review', expect=400)
        self.call('alice', '/api/host-drafts', expect=401)
        self.tokens['alice'] = self.login('alice')
        self.assertTrue(self.call('bob', '/api/conversations')['rooms'])

    def test_coordinator_expiry_blocks_history_despite_valid_other_session(self):
        binding = self.binding('bob')
        def expire_coordinator():
            auth = self.server.owner.underlying.primary.auth
            auth._db.execute('UPDATE sessions SET expires=0')
            auth._db.commit()
        self.server.owner_worker.submit(expire_coordinator).result()
        self.call('bob', '/api/conversations/thread_1/history', {'binding': binding}, expect=400)
        self.call('bob', '/api/conversations', expect=400)
        self.assertEqual(self.call('bob', '/api/state')['identity']['owner_id'], 'bob')
        self.assertEqual([item['id'] for item in self.call('bob', '/api/host-drafts')['connections']], ['bob_queue'])
        self.call('bob', self.route('alice') + '/review', expect=400)
        self.call('alice', '/api/state', expect=401)

    def test_static_import_graph_served_with_both_features(self):
        status, html = self.raw('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'app.mjs', html)
        pending, seen = ['/app.mjs'], set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            status, source = self.raw('GET', path)
            self.assertEqual(status, 200, path)
            text = source.decode()
            self.assertNotRegex(text, r'(?m)^(?:<<<<<<<|=======|>>>>>>>)')
            for target in re.findall(r'(?:from\s*|import\s*)[\'"]([^\'"]+\.mjs)[\'"]', text):
                self.assertTrue(target.startswith(('./', '/')), target)
                pending.append(urljoin(path, target))
        self.assertTrue({'/conversations.mjs', '/host_drafts.mjs', '/projections.mjs', '/operations.mjs'} <= seen, seen)

    def test_optional_features_independently_enabled_and_default_disabled(self):
        # Three constructor cases constitute one compatibility test, not three tests.
        self.stop()
        for conversations, drafts in ((False, False), (True, False), (False, True)):
            with self.subTest(conversations=conversations, drafts=drafts):
                self.start(conversations, drafts)
                self.tokens = {'alice': self.login('alice', account=conversations)}
                state = self.call('alice', '/api/state')
                self.assertEqual(state.get('conversations', {}).get('enabled', False), conversations)
                self.assertEqual(state.get('host_drafts', {}).get('enabled', False), drafts)
                self.call('alice', '/api/conversations', expect=200 if conversations else 400)
                self.call('alice', '/api/host-drafts', expect=200 if drafts else 400)
                self.stop()


if __name__ == '__main__':
    unittest.main()
