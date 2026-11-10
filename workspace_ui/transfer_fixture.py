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
from unittest.mock import patch
from pilot.https_carrier import send_file as real_send_file

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint, canonical
from pilot.runtime import PilotRuntime
from workspace_ui.server import WorkspaceHTTPServer
from pilot.workflow import FIXTURE_GRANT
from pilot.owner_transfer import TransferConfig, VERSION
from pilot.https_mailbox import Quarantine, MailboxServer, ROUTE
from pilot.tests.test_https_carrier import certificates

PASSWORD = 'Fictional browser test password'


def gated_sender(directory):
    # Fixture-only filesystem coordination. The browser arms exactly one send.
    # Pause only after the real TLS carrier returns: bytes are already retained
    # remotely, while the owner still observes the dispatch as in flight.
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    def send(source, target, recipient, *, ca_file=None):
        result = real_send_file(source, target, recipient, ca_file=ca_file)
        arm = directory / 'arm'
        if arm.exists():
            arm.unlink()
            (directory / 'retained').write_text('Real TLS send returned; no owner acceptance established.')
            deadline = time.monotonic() + 30
            while not (directory / 'release').exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError('Fixture release gate timed out')
                time.sleep(0.02)
            (directory / 'release').unlink()
        return result
    return send


def main():
    parser = argparse.ArgumentParser(description='Disposable synthetic browser fixture only')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--gate-directory', required=True, help='Disposable fixture-only browser synchronisation directory')
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
            for index, title in enumerate(('Central transfer delivery', 'Central transfer withdrawal')):
                item = receiver.propose(second_token, sender.fingerprint, 'task', title,
                    'SYNTHETIC ONLY: disposable Central transfer browser check.',
                    hashlib.sha256(title.encode()).hexdigest(), 'central-transfer-' + str(index), time.time() + 3300)
                receiver.release(second_token, item['id'], receiver.review(second_token, item['id'])['review_digest'])
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
        reverse_quarantine = Quarantine(receiver_spool, receiver_pin)
        reverse_mailbox = MailboxServer(reverse_quarantine, certificate, key, enabled=True)
        reverse_thread = threading.Thread(target=reverse_mailbox.serve_forever, kwargs={'poll_interval': 0.01})
        reverse_thread.start()
        server = second_server = second_thread = None
        try:
            transfer_config = TransferConfig({'version': VERSION, 'connections': [{'id': 'fixture-peer',
                'label': 'Fictional Atlas mailbox', 'peer_fingerprint': sender_pin,
                'destination': f'https://localhost:{mailbox.server_address[1]}{ROUTE}', 'ca_file': str(ca)}],
                'quarantine_directory': str(receiver_spool)})
            server = WorkspaceHTTPServer(root / 'second', args.port, synthetic_workflow=True, transfer_config=transfer_config)
            reverse_config = TransferConfig({'version': VERSION, 'connections': [{'id': 'fixture-peer',
                'label': 'Fictional Beacon mailbox', 'peer_fingerprint': receiver_pin,
                'destination': f'https://localhost:{reverse_mailbox.server_address[1]}{ROUTE}', 'ca_file': str(ca)}],
                'quarantine_directory': str(sender_spool)})
            second_server = WorkspaceHTTPServer(root / 'first', args.port + 1, synthetic_workflow=True, transfer_config=reverse_config)
            second_thread = threading.Thread(target=second_server.serve_forever, daemon=True)
            second_thread.start()
            print(json.dumps({'url': server.origin, 'other_owner_url': second_server.origin, 'synthetic_fixture': True}), flush=True)
            with patch('pilot.https_exchange.send_file', gated_sender(Path(args.gate_directory))):
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if second_server is not None:
                second_server.shutdown()
                second_thread.join(timeout=5)
                second_server.server_close()
            reverse_mailbox.shutdown(); reverse_thread.join(); reverse_mailbox.server_close(); reverse_quarantine.close()
            if server is not None:
                server.server_close()
            mailbox.shutdown(); mailbox_thread.join(); mailbox.server_close(); quarantine.close()


if __name__ == '__main__':
    main()
