"""Verified owner decisions for a separate execution process.

No private keys or signing function are present. Public-key enrollment is a trusted
bootstrap fixture, not proof of a real person's identity. Legacy owner_* APIs stay
internal and MUST NOT be exposed alongside this gateway. The DB/process is trusted.
"""
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from network import Denied, canonical, digest, snapshot_envelope

from owner_withdrawal import assert_not_withdrawn

DOMAIN = 'agent-network-owner-decision/v1'
_HEX64 = re.compile(r'[a-f0-9]{64}')
_HEX128 = re.compile(r'[a-f0-9]{128}')
_NONCE = re.compile(r'[a-f0-9]{32}')


def decision_bytes(decision):
    return (DOMAIN + '\n' + canonical(decision)).encode('ascii')


def validate_decision(value):
    try:
        encoded = canonical(value)
        if len(encoded.encode()) > 4096:
            raise Denied('Owner decision exceeds size limit')
        decision = json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise Denied('Owner decision must be bounded JSON') from exc
    fields = {'version', 'domain', 'action', 'owner', 'context', 'nonce', 'issued_at', 'expires_at', 'target'}
    if type(decision) is not dict or set(decision) != fields:
        raise Denied('Unknown or missing owner-decision fields')
    if type(decision['version']) is not int or decision['version'] != 1 or decision['domain'] != DOMAIN:
        raise Denied('Wrong owner-decision domain or version')
    if type(decision['owner']) is not str or not re.fullmatch(r'[a-z0-9_-]{1,64}', decision['owner']):
        raise Denied('Invalid owner identity')
    if type(decision['context']) is not str or not _HEX64.fullmatch(decision['context']):
        raise Denied('Invalid owner-decision context')
    if type(decision['nonce']) is not str or not _NONCE.fullmatch(decision['nonce']):
        raise Denied('Invalid decision nonce')
    for field in ('issued_at', 'expires_at'):
        if type(decision[field]) is not int or not 0 <= decision[field] < 2**63:
            raise Denied('Decision times must be nonnegative integer seconds')
    if not 1 <= decision['expires_at'] - decision['issued_at'] <= 600:
        raise Denied('Owner decisions must expire within ten minutes')
    target, action = decision['target'], decision['action']
    if type(target) is not dict or type(action) is not str:
        raise Denied('Invalid owner decision action or target')
    layouts = {'pair': {'peer', 'contact_version', 'ttl'}, 'revoke': {'peer', 'contact_version'},
               'send': {'recipient', 'envelope_digest', 'pair_versions'}, 'cancel': {'meeting'}}
    if action not in layouts or set(target) != layouts[action]:
        raise Denied('Unsupported owner decision or target fields')
    if action in ('pair', 'revoke'):
        if type(target['peer']) is not str or not re.fullmatch(r'[a-z0-9_-]{1,64}', target['peer']):
            raise Denied('Invalid decision peer')
        if type(target['contact_version']) is not int or not 0 <= target['contact_version'] < 2**63:
            raise Denied('Invalid contact version')
        if action == 'pair' and (type(target['ttl']) is not int or not 1 <= target['ttl'] <= 86400):
            raise Denied('Pairing duration must be at most one day')
    if action == 'send':
        if type(target['recipient']) is not str or not re.fullmatch(r'[a-z0-9_-]{1,64}', target['recipient']):
            raise Denied('Invalid decision recipient')
        if type(target['envelope_digest']) is not str or not _HEX64.fullmatch(target['envelope_digest']):
            raise Denied('Invalid message digest')
        versions = target['pair_versions']
        if type(versions) is not list or len(versions) != 2 or any(type(v) is not int or not 1 <= v < 2**63 for v in versions):
            raise Denied('Send decision needs both current contact versions')
    if action == 'cancel' and (type(target['meeting']) is not str or not re.fullmatch(r'[a-z0-9_-]{1,64}', target['meeting'])):
        raise Denied('Invalid cancellation meeting')
    return decision


