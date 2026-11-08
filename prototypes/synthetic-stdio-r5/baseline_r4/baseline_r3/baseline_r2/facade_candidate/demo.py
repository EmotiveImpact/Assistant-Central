"""Explicit sequential trusted fixture; never install as an assistant dispatcher."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from independent_peer.fixture import Experiment
from independent_peer.protocol import digest
from .store import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher


def run():
    with TemporaryDirectory() as directory, Experiment() as experiment:
        peers = {'alice': experiment.alice, 'bob': experiment.bob}
        public = {actor: peer.owner('describe')['descriptor'] for actor, peer in peers.items()}
        stores = {actor: ProposalStore(Path(directory) / (actor + '-proposals.sqlite'), actor=actor,
                    task_value=experiment.task, public=public) for actor in peers}
        try:
            assistants = {actor: AssistantFacade(store) for actor, store in stores.items()}
            owners = {actor: OwnerReview(store) for actor, store in stores.items()}
            publishers = {actor: SnapshotPublisher(store) for actor, store in stores.items()}
            # These calls are explicit synthetic owner decisions, outside assistant surface.
            bob_grant = peers['bob'].owner('allow_receive')['grant']
            alice_grant = peers['alice'].owner('allow_receive')['grant']
            before_proposal = {actor: peer.owner('inspect') for actor, peer in peers.items()}
            request = assistants['alice'].propose({'text': 'Name one imaginary blue fruit.'})
            assert before_proposal == {actor: peer.owner('inspect') for actor, peer in peers.items()}
            review = owners['alice'].review(request['proposal_id'], grant=bob_grant)
            command = owners['alice'].prepare_approve_and_release(request['proposal_id'],
                reviewed_content_digest=review['status']['content_digest'],
                reviewed_grant_digest=review['selected_grant_digest'], grant=review['selected_grant'])
            # Explicit manual owner-command execution; no facade owns a callback or pipe.
            released_request = peers['alice'].owner(command['op'], **{k:v for k,v in command.items() if k != 'op'})
            owners['alice'].record_response(request['proposal_id'], operation_id=command['operation_id'],
                command_digest=digest(command), response=released_request)
            peers['bob'].peer('deliver', released_request['packet'])
            publishers['bob'].publish(peers['bob'].owner('inspect'))
            assert assistants['bob'].processed_inbox({})['items'] == []
            peers['bob'].owner('process', id=released_request['id'])
            publishers['bob'].publish(peers['bob'].owner('inspect'))
            result = assistants['bob'].propose({'text': 'A moonberry (fictional).'})
            review = owners['bob'].review(result['proposal_id'], grant=alice_grant)
            command = owners['bob'].prepare_approve_and_release(result['proposal_id'],
                reviewed_content_digest=review['status']['content_digest'],
                reviewed_grant_digest=review['selected_grant_digest'], grant=review['selected_grant'])
            released_result = peers['bob'].owner(command['op'], **{k:v for k,v in command.items() if k != 'op'})
            owners['bob'].record_response(result['proposal_id'], operation_id=command['operation_id'],
                command_digest=digest(command), response=released_result)
            peers['alice'].peer('deliver', released_result['packet'])
            peers['alice'].owner('process', id=released_result['id'])
            publishers['alice'].publish(peers['alice'].owner('inspect'))
            return {'label': 'OFFLINE SYNTHETIC PROPOSAL FACADE; NO HOST ISOLATION',
                    'independent_proposal_stores': True,
                    'distinct_endpoint_pids': [peer.owner('inspect')['pid'] for peer in peers.values()],
                    'request_status': assistants['alice'].status({'proposal_id': request['proposal_id']}),
                    'result_status': assistants['bob'].status({'proposal_id': result['proposal_id']}),
                    'alice_processed_inbox': assistants['alice'].processed_inbox({}),
                    'bob_processed_inbox': assistants['bob'].processed_inbox({})}
        finally:
            for store in stores.values():
                store.close()


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
