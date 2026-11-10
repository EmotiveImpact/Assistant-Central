"""Disposable browser fixture. Fixed credentials are public test data only.

Never use this fixture or its password for real accounts. It generates fresh
temporary keys/stores on each invocation and enables no live provider route.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time

from .auth import LocalOwnerAuth
from .crypto import fingerprint, canonical
from .runtime import PilotRuntime
from .server import PilotHTTPServer
from .workflow import FIXTURE_GRANT
from .owner_transfer import TransferConfig, VERSION
from .https_mailbox import Quarantine, MailboxServer, ROUTE
from .tests.test_https_carrier import certificates

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
            sender_pin, receiver_pin = sender.fingerprint, receiver.fingerprint
            first_packet = None
            for index, title in enumerate(('Browser acceptance task', 'Browser rejection task', 'Research the community garden', 'Browser workflow task')):
                item = sender.propose(first_token, fingerprint(second.public_identity()), 'task', title,
                    'SYNTHETIC ONLY: ' + title + ' for a fictional community. No real personal information.',
                    hashlib.sha256(title.encode()).hexdigest(), 'browser-task-' + str(index), time.time() + 3300,
                    provider_disclosure=FIXTURE_GRANT if index == 3 else None)
                sender.release(first_token, item['id'], sender.review(first_token, item['id'])['review_digest'])
                packet = sender.prepare_delivery(first_token, 'proposal-' + item['id'])
                receiver.receive(second_token, packet)
                if first_packet is None:
                    first_packet = packet
                if index == 2:
                    receiver.decide(second_token, item['id'], receiver.review(second_token, item['id'])['review_digest'], 'accept')
        finally:
            if sender: sender.close()
            if receiver: receiver.close()
            first.close(); second.close()
        # Disposable fictional TLS fixtures only. Starting a mailbox does not
        # import, accept, reply or send anything on an owner's behalf.
        sender_spool, receiver_spool = root / 'sender-quarantine', root / 'receiver-quarantine'
        sender_spool.mkdir(mode=0o700); receiver_spool.mkdir(mode=0o700)
        raw = canonical(first_packet)
        selected = receiver_spool / (hashlib.sha256(raw).hexdigest() + '.json')
        selected.write_bytes(raw); selected.chmod(0o600)
        ca, certificate, key = certificates(root)
        quarantine = Quarantine(sender_spool, sender_pin)
        mailbox = MailboxServer(quarantine, certificate, key, enabled=True)
        mailbox_thread = threading.Thread(target=mailbox.serve_forever, kwargs={'poll_interval': 0.01})
        mailbox_thread.start()
        transfer_config = TransferConfig({'version': VERSION, 'connections': [{'id': 'fixture-peer',
            'label': 'Fictional Atlas mailbox', 'peer_fingerprint': sender_pin,
            'destination': f'https://localhost:{mailbox.server_address[1]}{ROUTE}', 'ca_file': str(ca)}],
            'quarantine_directory': str(receiver_spool)})
        server = PilotHTTPServer(root / 'second', args.port, synthetic_workflow=True, transfer_config=transfer_config)
        print(json.dumps({'url': server.origin, 'synthetic_fixture': True}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            mailbox.shutdown(); mailbox_thread.join(); mailbox.server_close(); quarantine.close()


if __name__ == '__main__':
    main()
