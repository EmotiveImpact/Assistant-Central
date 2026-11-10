"""Actual two-process synthetic work loop, with no live provider or real data.

Every decision crosses the owner HTTP API. Passwords and bearer sessions remain
inside this disposable harness's memory and never enter evidence or arguments.
The fixture produces labelled fictional text; it does not perform research.
"""
from contextlib import ExitStack
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from .crypto import fingerprint
from .demo import provision, request, running_process


FIXTURE_ROUTE = {'provider': 'openai', 'model': 'synthetic-research-v1', 'max_output_tokens': 128}


def response_status(url, method, path, body=None, token=None, *, origin=None):
    """Read only the status of an intentionally denied request, never its text."""
    connection = http.client.HTTPConnection('127.0.0.1', urlsplit(url).port, timeout=15)
    headers = {'Origin': url if origin is None else origin, 'Accept': 'application/json'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    encoded = None
    if body is not None:
        encoded = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    try:
        connection.request(method, path, encoded, headers)
        response = connection.getresponse()
        response.read(4096)
        return response.status
    finally:
        connection.close()


class TwoProcessWorkflow:
    """Fresh, separately stored fictional identities behind actual processes."""

    def __init__(self, *, enabled=True):
        self.enabled = enabled
        self.stack = ExitStack()
        self.receiver_process = None

    def __enter__(self):
        try:
            self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='assistant-central-work-loop-')))
            self.sender_dir, self.receiver_dir = self.root / 'requester', self.root / 'worker'
            self.sender_password, sender_public = provision(self.sender_dir, 'fictional-requester', 'atlas')
            self.receiver_password, receiver_public = provision(self.receiver_dir, 'fictional-worker', 'beacon')
            self.sender_pin, self.receiver_pin = fingerprint(sender_public), fingerprint(receiver_public)
            self.sender_url, self.sender_pid = self.stack.enter_context(running_process(self.sender_dir))
            self.sender_token = request(self.sender_url, 'POST', '/api/session', {'password': self.sender_password})['token']
            self.start_receiver()
            request(self.sender_url, 'POST', '/api/peers', {'public_identity': receiver_public,
                    'expected_fingerprint': self.receiver_pin, 'endpoint': self.receiver_url}, self.sender_token)
            request(self.receiver_url, 'POST', '/api/peers', {'public_identity': sender_public,
                    'expected_fingerprint': self.sender_pin, 'endpoint': self.sender_url}, self.receiver_token)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        self.stop_receiver()
        self.stack.close()

    def stop_receiver(self):
        if self.receiver_process is not None:
            self.receiver_process.__exit__(None, None, None)
            self.receiver_process = None

    def start_receiver(self, port=0):
        self.receiver_process = running_process(self.receiver_dir, port, synthetic_workflow=self.enabled)
        try:
            self.receiver_url, self.receiver_pid = self.receiver_process.__enter__()
        except BaseException:
            self.receiver_process = None
            raise
        self.receiver_token = request(self.receiver_url, 'POST', '/api/session', {'password': self.receiver_password})['token']

    def owner(self, receiver=False):
        return (self.receiver_url, self.receiver_token) if receiver else (self.sender_url, self.sender_token)

    def state(self, receiver=False):
        url, token = self.owner(receiver)
        return request(url, 'GET', '/api/state', token=token)

    def sync(self, receiver=False):
        url, token = self.owner(receiver)
        return request(url, 'POST', '/api/exchange', {}, token)

    def settle(self):
        # Three passes in each direction admit original packets and signed
        # receipts. No timer, background session or automatic retry is involved.
        for _ in range(3):
            self.sync(); self.sync(True)

    def item_review(self, item_id, receiver=False):
        url, token = self.owner(receiver)
        return request(url, 'GET', '/api/items/' + item_id + '/review', token=token)

    def item_action(self, item_id, action, receiver=False, decision=None):
        url, token = self.owner(receiver)
        body = {'review_digest': self.item_review(item_id, receiver)['review_digest']}
        if decision is not None:
            body['decision'] = decision
        return request(url, 'POST', '/api/items/' + item_id + '/' + action, body, token)

    def create_task(self, name, *, grant=True, decision='accept'):
        body = {'peer_id': self.receiver_pin, 'kind': 'task', 'title': 'Fictional ' + name,
                'text': 'SYNTHETIC ONLY: prepare a short fictional community research note for ' + name + '.',
                'context': hashlib.sha256(('SYNTHETIC context ' + name).encode()).hexdigest(),
                'task_id': name, 'expires': time.time() + 1200}
        if grant:
            body['provider_disclosure'] = dict(FIXTURE_ROUTE)
        task = request(self.sender_url, 'POST', '/api/proposals', body, self.sender_token)
        self.item_action(task['id'], 'release')
        if decision is not None:
            self.settle()
            self.item_action(task['id'], 'decision', True, decision)
            self.settle()
        return task

    def prepare(self, item_id):
        return request(self.receiver_url, 'POST', '/api/items/' + item_id + '/workflow', {}, self.receiver_token)

    def workflow(self, run_id, action='', body=None):
        method = 'GET' if body is None else 'POST'
        path = '/api/workflows/' + run_id + ('/' + action if action else '')
        return request(self.receiver_url, method, path, body, self.receiver_token)

    def approve(self, run_id):
        review = self.workflow(run_id, 'review')
        self.workflow(run_id, 'approve', {'review_digest': review['review_digest'], 'expires': time.time() + 600})
        return review['review_digest']


