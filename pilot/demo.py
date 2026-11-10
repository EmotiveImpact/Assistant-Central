"""Two separate loopback processes exchanging fictional work and an artifact.

Passwords and bearer tokens exist only in this disposable test harness's memory.
They are never command arguments, environment variables or result evidence.
"""
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from .auth import LocalOwnerAuth
from .crypto import fingerprint


def request(url, method, path, body=None, token=None):
    connection = http.client.HTTPConnection('127.0.0.1', urlsplit(url).port, timeout=15)
    headers = {'Origin': url, 'Accept': 'application/json'}
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        encoded = response.read(2 * 1024 * 1024 + 1)
        if response.status != 200 or len(encoded) > 2 * 1024 * 1024:
            raise AssertionError('Pilot request failed: ' + method + ' ' + path + ' status ' + str(response.status))
        return json.loads(encoded)
    finally:
        connection.close()


@contextmanager
def running_process(directory, port=0):
    # No inherited provider keys or unrelated credentials reach the pilot process.
    environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8',
                   'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen([sys.executable, '-B', '-m', 'pilot.server', 'serve',
                                '--directory', str(directory), '--port', str(port)],
                               cwd=Path(__file__).resolve().parents[1], env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise AssertionError('Pilot process did not become ready')
        line = process.stdout.readline(4096)
        if not line:
            raise AssertionError('Pilot process exited before readiness')
        ready = json.loads(line)
        yield ready['url'], process.pid
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def provision(directory, owner, agent):
    password = secrets.token_urlsafe(32)
    auth = LocalOwnerAuth(directory)
    try:
        public = auth.bootstrap(owner, agent, password)
    finally:
        auth.close()
    return password, public


