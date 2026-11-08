"""Run an entirely fictional two-process request/result exchange using anonymous pipes."""
import json

from .fixture import Experiment


def run():
    with Experiment() as experiment:
        alice, bob = experiment.alice, experiment.bob
        bob_grant = bob.owner('allow_receive')['grant']
        alice_grant = alice.owner('allow_receive')['grant']
        request = alice.owner('approve_send', payload='Name one imaginary blue fruit.', grant=bob_grant)
        receipt = bob.peer('deliver', request['packet'])
        alice.peer('evidence', {'status': 'received', 'evidence': receipt['received']})
        before = {'alice': alice.owner('inspect'), 'bob': bob.owner('inspect')}
        processed = bob.owner('process', id=request['id'])
        # Deliberately do not forward this proof separately. The result embeds it.
        result = bob.owner('approve_send', payload='A moonberry (fictional).', grant=alice_grant)
        received_result = alice.peer('deliver', result['packet'])
        bob.peer('evidence', {'status': 'received', 'evidence': received_result['received']})
        processed_result = alice.owner('process', id=result['id'])
        bob.peer('evidence', {'status': 'processed', 'evidence': processed_result['processed']})
        after = {'alice': alice.owner('inspect'), 'bob': bob.owner('inspect')}
        assert before['bob']['processed_projection'] == []
        assert before['alice']['outgoing'][0]['received_evidence_present'] and not before['alice']['outgoing'][0]['processed_evidence_present']
        assert after['alice']['outgoing'][0]['processed_evidence_present']
        assert after['alice']['processed_projection'][0]['payload'] == 'A moonberry (fictional).'
        assert after['alice']['pid'] != after['bob']['pid']
        return {'label': 'SYNTHETIC OFFLINE EXPERIMENT; NOT A LIVE NETWORK',
                'distinct_pids': [after['alice']['pid'], after['bob']['pid']],
                'stores': ['alice.sqlite (temporary)', 'bob.sqlite (temporary)'],
                'receipt_is_not_processed': True,
                'result_embedded_processed_request_evidence_verified': True,
                'alice_processed_result': after['alice']['processed_projection'][0]['payload'],
                'bob_knows_result_processed': after['bob']['outgoing'][0]['processed_evidence_present'],
                'private_keys': 'Generated separately inside each child; memory only; not exported.',
                'cleanup': 'Children reaped and temporary state removed on context exit.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
