"""Disposable combined owner workspace with fictional accounts and SDK drafts.

The fixed password belongs only to fresh temporary demonstration accounts. No
live credentials, provider calls, transport sends or execution are enabled.
This is a trusted local coordinator demonstration, not remote multi-owner hosting.
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import tempfile
import time

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from .conversation_fixture import PASSWORD, seed_conversations
from .host_draft_fixture import sdk_seed, write_private
from .host_draft_service import HostDraftConfig, VERSION
from .server import WorkspaceHTTPServer


@dataclass
class OwnerWorkspaceFixture:
    directory: Path
    conversation_config: object
    host_draft_config: HostDraftConfig
    principals: dict
    launches: dict
    drafts: dict
    seeded: dict


def seed_owner_workspace(root):
    """Seed real local accounts, a conversation and two isolated SDK queues."""
    root = Path(root)
    conversation_config = seed_conversations(root)
    principals, launches, drafts, seeded = {}, {}, {}, {}
    connections = []
    for name in ('alice', 'bob', 'carol'):
        auth = LocalOwnerAuth(root / name)
        try:
            principals[name] = fingerprint(auth.public_identity())
        finally:
            auth.close()
    for name in ('alice', 'bob'):
        host = root / (name + '_host')
        host.mkdir(mode=0o700)
        launch = {'storePath': str(host / 'drafts.sqlite'), 'keyHex': secrets.token_hex(32),
                  'binding': {'ownerId': principals[name], 'hostId': name + '_fictional_host',
                              'sessionId': name + '_fixture_session', 'conversationId': 'thread_1',
                              'recipientId': name + '_fictional_recipient',
                              'expiresAt': int(time.time() * 1000) + 600000}}
        draft = {'requestId': name + '_request', 'title': name.title() + ' fictional planning draft',
                 'instruction': 'Prepare a fictional checklist for ' + name + '. Do not contact anyone.'}
        seeded[name] = sdk_seed(launch, root, draft)
        launches[name], drafts[name] = launch, draft
        launch_file = host / 'launch.json'
        write_private(launch_file, launch)
        connections.append({'id': name + '_queue', 'owner_fingerprint': principals[name],
                            'launch_file': str(launch_file)})
    return OwnerWorkspaceFixture(root / 'alice', conversation_config,
                                 HostDraftConfig({'version': VERSION, 'connections': connections}),
                                 principals, launches, drafts, seeded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8778)
    args = parser.parse_args()
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error('Choose a loopback port from 1024 to 65535, or 0')
    with tempfile.TemporaryDirectory(prefix='central-owner-workspace-') as temporary:
        fixture = seed_owner_workspace(temporary)
        server = WorkspaceHTTPServer(fixture.directory, args.port,
                                     conversation_config=fixture.conversation_config,
                                     host_draft_config=fixture.host_draft_config)
        print(json.dumps({'url': server.origin, 'fictional_fixture': True,
                          'live_provider_enabled': False, 'accounts': ['alice', 'bob', 'carol']}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
