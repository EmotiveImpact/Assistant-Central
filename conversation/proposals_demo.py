"""Fictional trusted-local-host proposal demonstration; no external effects."""
import json
from pathlib import Path
import tempfile

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from .ledger import ConversationLedger
from .proposals import LocalProposals


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        auths, principals, sessions = {}, {}, {}
        now = 2000000000.0
        for name in ('owner_one', 'owner_two'):
            auth = LocalOwnerAuth(root / name, clock=lambda: now)
            auth.bootstrap(name, name + '_assistant', 'Fictional demo password only')
            auths[name], principals[name] = auth, fingerprint(auth.public_identity())
            sessions[name] = auth.login('Fictional demo password only')
        ledger = ConversationLedger(root / 'ledger', auths['owner_one'],
                                    {principals[n]: a for n, a in auths.items()}, clock=lambda: now)
        try:
            def actor(name):
                return principals[name], sessions[name]
            def binding(name):
                return ledger.bind_context(*actor(name), 'fictional_room')
            ledger.create(*actor('owner_one'), 'fictional_room')
            invite = ledger.invite(*actor('owner_one'), 'fictional_room', principals['owner_two'])
            ledger.accept_invitation(*actor('owner_two'), invite['id'])
            proposals = LocalProposals(ledger, *actor('owner_one'))
            first = proposals.create(*actor('owner_one'), binding('owner_one'), request_id='first_draft',
                                     content='Fictional plan for discussion: review two sample sketches.', expires_at=now + 300)
            proposal_id = first['proposal']['statement']['id']
            for name in auths:
                review = proposals.prepare_approval(*actor(name), binding(name), proposal_id)
                agreed = proposals.approve(*actor(name), binding(name), review, review['review_digest'])
            if not agreed['all_owners_approved']:
                raise RuntimeError('Separate owner approvals were not retained')
            second = proposals.create(*actor('owner_one'), binding('owner_one'), request_id='revised_draft',
                                      content='Fictional revised plan: review three sample sketches.', expires_at=now + 300,
                                      replaces=proposal_id)
            historical = proposals.inspect(*actor('owner_two'), binding('owner_two'), proposal_id)
            if historical['all_owners_approved'] or second['approvals']:
                raise RuntimeError('A revision incorrectly reused an approval')
            ledger.close()
            ledger = ConversationLedger(root / 'ledger', auths['owner_one'],
                                        {principals[n]: a for n, a in auths.items()}, clock=lambda: now)
            proposals = LocalProposals(ledger, *actor('owner_one'))
            recovered = proposals.inspect_request(*actor('owner_one'), binding('owner_one'), 'revised_draft')
            if recovered['proposal'] != second['proposal']:
                raise RuntimeError('Exact revision did not survive reopen')
            print(json.dumps({'contract': 'fictional trusted local host', 'separate_owner_approvals': len(agreed['approvals']),
                              'original_now_current': historical['proposal_current'], 'new_revision': recovered['proposal']['statement']['revision'],
                              'new_revision_approvals': len(recovered['approvals']), 'execution_authority': False,
                              'provider_calls': 0, 'external_agreement': False}, indent=2))
        finally:
            ledger.close()
            for auth in auths.values():
                auth.close()


if __name__ == '__main__':
    main()
