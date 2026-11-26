"""Offline durable outbox, separately stored receiver receipts and reconciliation.

No sockets, relay or calendars. Fixture recipient identity is owner-signed and
proof-of-possession checked, not verified real-person identity. All private keys
remain in live test actors. Storage reopen retains those keys; ReceiptReader can
recover existing receipt evidence without them, not restore identity or send anew.
"""
from owner_withdrawal import assert_not_withdrawn
import json
import hashlib
import re
from network import Denied, canonical, digest
from bound_identity import RECEIPT_DOMAIN, signed_bytes
from sdk_transport_fixture import PinnedSdkFixture
from vendor.a4a_sdk import crypto

RECEIPT_FIELDS = {'version', 'domain', 'delivery_id', 'context', 'sender', 'recipient',
                  'wire_digest', 'message_digest', 'received_at'}


def _bounded_copy(value, maximum=100000):
    try:
        encoded = canonical(value)
        if len(encoded.encode()) > maximum: raise Denied('Encrypted fixture packet exceeds limit')
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied('Packet must be bounded JSON') from exc


def verify_receipt(registry, value, row):
    value = _bounded_copy(value, 4096)
    if type(value) is not dict or set(value) != {'receipt', 'signature'}:
        raise Denied('A receiver-signed receipt is required')
    receipt = value['receipt']
    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        raise Denied('Unknown or missing receipt fields')
    if type(receipt['version']) is not int or receipt['version'] != 1 or receipt['domain'] != RECEIPT_DOMAIN:
        raise Denied('Wrong receipt domain')
    expected = {'delivery_id': row['nonce'], 'context': registry.context, 'sender': row['sender'],
                'recipient': row['recipient'], 'wire_digest': row['wire_digest'], 'message_digest': row['message_digest']}
    if any(receipt[k] != v for k, v in expected.items()):
        raise Denied('Receipt does not acknowledge this exact encrypted delivery')
    if type(receipt['received_at']) is not int or not 0 <= receipt['received_at'] < 2**63:
        raise Denied('Invalid receipt time')
    decision = json.loads(row['signed'])['decision']
    if not decision['issued_at'] <= receipt['received_at'] < decision['expires_at']:
        raise Denied('Receipt reports delivery outside the owner-approved time window')
    registry.permits(row['sender'], row['recipient'], receipt['received_at'])
    signature = value['signature']
    receipt_hash = hashlib.sha256(signed_bytes(RECEIPT_DOMAIN, receipt)).hexdigest()
    if (type(signature) is not str or not re.fullmatch(r'[a-f0-9]{128}', signature)
            or not crypto.verify(receipt_hash, signature, registry.public_keys[row['recipient']])):
        raise Denied('Receiver receipt signature failed')
    return value


