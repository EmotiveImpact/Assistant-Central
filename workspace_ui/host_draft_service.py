"""Default-disabled authenticated owner review of inert supported-host drafts.

The browser chooses only an opaque configured connection and draft ID. A fixed
Node helper exchanges one bounded request/reply over private pipes; no shell,
network listener, host command, model approval or additional credential exists.
"""
import hashlib
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time

from pilot.auth import _private_path
from pilot.crypto import fingerprint
from pilot.https_mailbox import read_private
from pilot.server import RequestDenied, encode, exact, strict_json

VERSION = 'assistant-central-host-draft-review/1'
HEX = re.compile(r'[a-f0-9]{64}\Z')
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
HELPER = Path(__file__).resolve().parents[1] / 'agent_bridge' / 'src' / 'owner_review.ts'
MAX_REPLY = 32768


def need(value):
    if not value:
        raise RequestDenied('Host draft review unavailable')


def private_path(value, *, directory=False):
    need(type(value) is str and len(value) <= 4096 and Path(value).is_absolute())
    path = Path(value)
    need(not any(p.is_symlink() for p in (path, *path.parents)))
    _private_path(path, directory=directory)
    return path


class HostDraftConfig:
    def __init__(self, value):
        exact(value, ('version', 'connections'))
        need(value['version'] == VERSION and type(value['connections']) is list and 1 <= len(value['connections']) <= 8)
        self.connections = {}
        seen = set()
        for item in value['connections']:
            exact(item, ('id', 'owner_fingerprint', 'launch_file'))
            need(type(item['id']) is str and ID.fullmatch(item['id']) and item['id'] not in self.connections)
            need(type(item['owner_fingerprint']) is str and HEX.fullmatch(item['owner_fingerprint']))
            path = private_path(item['launch_file'])
            need(path not in seen)
            seen.add(path)
            self.connections[item['id']] = (item['owner_fingerprint'], path)


def load_host_draft_config(path):
    private_path(str(path))
    return HostDraftConfig(strict_json(read_private(path, 16384)))


