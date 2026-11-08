"""Closed trusted startup catalog. Fictional labels are not persistent identities."""
from generic_capabilities import PUBLIC_SHORTLIST
from generic_protocol import IdentityReference, Conversation, Task, task_envelope
from network import Denied, digest

SELECTORS = ('garden', 'astronomy')


def fixture(selector='garden'):
    if type(selector) is not str or selector not in SELECTORS:
        raise Denied('Unknown trusted task fixture')
    identities = (IdentityReference('alice','provider-one-fixture','Alice'),
                  IdentityReference('bob','provider-two-fixture','Bob'))
    if selector == 'garden':
        task = Task('synthetic-resource-shortlist', Conversation('friends-resource-sharing', identities),
                    'alice','bob',PUBLIC_SHORTLIST,'find-public-resources')
        query, title, path = 'Synthetic examples for a community garden guide', 'Fictional public guide', 'garden-guide'
    else:
        task = Task('synthetic-astronomy-shortlist', Conversation('friends-astronomy-sharing', identities),
                    'bob','alice',PUBLIC_SHORTLIST,'find-astronomy-resources')
        query, title, path = 'Synthetic examples for a beginner astronomy guide', 'Fictional astronomy guide', 'astronomy-guide'
    request = task_envelope(task,'request',{'query':query,'max_items':2})
    result = task_envelope(task,'result',{'items':[{'title':title,'url':'https://example.invalid/'+path,
                'summary':'Synthetic resource reference; not browsed or verified.'}]},reply_to=digest(request))
    return task, identities, request, result


def exact_fixture(task):
    for selector in SELECTORS:
        candidate = fixture(selector)
        if type(task) is Task and candidate[0] == task:
            return candidate
    raise Denied('Guide only supports an exact immutable catalog task')
