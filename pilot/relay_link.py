"""Connect two people's copies of Parlu through a relay, starting from one invite link.

One person makes an invite. The link carries where to reach them (relay and
mailbox), a send token for a few packets, a join secret the relay never sees,
and their public identity. The other person opens the link in their own copy.
Their copy enrols the inviter from the link and sends back one encrypted,
signed ``join`` packet with its own public identity, its own mailbox and a
fresh send token. The inviter sees who joined and decides. Adding them returns
one ``welcome`` packet with a fresh send token, and the invite token is closed.

After that, ``sync`` carries the ordinary signed, encrypted packets both ways:
it fetches from the owner's mailbox into the same authenticated receive step
every other carrier uses, returns the original receipts, and posts each
released packet once.

What this is not: joining never accepts work, a relay answer is never a
delivery or a decision, and nothing is sent again unless the owner asks.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from relay.acrelay.client import RelayClient, send_with_invite
from relay.acrelay.protocol import MailboxKey, RelayError, new_send_token

from .auth import AuthError, _create_private_file, _private_path
from .crypto import MAX_PACKET, TransportDenied, b64, canonical, digest, fingerprint, packet_header, unb64, validate_public
from .storage import RecordStorage
from .transport import MAX_PEERS

VERSION = 'parlu-relay-link/1'
LINK_VERSION = 2
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
GRANT_ID = re.compile(r'[0-9a-f]{32}\Z')
SECRET = re.compile(r'[A-Za-z0-9_-]{22,64}\Z')
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
MAX_LINK = 2048
MAX_LABEL_BYTES = 64
MAX_OPEN_INVITES = 32
MAX_ATTEMPTS = 5
MAX_FETCH_ROUNDS = 20
INVITE_PACKETS = 4
MAX_INVITE_HOURS = 7 * 24
PEER_SECONDS = 364 * 86400  # Below the relay's one-year cap, leaving room for clock skew.
PEER_PACKETS = 50_000
WELCOME_WINDOW = 14 * 86400
JOIN_KEPT = 14 * 86400  # How long the relay keeps a stored packet.
SENT_MEMORY = 2 * 3600
SEALED = {'link_meta': ('key',), 'link_invites': ('secret', 'joiner'), 'link_peers': ('send',)}


class LinkDenied(ValueError):
    """A fixed refusal, without link, token or key detail."""


def need(condition):
    if not condition:
        raise LinkDenied('Invite or relay link unavailable')


def relay_origin(url):
    """The exact relay address: HTTPS, or plain HTTP on this machine only."""
    need(type(url) is str and 0 < len(url) <= 256)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise LinkDenied('Invite or relay link unavailable') from None
    need(parts.scheme in ('https', 'http') and parts.hostname and parts.username is None and parts.password is None)
    need(parts.path in ('', '/') and not parts.query and not parts.fragment)
    need(parts.scheme == 'https' or parts.hostname in ('127.0.0.1', 'localhost'))
    return f'{parts.scheme}://{parts.hostname}' + (f':{port}' if port else '')


def _strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result

    def reject(_):
        raise ValueError('Invalid JSON')
    try:
        return json.loads(raw.decode('utf-8') if type(raw) is bytes else raw, object_pairs_hook=pairs,
                          parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError):
        raise LinkDenied('Invite or relay link unavailable') from None


# Invite links -------------------------------------------------------------------

def link_code(fields):
    """A short code both people can read out to check they hold the same link.

    It is a slow hash of everything in the link, so someone who swaps the link
    for their own cannot cheaply search for one that shows the same code.
    """
    raw = hashlib.scrypt(canonical(fields), salt=b'parlu-invite-code/1', n=2 ** 14, r=8, p=1, dklen=5)
    number = int.from_bytes(raw, 'big')
    letters = ''.join(CODE_ALPHABET[(number >> shift) & 31] for shift in range(35, -1, -5))
    return letters[:4] + '-' + letters[4:]


def make_link(relay_url, mailbox, token, secret, public, label=''):
    """Everything after ``#`` stays on the two people's devices: servers never receive it."""
    public = validate_public(public)
    need(HEX64.fullmatch(mailbox) is not None and SECRET.fullmatch(secret) is not None)
    need(type(token) is str and 32 <= len(token) <= 64 and re.fullmatch(r'[A-Za-z0-9_-]+', token) is not None)
    need(type(label) is str and len(label.encode()) <= MAX_LABEL_BYTES)
    payload = [LINK_VERSION, mailbox, token, secret, label, public['owner_id'], public['agent_id'],
               public['signing_key'], public['exchange_key']]
    return relay_origin(relay_url) + '/invite#' + b64(json.dumps(payload, separators=(',', ':'),
                                                                   ensure_ascii=False).encode())


