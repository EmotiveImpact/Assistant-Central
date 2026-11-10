"""Trusted fixture driver over stdin, not a remote owner API or an agent sandbox."""
import hashlib
import json
import os
from pathlib import Path
import ssl
import socket
import sys
import tempfile
import time

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import TransportDenied, b64, canonical, unb64
from pilot.file_exchange import write_packet
from pilot.https_carrier import send_file
from pilot.https_exchange import HTTPSExchange, HTTPSOutcomeUnknown
from pilot.https_mailbox import MailboxServer, Quarantine, ROUTE, parse_packet, read_private
from pilot.runtime import PilotRuntime, RuntimeDenied

OWNERS = {'atlas': 22001, 'beacon': 22002}
PORT = 8443


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value)


def environment():
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    return {'uid': os.getuid(), 'gid': os.getgid(), 'groups': os.getgroups(),
            'namespaces': {key: os.readlink('/proc/self/ns/' + key) for key in ('net', 'mnt', 'pid')},
            'cap_effective': status['CapEff'].strip(), 'cap_permitted': status['CapPrm'].strip(),
            'seccomp': status['Seccomp'].strip(), 'no_new_privs': status['NoNewPrivs'].strip(),
            'interfaces': sorted(os.listdir('/sys/class/net'))}


def owner_operation(directory, spool, request):
    """Every fixture call logs in locally and closes its own store before returning."""
    auth = runtime = None
    try:
        auth = LocalOwnerAuth(directory)
        if request['operation'] == 'provision':
            auth.bootstrap('fictional-' + request['owner'], request['owner'], request['password'])
            private_write(directory / 'ca.pem', request['ca'])
            private_write(directory / 'wrong-ca.pem', request['wrong_ca'])
        session = auth.login(request['password'])
        runtime = PilotRuntime(directory, auth)
        exchange = HTTPSExchange(runtime)
        operation = request['operation']
        if operation == 'provision':
            return {'identity': runtime.identity, 'fingerprint': runtime.fingerprint}
        if operation == 'enrol':
            runtime.enrol_peer(session, request['identity'], request['fingerprint'])
            return {'enrolled': True}
        if operation == 'propose':
            return runtime.propose(session, request['recipient'], request.get('kind', 'task'),
                'Fictional HTTPS acceptance', request['text'], 'c' * 64,
                request.get('task_id', 'fictional-https-acceptance'), time.time() + (600 if request.get('parent_id') else 1200), request.get('parent_id'))
        if operation in ('release', 'accept', 'cancel'):
            identifier = request['id']
            review = runtime.review(session, identifier)
            if operation == 'accept':
                return runtime.decide(session, identifier, review['review_digest'], 'accept')
            return getattr(runtime, operation)(session, identifier, review['review_digest'])
        if operation in ('send', 'send_receipt'):
            ca = request.get('ca', 'ca.pem')
            assert ca in ('ca.pem', 'wrong-ca.pem', None)
            return getattr(exchange, operation)(session, request['message_id'], request['target'],
                request['recipient'], retry=request.get('retry', False), ca_file=directory / ca if ca else None)
        if operation == 'import':
            digest = request['file_digest']
            assert len(digest) == 64 and set(digest) <= set('0123456789abcdef')
            return exchange.receive(session, spool / (digest + '.json'), request['sender'], digest)
        if operation == 'state':
            state = runtime.state(session)
            return {'fingerprint': runtime.fingerprint, 'items': state['items'],
                    'provider_store_present': runtime.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pilot_provider_runs'").fetchone() is not None,
                    'history': state['history']}
        if operation == 'item':
            return runtime.status(session, request['id'])
        if operation == 'attempts':
            return exchange.status(session, request['message_id'])
        if operation == 'outbox':
            row = runtime.exchange.outbox_status(request['message_id'])
            # Deliberate retained-byte inspection; never output ciphertext or key material.
            packet = json.loads(runtime.exchange._outbox(request['message_id'])['packet'])
            return {'state': row['state'], 'attempts': row['attempts'],
                    'file_digest': hashlib.sha256(canonical(packet)).hexdigest(),
                    'message_id': packet['header']['message_id'], 'expires': packet['header']['expires']}
        if operation == 'tampered_send':
            # Adversarial manual carrier copy, not an owner release/attempt API.
            packet = json.loads(runtime.exchange._outbox(request['message_id'])['packet'])
            damaged = bytearray(unb64(packet['ciphertext']))
            damaged[0] ^= 1
            packet['ciphertext'] = b64(bytes(damaged))
            with tempfile.TemporaryDirectory(dir=directory) as temporary:
                path = Path(temporary) / 'packet.json'
                write_packet(path, packet)
                return send_file(path, request['target'], request['recipient'], ca_file=directory / 'ca.pem')
        raise AssertionError('Unsupported fixture operation')
    finally:
        if runtime is not None:
            runtime.close()
        if auth is not None:
            auth.close()


def dispatch(request):
    operation = request['operation']
    if operation == 'environment':
        return environment()
    owner = request['owner']
    assert owner in OWNERS
    directory, spool, tls = Path('/private') / owner, Path('/quarantine') / owner, Path('/tls') / owner
    if operation == 'tls_probe':
        peer = request['peer']
        assert peer in OWNERS
        context = ssl.create_default_context(cafile=directory / 'ca.pem')
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        try:
            with socket.create_connection(('mailbox-' + peer, PORT), timeout=1) as tcp:
                with context.wrap_socket(tcp, server_hostname='mailbox-' + peer) as secure:
                    return {'ready': True, 'version': secure.version(), 'peer_address': secure.getpeername()[0]}
        except (OSError, ssl.SSLError):
            return {'ready': False}
    if operation == 'mailbox_setup':
        for name in ('certificate', 'key', 'recipient'):
            private_write(tls / name, request[name])
        return {'configured': True}
    if operation == 'quarantine':
        files = sorted(spool.glob('*.json'))
        for path in files:
            raw = read_private(path, 32768)
            assert path.stem == hashlib.sha256(raw).hexdigest()
            packet = parse_packet(raw)
            assert set(packet) == {'header', 'ciphertext', 'signature'}
            assert all(marker.encode() not in raw for marker in request['markers'])
        return {'digests': [path.stem for path in files], 'ciphertext_only': True}
    return owner_operation(directory, spool, request)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == 'serve':
        owner = sys.argv[2]
        assert owner in OWNERS
        tls = Path('/tls') / owner
        quarantine = Quarantine(Path('/quarantine') / owner, (tls / 'recipient').read_text())
        try:
            with MailboxServer(quarantine, tls / 'certificate', tls / 'key',
                               address=('0.0.0.0', PORT), enabled=True) as server:
                print(json.dumps({'ready': True, 'tls_minimum': 'TLSv1.3'}), flush=True)
                server.serve_forever(poll_interval=0.1)
        finally:
            quarantine.close()
        return
    request = json.load(sys.stdin)
    try:
        result = dispatch(request)
        print(json.dumps({'ok': True, 'result': result}, sort_keys=True))
    except (AuthError, RuntimeDenied, TransportDenied, HTTPSOutcomeUnknown) as exc:
        # Only these explicit product refusals/unknown outcomes are observations.
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__}))
    except BaseException as exc:
        print(json.dumps({'ok': False, 'unexpected_error_type': type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
