"""The open SDK against the real assistant tools: in process, and over HTTP with a bearer token."""
import json
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
import time
import unittest

import anyio
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'sdk' / 'python'))

from parlu import ParluAgent, ParluError  # noqa: E402
from parlu.web import ParluWeb  # noqa: E402

from conversation import ConversationLedger  # noqa: E402
from conversation.inbox import InboxAccess, InboxStore  # noqa: E402
from mission_approvals.http import http_app  # noqa: E402
from mission_approvals.inbox import OfferInbox  # noqa: E402
from mission_approvals.server import build_server  # noqa: E402
from pilot.auth import LocalOwnerAuth  # noqa: E402
from pilot.crypto import fingerprint  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class SdkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.now = 2000000000.0
        self.auths, self.keys, self.sessions = {}, {}, {}
        for name in ('alice', 'bob'):
            auth = LocalOwnerAuth(root / name, clock=lambda: self.now)
            auth.bootstrap(name, name + '_assistant', 'Fictional test password')
            self.auths[name], self.keys[name] = auth, fingerprint(auth.public_identity())
            self.sessions[name] = auth.login('Fictional test password')
        self.ledger = ConversationLedger(root / 'ledger', self.auths['alice'],
                                         {self.keys[n]: a for n, a in self.auths.items()}, clock=lambda: self.now)
        self.ledger.create(self.keys['alice'], self.sessions['alice'], 'trip')
        invite = self.ledger.invite(self.keys['alice'], self.sessions['alice'], 'trip', self.keys['bob'])
        self.ledger.accept_invitation(self.keys['bob'], self.sessions['bob'], invite['id'])
        self.store = InboxStore(root / 'inbox', self.ledger)
        lease = self.store.provision(self.keys['bob'], self.sessions['bob'], 'bob_assistant', 'trip')
        self.access = InboxAccess(self.store, lease, lambda: self.sessions['bob'])
        self.server = build_server(OfferInbox(lambda: int(self.now)), conversation_inbox=self.access)

    def tearDown(self):
        self.store.close()
        self.ledger.close()
        for auth in self.auths.values():
            auth.close()
        self.tmp.cleanup()

    def post(self, text, request):
        binding = self.ledger.bind_context(self.keys['alice'], self.sessions['alice'], 'trip')
        return self.ledger.append(self.keys['alice'], self.sessions['alice'], binding, request_id=request, text=text)

    def serve(self, token):
        port = free_port()
        app = http_app(self.server, token, inbox_access=self.access, watch_interval=0.05)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.02)
        self.addCleanup(thread.join, 5)
        self.addCleanup(setattr, server, 'should_exit', True)
        return f'http://127.0.0.1:{port}/mcp'

    def test_agent_reads_inbox_and_wakes_in_process(self):
        self.post('Fictional: Friday train?', 'r1')
        async def run():
            async with ParluAgent(self.server) as parlu:
                self.assertIn('check_inbox', await parlu.tools())
                self.assertTrue(await parlu.pending())
                async for _ in parlu.wake_ups():
                    break  # Something is already waiting, so it yields at once.
                batch = await parlu.inbox()
                self.assertEqual(batch['messages'][0]['text'], 'Fictional: Friday train?')
                await parlu.acknowledge(batch['messages'][-1]['id'])
                self.assertFalse(await parlu.pending())
                with self.assertRaises(ParluError):
                    await parlu.acknowledge('not-a-message')
        anyio.run(run)

    def test_plain_web_client_needs_the_token(self):
        token = secrets.token_urlsafe(32)
        url = self.serve(token)
        self.post('Fictional: lunch?', 'r2')
        parlu = ParluWeb(url, token=token)
        self.assertIn('inbox_status', parlu.tools())
        self.assertTrue(parlu.pending())
        batch = parlu.inbox()
        self.assertEqual(batch['messages'][0]['text'], 'Fictional: lunch?')
        self.assertEqual(batch['peer_authored_fields'], ['text'])
        with self.assertRaises(ParluError):
            ParluWeb(url, token='wrong' * 8).pending()
        with self.assertRaises(ParluError):
            ParluWeb(url).pending()

    def test_remote_agent_wakes_when_a_message_arrives(self):
        token = secrets.token_urlsafe(32)
        url = self.serve(token)
        async def run():
            import httpx2
            from mcp.client.streamable_http import streamable_http_client
            async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + token}) as http:
                async with ParluAgent(streamable_http_client(url, http_client=http)) as parlu:
                    self.assertFalse(await parlu.pending())
                    async def later():
                        await anyio.sleep(0.3)
                        self.post('Fictional: dinner at seven?', 'r3')
                    with anyio.fail_after(10):
                        async with anyio.create_task_group() as group:
                            group.start_soon(later)
                            async for _ in parlu.wake_ups():
                                break
                    batch = await parlu.inbox()
                    self.assertIn('dinner', json.dumps(batch))
        anyio.run(run)

    def test_token_must_be_long(self):
        with self.assertRaises(ValueError):
            http_app(self.server, 'short')
        with self.assertRaises(ParluError):
            ParluWeb('http://example.com/mcp')


if __name__ == '__main__':
    unittest.main()
