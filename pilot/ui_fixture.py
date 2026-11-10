"""Disposable browser fixture. Fixed credentials are public test data only.

Never use this fixture or its password for real accounts. It generates fresh
temporary keys/stores on each invocation and enables no live provider route.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from .auth import LocalOwnerAuth
from .crypto import fingerprint
from .runtime import PilotRuntime
from .server import PilotHTTPServer
from .workflow import FIXTURE_GRANT

PASSWORD = 'Fictional browser test password'


def main():
    parser = argparse.ArgumentParser(description='Disposable synthetic browser fixture only')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit('Choose a loopback port from 1024 to 65535')
    with tempfile.TemporaryDirectory(prefix='assistant-central-browser-fixture-') as directory:
        root = Path(directory)
        first, second = LocalOwnerAuth(root / 'first'), LocalOwnerAuth(root / 'second')
        sender = receiver = None
        try:
            first.bootstrap('alex', 'atlas', PASSWORD)
            second.bootstrap('blair', 'beacon', PASSWORD)
            first_token, second_token = first.login(PASSWORD), second.login(PASSWORD)
            sender, receiver = PilotRuntime(root / 'first', first), PilotRuntime(root / 'second', second)
            sender.enrol_peer(first_token, second.public_identity(), fingerprint(second.public_identity()))
            receiver.enrol_peer(second_token, first.public_identity(), fingerprint(first.public_identity()))
            for index, title in enumerate(('Browser acceptance task', 'Browser rejection task', 'Research the community garden', 'Browser workflow task')):
                item = sender.propose(first_token, fingerprint(second.public_identity()), 'task', title,
                    'SYNTHETIC ONLY: ' + title + ' for a fictional community. No real personal information.',
                    hashlib.sha256(title.encode()).hexdigest(), 'browser-task-' + str(index), time.time() + 3300,
                    provider_disclosure=FIXTURE_GRANT if index == 3 else None)
                sender.release(first_token, item['id'], sender.review(first_token, item['id'])['review_digest'])
                receiver.receive(second_token, sender.prepare_delivery(first_token, 'proposal-' + item['id']))
                if index == 2:
                    receiver.decide(second_token, item['id'], receiver.review(second_token, item['id'])['review_digest'], 'accept')
        finally:
            if sender: sender.close()
            if receiver: receiver.close()
            first.close(); second.close()
        server = PilotHTTPServer(root / 'second', args.port, synthetic_workflow=True)
        print(json.dumps({'url': server.origin, 'synthetic_fixture': True}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