class SignedOwnerGateway:
    def __init__(self, session, owner_public_keys):
        self.session, self.delivery, self.db = session, session.delivery, session.db
        if type(owner_public_keys) is not dict or set(owner_public_keys) != set(session.meeting.participants):
            raise Denied('Trusted owner key map must exactly match participants')
        if any(type(v) is not str or not _HEX64.fullmatch(v) for v in owner_public_keys.values()):
            raise Denied('Owner verification keys must be canonical Ed25519 public keys')
        if len(set(owner_public_keys.values())) != len(owner_public_keys):
            raise Denied('Fixture owners need distinct verification keys')
        self.public_keys = dict(owner_public_keys)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS owner_authorization_withdrawals (
                source_nonce TEXT PRIMARY KEY, owner TEXT NOT NULL, context TEXT NOT NULL,
                fingerprint TEXT NOT NULL, review_digest TEXT NOT NULL,
                withdrawal_nonce TEXT NOT NULL UNIQUE, token TEXT NOT NULL,
                signature TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS owner_roots (context TEXT PRIMARY KEY, roots TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS owner_decisions (
                nonce TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
        ''')
        with self.delivery.transaction():
            roots = canonical(self.public_keys)
            row = self.db.execute('SELECT roots FROM owner_roots WHERE context=?', (session.context,)).fetchone()
            if row and row[0] != roots:
                raise Denied('Owner verification roots changed; automatic replacement is forbidden')
            if row is None:
                if self.db.execute('SELECT COUNT(*) FROM owner_roots').fetchone()[0] >= self.delivery.max_records:
                    raise Denied('Owner-root record limit reached')
                self.db.execute('INSERT INTO owner_roots VALUES (?,?)', (session.context, roots))

    def contact_versions(self, sender, recipient):
        return [self.delivery.contact_version(sender, recipient, self.session.context),
                self.delivery.contact_version(recipient, sender, self.session.context)]

    def apply(self, signed, envelope=None):
        if type(signed) is not dict or set(signed) != {'decision', 'signature'}:
            raise Denied('A signed owner decision is required')
        decision = validate_decision(signed['decision'])
        signature = signed['signature']
        if type(signature) is not str or not _HEX128.fullmatch(signature):
            raise Denied('Invalid owner signature encoding')
        owner = decision['owner']
        if owner not in self.public_keys or decision['context'] != self.session.context:
            raise Denied('Owner or context is not enrolled for this session')
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.public_keys[owner])).verify(
                bytes.fromhex(signature), decision_bytes(decision))
        except (InvalidSignature, ValueError) as exc:
            raise Denied('Owner signature verification failed') from exc
        target, action = decision['target'], decision['action']
        if action == 'send':
            message = snapshot_envelope(envelope)
            if (message['sender'] != owner or message['recipient'] != target['recipient']
                    or digest(message) != target['envelope_digest'] or message['context'] != self.session.context):
                raise Denied('Signed approval does not authorize this exact message')
        else:
            if envelope is not None:
                raise Denied('Only a send decision may include a message')
            message = None
        fingerprint = digest({'decision': decision, 'envelope': message})
        with self.delivery.transaction():
            assert_not_withdrawn(self.db, decision['nonce'])
            existing = self.db.execute('SELECT fingerprint,result FROM owner_decisions WHERE nonce=?', (decision['nonce'],)).fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise Denied('Decision nonce reused with a different meaning')
                return {'replayed': True, 'result': json.loads(existing['result'])}
            now = self.delivery.clock()
            if not decision['issued_at'] <= now < decision['expires_at']:
                raise Denied('Owner decision is expired or not yet valid')
            if self.db.execute('SELECT COUNT(*) FROM owner_decisions').fetchone()[0] >= self.delivery.max_records:
                raise Denied('Owner-decision record limit reached')
            if action in ('pair', 'revoke'):
                peer = target['peer']
                if peer not in self.session.registry:
                    raise Denied('Peer is not part of this meeting')
                if self.delivery.contact_version(owner, peer, self.session.context) != target['contact_version']:
                    raise Denied('Contact changed since owner reviewed this decision')
                if action == 'pair':
                    self.delivery._owner_pair_in_transaction(owner, peer, self.session.context, target['ttl'])
                else:
                    self.delivery._owner_revoke_in_transaction(owner, peer, self.session.context)
                result = {'action': action, 'owner': owner, 'peer': peer,
                          'contact_version': self.delivery.contact_version(owner, peer, self.session.context)}
            elif action == 'cancel':
                if target['meeting'] != self.session.meeting.id:
                    raise Denied('Cancellation names another meeting')
                result = {'action': action, **self.session._cancel_in_transaction(self.session.registry[owner])}
            else:
                if target['pair_versions'] != self.contact_versions(owner, message['recipient']):
                    raise Denied('Pairing changed since owner reviewed this message')
                self.delivery._paired(owner, message['recipient'], self.session.context)
                self.delivery._bound('approvals')
                if self.db.execute('SELECT 1 FROM approvals WHERE id=?', (decision['nonce'],)).fetchone():
                    raise Denied('Decision nonce collides with another approval')
                self.db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,0)',
                                (decision['nonce'], owner, message['recipient'], self.session.context,
                                 digest(message), decision['expires_at']))
                receipt = self.session._submit_in_transaction(self.session.registry[owner], message, decision['nonce'])
                result = {'action': action, 'receipt': receipt, 'state': 'processed_locally'}
            self.db.execute('INSERT INTO owner_decisions VALUES (?,?,?)', (decision['nonce'], fingerprint, canonical(result)))
            return {'replayed': False, 'result': result}