def run():
    with TwoProcessWorkflow() as pilot:
        assert pilot.sender_pid != pilot.receiver_pid
        assert pilot.state(True)['workflow']['enabled'] is True
        task = pilot.create_task('garden-research')
        prepared = pilot.prepare(task['id'])
        run_id = prepared['run_id']
        assert prepared['state'] == 'prepared'
        approved_digest = pilot.approve(run_id)
        completed = pilot.workflow(run_id, 'run', {'review_digest': approved_digest})
        assert completed['state'] == 'completed'
        reviewed = pilot.workflow(run_id, 'result')
        original_result_digest = completed['result_digest']
        assert original_result_digest

        # Offline delivery is retained at the requester. Restart the worker on
        # its original pinned endpoint and recover the original completed run.
        original_token = pilot.receiver_token
        port = urlsplit(pilot.receiver_url).port
        pilot.stop_receiver()
        alternative = pilot.create_task('declined-alternative', decision=None)
        assert pilot.sync()['unavailable'] >= 1
        pilot.start_receiver(port)
        assert response_status(pilot.receiver_url, 'GET', '/api/state', token=original_token) == 401
        recovered = pilot.workflow(run_id)
        assert recovered['state'] == 'completed' and recovered['result_digest'] == original_result_digest
        assert recovered['retry_allowed'] is False
        assert pilot.workflow(run_id, 'result')['review_digest'] == reviewed['review_digest']

        staged = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})
        artifact_id = staged['artifact_id']
        assert artifact_id
        duplicate = pilot.workflow(run_id, 'stage', {'review_digest': reviewed['review_digest']})
        assert duplicate['artifact_id'] == artifact_id
        worker_items = {item['id']: item for item in pilot.state(True)['items']}
        assert worker_items[artifact_id]['state'] == 'draft'
        assert worker_items[artifact_id]['parent_id'] == task['id']
        assert artifact_id not in {item['id'] for item in pilot.state()['items']}
        assert worker_items[artifact_id]['artifact_digest'] == original_result_digest
        pilot.item_action(artifact_id, 'release', True)
        pilot.settle()
        pilot.item_action(artifact_id, 'decision', decision='accept')
        pilot.item_action(alternative['id'], 'decision', True, 'reject')
        pilot.settle()

        # A separately accepted task still cannot run after its originator's
        # signed cancellation has crossed the process boundary.
        withdrawn = pilot.create_task('cancel-before-run')
        cancelled_run = pilot.prepare(withdrawn['id'])['run_id']
        cancelled_review = pilot.approve(cancelled_run)
        pilot.item_action(withdrawn['id'], 'cancel')
        pilot.settle()
        path = '/api/workflows/' + cancelled_run + '/run'
        assert response_status(pilot.receiver_url, 'POST', path,
            {'review_digest': cancelled_review}, pilot.receiver_token) == 400
        assert pilot.workflow(cancelled_run)['claimed_at'] is None
        assert response_status(pilot.receiver_url, 'POST', '/api/workflows/' + run_id + '/run',
            {'review_digest': approved_digest}, pilot.receiver_token) == 400

        requester = {item['id']: item for item in pilot.state()['items']}
        worker_state = pilot.state(True)
        worker = {item['id']: item for item in worker_state['items']}
        claimed = sum(item['claimed_at'] is not None for item in worker_state['workflow']['runs'])
        assert claimed == 1
        assert requester[artifact_id]['historical_state'] == worker[artifact_id]['historical_state'] == 'accepted'
        assert requester[alternative['id']]['historical_state'] == worker[alternative['id']]['historical_state'] == 'rejected'
        return {'synthetic_only': True, 'separate_processes': True, 'separate_private_stores': True,
                'source_grant': 'exact signed fixture route', 'provider_approval': 'separate local owner decision',
                'completed_result': 'original retained fixture result', 'artifact_stage': 'one inert draft; separate release',
                'requester_decision': 'accepted exact returned artifact', 'alternative': 'rejected',
                'offline_delivery': 'retained then delivered on original pinned endpoint',
                'restart': 'original result recovered; old session rejected',
                'duplicate_stage': 'original artifact identity retained',
                'cancellation': 'observed source withdrawal blocked dispatch',
                'fixture_dispatches': claimed, 'live_provider_calls': 0, 'real_people_enrolled': False,
                'hostile_same_uid_isolation_verified': False}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
