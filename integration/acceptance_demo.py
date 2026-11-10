"""Fictional, local-only release, rejection and restart acceptance demonstration."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.bootstrap import TeamWorkflow, Denied
from integration.recipient_acceptance import AcceptanceBoundary
from integration.team_proposals import BoundArtifactProposal
from integration.run_checks import guard
from team_workflow import AgentRef, TaskSpec, TeamPlan


def demonstrate():
    plan = TeamPlan('synthetic-acceptance-demo', 'lead', (
        AgentRef('lead', 'alice', 'fixture-a', 'review'),
        AgentRef('researcher', 'bob', 'fixture-b', 'research'),
        AgentRef('writer', 'carol', 'fixture-c', 'copy'),
    ), (
        TaskSpec('research', 'researcher', 'Research a fictional garden', 'research'),
        TaskSpec('copy', 'writer', 'Draft a fictional garden introduction', 'copy', ('research',)),
        TaskSpec('alternate', 'writer', 'Draft another fictional introduction', 'copy', ('research',)),
    ))
    text = 'SYNTHETIC ONLY: A fictional garden opens on Saturday.'
    with tempfile.TemporaryDirectory(prefix='synthetic-acceptance-') as directory:
        path = Path(directory) / 'team.sqlite'
        w = TeamWorkflow(path, plan, clock=lambda: 1000)
        bindings = []
        try:
            w.accept_lead('alice', expected_context=w.context)
            researcher = w.facade('researcher')
            request = researcher.propose_start('research', 'start-research')
            w.decide_start('bob', request['request_id'], request['review_digest'], 'approve',
                           expires=1100, expected_context=w.context)
            researcher.start(request['request_id'])
            researcher.submit('research', 'garden-note', text)
            review = w.disclosure_review('bob', 'garden-note', 'lead', expected_context=w.context)
            w.approve_disclosure('bob', 'garden-note', 'lead', review['review_digest'], expected_context=w.context)
            w.facade('lead').review_output('research', 'garden-note', 'accept')
            boundary = AcceptanceBoundary(w)
            source = boundary.source_control('bob', expected_context=w.context)
            receiver = boundary.recipient_control('carol', 'writer', expected_context=w.context)
            original = {}
            for task in ('copy', 'alternate'):
                review = w.disclosure_review('bob', 'garden-note', 'writer', task, expected_context=w.context)
                w.approve_disclosure('bob', 'garden-note', 'writer', review['review_digest'], task, expected_context=w.context)
                bound = BoundArtifactProposal(w, 'garden-note', task, expected_context=w.context)
                bindings.append(bound)
                bound.facade.propose({'text': text})
                offer_id = boundary.register(bound)['offer_id']
                source.decide(offer_id, source.review(offer_id)['review_digest'], 'approve', expires=1100)
                delivery = source.release(offer_id)
                assert source.status(offer_id)['outcome'] == 'uncertain'
                receiver.receive(delivery)
                review_digest = receiver.review(offer_id)['review_digest']
                if task == 'alternate':
                    receiver.decide(offer_id, review_digest, 'reject')
                original[task] = (offer_id, delivery, review_digest)
            w.close()
            w = TeamWorkflow(path, plan, clock=lambda: 1000)
            boundary = AcceptanceBoundary(w)
            source = boundary.source_control('bob', expected_context=w.context)
            receiver = boundary.recipient_control('carol', 'writer', expected_context=w.context)
            offer_id, delivery, review_digest = original['copy']
            accepted = receiver.decide(offer_id, review_digest, 'accept')
            assert receiver.receive(delivery) == accepted
            try:
                source.release(offer_id)
            except Denied:
                second_release_blocked = True
            else:
                raise AssertionError('Restart must never permit another release')
            rejected_id, rejected_delivery, _ = original['alternate']
            rejected = receiver.receive(rejected_delivery)
            assert rejected['recipient_state'] == 'rejected'
            assert all(w._row(task)['state'] == 'planned' for task in original)
            source.revoke(offer_id)
            historical = receiver.status(offer_id)
            assert historical['recipient_state'] == 'accepted'
            assert historical['current_source_authority'] == 'unavailable'
            return {'synthetic_only': True, 'authenticated_consent': False, 'external_calls': 0,
                    'accepted_after_restart': accepted, 'rejected_after_duplicate_delivery': rejected,
                    'accepted_history_after_withdrawal': historical,
                    'second_release_blocked': second_release_blocked,
                    'recipient_work': 'planned', 'owner_choices': 'scripted fictional controls'}
        finally:
            for bound in bindings: bound.close()
            w.close()


if __name__ == '__main__':
    sys.addaudithook(guard)
    print(json.dumps(demonstrate(), indent=2))
