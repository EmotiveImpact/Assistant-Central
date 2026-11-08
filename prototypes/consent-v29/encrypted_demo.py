"""Fictional owner-signed → encrypted queue → signed receipt → local processing.

Four owner signer subprocesses and a separate guarded executor. No owner private
keys enter the executor or this console. No network, real account or calendar.
"""
import argparse
import json
import secrets
import tempfile
import time
from demo import fixture
from fixture_ipc import JsonProcess
from bound_identity import DELIVERY_DOMAIN, IdentityRegistry
from network import Denied, context_digest, digest
from owner_auth import DOMAIN
from review import render_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate', action='store_true', help='Label all fictional owner confirmations as simulated')
    parser.add_argument('--scenario', choices=('normal','lost-receipt','cancel-before-dispatch','cancel-after-receipt'), default='normal')
    args = parser.parse_args()
    meeting, agents, projection = fixture()
    context = context_digest(meeting)
    print('V5 OFFLINE FIXTURE. Fictional people, owner identities, transport keys and calendars.')
    print('SIMULATED OWNER CONFIRMATIONS.' if args.simulate else 'One trusted console operator plays every fictional owner role.')
    print('Four separate owner signers; one verification/execution process; separate receiver databases.')
    signers, executor = {}, None
    roots, bindings, pair_versions = {}, {}, {}
    sent = 0

    def confirm(phrase):
        return phrase if args.simulate else input(f"Type '{phrase}' or anything else to deny: ")

    with tempfile.TemporaryDirectory(prefix='encrypted-network-fixture-') as directory:
        try:
            for owner in meeting.participants:
                signer = JsonProcess('owner_fixture_process.py','--owner',owner)
                signers[owner] = signer
                roots[owner] = signer.read()['public_key']
            executor = JsonProcess('encrypted_executor_process.py','--state-directory',directory)
            setup = executor.request({'owner_roots': roots})
            if not setup.get('ready_for_bindings'): raise Denied(setup.get('error','Executor refused setup'))
            for owner, request in setup['requests'].items():
                body = request['binding']
                print(f"Bind {owner} to fixture transport key {body['transport_pubkey']}; receive only from {', '.join(body['receive_from'])}; exact meeting {meeting.id}.")
                response = signers[owner].request({'binding_request':request,
                    'confirmation':confirm(f'BIND {owner} {digest(request)}')})
                if not response.get('ok'): raise Denied(response.get('error','Binding was not signed'))
                bindings[owner] = response['binding']
            registry = IdentityRegistry(meeting,roots,bindings)
            ready = executor.request({'bindings':bindings})
            if not ready.get('ready'): raise Denied(ready.get('error','Bound executor did not initialize'))
            for signer in signers.values():
                response = signer.request({'registry':{'owner_roots':roots,'bindings':bindings}})
                if not response.get('registry_verified'): raise Denied(response.get('error','Owner registry not verified'))

            def command(method, **fields):
                result = executor.request({'method':method,**fields})
                if not result.get('ok'): raise Denied(result.get('error','Executor denied command'))
                return result['result']

            def decision(owner, action, target, domain=DOMAIN, envelope=None):
                now = int(time.time())
                body = {'version':1,'domain':domain,'action':action,'owner':owner,'context':context,
                        'nonce':secrets.token_hex(16),'issued_at':now,'expires_at':now+300,'target':target}
                if envelope is not None:
                    print('\n'+render_review(meeting,envelope))
                    print('Approved recipient transport binding:',target['recipient_binding'])
                else:
                    print(f'Owner {owner}: {action}; exact target {json.dumps(target,sort_keys=True)}.')
                print('Decision expires at Unix time:',body['expires_at'])
                signed = signers[owner].request({'decision':body,'envelope':envelope,
                    'confirmation':confirm(f"APPROVE {owner} {action} {body['nonce']}")})
                if not signed.get('ok'): raise Denied(signed.get('error','Owner declined decision'))
                return signed['signed']

            def cancel():
                command('control',signed=decision('charlie','cancel',{'meeting':meeting.id}))

            for agent in agents:
                for owner,peer in dict.fromkeys(((agent.identity,'alice'),('alice',agent.identity))):
                    command('control',signed=decision(owner,'pair',{'peer':peer,'contact_version':0,'ttl':3600}))
                    pair_versions[(owner,peer)] = 1

            def send(message):
                nonlocal sent
                owner,recipient=message['sender'],message['recipient']
                target={'recipient':recipient,'envelope_digest':digest(message),
                        'pair_versions':[pair_versions[(owner,recipient)],pair_versions[(recipient,owner)]],
                        'sender_binding':registry.binding_digest(owner),'recipient_binding':registry.binding_digest(recipient)}
                signed=decision(owner,'send',target,DELIVERY_DOMAIN,message)
                nonce=signed['decision']['nonce']
                status=command('enqueue',signed=signed,envelope=message)
                print('Delivery stage:',status['state'],'(no receipt or scheduling transition yet)')
                if sent==0 and args.scenario=='cancel-before-dispatch':
                    cancel(); status=command('dispatch',delivery_id=nonce)
                    print('After cancellation:',status['state'],'; attempts:',status['attempts'])
                    print('Summary:',json.dumps(command('summary'),sort_keys=True));raise StopIteration
                if sent==0 and args.scenario=='lost-receipt':
                    status=command('lose_ack',delivery_id=nonce)
                    print('Acknowledgement deliberately lost:',status['state'],'(outcome initially unconfirmed)')
                    command('reopen_storage')
                    status=command('reconcile',delivery_id=nonce)
                    print('After storage reopen and read-only reconciliation:',status['state'],'; attempts:',status['attempts'])
                else:
                    status=command('dispatch',delivery_id=nonce)
                    print('Delivery stage:',status['state'],'(verified recipient receipt, not processed yet)')
                if sent==0 and args.scenario=='cancel-after-receipt':
                    cancel(); status=command('process',delivery_id=nonce)
                    print('After cancellation:',status['state'],'(receipt preserved, scheduling stopped)')
                    print('Summary:',json.dumps(command('summary'),sort_keys=True));raise StopIteration
                status=command('process',delivery_id=nonce)
                if status['state']!='processed':raise Denied('Scheduling processing was blocked: '+str(status))
                projection._validate(message);projection._apply_validated(message)
                sent+=1
                print('Delivery stage: processed locally; no calendar booking.')

            for agent in agents:send(agent.preview_availability(meeting))
            projection.propose(agents[0])
            for agent in agents:
                send(projection.preview_proposal(agents[0],agent.identity))
                send(projection.preview_acceptance(agent))
            print('Final summary:',json.dumps(command('summary'),sort_keys=True))
            print('No live relay, real identity enrollment, external message or calendar action occurred.')
        except StopIteration:
            print('Cancellation scenario finished; no new dispatches were attempted.')
        finally:
            if executor:executor.close()
            for signer in signers.values():signer.close()
            print('Fixture processes stopped; generated private keys were not saved or exported.')


if __name__=='__main__':
    try:main()
    except (Denied,EOFError,KeyboardInterrupt) as exc:print('Stopped safely:',str(exc))