def read_link(link):
    """Check and unpack an invite link. Raises ``LinkDenied`` for anything unexpected."""
    need(type(link) is str and 0 < len(link) <= MAX_LINK)
    try:
        parts = urlsplit(link.strip())
        need(parts.path == '/invite' and not parts.query and parts.fragment)
        relay_url = relay_origin(f'{parts.scheme}://{parts.netloc}')
        value = _strict(unb64(parts.fragment, maximum=1024))
        need(type(value) is list and len(value) == 9 and value[0] == LINK_VERSION
             and all(type(item) is str for item in value[1:]))
        _, mailbox, token, secret, label, owner_id, agent_id, signing_key, exchange_key = value
        need(HEX64.fullmatch(mailbox) is not None and SECRET.fullmatch(secret) is not None)
        need(32 <= len(token) <= 64 and re.fullmatch(r'[A-Za-z0-9_-]+', token) is not None)
        need(len(label.encode()) <= MAX_LABEL_BYTES and label.isprintable())
        public = validate_public({'owner_id': owner_id, 'agent_id': agent_id, 'signing_key': signing_key,
                                  'exchange_key': exchange_key})
    except (TransportDenied, ValueError, UnicodeError):
        raise LinkDenied('Invite or relay link unavailable') from None
    return {'relay_url': relay_url, 'mailbox': mailbox, 'send_token': token, 'join_secret': secret, 'label': label,
            'public': public, 'fingerprint': fingerprint(public), 'code': link_code(value)}


# Join and welcome packets -----------------------------------------------------------

def _envelope_key(shared, header):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(canonical(header)).digest(),
                info=VERSION.encode()).derive(shared)


def seal_envelope(auth, session, recipient_public, kind, body, now, *, name_sender):
    """One encrypted, signed link packet. A ``join`` hides who sent it from the relay."""
    sender, recipient = validate_public(auth.public_identity()), validate_public(recipient_public)
    ephemeral = X25519PrivateKey.generate()
    header = {'parlu_link': 1, 'kind': kind, 'recipient': fingerprint(recipient), 'created': int(now),
              'ephemeral': b64(ephemeral.public_key().public_bytes_raw()), 'nonce': b64(os.urandom(12))}
    if name_sender:
        header['sender'] = fingerprint(sender)
    try:
        shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(unb64(recipient['exchange_key'], 32)))
    except ValueError:
        raise LinkDenied('Invite or relay link unavailable') from None
    ciphertext = AESGCM(_envelope_key(shared, header)).encrypt(unb64(header['nonce'], 12), canonical(body),
                                                               canonical(header))
    signed = {'header': header, 'ciphertext': b64(ciphertext)}
    return {**signed, 'signature': b64(auth.sign(session, canonical(signed)))}


def is_envelope(packet):
    return (type(packet) is dict and type(packet.get('header')) is dict
            and packet['header'].get('parlu_link') == 1)


def _envelope_header(envelope, kind):
    need(type(envelope) is dict and set(envelope) == {'header', 'ciphertext', 'signature'})
    header = envelope['header']
    fields = {'parlu_link', 'kind', 'recipient', 'created', 'ephemeral', 'nonce'}
    need(type(header) is dict and header.get('kind') == kind
         and set(header) == (fields | {'sender'} if kind == 'welcome' else fields))
    need(type(header['created']) is int and type(header['recipient']) is str)
    return header


def open_envelope(auth, session, envelope, kind):
    header = _envelope_header(envelope, kind)
    need(header['recipient'] == fingerprint(auth.public_identity()))
    try:
        shared = auth.exchange(session, unb64(header['ephemeral'], 32))
        plaintext = AESGCM(_envelope_key(shared, header)).decrypt(
            unb64(header['nonce'], 12), unb64(envelope['ciphertext'], maximum=4096), canonical(header))
        body = _strict(plaintext)
    except (TransportDenied, InvalidTag, ValueError, TypeError):
        raise LinkDenied('Invite or relay link unavailable') from None
    need(type(body) is dict)
    return header, body


def verify_envelope(envelope, sender_public):
    try:
        Ed25519PublicKey.from_public_bytes(unb64(sender_public['signing_key'], 32)).verify(
            unb64(envelope['signature'], 64),
            canonical({'header': envelope['header'], 'ciphertext': envelope['ciphertext']}))
    except (InvalidSignature, TransportDenied, ValueError, TypeError, KeyError):
        raise LinkDenied('Invite or relay link unavailable') from None


