"""Disposable fictional SDK-to-owner-HTTP fixture. Never loads live credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from workspace_ui.host_draft_service import HostDraftConfig, HostDraftService, VERSION
from workspace_ui.server import WorkspaceHTTPServer

PASSWORD = 'Fictional host draft owner password'
DRAFT = {'requestId': 'fixture_request', 'title': 'Fictional host planning draft',
         'instruction': 'Prepare a fictional picnic checklist. <img src=x onerror="window.hostDraftExecuted=true"> Do not contact anyone.'}
ROOT = Path(__file__).resolve().parents[1]


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out)


def sdk_seed(launch, home, draft=DRAFT, operation='seed'):
    process = subprocess.run([shutil.which('node'), '--import', str(ROOT / 'agent_bridge/tests/no-network.mjs'),
                              str(ROOT / 'agent_bridge/tests/seed_owner_fixture.mjs')],
                             input=json.dumps({'launch': launch, 'home': str(home), 'draft': draft, 'operation': operation}),
                             text=True, capture_output=True, timeout=20,
                             env={'NODE_NO_WARNINGS': '1', 'OTEL_SDK_DISABLED': 'true', 'OPENAI_AGENTS_DISABLE_TRACING': '1'})
    if process.returncode:
        raise RuntimeError('Disposable SDK fixture failed')
    return json.loads(process.stdout)


def seed_host_review(root):
    root = Path(root)
    owner_dir = root / 'owner'
    auth = LocalOwnerAuth(owner_dir)
    try:
        identity = auth.bootstrap('blair', 'blair_assistant', PASSWORD)
    finally:
        auth.close()
    host = root / 'host'
    host.mkdir(mode=0o700)
    launch = {'storePath': str(host / 'drafts.sqlite'), 'keyHex': secrets.token_hex(32),
              'binding': {'ownerId': fingerprint(identity), 'hostId': 'fictional_sdk_host', 'sessionId': 'host_session_one',
                          'conversationId': 'fictional_conversation', 'recipientId': 'fictional_fixed_recipient',
                          'expiresAt': int(time.time() * 1000) + 600000}}
    saved = sdk_seed(launch, root)
    launch_file = host / 'launch.json'
    write_private(launch_file, launch)
    config = {'version': VERSION, 'connections': [{'id': 'fixture', 'owner_fingerprint': fingerprint(identity),
                                                  'launch_file': str(launch_file)}]}
    return owner_dir, config, launch, saved


def install_review(server, config):
    # Same constructor seam used by the optional launcher, before serving.
    server.owner = server.owner_worker.submit(HostDraftService, server.owner, HostDraftConfig(config)).result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8778)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='central-host-review-fixture-') as temp:
        owner, config, _, _ = seed_host_review(temp)
        server = WorkspaceHTTPServer(owner, args.port, host_draft_config=HostDraftConfig(config))
        print(json.dumps({'url': server.origin, 'fictional_fixture': True, 'live_provider_enabled': False}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
