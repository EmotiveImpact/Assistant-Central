"""Explicit workflow adapters to unchanged A4A private-message event primitives.

A draft is unsigned/unpublishable, not a capability grant. Scheduling v1 and task
v2 use separate closed validators; neither can silently masquerade as the other.
"""
import re
from a4a_adapter import scheduling_draft, DraftError
from generic_protocol import Task, validate_task_scope
from network import Meeting, canonical
from vendor.a4a.sanitize import wrap_untrusted


def private_message_draft(envelope, *, scope, peer_pubkeys, delivery_id, created_at):
    if type(scope) is Meeting:
        return scheduling_draft(envelope,meeting=scope,peer_pubkeys=peer_pubkeys,
                                delivery_id=delivery_id,created_at=created_at)
    if type(scope) is not Task:
        raise DraftError('Unknown private-message workflow adapter')
    message=validate_task_scope(scope,envelope)
    if (type(peer_pubkeys) is not dict or set(peer_pubkeys)!=set(scope.participants)
            or any(type(key) is not str or not re.fullmatch('[a-f0-9]{64}',key) for key in peer_pubkeys.values())
            or len(set(peer_pubkeys.values()))!=len(peer_pubkeys)):
        raise DraftError('Peer public references must match exact task participants')
    if type(created_at) is not int or not 0<=created_at<10**19:
        raise DraftError('Invalid private-message timestamp')
    if type(delivery_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,128}',delivery_id):
        raise DraftError('Invalid private-message delivery ID')
    content=canonical(message)
    inner={'id':'','pubkey':'','created_at':created_at,'kind':14,
           'tags':[['p',peer_pubkeys[message['recipient']]],['d',delivery_id],
                   ['a4a_conversation',message['context']]],'content':content,'sig':''}
    return {'offline_only':True,'authenticated':False,'encrypted':False,
            'authorization':'none','publishable':False,'adapter':'task-v2',
            'required_before_network':['exact owner disclosure approval','authenticated peer binding',
                                       'sign inner event','encrypt seal and gift wrap'],
            'inner_event':inner,'preview':wrap_untrusted(content)}