def run():
    with tempfile.TemporaryDirectory(prefix='assistant-central-two-owner-') as temporary:
        root = Path(temporary)
        first_dir, second_dir = root / 'first-owner', root / 'second-owner'
        first_password, first_public = provision(first_dir, 'fictional-alex', 'atlas')
        second_password, second_public = provision(second_dir, 'fictional-blair', 'beacon')
        with running_process(first_dir) as (first_url, first_pid), running_process(second_dir) as (second_url, second_pid):
            first_token = request(first_url, 'POST', '/api/session', {'password': first_password})['token']
            second_token = request(second_url, 'POST', '/api/session', {'password': second_password})['token']
            first_pin, second_pin = fingerprint(first_public), fingerprint(second_public)
            request(first_url, 'POST', '/api/peers', {'public_identity': second_public,
                    'expected_fingerprint': second_pin, 'endpoint': second_url}, first_token)
            request(second_url, 'POST', '/api/peers', {'public_identity': first_public,
                    'expected_fingerprint': first_pin, 'endpoint': first_url}, second_token)

            def sync(first=True):
                return request(first_url if first else second_url, 'POST', '/api/exchange', {}, first_token if first else second_token)

            def review(url, token, item_id):
                return request(url, 'GET', '/api/items/' + item_id + '/review', token=token)

            def action(url, token, item_id, name, decision=None):
                body = {'review_digest': review(url, token, item_id)['review_digest']}
                if decision: body['decision'] = decision
                return request(url, 'POST', '/api/items/' + item_id + '/' + name, body, token)

            context = hashlib.sha256(b'SYNTHETIC garden pilot context').hexdigest()
            expires = time.time() + 900
            task = request(first_url, 'POST', '/api/proposals', {'peer_id': second_pin, 'kind': 'task',
                'title': 'Draft a garden invitation', 'text': 'SYNTHETIC ONLY: Draft an invitation for a fictional garden opening.',
                'context': context, 'task_id': 'garden-invitation', 'expires': expires}, first_token)
            action(first_url, first_token, task['id'], 'release')
            sync(); sync(False); sync()
            received = request(second_url, 'GET', '/api/state', token=second_token)
            assert received['items'][0]['state'] == 'pending'
            action(second_url, second_token, task['id'], 'decision', 'accept')
            sync(False); sync(); sync(False)
            assert request(first_url, 'GET', '/api/state', token=first_token)['items'][0]['state'] == 'accepted'
            artifact = request(second_url, 'POST', '/api/proposals', {'peer_id': first_pin, 'kind': 'artifact',
                'title': 'Garden invitation draft', 'text': 'SYNTHETIC ONLY: Join us on Saturday to explore the fictional community garden.',
                'context': context, 'task_id': 'garden-invitation', 'parent_id': task['id'], 'expires': expires}, second_token)
            action(second_url, second_token, artifact['id'], 'release')
            sync(False); sync(); sync(False)
            action(first_url, first_token, artifact['id'], 'decision', 'accept')
            sync(); sync(False); sync()

            # A second task is explicitly refused. Both sides retain that result.
            rejected = request(first_url, 'POST', '/api/proposals', {'peer_id': second_pin, 'kind': 'task',
                'title': 'Declined alternative', 'text': 'SYNTHETIC ONLY: An alternative fictional task.',
                'context': hashlib.sha256(b'SYNTHETIC rejected task').hexdigest(),
                'task_id': 'declined-alternative', 'expires': expires}, first_token)
            action(first_url, first_token, rejected['id'], 'release')
            sync(); sync(False)
            action(second_url, second_token, rejected['id'], 'decision', 'reject')
            sync(False); sync(); sync(False)
            withdrawn = request(first_url, 'POST', '/api/proposals', {'peer_id': second_pin, 'kind': 'task',
                'title': 'Withdrawn before acceptance', 'text': 'SYNTHETIC ONLY: A task withdrawn by its original owner.',
                'context': hashlib.sha256(b'SYNTHETIC withdrawn task').hexdigest(),
                'task_id': 'withdrawn-task', 'expires': expires}, first_token)
            action(first_url, first_token, withdrawn['id'], 'release')
            sync(); sync(False); sync()
            action(first_url, first_token, withdrawn['id'], 'cancel')
            sync(); sync(False); sync()
            states = [request(first_url, 'GET', '/api/state', token=first_token),
                      request(second_url, 'GET', '/api/state', token=second_token)]
            for state in states:
                by_id = {item['id']: item for item in state['items']}
                assert by_id[task['id']]['historical_state'] == 'accepted'
                assert by_id[artifact['id']]['historical_state'] == 'accepted'
                assert by_id[rejected['id']]['historical_state'] == 'rejected'
                assert by_id[withdrawn['id']]['state'] == 'cancelled'
                assert not state['provider']['enabled']
            assert next(item for item in states[0]['items'] if item['id'] == withdrawn['id'])['cancel_packet_receipt_observed']
            assert next(item for item in states[1]['items'] if item['id'] == withdrawn['id'])['peer_cancellation_observed']
            public_results = {'synthetic_only': True, 'separate_processes': first_pid != second_pid,
                              'separate_stores': first_dir != second_dir,
                              'peer_enrolment': 'explicit fingerprint pinning',
                              'task': 'accepted by intended recipient',
                              'artifact': 'accepted by original task owner',
                              'alternative_task': 'rejected by intended recipient',
                              'cancellation': 'observed by peer, with cryptographic receipt at sender',
                              'transport_receipts_are_acceptance': False,
                              'provider_calls': 0, 'real_people_enrolled': False,
                              'hostile_same_uid_isolation_verified': False}
        # Restart both process stores: passwords unlock fresh sessions, history
        # survives, old tokens never become credentials for a fresh process.
        with running_process(first_dir) as (first_url, _), running_process(second_dir) as (second_url, _):
            for url, password in ((first_url, first_password), (second_url, second_password)):
                token = request(url, 'POST', '/api/session', {'password': password})['token']
                state = request(url, 'GET', '/api/state', token=token)
                assert len(state['items']) == 4
                assert sum(item['historical_state'] == 'accepted' for item in state['items']) == 2
                assert sum(item['historical_state'] == 'rejected' for item in state['items']) == 1
            public_results['restart_history'] = 'preserved in both stores'
        return public_results


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
