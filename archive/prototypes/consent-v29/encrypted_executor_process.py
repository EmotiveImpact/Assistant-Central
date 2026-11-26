"""Guarded offline v5 executor. Owner signing keys never enter this process.

Transport keys are disposable actor-local fixtures. Separate SQLite stores model
sender/receivers; reopening storage does not claim lost-key or machine recovery.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from offline_guard import install
install()
from workflow_scenarios import fixture_scope, receive_peers
from durable import LocalDelivery
from network import Denied, context_digest
from owner_auth import SignedOwnerGateway
from session import PersistentSession
from bound_identity import BINDING_DOMAIN, IdentityRegistry, possession_digest
from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver
from owner_workflow import OwnerWorkflow
from vendor.a4a_sdk.keys import Keys
from vendor.a4a_sdk import crypto


def frame():
    data = sys.stdin.buffer.readline(16385)
    if not data: return None
    if len(data) > 16384 or not data.endswith(b'\n'): raise Denied('Fixture frame exceeds 16 KiB')
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise Denied('Invalid bounded fixture JSON frame') from exc


def reply(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', action='store_true', required=True)
    parser.add_argument('--state-directory', required=True)
    parser.add_argument('--owner-workflow', action='store_true', help='Expose only reviewed owner requests, not raw approval APIs')
    parser.add_argument('--workflow', choices=('meeting','generic'), default='meeting')
    parser.add_argument('--task-fixture', choices=('garden','astronomy'))
    parser.add_argument('--task-spec')
    args = parser.parse_args()
    if args.workflow == 'generic' and not args.owner_workflow:
        raise Denied('Generic fixture requires the closed owner workflow surface')
    directory = Path(args.state_directory)
    directory.mkdir(parents=True, exist_ok=True)
    from task_composer import parse_startup
    task_spec = parse_startup(args.task_spec) if args.task_spec is not None else None
    meeting, agents = fixture_scope(args.workflow, args.task_fixture, task_spec)
    bootstrap = frame()
    if type(bootstrap) is not dict or set(bootstrap) != {'owner_roots'}:
        raise Denied('Trusted console must bootstrap public owner roots once')
    roots = bootstrap['owner_roots']
    keys = {owner: Keys() for owner in meeting.participants}
    now = int(time.time()); requests = {}
    for owner in meeting.participants:
        body = {'version': 1, 'domain': BINDING_DOMAIN, 'owner': owner, 'context': context_digest(meeting),
                'transport_pubkey': keys[owner].pubkey_hex,
                'receive_from': receive_peers(meeting, owner),
                'issued_at': now, 'expires_at': now + 86400}
        requests[owner] = {'binding': body, 'transport_proof': crypto.sign(possession_digest(body), keys[owner].privkey_hex)}
    reply({'ready_for_bindings': True, 'requests': requests, 'fixture_only': True})
    enrollment = frame()
    if type(enrollment) is not dict or set(enrollment) != {'bindings'}:
        raise Denied('Owner-signed public transport bindings are required')
    registry = IdentityRegistry(meeting, roots, enrollment['bindings'])
    if args.workflow == 'generic' and any(registry.bindings[o]['binding']['receive_from'] != receive_peers(meeting,o) for o in meeting.participants):
        raise Denied('Generic receive policies must exactly match the other task participant')
    if any(registry.public_keys[o] != keys[o].pubkey_hex for o in keys):
        raise Denied('Owner bound a different transport key from this fixture actor')
    sender, receiver_stores = None, {}

    def open_stores():
        nonlocal sender, receiver_stores
        if sender is not None: sender.close()
        for store in receiver_stores.values(): store.close()
        receiver_stores = {}
        sender = LocalDelivery(directory / 'sender.sqlite3')
        if args.workflow == 'generic':
            from generic_session import GenericPersistentSession
            session = GenericPersistentSession(sender, agents, meeting)
        else:
            session = PersistentSession(sender, agents, meeting)
        gateway = SignedOwnerGateway(session, roots)
        box = DurableEncryptedOutbox(gateway, registry, keys)
        receivers = {}
        for owner in meeting.participants:
            store = LocalDelivery(directory / (owner + '.sqlite3'))
            receiver_stores[owner] = store
            receivers[owner] = OfflineReceiver(store, registry, owner, keys[owner])
        from generic_owner_workflow import GenericOwnerWorkflow
        workflow_class = GenericOwnerWorkflow if args.workflow == 'generic' else OwnerWorkflow
        workflow = workflow_class(gateway, box) if args.owner_workflow else None
        if task_spec is not None:
            workflow.composed_spec = task_spec
        return session, gateway, box, receivers, workflow

    try:
        session, gateway, box, receivers, workflow = open_stores()
        reply({'ready': True, 'fixture_only': True, 'registry_fingerprint': registry.fingerprint})
        while True:
            request = frame()
            if request is None: break
            try:
                if type(request) is not dict: raise Denied('Expected a closed fixture command')
                method = request.get('method')
                if workflow is not None and method not in ('request_prepare','request_review','request_list','request_resolve',
                        'request_submit','request_recover','request_replace','request_pairing','withdrawal_prepare','withdrawal_commit','withdrawal_fresh',
                        'fixture_agent_call','agent_proposal_review','agent_proposal_list','workflow_next','delivery_view','delivery_check','delivery_attempt','delivery_process',
                        'fixture_lose_ack','fixture_fail_before_receipt','reopen_storage','summary',
                        'response_context','preview_response','prepare_response','received_messages'):
                    raise Denied('Owner workflow mode rejects raw approval, control and delivery bypasses')
                if args.workflow == 'generic' and method in ('fixture_agent_call','agent_proposal_review','agent_proposal_list'):
                    # TRUSTED HARNESS routing only. Never expose this outer pipe
                    # or actor selector to an adapter. Adapter input is command.
                    from agent_proposals import AgentProposalBoundary
                    expected = ({'method','actor','command'} if method == 'fixture_agent_call' else
                                {'method','actor'} if method == 'agent_proposal_list' else {'method','actor','proposal_id'})
                    if set(request) != expected:
                        raise Denied('Unknown agent fixture routing fields')
                    boundary = AgentProposalBoundary(workflow, request['actor'])
                    result = (boundary.dispatch(request['command']) if method == 'fixture_agent_call'
                              else boundary.list_owner_proposals() if method == 'agent_proposal_list'
                              else boundary.prepare_owner_review(request['proposal_id']))
                elif args.workflow == 'generic' and workflow is not None and method == 'received_messages' and set(request) == {'method','owner'}:
                    result = workflow.received_messages(request['owner'])
                elif args.workflow == 'generic' and method in ('response_context','preview_response','prepare_response'):
                    # Trusted owner pipe only; never dispatched by agent boundary.
                    fields = {'method','owner'}
                    if method != 'response_context': fields |= {'request_digest','payload'}
                    if method == 'prepare_response': fields |= {'preview_digest','confirmation'}
                    if set(request) != fields: raise Denied('Unexpected owner response fields')
                    result = getattr(workflow,method)(**{k:v for k,v in request.items() if k != 'method'})
                elif workflow is not None and method == 'request_prepare' and {'method','owner','action'} <= set(request) <= {'method','owner','action','peer','envelope','ttl'}:
                    result = workflow.prepare(request['owner'], request['action'], peer=request.get('peer'), envelope=request.get('envelope'), ttl=request.get('ttl',300))
                elif workflow is not None and method == 'workflow_next' and set(request)=={'method'}:
                    result = workflow.next_step()
                elif workflow is not None and method == 'request_list' and set(request)=={'method','owner'}:
                    result = workflow.inbox(request['owner'])
                elif workflow is not None and method in ('request_review','request_submit','request_recover','delivery_view') and set(request)=={'method','owner','request_id'}:
                    fn = {'request_review':workflow.review,'request_submit':workflow.submit,'request_recover':workflow.reconcile_request,'delivery_view':workflow.delivery}[method]
                    result = fn(request['owner'],request['request_id'])
                elif workflow is not None and method == 'request_replace' and set(request)=={'method','owner','request_id','review_digest'}:
                    result = workflow.replace_review(request['owner'],request['request_id'],request['review_digest'])
                elif workflow is not None and method == 'request_pairing' and set(request)=={'method','owner','request_id','review_digest','direction_owner'}:
                    result = workflow.recover_pairing(request['owner'],request['request_id'],request['review_digest'],request['direction_owner'])
                elif workflow is not None and method in ('withdrawal_prepare','withdrawal_fresh') and set(request)=={'method','owner','request_id','review_digest'}:
                    fn=workflow.prepare_withdrawal if method=='withdrawal_prepare' else workflow.prepare_after_withdrawal
                    result=fn(request['owner'],request['request_id'],request['review_digest'])
                elif workflow is not None and method=='withdrawal_commit' and set(request)=={'method','signed'}:
                    result=workflow.withdraw(request['signed'])
                elif workflow is not None and method == 'request_resolve' and {'method','owner','request_id','review_digest','choice'} <= set(request) <= {'method','owner','request_id','review_digest','choice','signed'}:
                    result = workflow.resolve(request['owner'],request['request_id'],request['review_digest'],request['choice'],request.get('signed'))
                elif workflow is not None and method in ('delivery_check','delivery_attempt','delivery_process','fixture_lose_ack','fixture_fail_before_receipt') and set(request)=={'method','owner','request_id'}:
                    nonce, owner = request['request_id'], request['owner']
                    workflow._row(owner,nonce)
                    row = box._row(nonce); receiver = receivers[row['recipient']]
                    if method == 'delivery_check': box.reconcile(nonce,receiver)
                    elif method == 'delivery_process': box.process_received(nonce)
                    elif method == 'delivery_attempt': box.dispatch(nonce,receiver)
                    else:
                        class LostAck:
                            owner, registry = receiver.owner, receiver.registry
                            def receipt(self, identifier): return receiver.receipt(identifier)
                            def receive(self, packet):
                                if method == 'fixture_lose_ack': receiver.receive(packet)
                                raise ConnectionError('Synthetic uncertain offline delivery')
                        try: box.dispatch(nonce,LostAck())
                        except ConnectionError: pass
                    result = workflow.delivery(owner,nonce)
                elif method == 'control' and set(request) == {'method', 'signed'}:
                    if request['signed'].get('decision', {}).get('action') == 'send':
                        raise Denied('This worker permits only identity-bound encrypted sends')
                    result = gateway.apply(request['signed'])
                elif method == 'enqueue' and set(request) == {'method', 'signed', 'envelope'}:
                    result = box.enqueue(request['signed'], request['envelope'])
                elif method in ('dispatch','reconcile','process','status','lose_ack') and set(request) == {'method', 'delivery_id'}:
                    nonce = request['delivery_id']
                    row = box._row(nonce); receiver = receivers[row['recipient']]
                    if method == 'dispatch': result = box.dispatch(nonce, receiver)
                    elif method == 'reconcile': result = box.reconcile(nonce, receiver)
                    elif method == 'process': result = box.process_received(nonce)
                    elif method == 'status': result = box.status(nonce)
                    else:
                        class LostAck:
                            owner, registry = receiver.owner, receiver.registry
                            def receipt(self, identifier): return receiver.receipt(identifier)
                            def receive(self, packet):
                                receiver.receive(packet)
                                raise ConnectionError('Synthetic lost acknowledgement after commit')
                        try: box.dispatch(nonce, LostAck())
                        except ConnectionError: pass
                        result = box.status(nonce)
                elif method == 'reopen_storage' and set(request) == {'method'}:
                    session, gateway, box, receivers, workflow = open_stores()
                    result = {'storage_reopened': True, 'transport_keys_remained_in_live_fixture': True}
                elif method == 'summary' and set(request) == {'method'}:
                    if args.workflow == 'generic':
                        result = {'task_state':session.view().state, 'transitions':sender.db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0],
                                  'receiver_receipts':sum(s.db.execute('SELECT COUNT(*) FROM encrypted_inbox').fetchone()[0] for s in receiver_stores.values()),
                                  'live_provider_calls':0,'executed_tools':0}
                        reply({'ok':True,'result':result})
                        continue
                    result = {'agreed': session.view().agreed, 'transitions': len(session.view().audit),
                              'receiver_receipts': sum(s.db.execute('SELECT COUNT(*) FROM encrypted_inbox').fetchone()[0] for s in receiver_stores.values())}
                else:
                    raise Denied('Worker rejects unknown, signing, key-export or bootstrap commands')
                reply({'ok': True, 'result': result})
            except (Denied, ValueError, TypeError, KeyError, AttributeError) as exc:
                reply({'ok': False, 'error': str(exc)})
    finally:
        if sender is not None: sender.close()
        for store in receiver_stores.values(): store.close()


if __name__ == '__main__':
    try: main()
    except (Denied, ValueError, EOFError) as exc:
        reply({'ok': False, 'error': str(exc)})
        sys.exit(1)
