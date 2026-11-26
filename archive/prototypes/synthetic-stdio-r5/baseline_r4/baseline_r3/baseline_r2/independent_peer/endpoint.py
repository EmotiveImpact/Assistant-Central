"""Recipient-owned authorization and application state. Single-threaded per endpoint."""
import json
import os
import sqlite3

from .protocol import (Identity, Rejected, canonical, descriptor, digest, exact,
                       grant_body, hexid, need, open_packet, scope, seal, task, token, verify, MAX_TEXT)


class Endpoint:
    def __init__(self, actor, database):
        self.identity = Identity(actor)
        self.actor = actor
        self.peer_actor = 'bob' if actor == 'alice' else 'alice'
        self.incoming_kind = 'result' if actor == 'alice' else 'request'
        self.outgoing_kind = 'request' if actor == 'alice' else 'result'
        # Existing state cannot be adopted using fresh in-memory keys. No recovery claim.
        need(not os.path.exists(database) or os.path.getsize(database) == 0, 'occupied store: no key recovery')
        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE policy(singleton INTEGER PRIMARY KEY CHECK(singleton=1), epoch INTEGER NOT NULL,
                                grant_json TEXT, active INTEGER NOT NULL, terminal TEXT);
            INSERT INTO policy VALUES(1,0,NULL,0,NULL);
            CREATE TABLE outbox(id TEXT PRIMARY KEY, kind TEXT NOT NULL UNIQUE, body TEXT NOT NULL,
                                packet TEXT NOT NULL, received TEXT, processed TEXT);
            CREATE TABLE inbox(id TEXT PRIMARY KEY, kind TEXT NOT NULL UNIQUE, body TEXT NOT NULL,
                               packet_hash TEXT NOT NULL, received TEXT NOT NULL, processed TEXT);
            CREATE TABLE owner_operations(id TEXT PRIMARY KEY, command_hash TEXT NOT NULL, response TEXT NOT NULL);
        ''')
        with self.db:
            self._set('identity', self.identity.descriptor)
        self.task = None
        self.peer = None

    def close(self):
        self.db.close()

    def _set(self, key, value):
        self.db.execute('INSERT INTO meta VALUES(?,?)', (key, canonical(value).decode()))

    def _policy(self):
        return self.db.execute('SELECT * FROM policy').fetchone()

    def _scope(self, incoming=False):
        need(self.task is not None, 'not configured')
        return scope(self.task, self.peer_actor if incoming else self.actor,
                     self.actor if incoming else self.peer_actor,
                     self.incoming_kind if incoming else self.outgoing_kind)

    def _descriptors(self):
        return {self.actor: self.identity.descriptor, self.peer_actor: self.peer}

    def _live(self):
        need(self._policy()['terminal'] is None, 'local task is terminal')

    def _current_grant(self, grant):
        self._live()
        policy = self._policy()
        need(policy['active'] == 1 and policy['grant_json'] == canonical(grant).decode(), 'recipient consent not current')
        body = verify(grant, 'grant', self.identity.descriptor)
        grant_body(body, self._scope(incoming=True), self._descriptors())

    def _evidence(self, status, body, packet_hash):
        evidence = {'scope': body['scope'], 'id': body['id'], 'message_digest': digest(body),
                    'packet_digest': packet_hash, 'grant_digest': digest(body['grant']),
                    'processor_binding': digest(self.identity.descriptor), 'status': status}
        return self.identity.sign(status, evidence)

    def _check_evidence(self, signed, status, body, packet_hash):
        evidence = verify(signed, status, self.peer)
        exact(evidence, 'scope id message_digest packet_digest grant_digest processor_binding status')
        expected = {'scope': body['scope'], 'id': body['id'], 'message_digest': digest(body),
                    'packet_digest': packet_hash, 'grant_digest': digest(body['grant']),
                    'processor_binding': digest(self.peer), 'status': status}
        need(evidence == expected, 'evidence binding mismatch')
        return evidence

    def _body_shape(self, body):
        exact(body, 'id scope grant request payload')
        hexid(body['id'])
        need(type(body['payload']) is str and not any(0xD800 <= ord(c) <= 0xDFFF for c in body['payload'])
             and 0 < len(body['payload'].encode('utf-8')) <= MAX_TEXT,
             'payload byte bound')

    def _link_result(self, body):
        link = body['request']
        exact(link, 'id digest processed')
        hexid(link['id'])
        row = self.db.execute('SELECT * FROM outbox WHERE id=? AND kind=?', (link['id'], 'request')).fetchone()
        need(row is not None, 'no locally authorized outgoing request')
        request_body = json.loads(row['body'])
        need(link['digest'] == digest(request_body), 'request digest mismatch')
        self._check_evidence(link['processed'], 'processed', request_body, digest(json.loads(row['packet'])))
        return row

    def handle_peer(self, command):
        """Closed untrusted ingress: no actor selector, control route or arbitrary signing."""
        exact(command, 'op value')
        need(command['op'] in ('deliver', 'evidence'), 'peer operation denied')
        need(self.task is not None, 'not configured')
        with self.db:
            if command['op'] == 'deliver':
                return self._deliver(command['value'])
            return self._receive_evidence(command['value'])

    def _deliver(self, packet):
        body = open_packet(self.identity, self.peer, packet)
        self._body_shape(body)
        need(body['scope'] == self._scope(incoming=True), 'message scope mismatch')
        # Authenticate and compare exact immutable packet BEFORE the historical replay fast path.
        existing = self.db.execute('SELECT * FROM inbox WHERE id=?', (body['id'],)).fetchone()
        packet_hash = digest(packet)
        if existing is not None:
            need(existing['packet_hash'] == packet_hash and existing['body'] == canonical(body).decode(), 'id collision')
            return {'historical_replay': True, 'received': json.loads(existing['received']),
                    'processed': json.loads(existing['processed']) if existing['processed'] else None}
        self._current_grant(body['grant'])
        # One fixed request/result per task, not a general session or chat.
        need(self.db.execute('SELECT 1 FROM inbox WHERE kind=?', (self.incoming_kind,)).fetchone() is None, 'incoming slot already used')
        linked = None
        if self.incoming_kind == 'request':
            need(body['request'] is None, 'request cannot carry request link')
        else:
            linked = self._link_result(body)
        receipt = self._evidence('received', body, packet_hash)
        self.db.execute('INSERT INTO inbox VALUES(?,?,?,?,?,NULL)',
                        (body['id'], self.incoming_kind, canonical(body).decode(), packet_hash, canonical(receipt).decode()))
        if linked is not None:
            self.db.execute('UPDATE outbox SET processed=? WHERE id=?',
                            (canonical(body['request']['processed']).decode(), linked['id']))
        return {'historical_replay': False, 'received': receipt, 'processed': None}

    def _receive_evidence(self, value):
        exact(value, 'status evidence')
        status = value['status']
        need(status in ('received', 'processed'), 'unknown evidence status')
        evidence = verify(value['evidence'], status, self.peer)
        need(type(evidence) is dict and type(evidence.get('id')) is str, 'invalid evidence')
        row = self.db.execute('SELECT * FROM outbox WHERE id=?', (evidence['id'],)).fetchone()
        need(row is not None, 'unknown outgoing message')
        self._check_evidence(value['evidence'], status, json.loads(row['body']), digest(json.loads(row['packet'])))
        # Evidence is historical knowledge, not new inbound application data. It remains
        # admissible after local cancellation and never revives authorization.
        old = row[status]
        need(old is None or old == canonical(value['evidence']).decode(), 'conflicting evidence')
        self.db.execute(f'UPDATE outbox SET {status}=? WHERE id=?', (canonical(value['evidence']).decode(), row['id']))
        return {'recorded': status, 'id': row['id'], 'historical_replay': old is not None}

    def handle_owner(self, command):
        need(type(command) is dict and type(command.get('op')) is str, 'invalid owner command')
        op = command['op']
        if op == 'describe':
            exact(command, 'op')
            return {'descriptor': self.identity.descriptor, 'pid': os.getpid()}
        if op == 'inspect':
            exact(command, 'op')
            return self.snapshot()
        if op == 'packet':
            exact(command, 'op id')
            self._live()
            row = self.db.execute('SELECT packet FROM outbox WHERE id=?', (command['id'],)).fetchone()
            need(row is not None, 'unknown outgoing message')
            return json.loads(row['packet'])
        fields = {
            'configure': 'op operation_id task peer',
            'allow_receive': 'op operation_id',
            'revoke_receive': 'op operation_id',
            'cancel': 'op operation_id',
            'refuse': 'op operation_id',
            'approve_send': 'op operation_id payload grant',
            'process': 'op operation_id id',
        }
        need(op in fields, 'owner operation denied')
        exact(command, fields[op])
        hexid(command['operation_id'])
        command_hash = digest(command)
        with self.db:
            existing = self.db.execute('SELECT * FROM owner_operations WHERE id=?', (command['operation_id'],)).fetchone()
            if existing:
                need(existing['command_hash'] == command_hash, 'owner operation id collision')
                if op == 'approve_send':
                    self._live()  # Terminal local cancellation forbids exporting packet bytes again.
                prior = json.loads(existing['response'])
                if op == 'approve_send':
                    prior['historical_replay'] = True
                return prior
            # Configuration is assigned in memory only after transaction commit below.
            response = self._mutate_owner(command)
            self.db.execute('INSERT INTO owner_operations VALUES(?,?,?)',
                            (command['operation_id'], command_hash, canonical(response).decode()))
            self.before_commit()  # Test subclasses may raise to prove rollback; no IPC hook.
        if op == 'configure':
            self.task, self.peer = command['task'], command['peer']
        return response

    def before_commit(self):
        pass

    def _mutate_owner(self, command):
        op = command['op']
        if op == 'configure':
            need(self.task is None and self.db.execute("SELECT 1 FROM meta WHERE key='task'").fetchone() is None, 'already configured')
            task(command['task'])
            descriptor(command['peer'])
            need(command['peer']['actor'] == self.peer_actor, 'wrong fixed peer')
            self._set('task', command['task'])
            self._set('peer', command['peer'])
            return {'configured': True}
        self._scope()
        if op in ('cancel', 'refuse'):
            policy = self._policy()
            if policy['terminal'] is None:
                self.db.execute('UPDATE policy SET terminal=?,active=0 WHERE singleton=1', (op,))
            return {'terminal': self._policy()['terminal']}
        if op == 'revoke_receive':
            self.db.execute('UPDATE policy SET active=0 WHERE singleton=1')
            return {'revoked': True}
        self._live()
        if op == 'allow_receive':
            epoch = self._policy()['epoch'] + 1
            grant = self.identity.sign('grant', {'scope': self._scope(incoming=True), 'nonce': token(), 'epoch': epoch,
                                               'sender_binding': digest(self.peer),
                                               'recipient_binding': digest(self.identity.descriptor)})
            self.db.execute('UPDATE policy SET epoch=?,grant_json=?,active=1 WHERE singleton=1',
                            (epoch, canonical(grant).decode()))
            return {'grant': grant}
        if op == 'approve_send':
            grant = command['grant']
            grant_body(verify(grant, 'grant', self.peer), self._scope(), self._descriptors())
            need(self.db.execute('SELECT 1 FROM outbox').fetchone() is None, 'outgoing slot already used')
            link = None
            if self.outgoing_kind == 'result':
                incoming = self.db.execute("SELECT * FROM inbox WHERE kind='request'").fetchone()
                need(incoming is not None and incoming['processed'] is not None, 'request not locally processed')
                incoming_body = json.loads(incoming['body'])
                # Revocation stops subsequent new derived disclosures too.
                self._current_grant(incoming_body['grant'])
                link = {'id': incoming['id'], 'digest': digest(incoming_body), 'processed': json.loads(incoming['processed'])}
            body = {'id': token(), 'scope': self._scope(), 'grant': grant, 'request': link, 'payload': command['payload']}
            self._body_shape(body)
            packet = seal(self.identity, self.peer, self.identity.sign('message', body))
            self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,NULL,NULL)',
                            (body['id'], self.outgoing_kind, canonical(body).decode(), canonical(packet).decode()))
            return {'id': body['id'], 'message_digest': digest(body), 'packet': packet,
                    'release': 'approved_and_released', 'historical_replay': False}
        if op == 'process':
            row = self.db.execute('SELECT * FROM inbox WHERE id=?', (command['id'],)).fetchone()
            need(row is not None, 'unknown incoming message')
            # Already processed is a historical fact; no second application transition.
            if row['processed']:
                return {'processed': json.loads(row['processed']), 'historical_replay': True}
            body = json.loads(row['body'])
            self._current_grant(body['grant'])
            proof = self._evidence('processed', body, row['packet_hash'])
            self.db.execute('UPDATE inbox SET processed=? WHERE id=?', (canonical(proof).decode(), row['id']))
            return {'processed': proof, 'historical_replay': False}
        raise Rejected('owner operation denied')

    def snapshot(self):
        """Owner-only view: own accepted bytes versus processed application projection."""
        policy = self._policy()
        inbox = [dict(r) for r in self.db.execute('SELECT * FROM inbox')]
        outbox = [dict(r) for r in self.db.execute('SELECT * FROM outbox')]
        def view(row, incoming):
            body = json.loads(row['body'])
            return {'id': row['id'], 'kind': row['kind'], 'message_digest': digest(body),
                    'received_evidence_present': row['received'] is not None, 'processed_evidence_present': row['processed'] is not None,
                    'payload': body['payload'] if not incoming or row['processed'] else None}
        return {'actor': self.actor, 'pid': os.getpid(), 'identity': self.identity.descriptor,
                'configured': self.task is not None, 'policy': {'epoch': policy['epoch'], 'active': bool(policy['active']), 'terminal': policy['terminal']},
                'incoming': [view(r, True) for r in inbox], 'outgoing': [view(r, False) for r in outbox],
                'processed_projection': [view(r, True) for r in inbox if r['processed']],
                'owner_operation_count': self.db.execute('SELECT count(*) FROM owner_operations').fetchone()[0]}