def join_proof(secret, inviter, joiner, mailbox, token):
    """Only someone who held the link can make this: the relay never sees the join secret."""
    return hmac.new(secret.encode(), canonical(['parlu-link-join/1', inviter, joiner, mailbox, token]),
                    hashlib.sha256).hexdigest()


class _LinkStorage(RecordStorage):
    def _context(self, table, row_id, column):
        need(table in SEALED and column in SEALED[table] and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class RelayLink:
    """One owner's mailbox, invites and peer links on one relay. Use on the owner thread only."""

    def __init__(self, directory, auth, runtime, relay_url, *, clock=time.time, timeout=6, transport=None):
        self.auth, self.runtime, self.clock, self.timeout = auth, runtime, clock, timeout
        self.relay_url = relay_origin(relay_url)
        self.relay_host = urlsplit(self.relay_url).netloc
        self._transport = {} if transport is None else {'transport': transport}
        self.identity = auth.public_identity()
        self.fingerprint = fingerprint(self.identity)
        self.last_sync = None
        self.directory = Path(directory).absolute()
        _private_path(self.directory, directory=True)
        path = self.directory / 'relay-link.sqlite'
        _create_private_file(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.storage = _LinkStorage(self.db, auth, create=True)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS link_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL,relay_url TEXT NOT NULL,mailbox TEXT,registered INTEGER NOT NULL DEFAULT 0,key TEXT);
                CREATE TABLE IF NOT EXISTS link_invites(id TEXT PRIMARY KEY,label TEXT NOT NULL,code TEXT NOT NULL,created REAL NOT NULL,join_by REAL NOT NULL,state TEXT NOT NULL CHECK(state IN ('open','joined','added','declined','revoked')),secret TEXT NOT NULL,joiner TEXT);
                CREATE TABLE IF NOT EXISTS link_peers(peer TEXT PRIMARY KEY,mailbox TEXT NOT NULL,grant_id TEXT NOT NULL,expires REAL NOT NULL,state TEXT NOT NULL CHECK(state IN ('joining','waiting','connected','closed')),send TEXT NOT NULL,control TEXT,join_digest TEXT,attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS link_sent(message_id TEXT PRIMARY KEY,peer TEXT NOT NULL,stored REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS link_receipts(digest TEXT PRIMARY KEY,peer TEXT NOT NULL,packet TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
            ''')
            with self._txn():
                row = self._meta()
                if row is None:
                    self.db.execute('INSERT INTO link_meta VALUES(1,?,?,?,NULL,0,NULL)',
                                    (VERSION, self.fingerprint, self.relay_url))
                else:
                    # A mailbox lives on one relay. Moving relays needs a new, deliberate setup.
                    need(row['version'] == VERSION and row['owner'] == self.fingerprint
                         and row['relay_url'] == self.relay_url)
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    # Internals ------------------------------------------------------------------

    def _txn(self):
        return _Txn(self.db)

    def _meta(self):
        return self.db.execute('SELECT * FROM link_meta WHERE singleton=1').fetchone()

    def _now(self):
        return self.clock()

    def _owner(self, session):
        need(self.auth.authenticate(session)['identity_fingerprint'] == self.fingerprint)

    def _seal(self, table, row_id, column, value):
        return self.storage.seal(table, row_id, column, canonical(value).decode())

    def _open(self, table, row_id, column, value):
        return json.loads(self.storage.open(table, row_id, column, value))

    def _relay(self, call):
        """Run one relay call. Returns ``(value, None)`` or ``(None, problem)``.

        ``problem`` is ``closed`` when the relay says the send token is no longer
        good, ``refused`` for any other definite no, and ``unreachable`` when the
        outcome is unknown.
        """
        try:
            return call(), None
        except RelayError as error:
            if error.code == 'no_grant':
                return None, 'closed'
            return None, 'refused' if error.status in (400, 401, 404, 409, 413, 507) else 'unreachable'
        except AuthError:
            raise
        except Exception:
            return None, 'unreachable'

    def _mailbox(self, session):
        """The owner's relay client, making and registering the mailbox on first use."""
        row = self._meta()
        if row['key'] is None:
            seed = secrets.token_bytes(32)
            with self._txn():
                self.db.execute('UPDATE link_meta SET key=?,mailbox=? WHERE singleton=1',
                                (self._seal('link_meta', 'mailbox', 'key', seed.hex()),
                                 MailboxKey.from_seed(seed).mailbox))
            row = self._meta()
        key = MailboxKey.from_seed(bytes.fromhex(self._open('link_meta', 'mailbox', 'key', row['key'])))
        need(key.mailbox == row['mailbox'])
        client = RelayClient(self.relay_url, key, timeout=self.timeout, clock=self.clock, **self._transport)
        if not row['registered']:
            _, problem = self._relay(client.register)
            if problem:
                return None, problem
            with self._txn():
                self.db.execute('UPDATE link_meta SET registered=1 WHERE singleton=1')
        return client, None

    def _post(self, mailbox, token, raw):
        target = {'relay_url': self.relay_url, 'mailbox': mailbox, 'send_token': token}
        return self._relay(lambda: send_with_invite(target, raw, timeout=self.timeout, **self._transport))

    def _peer_state(self, peer):
        for entry in self.runtime.exchange.peers():
            if entry['fingerprint'] == peer:
                return entry['state']
        return None

    # Inviting ------------------------------------------------------------------

    def _invite_state(self, row, now):
        return 'expired' if row['state'] == 'open' and now >= row['join_by'] else row['state']

    def _invite_view(self, row, now, *, with_link=False):
        view = {'id': row['id'], 'label': row['label'], 'code': row['code'], 'created': row['created'],
                'join_by': row['join_by'], 'state': self._invite_state(row, now)}
        if with_link:
            secret = self._open('link_invites', row['id'], 'secret', row['secret'])
            view['link'] = make_link(self.relay_url, self._meta()['mailbox'], secret['token'], secret['secret'],
                                     self.identity)
        return view

    def create_invite(self, session, label='', *, hours=24):
        self._owner(session)
        need(type(label) is str and type(hours) is int and 1 <= hours <= MAX_INVITE_HOURS)
        label = label.strip()
        need(len(label.encode()) <= MAX_LABEL_BYTES and (not label or label.isprintable()))
        now = self._now()
        need(self.db.execute("SELECT COUNT(*) FROM link_invites WHERE state IN ('open','joined') AND join_by>?",
                             (now,)).fetchone()[0] < MAX_OPEN_INVITES)
        client, problem = self._mailbox(session)
        if problem:
            return {'made': False, 'relay': problem}
        token, secret = new_send_token(), secrets.token_urlsafe(16)
        grant, problem = self._relay(lambda: client.grant(token, seconds=hours * 3600, packets=INVITE_PACKETS))
        if problem:
            return {'made': False, 'relay': problem}
        invite_id = grant['grant_id']
        need(type(invite_id) is str and GRANT_ID.fullmatch(invite_id) is not None)
        # The label is a private note for the person who made the invite: it never goes in the link.
        code = read_link(make_link(self.relay_url, client.mailbox, token, secret, self.identity))['code']
        with self._txn():
            self.db.execute("INSERT INTO link_invites VALUES(?,?,?,?,?,'open',?,NULL)",
                            (invite_id, label, code, now, now + hours * 3600,
                             self._seal('link_invites', invite_id, 'secret', {'token': token, 'secret': secret})))
        row = self.db.execute('SELECT * FROM link_invites WHERE id=?', (invite_id,)).fetchone()
        return {'made': True, **self._invite_view(row, now, with_link=True)}

    def _invite(self, invite_id):
        need(type(invite_id) is str and GRANT_ID.fullmatch(invite_id) is not None)
        row = self.db.execute('SELECT * FROM link_invites WHERE id=?', (invite_id,)).fetchone()
        need(row is not None)
        return row

    def show_invite(self, session, invite_id):
        """The link again, for the person who made it, while it can still be used."""
        self._owner(session)
        row, now = self._invite(invite_id), self._now()
        need(self._invite_state(row, now) == 'open')
        return self._invite_view(row, now, with_link=True)

    def revoke_invite(self, session, invite_id):
        self._owner(session)
        row = self._invite(invite_id)
        need(row['state'] in ('open', 'joined'))
        with self._txn():
            self.db.execute("UPDATE link_invites SET state='revoked',joiner=NULL WHERE id=?", (invite_id,))
        client, problem = self._mailbox(session)
        if client is not None:
            _, problem = self._relay(lambda: client.revoke(invite_id))
        # Revoked here whatever the relay says: a join under this invite is ignored from now on.
        return {'revoked': True, 'relay': problem or 'ok'}

    # Joining ---------------------------------------------------------------------

    def _review(self, target):
        inviter = {'owner_id': target['public']['owner_id'], 'agent_id': target['public']['agent_id'],
                   'fingerprint': target['fingerprint']}
        base = {'inviter': inviter, 'label': target['label'], 'relay_host': urlsplit(target['relay_url']).netloc}
        if target['fingerprint'] == self.fingerprint:
            return {**base, 'ok': False, 'reason': 'own_invite'}
        if target['relay_url'] != self.relay_url:
            return {**base, 'ok': False, 'reason': 'other_relay'}
        known = self._peer_state(target['fingerprint'])
        if known == 'revoked':
            return {**base, 'ok': False, 'reason': 'revoked_before'}
        linked = self.db.execute('SELECT state FROM link_peers WHERE peer=?', (target['fingerprint'],)).fetchone()
        if linked is not None and linked['state'] != 'closed':
            # Trying another invite must never disturb a link that works or is waiting.
            return {**base, 'ok': False, 'reason': 'already_linked'}
        return {**base, 'ok': True, 'code': target['code'], 'known': known == 'active',
                'review_digest': digest(['parlu-link-accept/1', self.fingerprint, target['fingerprint'],
                                         target['mailbox'], target['code']])}

    def open_invite(self, session, link):
        """Who the link is from, before anything is added or sent."""
        self._owner(session)
        return self._review(read_link(link))

    def accept_invite(self, session, link, review_digest):
        self._owner(session)
        target = read_link(link)
        review = self._review(target)
        need(review['ok'] and type(review_digest) is str and review_digest == review['review_digest'])
        peer = target['fingerprint']
        if not self._can_enrol(target['public']):
            return {'joined': False, 'reason': 'cannot_add'}
        client, problem = self._mailbox(session)
        if problem:
            return {'joined': False, 'reason': 'relay_' + problem}
        mine = new_send_token()
        grant, problem = self._relay(lambda: client.grant(mine, seconds=PEER_SECONDS, packets=PEER_PACKETS))
        if problem:
            return {'joined': False, 'reason': 'relay_' + problem}
        now = self._now()
        join = seal_envelope(self.auth, session, target['public'], 'join',
                             {'public': self.identity, 'relay_url': self.relay_url, 'mailbox': client.mailbox,
                              'token': mine, 'proof': join_proof(target['join_secret'], peer, self.fingerprint,
                                                                 client.mailbox, mine)},
                             now, name_sender=False)
        old = self.db.execute('SELECT grant_id FROM link_peers WHERE peer=?', (peer,)).fetchone()
        with self._txn():
            self.db.execute("INSERT OR REPLACE INTO link_peers VALUES(?,?,?,?,'joining',?,?,?,0)",
                            (peer, target['mailbox'], grant['grant_id'], grant['expires'],
                             self._seal('link_peers', peer, 'send', {'token': target['send_token']}),
                             canonical(join).decode(), digest(join)))
        if old is not None:
            self._relay(lambda: client.revoke(old['grant_id']))
        self._flush_control(peer)
        state = self.db.execute('SELECT state FROM link_peers WHERE peer=?', (peer,)).fetchone()['state']
        if state == 'closed':
            # Refused for certain, so nothing is added: an enrolment can be revoked but never undone.
            with self._txn():
                self.db.execute('DELETE FROM link_peers WHERE peer=?', (peer,))
            self._relay(lambda: client.revoke(grant['grant_id']))
            return {'joined': False, 'reason': 'invite_closed', 'peer_id': peer}
        # Stored, or perhaps stored: the inviter may add us, so their welcome must be checkable.
        try:
            self.runtime.enrol_peer(session, target['public'], peer)
        except TransportDenied:
            return {'joined': False, 'reason': 'cannot_add', 'peer_id': peer}
        return {'joined': True, 'state': state, 'peer_id': peer}

    def _can_enrol(self, public):
        """Whether enrolling would work: new, or the same pinned key already active."""
        pin = fingerprint(public)
        for entry in self.runtime.exchange.peers():
            same = (entry['public']['owner_id'], entry['public']['agent_id']) == (public['owner_id'], public['agent_id'])
            if entry['fingerprint'] == pin or same:
                return entry['fingerprint'] == pin and entry['state'] == 'active'
        return pin != self.fingerprint and len(self.runtime.exchange.peers()) < MAX_PEERS

    def _flush_control(self, peer):
        """Post a waiting join or welcome packet once. The try is recorded before bytes leave."""
        row = self.db.execute('SELECT * FROM link_peers WHERE peer=?', (peer,)).fetchone()
        if row is None or row['control'] is None or row['attempts'] >= MAX_ATTEMPTS:
            return None
        token = self._open('link_peers', peer, 'send', row['send'])['token']
        with self._txn():
            self.db.execute('UPDATE link_peers SET attempts=attempts+1 WHERE peer=?', (peer,))
        stored, problem = self._post(row['mailbox'], token, row['control'].encode())
        with self._txn():
            if stored is not None:
                self.db.execute('UPDATE link_peers SET control=NULL,attempts=0,state=? WHERE peer=?',
                                ('waiting' if row['state'] == 'joining' else row['state'], peer))
            elif problem in ('closed', 'refused'):
                self.db.execute("UPDATE link_peers SET control=NULL,state='closed' WHERE peer=?", (peer,))
        return problem

    # The inviting side decides ------------------------------------------------------

    def _joiner_view(self, row):
        joiner = self._open('link_invites', row['id'], 'joiner', row['joiner'])
        peer = fingerprint(joiner['public'])
        return joiner, {'invite_id': row['id'], 'label': row['label'], 'code': row['code'],
                        'owner_id': joiner['public']['owner_id'], 'agent_id': joiner['public']['agent_id'],
                        'fingerprint': peer, 'known': self._peer_state(peer) == 'active',
                        'review_digest': digest(['parlu-link-add/1', self.fingerprint, row['id'], peer])}

    def decide_joiner(self, session, invite_id, review_digest, decision):
        self._owner(session)
        need(decision in ('add', 'decline'))
        row = self._invite(invite_id)
        need(row['state'] == 'joined')
        joiner, view = self._joiner_view(row)
        need(type(review_digest) is str and review_digest == view['review_digest'])
        peer = view['fingerprint']
        client, problem = self._mailbox(session)
        if decision == 'decline':
            with self._txn():
                self.db.execute("UPDATE link_invites SET state='declined',joiner=NULL WHERE id=?", (invite_id,))
            if client is not None:
                self._relay(lambda: client.revoke(invite_id))
            return {'decided': True, 'added': False}
        if problem:
            return {'decided': False, 'reason': 'relay_' + problem}
        if not self._can_enrol(joiner['public']):
            return {'decided': False, 'reason': 'cannot_add'}
        token = new_send_token()
        grant, problem = self._relay(lambda: client.grant(token, seconds=PEER_SECONDS, packets=PEER_PACKETS))
        if problem:
            return {'decided': False, 'reason': 'relay_' + problem}
        try:
            self.runtime.enrol_peer(session, joiner['public'], peer)
        except TransportDenied:
            self._relay(lambda: client.revoke(grant['grant_id']))
            return {'decided': False, 'reason': 'cannot_add'}
        welcome = seal_envelope(self.auth, session, joiner['public'], 'welcome',
                                {'token': token, 'join_digest': joiner['join_digest']}, self._now(),
                                name_sender=True)
        old = self.db.execute('SELECT grant_id FROM link_peers WHERE peer=?', (peer,)).fetchone()
        with self._txn():
            self.db.execute("INSERT OR REPLACE INTO link_peers VALUES(?,?,?,?,'connected',?,?,NULL,0)",
                            (peer, joiner['mailbox'], grant['grant_id'], grant['expires'],
                             self._seal('link_peers', peer, 'send', {'token': joiner['token']}),
                             canonical(welcome).decode()))
            self.db.execute("UPDATE link_invites SET state='added',joiner=NULL WHERE id=?", (invite_id,))
        # The invite token has done its job. From here each side uses its own fresh token.
        self._relay(lambda: client.revoke(invite_id))
        if old is not None:
            self._relay(lambda: client.revoke(old['grant_id']))
        self._flush_control(peer)
        return {'decided': True, 'added': True, 'peer_id': peer}

    def forget_peer(self, session, peer):
        """Close the relay link to one person: their send token stops working."""
        self._owner(session)
        need(type(peer) is str and HEX64.fullmatch(peer) is not None)
        row = self.db.execute('SELECT grant_id FROM link_peers WHERE peer=?', (peer,)).fetchone()
        if row is None:
            return {'closed': False, 'relay': 'ok'}
        with self._txn():
            self.db.execute('DELETE FROM link_peers WHERE peer=?', (peer,))
            self.db.execute('DELETE FROM link_receipts WHERE peer=?', (peer,))
        client, problem = self._mailbox(session)
        if client is not None:
            _, problem = self._relay(lambda: client.revoke(row['grant_id']))
        return {'closed': True, 'relay': problem or 'ok'}

    # Carrying packets --------------------------------------------------------------

    def _take_join(self, session, envelope, grant_id, now):
        need(type(grant_id) is str and GRANT_ID.fullmatch(grant_id) is not None)
        row = self.db.execute('SELECT * FROM link_invites WHERE id=?', (grant_id,)).fetchone()
        # One invite, one person: the first valid join wins and later ones are ignored.
        # The relay stops taking packets under the invite grant at its expiry, so a join found
        # here was stored in time, even if the inviter only signs in to fetch it days later.
        need(row is not None and row['state'] == 'open' and now < row['join_by'] + JOIN_KEPT)
        header, body = open_envelope(self.auth, session, envelope, 'join')
        need(row['created'] - 300 <= header['created'] <= min(now, row['join_by']) + 300)
        need(set(body) == {'public', 'relay_url', 'mailbox', 'token', 'proof'})
        try:
            public = validate_public(body['public'])
        except TransportDenied:
            raise LinkDenied('Invite or relay link unavailable') from None
        peer = fingerprint(public)
        verify_envelope(envelope, public)
        need(peer != self.fingerprint and body['relay_url'] == self.relay_url)
        need(type(body['mailbox']) is str and HEX64.fullmatch(body['mailbox']) is not None)
        need(type(body['token']) is str and 32 <= len(body['token']) <= 64
             and re.fullmatch(r'[A-Za-z0-9_-]+', body['token']) is not None)
        secret = self._open('link_invites', row['id'], 'secret', row['secret'])['secret']
        need(type(body['proof']) is str and hmac.compare_digest(
            body['proof'], join_proof(secret, self.fingerprint, peer, body['mailbox'], body['token'])))
        with self._txn():
            self.db.execute("UPDATE link_invites SET state='joined',joiner=? WHERE id=?",
                            (self._seal('link_invites', row['id'], 'joiner',
                                        {'public': public, 'mailbox': body['mailbox'], 'token': body['token'],
                                         'join_digest': digest(envelope)}), row['id']))

    def _take_welcome(self, session, envelope, grant_id, now):
        header = _envelope_header(envelope, 'welcome')
        sender = header['sender']
        need(type(sender) is str and HEX64.fullmatch(sender) is not None)
        row = self.db.execute('SELECT * FROM link_peers WHERE peer=?', (sender,)).fetchone()
        # It must come from the person whose link was opened, under the token made for them.
        need(row is not None and row['state'] in ('joining', 'waiting') and row['grant_id'] == grant_id)
        need(abs(now - header['created']) <= WELCOME_WINDOW)
        try:
            public = self.runtime.exchange.peer_public(sender)
        except TransportDenied:
            raise LinkDenied('Invite or relay link unavailable') from None
        verify_envelope(envelope, public)
        _, body = open_envelope(self.auth, session, envelope, 'welcome')
        need(set(body) == {'token', 'join_digest'} and body['join_digest'] == row['join_digest'])
        need(type(body['token']) is str and 32 <= len(body['token']) <= 64
             and re.fullmatch(r'[A-Za-z0-9_-]+', body['token']) is not None)
        with self._txn():
            self.db.execute("UPDATE link_peers SET state='connected',send=?,control=NULL,attempts=0 WHERE peer=?",
                            (self._seal('link_peers', sender, 'send', {'token': body['token']}), sender))

    def _incoming(self, session, item, summary, now):
        try:
            raw, grant_id = item['body'], item['grant_id']
            need(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET)
            packet = _strict(raw)
            if is_envelope(packet):
                kind = packet['header'].get('kind')
                need(kind in ('join', 'welcome'))
                if kind == 'join':
                    self._take_join(session, packet, grant_id, now)
                    summary['joined'] += 1
                else:
                    self._take_welcome(session, packet, grant_id, now)
                    summary['connected'] += 1
                return
            sender = packet_header(packet)['sender']
            result = self.runtime.receive(session, packet)
        except (ValueError, PermissionError, KeyError, TypeError):
            # A lapsed session stops the sync with the packet still on the relay. Anything
            # else is a packet that can never become valid, so it is counted and dropped.
            self.auth.authenticate(session)
            summary['rejected'] += 1
            return
        receipt = result.get('receipt')
        if receipt is not None:
            with self._txn():
                self.db.execute('INSERT OR IGNORE INTO link_receipts VALUES(?,?,?,0)',
                                (digest(receipt), sender, canonical(receipt).decode()))
        if not result['duplicate']:
            summary['received'] += 1

    def _connected(self):
        return {row['peer']: row for row in self.db.execute("SELECT * FROM link_peers WHERE state='connected'")}

    def _unsent(self):
        """Released packets for linked people that this relay has not stored yet."""
        connected = self._connected()
        waiting = []
        for status in self.runtime.exchange.pending():
            if status['peer'] in connected and not self.db.execute(
                    'SELECT 1 FROM link_sent WHERE message_id=?', (status['message_id'],)).fetchone():
                waiting.append((status, connected[status['peer']]))
        return waiting

    def sync(self, session, *, send):
        """Fetch what is waiting and return receipts. With ``send``, post each released packet once.

        A relay answer only ever means "stored" or "not stored". Fetched packets go
        through the same authenticated receive step as every other carrier, and are
        deleted from the relay only after that step has kept or refused them.
        """
        self._owner(session)
        need(type(send) is bool)
        now = self._now()
        summary = {'relay': 'ok', 'received': 0, 'rejected': 0, 'joined': 0, 'connected': 0, 'sent': 0,
                   'receipts_sent': 0, 'waiting_to_send': 0, 'at': now}
        if self._meta()['key'] is None:
            self.last_sync = {**summary, 'relay': 'idle'}
            return dict(self.last_sync)
        client, problem = self._mailbox(session)
        if problem:
            summary['relay'] = problem
        after = 0
        for _ in range(MAX_FETCH_ROUNDS if client is not None else 0):
            page, problem = self._relay(lambda: client.fetch(after=after, limit=50))
            if problem or type(page.get('packets')) is not list:
                summary['relay'] = problem or 'unreachable'
                break
            through = None
            for item in page['packets']:
                if type(item) is not dict or type(item.get('seq')) is not int:
                    summary['relay'] = 'unreachable'
                    break
                self._incoming(session, item, summary, now)
                through = item['seq']
            if through is not None:
                _, problem = self._relay(lambda: client.acknowledge(through))
                if problem:
                    summary['relay'] = problem
                    break
                after = through
            if summary['relay'] != 'ok' or not page.get('more'):
                break
        if summary['relay'] == 'ok':
            for row in self.db.execute('SELECT peer FROM link_peers WHERE control IS NOT NULL').fetchall():
                if self._flush_control(row['peer']) == 'unreachable':
                    summary['relay'] = 'unreachable'
                    break
        if summary['relay'] == 'ok':
            self._send_receipts(summary)
        with self._txn():
            self.db.execute('DELETE FROM link_sent WHERE stored<?', (now - SENT_MEMORY,))
        for status, row in self._unsent():
            if not send or summary['relay'] != 'ok':
                summary['waiting_to_send'] += 1
                continue
            packet = self.runtime.prepare_delivery(session, status['message_id'])
            token = self._open('link_peers', row['peer'], 'send', row['send'])['token']
            stored, problem = self._post(row['mailbox'], token, canonical(packet))
            if stored is not None:
                with self._txn():
                    self.db.execute('INSERT OR REPLACE INTO link_sent VALUES(?,?,?)',
                                    (status['message_id'], row['peer'], now))
                summary['sent'] += 1
            elif problem == 'closed':
                with self._txn():
                    self.db.execute("UPDATE link_peers SET state='closed' WHERE peer=?", (row['peer'],))
            else:
                summary['waiting_to_send'] += 1
                if problem == 'unreachable':
                    summary['relay'] = problem
        self.last_sync = summary
        return dict(summary)

    def _send_receipts(self, summary):
        connected = self._connected()
        for row in self.db.execute('SELECT * FROM link_receipts ORDER BY digest').fetchall():
            link = connected.get(row['peer'])
            if link is None or row['attempts'] >= MAX_ATTEMPTS:
                continue
            with self._txn():
                self.db.execute('UPDATE link_receipts SET attempts=attempts+1 WHERE digest=?', (row['digest'],))
            token = self._open('link_peers', row['peer'], 'send', link['send'])['token']
            stored, problem = self._post(link['mailbox'], token, row['packet'].encode())
            if stored is not None:
                with self._txn():
                    self.db.execute('DELETE FROM link_receipts WHERE digest=?', (row['digest'],))
                summary['receipts_sent'] += 1
            elif problem == 'closed':
                with self._txn():
                    self.db.execute("UPDATE link_peers SET state='closed' WHERE peer=?", (row['peer'],))
                connected.pop(row['peer'], None)
            elif problem == 'unreachable':
                summary['relay'] = problem
                return

    # What the owner sees ---------------------------------------------------------------

    def snapshot(self, session):
        self._owner(session)
        now = self._now()
        invites, joiners = [], []
        for row in self.db.execute("SELECT * FROM link_invites WHERE state IN ('open','joined') "
                                   'ORDER BY created DESC,id').fetchall():
            if self._invite_state(row, now) == 'expired':
                continue
            invites.append(self._invite_view(row, now))
            if row['state'] == 'joined':
                joiners.append(self._joiner_view(row)[1])
        links = [{'peer_id': row['peer'], 'state': row['state'], 'expires': row['expires']}
                 for row in self.db.execute('SELECT peer,state,expires FROM link_peers ORDER BY peer')]
        return {'enabled': True, 'relay_host': self.relay_host, 'mailbox_ready': bool(self._meta()['registered']),
                'invites': invites, 'joiners': joiners, 'links': links,
                'waiting_to_send': len(self._unsent()), 'last_sync': self.last_sync}


class _Txn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute('BEGIN IMMEDIATE')

    def __exit__(self, kind, error, trace):
        if self.db.in_transaction:
            self.db.execute('ROLLBACK' if kind else 'COMMIT')
        return False
