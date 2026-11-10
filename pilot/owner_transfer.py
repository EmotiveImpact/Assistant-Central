"""Host-configured, explicitly reviewed owner transfers; no browser-selected paths."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import ssl

from .crypto import MAX_PACKET, canonical, digest, packet_header, token
from .file_exchange import private_parent, FileExchangeDenied
from .https_exchange import HTTPSExchange, destination
from .https_mailbox import parse_packet, read_private
from .runtime import hash_id, need
from .transport import MAX_ATTEMPTS, MAX_HISTORY

CONNECTION_ID = r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}'
VERSION = 'assistant-central-owner-transfer/1'


def _exact(value, required, optional=()):
    need(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional), 'Invalid transfer configuration')


def load_config(path):
    """Trusted startup only. No HTTP operation accepts this path or its contents."""
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'Duplicate configuration member')
            result[key] = value
        return result
    return TransferConfig(json.loads(read_private(path, 16384), object_pairs_hook=pairs))


class TransferConfig:
    def __init__(self, value):
        _exact(value, ('version', 'connections'), ('quarantine_directory',))
        need(value['version'] == VERSION and type(value['connections']) is list and len(value['connections']) <= 16,
             'Invalid transfer configuration')
        self.connections = {}
        for connection in value['connections']:
            _exact(connection, ('id', 'label', 'peer_fingerprint', 'destination'), ('ca_file',))
            identifier, label = connection['id'], connection['label']
            need(type(identifier) is str and re.fullmatch(CONNECTION_ID, identifier) is not None
                 and identifier not in self.connections, 'Invalid connection ID')
            need(type(label) is str and 0 < len(label) <= 80 and all(ord(c) >= 32 for c in label), 'Invalid connection label')
            hash_id(connection['peer_fingerprint'])
            destination(connection['destination'])
            ca_file = connection.get('ca_file')
            if ca_file is not None:
                need(type(ca_file) is str and Path(ca_file).is_absolute(), 'CA path must be host-selected and absolute')
                # Pin/read private CA configuration without exposing its path to the UI.
                read_private(ca_file, 65536)
                ssl.create_default_context(cafile=ca_file)
            self.connections[identifier] = dict(connection)
        self.quarantine = value.get('quarantine_directory')
        if self.quarantine is not None:
            need(type(self.quarantine) is str and Path(self.quarantine).is_absolute(), 'Quarantine path must be host-selected and absolute')
            with private_parent(Path(self.quarantine) / 'selected.json'):
                pass

    def connection(self, identifier):
        need(type(identifier) is str and identifier in self.connections, 'Unknown configured connection')
        return self.connections[identifier]

    def public(self, identifier):
        connection = self.connection(identifier)
        return {key: connection[key] for key in ('id', 'label', 'peer_fingerprint', 'destination')}


class OwnerTransfer:
    """All runtime operations stay on the owner thread; one network worker only."""
    def __init__(self, runtime, config=None):
        self.runtime, self.config = runtime, config
        self.exchange = HTTPSExchange(runtime)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='explicit-https')
        self.future = None
        self.dispatched = None

    def close(self):
        # An in-flight network call cannot be recalled. Cleanup waits for it.
        self.worker.shutdown(wait=True)

    def _enabled(self):
        need(self.config is not None, 'HTTPS transfers are not configured by the host')

    def active(self):
        return self.future is not None and not self.future.done()

    def _observation(self):
        if self.future is None:
            return None
        observation = {**self.dispatched, 'state': 'in_flight' if self.active() else 'outcome_unknown',
                       'transport_acknowledged': False, 'delivery': 'uncertain', 'authorises_execution': False}
        if not self.active():
            try:
                result = self.future.result()
            except BaseException:
                pass  # Never return exception or peer response contents.
            else:
                observation.update(state='finished', transport_acknowledged=result['transport_acknowledged'])
        return observation

    def _quarantine(self):
        if not self.config or not self.config.quarantine:
            return []
        result = []
        with private_parent(Path(self.config.quarantine) / 'selected.json') as (fd, _):
            with os.scandir(fd) as entries:
                for count, entry in enumerate(entries):
                    need(count < MAX_HISTORY + 1, 'Quarantine inspection bound reached')
                    if re.fullmatch(r'[a-f0-9]{64}\.json', entry.name):
                        need(len(result) < MAX_HISTORY, 'Quarantine inspection bound reached')
                        result.append(entry.name[:-5])
        return sorted(result)

    def _receipt(self, incoming_id):
        token(incoming_id)
        row = self.runtime.db.execute('SELECT packet,digest FROM peer_receipts WHERE id=?', (incoming_id,)).fetchone()
        need(row is not None, 'Original cached receipt required')
        packet = json.loads(row['packet'])  # Already-encrypted wire packet, not application plaintext.
        header = packet_header(packet)
        need(digest(packet) == row['digest'] and header['kind'] == 'receipt'
             and header['sender'] == self.runtime.fingerprint, 'Invalid cached receipt')
        return packet

    def snapshot(self, session):
        with self.runtime._transaction(session):
            outbox = [self.runtime.exchange.outbox_status(row[0]) for row in self.runtime.db.execute('SELECT id FROM peer_outbox ORDER BY id')]
            receipts = []
            for row in self.runtime.db.execute('SELECT id FROM peer_receipts ORDER BY id'):
                header = packet_header(self._receipt(row[0]))
                receipts.append({'incoming_id': row[0], 'message_id': header['message_id'],
                                 'peer': header['recipient'], 'expires': header['expires']})
            return {'enabled': self.config is not None, 'connections': [self.config.public(key) for key in self.config.connections] if self.config else [],
                    'outbox': outbox, 'receipts': receipts, 'quarantine': self._quarantine(),
                    'dispatch': self._observation(), 'authorises_execution': False,
                    'automatic_delivery': False}

    def review(self, session, connection_id, kind, identifier):
        self._enabled()
        connection = self.config.connection(connection_id)
        with self.runtime._transaction(session):
            actions = []
            outbox = None
            if kind == 'outbox':
                row = self.runtime.exchange._outbox(identifier)
                packet = json.loads(row['packet'])
                outbox = self.runtime.exchange.outbox_status(identifier)
                prior = outbox['attempts']
            elif kind == 'receipt':
                packet = self._receipt(identifier)
                prior = 0
            else:
                need(kind == 'quarantine' and self.config.quarantine is not None, 'Unknown transfer selection')
                hash_id(identifier)
                try:
                    raw = read_private(Path(self.config.quarantine) / (identifier + '.json'), MAX_PACKET)
                except (OSError, FileExchangeDenied):
                    need(False, 'Selected private quarantine file unavailable')
                need(hashlib.sha256(raw).hexdigest() == identifier, 'Quarantine bytes differ from selected digest')
                packet = parse_packet(raw)
                header = packet_header(packet)
                need(header['sender'] == connection['peer_fingerprint'] and header['recipient'] == self.runtime.fingerprint,
                     'Selected quarantine sender or recipient differs')
                result = {'connection': self.config.public(connection_id), 'kind': kind, 'identifier': identifier,
                          'message_id': header['message_id'], 'packet_kind': header['kind'],
                          'packet_digest': digest(packet), 'expires': header['expires'], 'outbox': None,
                          'attempts': [], 'allowed_actions': ['import'], 'authorises_execution': False,
                          'owner_acceptance': 'not_established', 'authenticated': False}
                result['review_digest'] = digest(result)
                return result
            header = packet_header(packet)
            need(header['recipient'] == connection['peer_fingerprint'], 'Connection differs from retained recipient')
            attempts = self.exchange._rows(header['message_id'])
            prior = max(prior, len(attempts))
            try:
                self.runtime.exchange.peer_public(connection['peer_fingerprint'])
                need(header['expires'] > self.runtime._now() and len(attempts) < MAX_ATTEMPTS, 'Transfer unavailable')
                if outbox:
                    need(outbox['state'] in ('queued', 'uncertain') and outbox['attempts'] < MAX_ATTEMPTS, 'Transfer unavailable')
                    self.exchange._proposal_gate(packet)
                actions = ['retry' if prior else 'send']
            except (ValueError, PermissionError):
                pass
            result = {'connection': self.config.public(connection_id), 'kind': kind, 'identifier': identifier,
                      'message_id': header['message_id'], 'packet_kind': header['kind'], 'packet_digest': digest(packet),
                      'expires': header['expires'], 'outbox': outbox, 'attempts': attempts,
                      'allowed_actions': actions, 'authorises_execution': False, 'owner_acceptance': 'not_established',
                      'authenticated': True}
            # In-flight status is observational, not part of a mutable approval.
            result['review_digest'] = digest(result)
            return result

    def send(self, session, connection_id, kind, identifier, review_digest, retry):
        need(not self.active(), 'Another HTTPS attempt is still in flight; no request was queued')
        need(kind in ('outbox', 'receipt') and type(retry) is bool, 'Invalid send operation')
        review = self.review(session, connection_id, kind, identifier)
        need(review_digest == review['review_digest'] and ('retry' if retry else 'send') in review['allowed_actions'],
             'Inspect the exact current transfer before sending')
        connection = self.config.connection(connection_id)
        prepared = self.exchange._prepare_send(session, identifier, connection['destination'], connection['peer_fingerprint'],
                     retry=retry, ca_file=connection.get('ca_file'), receipt=kind == 'receipt')
        try:
            self.future = self.worker.submit(prepared.dispatch)
        except BaseException:
            prepared.close()
            raise
        self.dispatched = {'message_id': review['message_id'], 'connection_id': connection_id}
        return {'message_id': review['message_id'], 'delivery': 'uncertain', 'dispatch_started': True,
                'owner_acceptance': 'not_established', 'authorises_execution': False}

    def receive(self, session, connection_id, identifier, review_digest):
        review = self.review(session, connection_id, 'quarantine', identifier)
        need(review_digest == review['review_digest'], 'Inspect the exact selected quarantine entry')
        connection = self.config.connection(connection_id)
        return self.exchange.receive(session, Path(self.config.quarantine) / (identifier + '.json'),
                                     connection['peer_fingerprint'], identifier)
