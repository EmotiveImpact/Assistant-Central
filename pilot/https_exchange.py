"""Explicit authenticated owner HTTPS handoff, never mailbox-derived authority."""
import argparse
from contextlib import ExitStack
import getpass
import hashlib
import json
from pathlib import Path
import re
import ssl
import tempfile
import threading
import time
import math
from urllib.parse import urlsplit
import warnings

from .auth import LocalOwnerAuth
from .crypto import MAX_PACKET, TransportDenied, canonical, digest, packet_header, token
from .file_exchange import FileExchange, private_parent, write_packet
from .https_carrier import send_file
from .https_mailbox import ROUTE, parse_packet, read_private
from .runtime import PilotRuntime, RuntimeDenied, hash_id, need
from .transport import MAX_ATTEMPTS, MAX_HISTORY


class HTTPSOutcomeUnknown(RuntimeError):
    """Inspect retained attempts/inbox before another explicitly chosen operation."""


def destination(value):
    """Preflight the same narrow destination grammar before consuming an attempt."""
    need(type(value) is str and 0 < len(value) <= 512
         and all(33 <= ord(char) <= 126 for char in value), 'Invalid HTTPS destination')
    try:
        url = urlsplit(value)
        need(url.scheme == 'https' and url.path == ROUTE and not url.query and not url.fragment
             and url.username is None and url.password is None and url.hostname is not None
             and re.fullmatch(r'[A-Za-z0-9.-]+', url.hostname) is not None
             and (url.port is None or 1 <= url.port <= 65535)
             and url.netloc in (url.hostname, f'{url.hostname}:{url.port}'), 'Invalid HTTPS destination')
    except ValueError:
        raise RuntimeDenied('Invalid HTTPS destination') from None
    return value