class OfflineReceiver:
    """One fixture recipient, its own private transport key, and its own SQLite DB."""
    def __init__(self, store, registry, owner, private_key):
        self.store, self.db, self.registry, self.owner = store, store.db, registry, owner
        self.peer = PinnedSdkFixture.for_bound_peer(registry.meeting, owner, private_key, registry.public_keys)
        self._private_key = private_key
        registry.pin(store)
        self.db.execute('''CREATE TABLE IF NOT EXISTS encrypted_inbox (
            nonce TEXT PRIMARY KEY, context TEXT NOT NULL, sender TEXT NOT NULL,
            recipient TEXT NOT NULL, wire_digest TEXT NOT NULL, message_digest TEXT NOT NULL,
            signed TEXT NOT NULL, body TEXT NOT NULL, receipt TEXT NOT NULL)''')

    def receive(self, packet):
        packet = _bounded_copy(packet)
        if type(packet) is not dict or set(packet) != {'signed', 'wire'}:
            raise Denied('Unknown or missing encrypted packet fields')
        decision, _ = self.registry.verify_delivery(packet['signed'])
        if decision['target']['recipient'] != self.owner:
            raise Denied('Packet was approved for another receiver')
        nonce, sender = decision['nonce'], decision['owner']
        wire_digest, signed_body = digest(packet['wire']), canonical(packet['signed'])
        with self.store.transaction():
            existing = self.db.execute('SELECT * FROM encrypted_inbox WHERE nonce=?', (nonce,)).fetchone()
            if existing:
                if (existing['wire_digest'] != wire_digest or existing['signed'] != signed_body
                        or existing['recipient'] != self.owner or existing['context'] != self.registry.context):
                    raise Denied('Delivery ID reused with different ciphertext, consent or recipient')
                # Stored, verified receipt only: expired replay creates no new receipt.
                return json.loads(existing['receipt'])
            now = int(self.store.clock())
            if not decision['issued_at'] <= now < decision['expires_at']:
                raise Denied('Delivery owner approval expired or not yet valid')
            self.registry.permits(sender, self.owner, now)
            message = self.peer.open(packet['wire'], self.owner, nonce)
            self.registry.verify_delivery(packet['signed'], message)
            if self.db.execute('SELECT COUNT(*) FROM encrypted_inbox').fetchone()[0] >= self.store.max_records:
                raise Denied('Encrypted receiver record limit reached')
            body = {'version': 1, 'domain': RECEIPT_DOMAIN, 'delivery_id': nonce, 'context': self.registry.context,
                    'sender': sender, 'recipient': self.owner, 'wire_digest': wire_digest,
                    'message_digest': digest(message), 'received_at': now}
            receipt = {'receipt': body, 'signature': crypto.sign(hashlib.sha256(signed_bytes(RECEIPT_DOMAIN, body)).hexdigest(),
                                                               self._private_key.privkey_hex)}
            self.db.execute('INSERT INTO encrypted_inbox VALUES (?,?,?,?,?,?,?,?,?)',
                            (nonce, self.registry.context, sender, self.owner, wire_digest, digest(message),
                             signed_body, canonical(message), canonical(receipt)))
            return receipt

    def receipt(self, nonce):
        """Read-only local reconciliation, not another disclosure or processing action."""
        row = self.db.execute('SELECT receipt FROM encrypted_inbox WHERE nonce=? AND context=? AND recipient=?',
                              (nonce, self.registry.context, self.owner)).fetchone()
        return json.loads(row[0]) if row else None


class ReceiptReader:
    """Read existing signed receipts after private actor keys are gone.

    Cannot receive or decrypt messages. This permits evidence reconciliation,
    not identity/key recovery or retransmission.
    """
    def __init__(self, store, registry, owner):
        self.store, self.db, self.registry, self.owner = store, store.db, registry, owner
        if owner not in registry.public_keys:
            raise Denied('Unknown receipt owner')
        row = self.db.execute('SELECT fingerprint FROM encrypted_identity_registry WHERE context=?', (registry.context,)).fetchone()
        if row is None or row[0] != registry.fingerprint:
            raise Denied('Stored receiver registry does not match approved identities')

    def receipt(self, nonce):
        if type(nonce) is not str or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            raise Denied('Invalid encrypted receipt ID')
        row = self.db.execute('SELECT receipt FROM encrypted_inbox WHERE nonce=? AND context=? AND recipient=?',
                              (nonce, self.registry.context, self.owner)).fetchone()
        return json.loads(row[0]) if row else None


