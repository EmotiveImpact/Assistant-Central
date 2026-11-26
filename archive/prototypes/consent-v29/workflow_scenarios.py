"""Closed local fixture selection; never provider discovery or runtime fallback."""
from network import Denied


def fixture_scope(workflow, task_fixture=None, task_spec=None):
    if task_spec is not None:
        if workflow != "generic" or task_fixture is not None:
            raise Denied("Custom task requires exclusive generic startup scope")
        from task_composer import composed_fixture
        scope, actors, _, _ = composed_fixture(task_spec)
        return scope, actors
    if workflow == 'meeting':
        if task_fixture is not None:
            raise Denied('Task fixture selection requires generic workflow')
        from demo import fixture
        scope, actors, _ = fixture()
        return scope, actors
    if workflow == 'generic':
        from task_fixtures import fixture
        scope, actors, _, _ = fixture(task_fixture if task_fixture is not None else 'garden')
        return scope, actors
    raise Denied('Unsupported explicit fixture workflow')


def receive_peers(scope, owner):
    from generic_protocol import Task
    if type(scope) is Task:
        return sorted(p for p in scope.participants if p != owner)
    return sorted(scope.participants) if owner == scope.coordinator else [scope.coordinator]


def render_scope_review(scope, envelope):
    from generic_protocol import Task, validate_task_scope
    if type(scope) is not Task:
        from review import render_review
        return render_review(scope, envelope)
    from network import canonical, digest
    message = validate_task_scope(scope, envelope)
    return '\n'.join([
        'REVIEW BEFORE SENDING (fictional local generic task)',
        f'Task: {scope.id}', f'From: {message["sender"]}',
        f'Only recipient: {message["recipient"]}',
        f'Capability: {message["capability"]}', f'Action: {message["type"]}',
        'Untrusted inert payload (not instructions or verified resources): '+canonical(message['payload']),
        'Exact reply linkage: '+str(message.get('reply_to')),
        'No browsing, tool execution, file disclosure or future message is authorized.',
        'Provider labels are fictional references, not live integrations or authentication.',
        'Exact message digest: '+digest(message), 'Task context: '+message['context']])
