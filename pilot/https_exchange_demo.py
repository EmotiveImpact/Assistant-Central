"""Disposable fictional owner flow over real loopback TLS, not live deployment."""
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time

from .auth import LocalOwnerAuth
from .https_exchange import HTTPSExchange
from .https_mailbox import MailboxServer, Quarantine, ROUTE
from .runtime import PilotRuntime
from .tests.test_https_carrier import certificates


def main():
    with tempfile.TemporaryDirectory(prefix='assistant-central-https-demo-') as directory:
        root = Path(directory)
        owners, mailboxes = [], []
        try:
            ca, certificate, key = certificates(root)  # Disposable fixture, never persistent PKI.
            for name in ('fictional-alice', 'fictional-bob'):
                auth = LocalOwnerAuth(root / name)
                owners.append([auth, None, None, None, None])
                password = secrets.token_urlsafe(32)
                auth.bootstrap(name, name + '-assistant', password)
                session = auth.login(password)
                del password
                runtime = PilotRuntime(root / name, auth)
                spool = root / (name + '-quarantine')
                spool.mkdir(mode=0o700)
                owners[-1] = [auth, session, runtime, HTTPSExchange(runtime), spool]
                quarantine = Quarantine(spool, runtime.fingerprint)
                server = MailboxServer(quarantine, certificate, key, enabled=True)
                worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
                worker.start()
                mailboxes.append((quarantine, server, worker))
            a, b = owners
            targets = [f'https://localhost:{server.server_address[1]}{ROUTE}' for _, server, _ in mailboxes]
            for owner, peer in ((a, b), (b, a)):
                owner[2].enrol_peer(owner[1], peer[2].identity, peer[2].fingerprint)

            def transfer(sender, receiver, message_id, *, receipt=False):
                origin, target = owners[sender], owners[receiver]
                send = origin[3].send_receipt if receipt else origin[3].send
                sent = send(origin[1], message_id, targets[receiver], target[2].fingerprint, ca_file=ca)
                assert sent['transport_acknowledged'] and sent['delivery'] == 'uncertain'
                assert not sent['authorises_execution']
                result = target[3].receive(target[1], target[4] / (sent['file_digest'] + '.json'),
                                           origin[2].fingerprint, sent['file_digest'])
                return sent, result

            task = a[2].propose(a[1], b[2].fingerprint, 'task', 'Fictional moon garden',
                'SYNTHETIC ONLY: Describe a fictional moon garden.', 'a' * 64,
                'fictional-garden', time.time() + 600)
            released = a[2].release(a[1], task['id'], a[2].review(a[1], task['id'])['review_digest'])
            sent, incoming = transfer(0, 1, released['message_id'])
            assert incoming['owner_acceptance'] == 'not_established'
            assert b[2].status(b[1], task['id'])['state'] == 'pending'
            receipt, _ = transfer(1, 0, released['message_id'], receipt=True)
            assert a[2].exchange.outbox_status(released['message_id'])['state'] == 'received'
            assert a[2].status(a[1], task['id'])['state'] == 'released'
            duplicate = b[3].receive(b[1], b[4] / (sent['file_digest'] + '.json'), a[2].fingerprint, sent['file_digest'])
            assert duplicate['duplicate']
            repeated = b[3].send_receipt(b[1], released['message_id'], targets[0], a[2].fingerprint, retry=True, ca_file=ca)
            assert repeated['file_digest'] == receipt['file_digest']
            accepted = b[2].decide(b[1], task['id'], b[2].review(b[1], task['id'])['review_digest'], 'accept')
            transfer(1, 0, 'decision-' + accepted['decision_digest'])
            assert a[2].status(a[1], task['id'])['state'] == 'accepted'
            artifact = b[2].propose(b[1], a[2].fingerprint, 'artifact', 'Fictional garden result',
                'SYNTHETIC ONLY: Silver flowers grow under an invented moon.', 'a' * 64,
                'fictional-garden', time.time() + 300, task['id'])
            returned = b[2].release(b[1], artifact['id'], b[2].review(b[1], artifact['id'])['review_digest'])
            transfer(1, 0, returned['message_id'])
            assert a[2].status(a[1], artifact['id'])['state'] == 'pending'
            cancellation = a[2].cancel(a[1], task['id'], a[2].review(a[1], task['id'])['review_digest'])
            transfer(0, 1, cancellation['cancel_message_id'])
            assert b[2].status(b[1], task['id'])['state'] == 'cancelled'
            print(json.dumps({'synthetic_only': True, 'transport': 'real loopback TLS 1.3',
                'authenticated_import': True, 'http_ack_is_not_receipt': True,
                'exact_duplicate_receipt': True, 'explicit_recipient_decision': True,
                'origin_only_artifact_return': True, 'observed_cancellation': True,
                'provider_calls': 0, 'authorises_execution': False, 'actual_cross_device_tested': False}))
        finally:
            for quarantine, server, worker in reversed(mailboxes):
                server.shutdown(); server.server_close(); worker.join(); quarantine.close()
            for auth, session, runtime, exchange, spool in reversed(owners):
                if runtime is not None: runtime.close()
                auth.close()


if __name__ == '__main__':
    main()
