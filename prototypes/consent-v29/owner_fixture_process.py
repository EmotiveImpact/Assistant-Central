"""Disposable fictional owner signer, controlled only by the trusted local console.

No key is loaded, stored or exported. Do not expose this stdio channel to an agent.
This verifies key possession and exact confirmation, not the identity of a human.
"""
import argparse
import json
import sys
from offline_guard import install
install()
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from workflow_scenarios import fixture_scope, receive_peers
from network import Denied, digest, context_digest
from owner_auth import decision_bytes, validate_decision
from owner_withdrawal import validate_withdrawal, withdrawal_bytes
from workflow_scenarios import render_scope_review as render_review
from bound_identity import (BINDING_DOMAIN, DELIVERY_DOMAIN, IdentityRegistry,
                            signed_bytes, verify_binding_token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True, choices=('alice', 'bob', 'charlie', 'dana'))
    parser.add_argument('--fixture', action='store_true', required=True)
    parser.add_argument('--workflow', choices=('meeting','generic'), default='meeting')
    parser.add_argument('--task-fixture', choices=('garden','astronomy'))
    parser.add_argument('--task-spec')
    parser.add_argument('--continuity-incarnation')
    parser.add_argument('--continuity-selector')
    args = parser.parse_args()
    if (args.continuity_incarnation is None) != (args.continuity_selector is None):
        raise Denied('Both continuity startup anchors required')
    if args.continuity_incarnation is not None:
        from continuity_proofs import hex64, selector
        hex64(args.continuity_incarnation); selector(args.continuity_selector)
    from task_composer import parse_startup
    task_spec = parse_startup(args.task_spec) if args.task_spec is not None else None
    meeting, _ = fixture_scope(args.workflow, args.task_fixture, task_spec)
    if args.owner not in meeting.participants:
        raise Denied('Owner is not a participant in this fixture workflow')
    key = Ed25519PrivateKey.generate()
    print(json.dumps({'owner': args.owner, 'public_key': key.public_key().public_bytes_raw().hex(),
                      'fixture_only': True}), flush=True)
    registry = None
    continuity_used = set()
    for line in iter(lambda: sys.stdin.buffer.readline(16385), b''):
        if len(line) > 16384 or not line.endswith(b'\n'):
            print(json.dumps({'ok': False, 'error': 'Signer frame exceeds fixture limit'}), flush=True)
            return
        try:
            from fixture_ipc import _unique_object, _reject_constant
            request = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            if type(request) is dict and set(request) == {'continuity_proof', 'anchor', 'confirmation'}:
                from continuity_proofs import OWNER_DOMAIN, validate_body
                import time
                body = validate_body(request['continuity_proof'])
                expected_anchor = {k:body[k] for k in ('incarnation','identity_id','identity_version','continuity_root','fingerprint')}
                if type(request['anchor']) is not dict or digest(request['anchor']) != digest(expected_anchor):
                    raise Denied('Wrong exact continuity anchor')
                if (args.continuity_incarnation is None or body['incarnation'] != args.continuity_incarnation
                        or body['selector'] != args.continuity_selector or body['context'] != context_digest(meeting)
                        or body['actor'] != args.owner or body['owner_root'] != key.public_key().public_bytes_raw().hex()
                        or not body['issued_at'] <= int(time.time()) < body['review_expires_at']):
                    raise Denied('Wrong task possession scope or stale proof')
                if request['confirmation'] != 'ASSOCIATE '+digest(body):
                    raise Denied('Exact informational association confirmation required')
                if body['association_id'] in continuity_used or len(continuity_used) >= 20:
                    raise Denied('No owner proof retries or capacity remaining')
                continuity_used.add(body['association_id'])
                print(json.dumps({'ok':True,'signature':key.sign(signed_bytes(OWNER_DOMAIN,body)).hex()}),flush=True)
                continue
            if type(request) is dict and set(request) == {'binding_request', 'confirmation'}:
                pending = request['binding_request']
                if type(pending) is not dict or set(pending) != {'binding', 'transport_proof'}:
                    raise Denied('Invalid fixture binding request')
                phrase = f"BIND {args.owner} {digest(pending)}"
                if request['confirmation'] != phrase:
                    raise Denied('Exact owner binding confirmation was not supplied')
                if args.workflow == 'generic' and (type(pending['binding']) is not dict or pending['binding'].get('receive_from') != receive_peers(meeting,args.owner)):
                    raise Denied('Generic receive peers must exactly match the other task participant')
                token = {**pending, 'owner_signature': key.sign(signed_bytes(BINDING_DOMAIN, pending)).hex()}
                token = verify_binding_token(meeting, key.public_key().public_bytes_raw().hex(), args.owner, token)
                print(json.dumps({'ok': True, 'binding': token}), flush=True)
                continue
            if type(request) is dict and set(request) == {'registry'}:
                value = request['registry']
                if type(value) is not dict or set(value) != {'owner_roots', 'bindings'}:
                    raise Denied('Invalid fixture registry')
                candidate = IdentityRegistry(meeting, value['owner_roots'], value['bindings'])
                if candidate.owner_roots[args.owner] != key.public_key().public_bytes_raw().hex():
                    raise Denied('Registry replaced this owner verification key')
                if registry is not None and registry.fingerprint != candidate.fingerprint:
                    raise Denied('Signer fixture registry cannot be silently replaced')
                if args.workflow == 'generic' and any(candidate.bindings[o]['binding']['receive_from'] != receive_peers(meeting,o) for o in meeting.participants):
                    raise Denied('Generic registry receive peers must exactly match task')
                registry = candidate
                print(json.dumps({'ok': True, 'registry_verified': True}), flush=True)
                continue
            if type(request) is dict and set(request)=={'withdrawal','original','confirmation'}:
                withdrawal=validate_withdrawal(request['withdrawal'])
                original=request['original']
                if type(original) is not dict or set(original)!={'decision','envelope'}:
                    raise Denied('Withdrawal needs the exact original decision and envelope')
                value=original['decision']
                if type(value) is dict and value.get('domain')==DELIVERY_DOMAIN:
                    if registry is None:raise Denied('Withdrawal requires the verified owner registry')
                    decision,envelope=registry.validate_delivery(value,original['envelope'])
                    if envelope is None:raise Denied('Withdrawal must show the exact original message')
                    render_review(meeting,envelope)
                else:
                    decision=validate_decision(value);envelope=original['envelope']
                    if decision['action']=='send' or envelope is not None:
                        raise Denied('Only bound sends or message-free controls may be withdrawn here')
                if decision['context'] != context_digest(meeting):
                    raise Denied('Withdrawal original is outside this fixture scope')
                target=withdrawal['target']
                if (withdrawal['owner']!=args.owner or decision['owner']!=args.owner
                        or withdrawal['context']!=decision['context']
                        or target['request_id']!=decision['nonce']
                        or target['fingerprint']!=digest({'decision':decision,'envelope':envelope})):
                    raise Denied('Withdrawal does not identify this owner\'s exact original authorization')
                phrase=f"WITHDRAW {args.owner} {target['request_id']} {digest(withdrawal)}"
                if request['confirmation']!=phrase:
                    raise Denied('Exact owner withdrawal confirmation was not supplied')
                signed={'withdrawal':withdrawal,'signature':key.sign(withdrawal_bytes(withdrawal)).hex()}
                print(json.dumps({'ok':True,'signed':signed}),flush=True)
                continue
            if type(request) is not dict or set(request) != {'decision', 'envelope', 'confirmation'}:
                raise Denied('Signer requires an exact decision and explicit local confirmation')
            value = request['decision']
            encrypted = type(value) is dict and value.get('domain') == DELIVERY_DOMAIN
            if encrypted:
                if registry is None:
                    raise Denied('Encrypted delivery requires the owner-verified fixture registry')
                # Validate the exact v5 schema, identity bindings and message before
                # returning any signature. This temporary signature never escapes
                # unless both verification and explicit confirmation succeed.
                candidate = {'decision': value, 'signature': key.sign(signed_bytes(DELIVERY_DOMAIN, value)).hex()}
                decision, _ = registry.verify_delivery(candidate, request['envelope'])
            else:
                decision = validate_decision(value)
            if decision['context'] != context_digest(meeting):
                raise Denied('Decision is outside this immutable fixture context')
            if decision['action'] in ('pair','revoke') and (decision['target']['peer'] not in meeting.participants or (args.workflow == 'generic' and decision['target']['peer'] == args.owner)):
                raise Denied('Control peer is outside this fixture scope')
            if decision['action'] == 'cancel' and decision['target']['meeting'] != meeting.id:
                raise Denied('Cancellation is outside this fixture scope')
            if decision['owner'] != args.owner:
                raise Denied('A fixture owner cannot sign for another owner')
            phrase = f"APPROVE {args.owner} {decision['action']} {decision['nonce']}"
            if request['confirmation'] != phrase:
                raise Denied('Exact owner confirmation phrase was not supplied')
            if decision['action'] == 'send':
                render_review(meeting, request['envelope'])
                if task_spec is not None:
                    from task_composer import validate_composed_request
                    validate_composed_request(task_spec, request['envelope'])
                if (request['envelope']['sender'] != args.owner
                        or digest(request['envelope']) != decision['target']['envelope_digest']
                        or request['envelope']['recipient'] != decision['target']['recipient']):
                    raise Denied('Reviewed message does not match owner decision')
                # Never return private key material, only the public signed decision.
            elif request['envelope'] is not None:
                raise Denied('Non-send decision cannot contain a message')
            signature_bytes = signed_bytes(DELIVERY_DOMAIN, decision) if encrypted else decision_bytes(decision)
            signed = {'decision': decision, 'signature': key.sign(signature_bytes).hex()}
            print(json.dumps({'ok': True, 'signed': signed}), flush=True)
        except (Denied, ValueError, TypeError, KeyError, RecursionError) as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}), flush=True)


if __name__ == '__main__':
    main()