class DurableEncryptedOutbox:
    def __init__(self, gateway, registry, sender_keys=None):
        self.gateway, self.session = gateway, gateway.session
        self.store, self.db, self.registry = gateway.delivery, gateway.db, registry
        if registry.context != self.session.context or registry.owner_roots != gateway.public_keys:
            raise Denied('Encrypted transport and owner-approval roots do not agree')
        self.peers = {owner: PinnedSdkFixture.for_bound_peer(self.session.meeting, owner, key, registry.public_keys)
                      for owner, key in (sender_keys or {}).items()}
        registry.pin(self.store)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS encrypted_outbox (
                nonce TEXT PRIMARY KEY, context TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL,
                message_type TEXT NOT NULL, message_digest TEXT NOT NULL, signed TEXT NOT NULL,
                body TEXT NOT NULL, wire TEXT NOT NULL, wire_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued','dispatched','received','processed','blocked','received_blocked','stopped_uncertain')),
                attempts INTEGER NOT NULL DEFAULT 0, receipt TEXT, reason TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_pending_encrypted_operation
                ON encrypted_outbox(context,sender,recipient,message_type)
                WHERE state IN ('queued','dispatched','received','processed','received_blocked','stopped_uncertain');
        ''')

    def _row(self, nonce):
        if type(nonce) is not str or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            raise Denied('Invalid encrypted delivery ID')
        row = self.db.execute('SELECT * FROM encrypted_outbox WHERE nonce=? AND context=?', (nonce, self.registry.context)).fetchone()
        if row is None: raise Denied('Unknown encrypted delivery')
        return row

    def status(self, nonce):
        row = self._row(nonce)
        return {'delivery_id': nonce, 'state': row['state'], 'attempts': row['attempts'], 'reason': row['reason']}

    def _current_permission(self, decision):
        self.store._require_active(self.session.context)
        target, owner = decision['target'], decision['owner']
        if target['pair_versions'] != self.gateway.contact_versions(owner, target['recipient']):
            raise Denied('Contact changed since this encrypted message was approved')
        self.store._paired(owner, target['recipient'], self.session.context)

    def enqueue(self, signed, envelope):
        signed = _bounded_copy(signed, 8192)
        decision, message = self.registry.verify_delivery(signed, envelope)
        fingerprint = digest({'decision': decision, 'envelope': message})
        with self.store.transaction():
            assert_not_withdrawn(self.db, decision['nonce'])
            existing = self.db.execute('SELECT fingerprint FROM owner_decisions WHERE nonce=?', (decision['nonce'],)).fetchone()
            if existing:
                if existing[0] != fingerprint: raise Denied('Decision nonce reused with a different meaning')
                self._row(decision['nonce'])  # A v4 send cannot silently become a v5 queued send.
                return self.status(decision['nonce'])
            now = int(self.store.clock())
            if not decision['issued_at'] <= now < decision['expires_at']:
                raise Denied('Owner delivery decision expired or not yet valid')
            self._current_permission(decision)
            self.registry.permits(message['sender'], message['recipient'], now)
            self.session._restore()._validate(message)
            for table in ('encrypted_outbox', 'owner_decisions'):
                if self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] >= self.store.max_records:
                    raise Denied('Encrypted outbox or owner-decision record limit reached')
            if message['sender'] not in self.peers: raise Denied('No live fixture sender key is available to seal this message')
            if self.db.execute("SELECT 1 FROM encrypted_outbox WHERE context=? AND sender=? AND recipient=? AND message_type=? AND state!='blocked'",
                               (self.registry.context, message['sender'], message['recipient'], message['type'])).fetchone():
                raise Denied('An approved delivery for this scheduling step is already pending or processed')
            if self.db.execute('''SELECT 1 FROM approvals WHERE id=?
                    UNION ALL SELECT 1 FROM deliveries WHERE id=?
                    UNION ALL SELECT 1 FROM transitions WHERE delivery_id=?''',
                    (decision['nonce'],) * 3).fetchone():
                raise Denied('Encrypted nonce collides with a legacy approval or receipt')
            wire = self.peers[message['sender']].seal(message, decision['nonce'], now).model_dump()
            self.db.execute('''INSERT INTO encrypted_outbox
                (nonce,context,sender,recipient,message_type,message_digest,signed,body,wire,wire_digest,state)
                VALUES (?,?,?,?,?,?,?,?,?,?,'queued')''',
                (decision['nonce'], self.registry.context, message['sender'], message['recipient'], message['type'],
                 digest(message), canonical(signed), canonical(message), canonical(wire), digest(wire)))
            self.db.execute('INSERT INTO owner_decisions VALUES (?,?,?)',
                            (decision['nonce'], fingerprint, canonical({'action': 'send_encrypted', 'state': 'queued'})))
            return self.status(decision['nonce'])

    def packet(self, nonce):
        """Trusted local test harness only. This is NOT a network or publication API."""
        row = self._row(nonce)
        return {'signed': json.loads(row['signed']), 'wire': json.loads(row['wire'])}

    def record_receipt(self, nonce, receipt):
        with self.store.transaction():
            row = self._row(nonce)
            if row['attempts'] == 0: raise Denied('No dispatch attempt exists for this receipt')
            receipt = verify_receipt(self.registry, receipt, row)
            if receipt['receipt']['received_at'] > self.store.clock():
                raise Denied('Receipt time is in the future for this controlled-clock fixture')
            serialized = canonical(receipt)
            if row['receipt'] is not None:
                if row['receipt'] != serialized: raise Denied('Receiver receipt changed for a committed delivery')
                return self.status(nonce)
            # A valid receipt can arrive after cancellation; preserve the truth that
            # information reached the receiver. Cancellation cannot recall it.
            self.store._bound('deliveries')
            self.db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,'received')",
                            (nonce, row['sender'], row['recipient'], row['context'], row['body']))
            self.db.execute("UPDATE encrypted_outbox SET state='received',receipt=?,reason=NULL WHERE nonce=?", (serialized, nonce))
            return self.status(nonce)

    def reconcile(self, nonce, receiver):
        """Query only. Never retransmit to determine whether an earlier attempt landed."""
        row = self._row(nonce)
        if row['state'] in ('received', 'processed', 'received_blocked'): return self.status(nonce)
        if receiver.owner != row['recipient'] or receiver.registry.fingerprint != self.registry.fingerprint:
            raise Denied('Reconciliation receiver does not match the approved transport identity')
        receipt = receiver.receipt(nonce)
        if receipt is not None: return self.record_receipt(nonce, receipt)
        return self.status(nonce)

    def dispatch(self, nonce, receiver):
        # Reconcile before retrying an uncertain previous attempt. If the receiver
        # is unavailable, the exception leaves the prior state uncertain, unsent again.
        row = self._row(nonce)
        if row['state'] in ('received', 'processed', 'received_blocked'): return self.status(nonce)
        if row['attempts']:
            self.reconcile(nonce, receiver)
            if self._row(nonce)['receipt'] is not None: return self.status(nonce)
        if not callable(getattr(receiver, 'receive', None)):
            raise Denied('Read-only receipt recovery cannot retransmit or decrypt new messages')
        with self.store.transaction():
            row = self._row(nonce)
            if row['state'] in ('blocked', 'stopped_uncertain', 'received', 'processed', 'received_blocked'):
                return self.status(nonce)
            if receiver.owner != row['recipient'] or receiver.registry.fingerprint != self.registry.fingerprint:
                raise Denied('Dispatch receiver identity differs from the approved recipient')
            decision, message = self.registry.verify_delivery(json.loads(row['signed']), json.loads(row['body']))
            try:
                now = int(self.store.clock())
                if not decision['issued_at'] <= now < decision['expires_at']:
                    raise Denied('Approval expired before a confirmed receipt')
                self._current_permission(decision)
                self.registry.permits(row['sender'], row['recipient'], now)
                self.session._restore()._validate(message)
            except Denied as exc:
                # A missing receipt cannot prove a prior in-flight attempt did not
                # land. Stop resending, retain the reservation, and keep reconciling.
                state = 'stopped_uncertain' if row['attempts'] else 'blocked'
                self.db.execute("UPDATE encrypted_outbox SET state=?,reason=? WHERE nonce=?", (state, str(exc), nonce))
                return self.status(nonce)
            if row['attempts'] >= 10: raise Denied('Offline dispatch retry limit reached')
            self.db.execute("UPDATE encrypted_outbox SET state='dispatched',attempts=attempts+1,reason=NULL WHERE nonce=?", (nonce,))
            packet = {'signed': json.loads(row['signed']), 'wire': json.loads(row['wire'])}
        # Deliberately outside the sender transaction: a process failure here is
        # an uncertain outcome, reconciled by the stable delivery ID and receipt.
        receipt = receiver.receive(packet)
        return self.record_receipt(nonce, receipt)

    def process_received(self, nonce):
        with self.store.transaction():
            row = self._row(nonce)
            if row['state'] in ('processed', 'received_blocked'): return self.status(nonce)
            if row['state'] != 'received': raise Denied('No verified receiver receipt is available to process')
            verify_receipt(self.registry, json.loads(row['receipt']), row)
            decision, message = self.registry.verify_delivery(json.loads(row['signed']), json.loads(row['body']))
            try:
                self._current_permission(decision)
                self.session._restore()._validate(message)
            except Denied as exc:
                self.db.execute("UPDATE encrypted_outbox SET state='received_blocked',reason=? WHERE nonce=?", (str(exc), nonce))
                return self.status(nonce)
            # Consent was consumed at enqueue; receipt proves it was delivered
            # during its valid window. Later local processing does not resend it.
            self.db.execute('INSERT INTO transitions(session_id,delivery_id,body) VALUES (?,?,?)',
                            (self.session.meeting.id, nonce, canonical(message)))
            self.store.mark_processed(message['recipient'], nonce)
            self.db.execute("UPDATE encrypted_outbox SET state='processed',reason=NULL WHERE nonce=?", (nonce,))
            return self.status(nonce)