def run_review_helper(request):
    """Fixed argv, allowlisted environment, bounded pipes and real deadline.

    A timeout/lost response can follow a committed dismiss. Callers must inspect
    retained state; they must not substitute a fabricated success or retry.
    """
    raw = encode(request)
    need(len(raw) <= 16384)
    node = shutil.which('node')
    need(node is not None and Path(node).is_absolute())
    output = bytearray()
    with subprocess.Popen([node, str(HELPER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env={'NODE_NO_WARNINGS': '1'},
                          cwd=str(HELPER.parent), close_fds=True) as child:
        try:
            deadline = time.monotonic() + 5
            os.set_blocking(child.stdin.fileno(), False)
            os.set_blocking(child.stdout.fileno(), False)
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdin, selectors.EVENT_WRITE)
                ready.register(child.stdout, selectors.EVENT_READ)
                sent = 0
                while ready.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Host draft outcome unavailable')
                    for key, _ in ready.select(remaining):
                        if key.fileobj is child.stdin:
                            sent += os.write(child.stdin.fileno(), raw[sent:])
                            if sent == len(raw):
                                ready.unregister(child.stdin)
                                child.stdin.close()
                        else:
                            chunk = os.read(child.stdout.fileno(), 4096)
                            if not chunk:
                                ready.unregister(child.stdout)
                            else:
                                output.extend(chunk)
                                if len(output) > MAX_REPLY:
                                    raise RuntimeError('Host draft outcome unavailable')
            code = child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except BaseException:
            child.kill()
            child.wait()
            raise
    try:
        reply = strict_json(bytes(output))
        if code != 0:
            if reply == {'error': 'unavailable'}:
                raise RequestDenied('Host draft review unavailable')
            raise RuntimeError('Host draft outcome unavailable')
        exact(reply, ('result',))
        need(type(reply['result']) is dict)
    except RequestDenied:
        if code != 0 and bytes(output) == b'{"error":"unavailable"}':
            raise
        raise RuntimeError('Host draft outcome unavailable') from None
    return reply['result']


class HostDraftService:
    """Wrap either OwnerService or the authenticated local conversation facade."""
    def __init__(self, underlying, config):
        need(type(config) is HostDraftConfig)
        self.underlying = underlying
        self.mailbox = underlying.mailbox
        self.config = config
        services = getattr(underlying, 'services', None)
        known = set(services) if services is not None else {fingerprint(underlying.auth.public_identity())}
        need(all(principal in known for principal, _ in config.connections.values()))

    def close(self):
        self.underlying.close()

    def actor(self, token):
        if hasattr(self.underlying, 'actor'):
            return self.underlying.actor(token)
        self.underlying.auth.authenticate(token)
        return fingerprint(self.underlying.auth.public_identity()), self.underlying

    def call(self, method, path, token, body):
        if not path.startswith('/api/host-drafts'):
            result = self.underlying.call(method, path, token, body)
            if path == '/api/state' and method == 'GET':
                result['host_drafts'] = {'enabled': True, 'local_only': True, 'execution_authority': False}
            return result
        principal, service = self.actor(token)
        # Hold the actual owner's revocation ordering until the bounded helper
        # exits; send only a session digest and its current absolute deadline.
        with service.auth.authorised(token) as session:
            need(principal == session['identity_fingerprint'])
            context = {'principal': principal, 'sessionDigest': hashlib.sha256(token.encode()).hexdigest(),
                       'sessionExpiresAt': int(session['expires_at'] * 1000)}
            if path == '/api/host-drafts' and method == 'GET':
                connections = []
                for connection, (owner, launch_file) in self.config.connections.items():
                    if owner != principal:
                        continue
                    try:
                        result = self.run(connection, principal, context, {'kind': 'list'})
                        connections.append({'id': connection, 'available': True, 'items': result['items']})
                    except (RequestDenied, ValueError, PermissionError):
                        connections.append({'id': connection, 'available': False, 'items': []})
                service.auth.authenticate(token)
                return {'connections': connections, 'local_only': True, 'execution_authority': False}
            route = re.fullmatch(r'/api/host-drafts/([A-Za-z0-9_-]{1,64})/([A-Za-z0-9_-]{1,64})/(review|dismiss)', path)
            need(route is not None)
            connection, draft_id, action = route.groups()
            operation = {'kind': action, 'draftId': draft_id}
            if action == 'review' and method == 'GET':
                exact(body, ())
            elif action == 'dismiss' and method == 'POST':
                exact(body, ('digest', 'reviewToken'))
                need(type(body['digest']) is str and HEX.fullmatch(body['digest']))
                need(type(body['reviewToken']) is str and 1 <= len(body['reviewToken']) <= 2048)
                operation.update(body)
            else:
                raise RequestDenied('Unknown host draft operation')
            result = self.run(connection, principal, context, operation)
            service.auth.authenticate(token)
            return result

    def run(self, connection, principal, context, operation):
        need(connection in self.config.connections)
        owner, launch_file = self.config.connections[connection]
        need(owner == principal)
        # Re-read the host's current binding and key every time. Replaced scopes,
        # rotated keys, expiry and bridge revocation cannot use an old UI review.
        private_path(str(launch_file))
        launch = strict_json(read_private(launch_file, 8192))
        exact(launch, ('storePath', 'keyHex', 'binding'))
        private_path(launch['storePath'])
        private_path(str(Path(launch['storePath']).parent), directory=True)
        exact(launch['binding'], ('ownerId', 'hostId', 'sessionId', 'conversationId', 'recipientId', 'expiresAt'))
        need(launch['binding']['ownerId'] == principal)
        return run_review_helper({'launch': launch, 'owner': context, 'operation': operation})