class HTTPSExchange:
    """One explicit owner action at a time, sharing the runtime's auth/lock order.

    No background worker, peer enrolment, owner decision or provider is invoked.
    Journal records stay uncertain even when a TLS peer returns the fixed ACK.
    """
    def __init__(self, runtime):
        self.runtime = runtime
        self.files = FileExchange(runtime)

    def _schema(self):
        self.runtime.db.execute('''CREATE TABLE IF NOT EXISTS https_send_attempts(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL,
            packet_digest TEXT NOT NULL, file_digest TEXT NOT NULL,
            recipient TEXT NOT NULL, destination TEXT NOT NULL,
            kind TEXT NOT NULL, state TEXT NOT NULL CHECK(state='uncertain'))''')

    def _rows(self, message_id):
        exists = self.runtime.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='https_send_attempts'").fetchone()
        if not exists:
            return []
        return [dict(row) for row in self.runtime.db.execute(
            'SELECT * FROM https_send_attempts WHERE message_id=? ORDER BY sequence', (message_id,))]

    def status(self, session, message_id):
        token(message_id)
        with self.runtime._transaction(session):
            return {'message_id': message_id, 'attempts': self._rows(message_id),
                    'owner_acceptance': 'not_established', 'authorises_execution': False}

    def _proposal_gate(self, packet):
        if packet['header']['kind'] != 'proposal':
            return  # Original signed cancellation/decision remains transportable.
        runtime = self.runtime
        row, body = runtime._row(packet['header']['proposal_id'])
        need(row['direction'] == 'outgoing' and row['state'] in ('released', 'accepted')
             and row['message_id'] == packet['header']['message_id'], 'Unreleased or stopped proposal')
        runtime._current(row)
        runtime._validate_body(body, runtime.identity, runtime.exchange.peer_public(row['peer_id']), sending=True)

    def _prepare(self, session, identifier, recipient, target, retry, receipt):
        runtime = self.runtime
        with runtime._transaction(session) as checks:
            self._schema()
            if receipt:
                # Missing cache is corruption/incomplete state, never permission to reseal.
                need(runtime.db.execute('SELECT 1 FROM peer_receipts WHERE id=?', (identifier,)).fetchone() is not None,
                     'Original cached receipt required')
                packet = runtime.exchange.receipt_for(runtime.auth, session, identifier)
            else:
                row = runtime.exchange._outbox(identifier)
                need(row['peer'] == recipient, 'Explicit recipient differs from queued packet')
                need(row['attempts'] == 0 or retry, 'Prior delivery attempt requires explicit retry')
                packet = json.loads(row['packet'])
                self._proposal_gate(packet)
                packet = runtime.exchange.prepare_attempt(identifier)
                checks.append(lambda: self._proposal_gate(packet))
            header = packet_header(packet)
            need(header['sender'] == runtime.fingerprint and header['recipient'] == recipient,
                 'Explicit recipient differs from original packet')
            runtime.exchange.peer_public(recipient)
            need(header['expires'] > runtime._now(), 'Original packet has expired')
            checks.append(lambda: need(header['expires'] > runtime._now(), 'Original packet has expired'))
            attempts = self._rows(header['message_id'])
            need(not attempts or retry, 'Prior HTTPS attempt requires explicit retry')
            need(len(attempts) < MAX_ATTEMPTS, 'HTTPS attempt bound reached')
            need(runtime.db.execute('SELECT COUNT(*) FROM https_send_attempts').fetchone()[0] < MAX_HISTORY,
                 'HTTPS history is full; no eviction')
            raw = canonical(packet)
            runtime.db.execute("INSERT INTO https_send_attempts(message_id,packet_digest,file_digest,recipient,destination,kind,state) VALUES(?,?,?,?,?,?,'uncertain')",
                (header['message_id'], digest(packet), hashlib.sha256(raw).hexdigest(), recipient, target, header['kind']))
            sequence = runtime.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        return packet, sequence

    def _prepare_send(self, session, identifier, target, recipient, *, retry, ca_file, receipt):
        """Owner-thread preparation; returns a one-shot network-only capability.

        No database or key access is delegated. The final owner/expiry gates are
        here; cancellation after this boundary cannot recall an in-flight send.
        The caller must dispatch once or close the capability to remove staging.
        """
        runtime = self.runtime
        staging = ExitStack()
        try:
            with self.files.authorised(session), runtime._lock:
                token(identifier)
                hash_id(recipient)
                need(type(retry) is bool, 'Explicit retry flag must be boolean')
                destination(target)
                ssl.create_default_context(cafile=ca_file)
                try:
                    packet, sequence = self._prepare(session, identifier, recipient, target, retry, receipt)
                except (RuntimeDenied, TransportDenied, PermissionError):
                    raise
                except BaseException:
                    raise HTTPSOutcomeUnknown('Preparation outcome unavailable; inspect retained state before any explicit retry.') from None
                try:
                    directory = staging.enter_context(tempfile.TemporaryDirectory(
                        prefix='.https-send-', dir=runtime.directory))
                    source = Path(directory) / 'packet.json'
                    write_packet(source, packet)
                    self._proposal_gate(packet)
                    prepared_at = runtime._now()
                    need(packet['header']['expires'] > prepared_at, 'Original packet has expired')
                    runtime.exchange.peer_public(recipient)
                    runtime.auth.authenticate(session)
                except BaseException:
                    raise HTTPSOutcomeUnknown('Attempt retained as uncertain; inspect state before any explicit retry.') from None
                metadata = {'message_id': packet['header']['message_id'], 'attempt_sequence': sequence,
                            'delivery': 'uncertain', 'owner_acceptance': 'not_established',
                            'authorises_execution': False, 'packet_digest': digest(packet),
                            'file_digest': hashlib.sha256(canonical(packet)).hexdigest(), 'recipient': recipient}
            # Transfer cleanup ownership only after the auth context's final
            # check exits successfully. Failed exit must not leak staging.
            prepared = _PreparedHTTPSAttempt(source, target, recipient, ca_file, metadata, staging,
                         expires=packet['header']['expires'], prepared_at=prepared_at, clock=runtime.clock)
            staging = None
            return prepared
        finally:
            if staging is not None:
                staging.close()

    def _send(self, session, identifier, target, recipient, *, retry, ca_file, receipt):
        prepared = self._prepare_send(session, identifier, target, recipient,
                                      retry=retry, ca_file=ca_file, receipt=receipt)
        return prepared.dispatch()

    def send(self, session, message_id, target, recipient, *, retry=False, ca_file=None):
        return self._send(session, message_id, target, recipient, retry=retry, ca_file=ca_file, receipt=False)

    def send_receipt(self, session, incoming_id, target, recipient, *, retry=False, ca_file=None):
        return self._send(session, incoming_id, target, recipient, retry=retry, ca_file=ca_file, receipt=True)

    def receive(self, session, source, sender, file_digest):
        """Import one owner-selected immutable quarantine entry, not a mailbox ACK."""
        with self.files.authorised(session), self.runtime._lock:
            hash_id(sender)
            hash_id(file_digest)
            need(Path(source).name == file_digest + '.json', 'Choose the exact quarantine digest file')
            raw = read_private(source, MAX_PACKET)
            need(hashlib.sha256(raw).hexdigest() == file_digest, 'Quarantine bytes differ from selected digest')
            packet = parse_packet(raw)
            need(packet['header']['sender'] == sender and packet['header']['recipient'] == self.runtime.fingerprint,
                 'Selected quarantine sender or recipient differs')
            try:
                result = self.runtime.receive(session, packet)
            except (RuntimeDenied, TransportDenied, PermissionError):
                raise
            except BaseException:
                raise HTTPSOutcomeUnknown('Import outcome unavailable; inspect inbox and cached receipt before retry.') from None
            return {'message_id': result['message_id'], 'file_digest': file_digest,
                    'duplicate': result['duplicate'], 'receipt_available': result['receipt'] is not None,
                    'owner_acceptance': result['owner_acceptance'], 'authorises_execution': False}


