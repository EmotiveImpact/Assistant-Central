"""Durable exact-packet exchange helpers. No HTTP client or background retry.

Runtime must compose receive and its own proposal/decision writes in the same
SQLite transaction. A transport receipt proves durable receipt only, never owner
acceptance, work execution, provider consent or successful cancellation.
"""
from contextlib import contextmanager
import json
import sqlite3
import time

from .crypto import (TransportDenied, _need, _timestamp, canonical, digest, fingerprint,
                     open_packet, packet_header, seal, token, validate_public, verify_packet)

VERSION = 'assistant-central-pilot-exchange/1'
MAX_HISTORY = 1024
MAX_ATTEMPTS = 5


class PeerExchange:
    def __init__(self, db, local_public, *, clock=time.time):
        _need(type(db) is sqlite3.Connection, 'Expected local SQLite connection')
        self.db, self.local, self.clock = db, validate_public(local_public), clock
        self.local_fingerprint = fingerprint(self.local)
        with self._atomic():
            db.execute('CREATE TABLE IF NOT EXISTS peer_meta(id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL, public TEXT NOT NULL)')
            old = db.execute('SELECT version,public FROM peer_meta WHERE id=1').fetchone()
            if old:
                _need(old[0] == VERSION and old[1] == canonical(self.local).decode(), 'Exchange identity/version is immutable')
            else:
                db.execute('INSERT INTO peer_meta VALUES(1,?,?)', (VERSION, canonical(self.local).decode()))
            db.execute('''CREATE TABLE IF NOT EXISTS peer_enrolment(
                fingerprint TEXT PRIMARY KEY, owner_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                public TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','revoked')),
                UNIQUE(owner_id,agent_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS peer_outbox(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, packet TEXT NOT NULL,
                peer TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('queued','uncertain','received','cancelled')),
                attempts INTEGER NOT NULL DEFAULT 0, expires REAL NOT NULL,
                receipt_id TEXT, receipt_digest TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS peer_inbox(
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, header TEXT NOT NULL,
                peer TEXT NOT NULL, kind TEXT NOT NULL, received REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS peer_receipts(
                id TEXT PRIMARY KEY REFERENCES peer_inbox(id), packet TEXT NOT NULL, digest TEXT NOT NULL)''')

    @contextmanager
    def _atomic(self):
        if self.db.in_transaction:
            yield  # enclosing runtime owns commit/rollback
            return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            raise

    def _now(self):
        return _timestamp(self.clock())

    def _capacity(self, table):
        # Table name is from fixed internal call sites, never caller input.
        _need(self.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] < MAX_HISTORY,
              'Bounded exchange history is full; no eviction or reset')

    def enroll_peer(self, peer_public, expected_fingerprint):
        public = validate_public(peer_public)
        pin = fingerprint(public)
        _need(type(expected_fingerprint) is str and expected_fingerprint == pin
              and pin != self.local_fingerprint, 'Explicit exact peer fingerprint required')
        with self._atomic():
            old = self.db.execute('SELECT fingerprint,public,state FROM peer_enrolment WHERE owner_id=? AND agent_id=?',
                                  (public['owner_id'], public['agent_id'])).fetchone()
            if old:
                _need(old[0] == pin and old[1] == canonical(public).decode() and old[2] == 'active',
                      'Peer pin cannot be replaced or revived')
            else:
                _need(self.db.execute('SELECT COUNT(*) FROM peer_enrolment').fetchone()[0] < 16,
                      'Pilot peer capacity reached')
                self.db.execute('INSERT INTO peer_enrolment VALUES(?,?,?,?,\'active\')',
                                (pin, public['owner_id'], public['agent_id'], canonical(public).decode()))
        return {'fingerprint': pin, 'public': public, 'state': 'active'}

    def revoke_peer(self, peer_fingerprint):
        with self._atomic():
            self._peer(peer_fingerprint, active=False)
            self.db.execute("UPDATE peer_enrolment SET state='revoked' WHERE fingerprint=?", (peer_fingerprint,))

    def peers(self):
        return [{'fingerprint': row[0], 'public': json.loads(row[1]), 'state': row[2]}
                for row in self.db.execute('SELECT fingerprint,public,state FROM peer_enrolment ORDER BY fingerprint')]

    def _peer(self, pin, *, active=True):
        _need(type(pin) is str and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin),
              'Invalid peer fingerprint')
        row = self.db.execute('SELECT public,state FROM peer_enrolment WHERE fingerprint=?', (pin,)).fetchone()
        _need(row is not None and (not active or row[1] == 'active'), 'Peer is not explicitly enrolled and active')
        public = json.loads(row[0])
        _need(fingerprint(public) == pin, 'Retained peer identity mismatch')
        return public

    def peer_public(self, pin):
        return self._peer(pin)

    def _outbox(self, message_id):
        token(message_id)
        row = self.db.execute('SELECT id,digest,packet,peer,state,attempts,expires,receipt_id,receipt_digest FROM peer_outbox WHERE id=?', (message_id,)).fetchone()
        _need(row is not None, 'Unknown outgoing packet')
        return dict(zip(('message_id','packet_digest','packet','peer','state','attempts','expires','receipt_id','receipt_digest'), row))

    @staticmethod
    def _status(row):
        return {key: value for key, value in row.items() if key != 'packet'} | {
            'transport_receipt_only': True, 'owner_acceptance': 'not_established', 'work_execution': 'not_established'}

    def outbox_status(self, message_id):
        return self._status(self._outbox(message_id))

    def queue(self, packet):
        header = packet_header(packet)
        with self._atomic():
            peer = self._peer(header['recipient'])
            verify_packet(packet, self.local, peer)
            encoded, packet_digest = canonical(packet).decode(), digest(packet)
            old = self.db.execute('SELECT digest,packet FROM peer_outbox WHERE id=?', (header['message_id'],)).fetchone()
            if old:
                _need(old[0] == packet_digest and old[1] == encoded, 'Message ID already binds a different packet')
                return self.outbox_status(header['message_id'])
            _need(header['created'] <= self._now() + 30 and header['expires'] > self._now(), 'Cannot queue expired/future packet')
            _need(header['kind'] != 'receipt', 'Receipts use the exact inbound receipt cache')
            self._capacity('peer_outbox')
            self.db.execute("INSERT INTO peer_outbox VALUES(?,?,?,?,'queued',0,?,NULL,NULL)",
                            (header['message_id'], packet_digest, encoded, header['recipient'], header['expires']))
            return self.outbox_status(header['message_id'])

    def pending(self):
        result = []
        for row in self.db.execute("SELECT id FROM peer_outbox WHERE state IN ('queued','uncertain') ORDER BY id"):
            status = self.outbox_status(row[0])
            if status['expires'] > self._now() and status['attempts'] < MAX_ATTEMPTS:
                try: self._peer(status['peer'])
                except TransportDenied: continue
                result.append(status)
        return result

    def prepare_attempt(self, message_id):
        """Durably record uncertainty before returning the same stored packet."""
        with self._atomic():
            row = self._outbox(message_id)
            _need(row['state'] in ('queued','uncertain') and row['attempts'] < MAX_ATTEMPTS
                  and row['expires'] > self._now(), 'Outgoing packet is stopped, expired or attempt bound reached')
            peer = self._peer(row['peer'])
            packet = json.loads(row['packet'])
            _need(digest(packet) == row['packet_digest'], 'Retained outgoing packet changed')
            verify_packet(packet, self.local, peer)
            self.db.execute("UPDATE peer_outbox SET state='uncertain',attempts=attempts+1 WHERE id=?", (message_id,))
        return packet

    def cancel(self, message_id):
        """Stop local attempts. This is not remote recall or recipient cancellation."""
        with self._atomic():
            row = self._outbox(message_id)
            if row['state'] in ('queued','uncertain'):
                self.db.execute("UPDATE peer_outbox SET state='cancelled' WHERE id=?", (message_id,))
            return self.outbox_status(message_id)

    def receive(self, packet, auth, session):
        header = packet_header(packet)
        auth.authenticate(session)
        _need(fingerprint(auth.public_identity()) == self.local_fingerprint, 'Wrong local receiver identity')
        with self._atomic():
            peer = self._peer(header['sender'])
            verify_packet(packet, peer, self.local)
            packet_digest = digest(packet)
            old = self.db.execute('SELECT digest FROM peer_inbox WHERE id=?', (header['message_id'],)).fetchone()
            if old:
                _need(old[0] == packet_digest, 'Received message ID already binds different ciphertext')
                return {'duplicate': True, 'envelope': None, 'message_id': header['message_id'],
                        'packet_digest': packet_digest, 'transport_receipt_only': True}
            envelope = open_packet(auth, session, peer, packet, self._now())
            if header['kind'] == 'receipt':
                self._apply_receipt(envelope)
            self._capacity('peer_inbox')
            self.db.execute('INSERT INTO peer_inbox VALUES(?,?,?,?,?,?)',
                            (header['message_id'], packet_digest, canonical(header).decode(),
                             header['sender'], header['kind'], self._now()))
            return {'duplicate': False, 'envelope': envelope, 'message_id': header['message_id'],
                    'packet_digest': packet_digest, 'transport_receipt_only': True}

    def _apply_receipt(self, envelope):
        header, payload = envelope['header'], envelope['payload']
        _need(type(payload) is dict and set(payload) == {'message_id','packet_digest','effect'}
              and payload['effect'] == 'durably_received_only', 'Invalid transport receipt')
        row = self._outbox(payload['message_id'])
        original = packet_header(json.loads(row['packet']))
        _need(payload['packet_digest'] == row['packet_digest'] and header['sender'] == row['peer']
              and all(header[field] == original[field] for field in ('context','artifact_id','proposal_id')),
              'Receipt does not bind the original packet and direction')
        _need(row['receipt_id'] is None or (row['receipt_id'] == header['message_id']
              and row['receipt_digest'] == digest(envelope)), 'Original receipt cannot be replaced')
        # Retain local cancellation separately: late receipt proves exposure,
        # never a renewed permission or successful recall.
        state = 'cancelled' if row['state'] == 'cancelled' else 'received'
        self.db.execute('UPDATE peer_outbox SET state=?,receipt_id=?,receipt_digest=? WHERE id=?',
                        (state, header['message_id'], digest(envelope), payload['message_id']))

    def receipt_for(self, auth, session, incoming_id):
        token(incoming_id)
        auth.authenticate(session)
        _need(fingerprint(auth.public_identity()) == self.local_fingerprint, 'Wrong local receipt identity')
        with self._atomic():
            incoming = self.db.execute('SELECT digest,header,peer,kind FROM peer_inbox WHERE id=?', (incoming_id,)).fetchone()
            _need(incoming is not None and incoming[3] != 'receipt', 'Receipt requires a known non-receipt packet')
            peer = self._peer(incoming[2])
            old = self.db.execute('SELECT packet,digest FROM peer_receipts WHERE id=?', (incoming_id,)).fetchone()
            if old:
                packet = json.loads(old[0])
                _need(digest(packet) == old[1], 'Stored receipt changed')
                verify_packet(packet, self.local, peer)
                return packet
            original = json.loads(incoming[1])
            now = self._now()
            packet = seal(auth, session, peer, message_id='receipt-' + incoming[0],
                          context=original['context'], artifact_id=original['artifact_id'],
                          proposal_id=original['proposal_id'], kind='receipt',
                          payload={'message_id': incoming_id, 'packet_digest': incoming[0],
                                   'effect': 'durably_received_only'}, expires=now + 3600, now=now)
            self.db.execute('INSERT INTO peer_receipts VALUES(?,?,?)',
                            (incoming_id, canonical(packet).decode(), digest(packet)))
            return packet
