"""Disposable fictional two-owner file handoff. No network or provider calls."""
import json
from pathlib import Path
import secrets
import tempfile
import time

from .auth import LocalOwnerAuth
from .file_exchange import FileExchange
from .runtime import PilotRuntime


def main():
    with tempfile.TemporaryDirectory(prefix='assistant-central-file-demo-') as directory:
        root = Path(directory)
        owners = []
        try:
            for name in ('fictional-alice', 'fictional-bob'):
                auth = LocalOwnerAuth(root / name)
                owners.append([auth, None, None])
                password = secrets.token_urlsafe(32)
                auth.bootstrap(name, name + '-assistant', password)
                session = auth.login(password)
                runtime = PilotRuntime(root / name, auth)
                owners[-1] = [auth, session, runtime]
                del password
            a, b = owners
            for owner, peer in ((a, b), (b, a)):
                owner[2].enrol_peer(owner[1], peer[2].identity, peer[2].fingerprint)
            outgoing = a[2].propose(a[1], b[2].fingerprint, 'task', 'Fictional garden',
                'SYNTHETIC ONLY: Describe a fictional moon garden.', 'a'*64,
                'fictional-garden', time.time() + 600)
            released = a[2].release(a[1], outgoing['id'], a[2].review(a[1], outgoing['id'])['review_digest'])
            first, second = FileExchange(a[2]), FileExchange(b[2])
            first.export(a[1], released['message_id'], root/'proposal.json')
            received = second.receive(b[1], root/'proposal.json', root/'receipt.json')
            duplicate = second.receive(b[1], root/'proposal.json', root/'duplicate-receipt.json')
            assert duplicate['duplicate']
            assert (root/'receipt.json').read_bytes() == (root/'duplicate-receipt.json').read_bytes()
            first.receive(a[1], root/'receipt.json')
            assert received['owner_acceptance'] == 'not_established'
            assert b[2].status(b[1], outgoing['id'])['state'] == 'pending'
            accepted = b[2].decide(b[1], outgoing['id'], b[2].review(b[1], outgoing['id'])['review_digest'], 'accept')
            decision_id = 'decision-' + accepted['decision_digest']
            second.export(b[1], decision_id, root/'decision.json')
            first.receive(a[1], root/'decision.json', root/'decision-receipt.json')
            second.receive(b[1], root/'decision-receipt.json')
            assert a[2].status(a[1], outgoing['id'])['state'] == 'accepted'
            print(json.dumps({'synthetic_only': True, 'network_calls': 0,
                              'exact_duplicate_receipt': True, 'recipient_decision_observed': True,
                              'authorises_execution': False, 'actual_cross_device_tested': False}))
        finally:
            for auth, session, runtime in reversed(owners):
                if runtime is not None:
                    runtime.close()
                auth.close()


if __name__ == '__main__':
    main()