class _PreparedHTTPSAttempt:
    """Internal one-shot capability, never constructible from an HTTP request.

    Carries only an already-accounted immutable ciphertext file and fixed route.
    Consumes the capability before any network call, even when that call fails.
    Closing an unused capability abandons delivery, not its durable attempt.
    """
    def __init__(self, source, target, recipient, ca_file, metadata, staging, *, expires, prepared_at, clock):
        self._source, self._target, self._recipient, self._ca_file = source, target, recipient, ca_file
        self._metadata, self._staging = metadata, staging
        self._lock, self._used = threading.Lock(), False
        self._state, self._acknowledged = 'prepared', False
        self._expires, self._prepared_at, self._clock = expires, prepared_at, clock
        self._start_deadline = time.monotonic() + 5

    def observation(self):
        with self._lock:
            return {'state': self._state, 'transport_acknowledged': self._acknowledged}

    def dispatch(self):
        with self._lock:
            need(not self._used, 'Prepared transfer already consumed')
            self._used = True
            self._state = 'running'
        result = None
        try:
            now = self._clock()
            need(type(now) in (int, float) and math.isfinite(now) and 0 < self._prepared_at <= now < self._expires
                 and time.monotonic() < self._start_deadline, 'Prepared transfer start window expired')
            sent = send_file(self._source, self._target, self._recipient, ca_file=self._ca_file)
            result = {**self._metadata, 'transport_acknowledged': sent['transport_acknowledged'] is True}
        except BaseException:
            raise HTTPSOutcomeUnknown('Attempt retained as uncertain; inspect state and quarantine before any explicit retry.') from None
        finally:
            try:
                self._staging.close()
            except BaseException:
                result = None
                raise HTTPSOutcomeUnknown('Attempt retained as uncertain; staging cleanup outcome unavailable.') from None
            finally:
                with self._lock:
                    self._state = 'finished' if result is not None else 'outcome_unknown'
                    self._acknowledged = bool(result and result['transport_acknowledged'])
        return result

    def close(self):
        with self._lock:
            if self._used:
                return
            self._used = True
            self._state = 'outcome_unknown'
        self._staging.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Authenticated explicit HTTPS handoff. Stop the owner service first. Synthetic data only.')
    parser.add_argument('--directory', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('send', 'send-receipt'):
        sub = commands.add_parser(command)
        sub.add_argument('--message-id', required=True, help='For send-receipt: original incoming message ID')
        sub.add_argument('--destination', required=True)
        sub.add_argument('--recipient', required=True)
        sub.add_argument('--retry', action='store_true')
        sub.add_argument('--ca-file')
    sub = commands.add_parser('import')
    sub.add_argument('--input', required=True)
    sub.add_argument('--sender', required=True)
    sub.add_argument('--file-digest', required=True)
    sub = commands.add_parser('status')
    sub.add_argument('--message-id', required=True)
    args = parser.parse_args(argv)
    auth = runtime = None
    try:
        need(all((Path(args.directory) / name).is_file() for name in ('auth.sqlite', 'runtime.sqlite')),
             'Existing owner stores required')
        with private_parent(Path(args.directory) / 'auth.sqlite'):
            pass
        auth = LocalOwnerAuth(args.directory)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Local owner password: ')
        session = auth.login(password)
        del password
        runtime = PilotRuntime(args.directory, auth)
        exchange = HTTPSExchange(runtime)
        if args.command == 'import':
            result = exchange.receive(session, args.input, args.sender, args.file_digest)
        elif args.command == 'status':
            result = exchange.status(session, args.message_id)
        else:
            operation = exchange.send if args.command == 'send' else exchange.send_receipt
            result = operation(session, args.message_id, args.destination, args.recipient,
                               retry=args.retry, ca_file=args.ca_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Stopped. Inspect retained state before any explicit retry.')
        return 1
    except Exception:
        print('Operation unavailable. Stop the owner service; inspect retained state and quarantine before retrying. No automatic retry was made.')
        return 1
    finally:
        if runtime is not None:
            runtime.close()
        if auth is not None:
            auth.close()


if __name__ == '__main__':
    raise SystemExit(main())
