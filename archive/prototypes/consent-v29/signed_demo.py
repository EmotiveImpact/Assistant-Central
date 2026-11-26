"""Fictional multi-process owner approvals. No real identities/accounts or network.

Four disposable signer processes retain their own ephemeral private keys. One
separate executor receives only verification keys and exact signed decisions.
The local operator controls every owner role; this is NOT production human auth.
"""
import argparse
import json
import secrets
import tempfile
import time
from pathlib import Path
from demo import fixture
from fixture_ipc import JsonProcess
from network import Denied, context_digest, digest
from owner_auth import DOMAIN
from review import render_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true', help='Explicitly simulate every fictional owner confirmation')
    parser.add_argument('--cancel-after', type=int, help='Cancel after this many messages (1 through 12)')
    args = parser.parse_args()
    if args.cancel_after is not None and not 1 <= args.cancel_after <= 12:
        raise Denied('Cancel-after must be between 1 and 12')
    print('FICTIONAL OFFLINE FIXTURE. No live identity, relay, calendar or account.')
    print('SIMULATED OWNER CONFIRMATIONS.' if args.simulate else 'One local operator plays every owner role.')
    print('Signing keys are disposable, process-local and never exported or saved.')
    meeting, agents, projection = fixture()
    context = context_digest(meeting)
    signers, executor = {}, None
    pair_versions = {}
    messages_sent = 0
    with tempfile.TemporaryDirectory(prefix='signed-network-fixture-') as directory:
        try:
            public_keys = {}
            for owner in meeting.participants:
                signer = JsonProcess('owner_fixture_process.py', '--owner', owner)
                signers[owner] = signer
                hello = signer.read()
                public_keys[owner] = hello['public_key']
            executor = JsonProcess('executor_fixture_process.py', '--state-file', str(Path(directory) / 'state.sqlite3'))
            ready = executor.request({'owner_public_keys': public_keys})
            if not ready.get('ready'):
                raise Denied(ready.get('error', 'Execution fixture did not initialize'))

            def act(owner, action, target, envelope=None):
                now = int(time.time())
                decision = {'version': 1, 'domain': DOMAIN, 'owner': owner, 'action': action,
                            'context': context, 'nonce': secrets.token_hex(16), 'issued_at': now,
                            'expires_at': now + 300, 'target': target}
                if envelope is not None:
                    print('\n' + render_review(meeting, envelope))
                else:
                    print(f'Owner {owner}: {action}; exact target {json.dumps(target, sort_keys=True)}; meeting {meeting.id}.')
                phrase = f"APPROVE {owner} {action} {decision['nonce']}"
                confirmation = phrase if args.simulate else input(f"Type '{phrase}' or anything else to deny: ")
                response = signers[owner].request({'decision': decision, 'envelope': envelope, 'confirmation': confirmation})
                if not response.get('ok'):
                    raise Denied(response.get('error', 'Owner did not sign'))
                result = executor.request({'signed': response['signed'], 'envelope': envelope})
                if not result.get('ok'):
                    raise Denied(result.get('error', 'Executor refused decision'))
                return result

            for agent in agents:
                for owner, peer in dict.fromkeys(((agent.identity, 'alice'), ('alice', agent.identity))):
                    act(owner, 'pair', {'peer': peer, 'contact_version': 0, 'ttl': 3600})
                    pair_versions[(owner, peer)] = 1

            def send(agent, envelope):
                nonlocal messages_sent
                versions = [pair_versions[(envelope['sender'], envelope['recipient'])],
                            pair_versions[(envelope['recipient'], envelope['sender'])]]
                result = act(agent.identity, 'send', {'recipient': envelope['recipient'],
                             'envelope_digest': digest(envelope), 'pair_versions': versions}, envelope)
                # The projection is only the console's display, not executor authority.
                projection._validate(envelope)
                projection._apply_validated(envelope)
                messages_sent += 1
                if args.cancel_after == messages_sent:
                    act('bob', 'cancel', {'meeting': meeting.id})
                    print(f'Cancelled by fictional owner Bob after {messages_sent} locally processed messages.')
                    raise StopIteration
                return result

            for agent in agents:
                send(agent, agent.preview_availability(meeting))
            projection.propose(agents[0])
            for agent in agents:
                send(agents[0], projection.preview_proposal(agents[0], agent.identity))
                send(agent, projection.preview_acceptance(agent))
            print(f'All four fictional participants accepted: {projection.agreed}. Signed message decisions: {messages_sent}.')
            print('No calendar booking or external communication occurred.')
        except StopIteration:
            print('Cancellation fixture complete. No remote cancellation notification exists.')
        finally:
            if executor:
                executor.close()
            for signer in signers.values():
                signer.close()
            print('All disposable signer processes stopped; no signing keys saved.')


if __name__ == '__main__':
    try:
        main()
    except (Denied, EOFError, KeyboardInterrupt) as exc:
        print('Stopped safely:', str(exc))
