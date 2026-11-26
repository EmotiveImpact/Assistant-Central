# SPDX-License-Identifier: AGPL-3.0-only
"""The relay itself: a framework-free request handler over a ``SqlStore``.

``Relay.handle(method, target, headers, body)`` returns ``(status, headers, body)``
so the same code runs under a local HTTP server, a test, or a serverless function.
"""
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from .protocol import (HEX64, VERSION, RelayError, b64d, b64e, mailbox_id, token_hash, verify_signed)

SOURCE_URL = 'https://github.com/EmotiveImpact/Assistant-Central/tree/main/relay'
MAX_BODY = 65536
MAX_QUEUED = 1000
MAX_QUEUED_BYTES = 32 * 1024 * 1024
MAX_GRANTS = 256
MAX_MAILBOXES = 1_000_000
RETENTION = 14 * 86400
MAX_GRANT_SECONDS = 365 * 86400
MAX_GRANT_PACKETS = 100_000
MAX_FETCH = 100
GRANT_ID = re.compile(r'[0-9a-f]{32}\Z')


def _json(status, value):
    return status, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}, json.dumps(value).encode()


class Relay:
    def __init__(self, store, *, clock=time.time, source_url=SOURCE_URL):
        self.store, self.clock, self.source_url = store, clock, source_url

    def _now(self):
        return int(self.clock())

    # Entry point -------------------------------------------------------------

    def handle(self, method, target, headers, body):
        headers = {k.lower(): v for k, v in headers.items()}
        try:
            if body is None:
                body = b''
            if len(body) > MAX_BODY:
                raise RelayError(413, 'too_large')
            parts = urlsplit(target)
            path, query = parts.path, parse_qs(parts.query, max_num_fields=4)
            segments = [s for s in path.split('/') if s]
            if method == 'GET' and path == '/v1/health':
                return _json(200, {'ok': True, 'version': VERSION})
            if method == 'GET' and path in ('/source', '/v1/source'):
                return _json(200, {'licence': 'AGPL-3.0-only', 'source': self.source_url})
            if method == 'GET' and path == '/invite':
                return self._invite_page()
            if segments[:2] != ['v1', 'mailboxes']:
                raise RelayError(404, 'not_found')
            if method == 'POST' and len(segments) == 2:
                return self._register(target, headers, body)
            if len(segments) < 4 or not HEX64.fullmatch(segments[2]):
                raise RelayError(404, 'not_found')
            mailbox, resource = segments[2], segments[3]
            if resource == 'packets' and len(segments) == 4:
                if method == 'POST':
                    return self._deliver(mailbox, headers, body)
                if method == 'GET':
                    return self._fetch(mailbox, target, headers, body, query)
                if method == 'DELETE':
                    return self._ack(mailbox, target, headers, body, query)
            if resource == 'grants':
                if method == 'POST' and len(segments) == 4:
                    return self._grant(mailbox, target, headers, body)
                if method == 'DELETE' and len(segments) == 5 and GRANT_ID.fullmatch(segments[4]):
                    return self._revoke(mailbox, target, headers, body, segments[4])
            raise RelayError(404, 'not_found')
        except RelayError as error:
            return _json(error.status, {'error': error.code})
        except Exception:
            return _json(500, {'error': 'unavailable'})

    # Authentication ------------------------------------------------------------

    def _signed(self, tx, mailbox, method, target, headers, body):
        if headers.get('ac-mailbox') != mailbox:
            raise RelayError(401, 'bad_signature')
        row = tx.one('SELECT public_key FROM relay_mailboxes WHERE id=?', (mailbox,))
        if row is None:
            raise RelayError(401, 'bad_signature')  # Same answer as a bad signature.
        now = self._now()
        nonce, _ = verify_signed(b64d(row[0]), method, target, headers, body, now)
        tx.execute('DELETE FROM relay_nonces WHERE expires<?', (now,))
        if tx.one('SELECT 1 FROM relay_nonces WHERE mailbox=? AND nonce=?', (mailbox, nonce)):
            raise RelayError(401, 'replayed')
        tx.execute('INSERT INTO relay_nonces VALUES(?,?,?)', (mailbox, nonce, now + 2 * 300 + 1))
        return now

    # Owner operations -----------------------------------------------------------

    def _register(self, target, headers, body):
        try:
            value = json.loads(body)
            public = b64d(value['public_key'])
            if set(value) != {'public_key'} or len(public) != 32:
                raise ValueError()
        except (ValueError, TypeError, KeyError, RelayError):
            raise RelayError(400, 'bad_request') from None
        mailbox = mailbox_id(public)
        if headers.get('ac-mailbox') != mailbox:
            raise RelayError(401, 'bad_signature')
        now = self._now()
        nonce, _ = verify_signed(public, 'POST', target, headers, body, now)
        with self.store.transaction() as tx:
            existing = tx.one('SELECT public_key FROM relay_mailboxes WHERE id=?', (mailbox,))
            if existing is None:
                if tx.one('SELECT COUNT(*) FROM relay_mailboxes')[0] >= MAX_MAILBOXES:
                    raise RelayError(503, 'full')
                tx.execute('INSERT INTO relay_mailboxes VALUES(?,?,?)', (mailbox, b64e(public), now))
                tx.execute('INSERT INTO relay_counters VALUES(?,1)', (mailbox,))
            if tx.one('SELECT 1 FROM relay_nonces WHERE mailbox=? AND nonce=?', (mailbox, nonce)):
                raise RelayError(401, 'replayed')
            tx.execute('INSERT INTO relay_nonces VALUES(?,?,?)', (mailbox, nonce, now + 601))
        return _json(200, {'mailbox': mailbox})

    def _grant(self, mailbox, target, headers, body):
        try:
            value = json.loads(body)
            if set(value) != {'token_hash', 'expires', 'packets'}:
                raise ValueError()
            th, expires, packets = value['token_hash'], value['expires'], value['packets']
            if not HEX64.fullmatch(th) or type(expires) is not int or type(packets) is not int:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise RelayError(400, 'bad_request') from None
        with self.store.transaction() as tx:
            now = self._signed(tx, mailbox, 'POST', target, headers, body)
            if not now < expires <= now + MAX_GRANT_SECONDS or not 1 <= packets <= MAX_GRANT_PACKETS:
                raise RelayError(400, 'bad_request')
            tx.execute('DELETE FROM relay_grants WHERE mailbox=? AND (expires<? OR revoked=1 OR remaining=0)',
                       (mailbox, now))
            if tx.one('SELECT COUNT(*) FROM relay_grants WHERE mailbox=?', (mailbox,))[0] >= MAX_GRANTS:
                raise RelayError(409, 'too_many_grants')
            if tx.one('SELECT 1 FROM relay_grants WHERE token_hash=?', (th,)):
                raise RelayError(409, 'duplicate')
            grant = secrets.token_hex(16)
            tx.execute('INSERT INTO relay_grants VALUES(?,?,?,?,?,0,?)', (grant, mailbox, th, expires, packets, now))
        return _json(200, {'grant_id': grant, 'expires': expires, 'packets': packets})

    def _revoke(self, mailbox, target, headers, body, grant):
        with self.store.transaction() as tx:
            self._signed(tx, mailbox, 'DELETE', target, headers, body)
            tx.execute('UPDATE relay_grants SET revoked=1 WHERE id=? AND mailbox=?', (grant, mailbox))
        return _json(200, {'grant_id': grant, 'revoked': True})

    def _fetch(self, mailbox, target, headers, body, query):
        after, limit = _int(query, 'after', 0), _int(query, 'limit', 50)
        if after < 0 or not 1 <= limit <= MAX_FETCH:
            raise RelayError(400, 'bad_request')
        with self.store.transaction() as tx:
            now = self._signed(tx, mailbox, 'GET', target, headers, body)
            tx.execute('DELETE FROM relay_packets WHERE mailbox=? AND expires<?', (mailbox, now))
            rows = tx.all('SELECT seq,id,grant_id,received,body FROM relay_packets WHERE mailbox=? AND seq>? '
                          'ORDER BY seq LIMIT ?', (mailbox, after, limit + 1))
        packets = [{'seq': r[0], 'id': r[1], 'grant_id': r[2], 'received_at': r[3], 'body': r[4]} for r in rows[:limit]]
        return _json(200, {'packets': packets, 'more': len(rows) > limit})

    def _ack(self, mailbox, target, headers, body, query):
        through = _int(query, 'through', -1)
        if through < 1:
            raise RelayError(400, 'bad_request')
        with self.store.transaction() as tx:
            self._signed(tx, mailbox, 'DELETE', target, headers, body)
            removed = tx.execute('DELETE FROM relay_packets WHERE mailbox=? AND seq<=?', (mailbox, through)).rowcount
        return _json(200, {'deleted_through': through, 'deleted': removed})

    # Sender operation ----------------------------------------------------------

    def _deliver(self, mailbox, headers, body):
        auth = headers.get('authorization', '')
        if not auth.startswith('Bearer ') or not 32 <= len(auth) - 7 <= 64 or not body:
            raise RelayError(401, 'no_grant')
        th = token_hash(auth[7:])
        with self.store.transaction() as tx:
            now = self._now()
            grant = tx.one('SELECT id,expires,remaining,revoked FROM relay_grants WHERE token_hash=? AND mailbox=?',
                           (th, mailbox))
            if grant is None or grant[3] or grant[1] <= now or grant[2] <= 0:
                raise RelayError(401, 'no_grant')  # One answer for unknown, used up, revoked or expired.
            tx.execute('DELETE FROM relay_packets WHERE mailbox=? AND expires<?', (mailbox, now))
            count, size = tx.one('SELECT COUNT(*), COALESCE(SUM(LENGTH(body)),0) FROM relay_packets WHERE mailbox=?',
                                 (mailbox,))
            encoded = b64e(body)
            if count >= MAX_QUEUED or size + len(encoded) > MAX_QUEUED_BYTES:
                raise RelayError(507, 'mailbox_full')
            seq = tx.one('SELECT next_seq FROM relay_counters WHERE mailbox=?', (mailbox,))[0]
            tx.execute('UPDATE relay_counters SET next_seq=? WHERE mailbox=?', (seq + 1, mailbox))
            tx.execute('UPDATE relay_grants SET remaining=remaining-1 WHERE id=?', (grant[0],))
            packet = secrets.token_hex(16)
            tx.execute('INSERT INTO relay_packets VALUES(?,?,?,?,?,?,?)',
                       (mailbox, seq, packet, grant[0], now, now + RETENTION, encoded))
        return _json(202, {'packet_id': packet, 'stored_until': now + RETENTION})

    def _invite_page(self):
        page = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>Assistant Central invite</title>'
                '<body style="font:16px system-ui;max-width:36rem;margin:3rem auto;padding:0 1rem">'
                '<h1>You have an Assistant Central invite</h1>'
                '<p>Open this link in Assistant Central, or copy the whole address into Central under '
                '<b>Add a person</b>. The part after <code>#</code> stays on your device and was never sent here.</p>'
                f'<p><a href="{self.source_url}">Relay source code (AGPL-3.0)</a></p>')
        return 200, {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store',
                     'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"}, page.encode()


def _int(query, name, default):
    values = query.get(name)
    if not values:
        return default
    if len(values) != 1 or not re.fullmatch(r'\d{1,12}', values[0]):
        raise RelayError(400, 'bad_request')
    return int(values[0])
