"""Fictional direct-to-group history, restart and revocation demonstration."""
import json
from pathlib import Path
import tempfile

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from .ledger import ConversationLedger, ConversationDenied


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        auths, sessions, principals = {}, {}, {}
        for name in ('alice', 'bob', 'carol'):
            auths[name] = LocalOwnerAuth(root / name)
            auths[name].bootstrap(name, name + '_assistant', 'Fictional demo password')
            sessions[name] = auths[name].login('Fictional demo password')
            principals[name] = fingerprint(auths[name].public_identity())
        def actor(name):
            return principals[name], sessions[name]
        def open_ledger():
            return ConversationLedger(root / 'ledger', auths['alice'], {principals[n]: a for n, a in auths.items()})
        ledger = open_ledger()
        try:
            ledger.create(*actor('alice'), 'shared_research')
            invitation = ledger.invite(*actor('alice'), 'shared_research', principals['bob'])
            ledger.accept_invitation(*actor('bob'), invitation['id'])
            old = ledger.append(*actor('alice'), ledger.bind_context(*actor('alice'), 'shared_research'),
                                request_id='first_message', text='Fictional private research context.')
            invitation = ledger.invite(*actor('alice'), 'shared_research', principals['carol'])
            ledger.accept_invitation(*actor('carol'), invitation['id'])
            def history():
                return ledger.history(*actor('carol'), ledger.bind_context(*actor('carol'), 'shared_research'))
            assert history() == []
            import time
            review = ledger.prepare_history_grant(*actor('alice'), 'shared_research', principals['carol'], [old['id']],
                                                  purpose='Review this exact fictional context', expires_at=time.time() + 300)
            grant = ledger.approve_history_grant(*actor('alice'), review, review['review_digest'])
            assert [x['id'] for x in history()] == [old['id']]
            ledger.close()
            for name, auth in auths.items():
                auth.close()
                auths[name] = LocalOwnerAuth(root / name)
                sessions[name] = auths[name].login('Fictional demo password')
            ledger = open_ledger()
            assert [x['id'] for x in history()] == [old['id']]
            ledger.revoke_history_grant(*actor('alice'), grant)
            assert history() == []
            print(json.dumps({'demonstration': 'fictional-local-host-only', 'future_only_join': True,
                              'exact_author_grant': True, 'restart_preserved_history': True,
                              'revocation_prevents_fresh_retrieval': True, 'live_provider_or_transport': False}))
        finally:
            ledger.close()
            for auth in auths.values():
                auth.close()


if __name__ == '__main__':
    main()
