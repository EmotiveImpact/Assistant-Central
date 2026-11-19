"""Directly authored offers between separately provisioned owner runtimes."""
from .crypto import digest
from .mission import PROJECTION, direct_offer, direct_task_text, evidence, mission_context, task_details
from .runtime import need
from .workflow import FIXTURE_GRANT


def propose(runtime, token, agreed, brief, task_id, expires, permit_fixture):
    need(type(permit_fixture) is bool)
    offer = direct_offer(runtime.fingerprint, task_id, expires, agreed)
    context = mission_context(digest(offer), agreed['cap_microusd'])
    grant = {**FIXTURE_GRANT, 'projection': PROJECTION} if permit_fixture else None
    title = agreed['goal'].encode('utf-8')[:128].decode('utf-8', errors='ignore')
    return runtime.propose(token, agreed['executor'], 'task', title,
                           direct_task_text(brief, offer), context, task_id, expires,
                           provider_disclosure=grant)


def evaluate_return(runtime, token, artifact_id):
    with runtime._transaction(token) as checks:
        row, artifact = runtime._row(artifact_id)
        need(row['direction'] == 'incoming' and row['state'] in ('pending','accepted') and artifact['kind'] == 'artifact')
        def current():
            runtime._current(row)
            runtime._parent(artifact, sending=False)
        current()
        checks.append(current)
        _, parent = runtime._row(artifact['parent_id'])
        value, _ = task_details(parent['text'], parent['context'])
        offer = value.get('offer')
        need(offer is not None and offer['requester'] == runtime.fingerprint)
        return evidence(offer['terms'], artifact['parent_id'], 1, digest(offer), artifact_id, artifact)
