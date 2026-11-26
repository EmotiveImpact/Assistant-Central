# SPDX-License-Identifier: AGPL-3.0-only
"""Durable relay state over SQL. SQLite locally; any DB-API driver in production.

Binary values are stored as base64 text so the schema is portable. The schema holds no plaintext and no identities: mailbox public keys, hashed
send tokens, opaque packets and short-lived replay nonces.
"""
import sqlite3
import threading
from contextlib import contextmanager

SCHEMA = '''
CREATE TABLE IF NOT EXISTS relay_mailboxes(id TEXT PRIMARY KEY, public_key TEXT NOT NULL, created BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS relay_grants(id TEXT PRIMARY KEY, mailbox TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    expires BIGINT NOT NULL, remaining BIGINT NOT NULL, revoked BIGINT NOT NULL DEFAULT 0, created BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS relay_packets(mailbox TEXT NOT NULL, seq BIGINT NOT NULL, id TEXT NOT NULL UNIQUE,
    grant_id TEXT NOT NULL, received BIGINT NOT NULL, expires BIGINT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY(mailbox, seq));
CREATE TABLE IF NOT EXISTS relay_nonces(mailbox TEXT NOT NULL, nonce TEXT NOT NULL, expires BIGINT NOT NULL,
    PRIMARY KEY(mailbox, nonce));
CREATE TABLE IF NOT EXISTS relay_counters(mailbox TEXT PRIMARY KEY, next_seq BIGINT NOT NULL);
'''


class SqlStore:
    """A thin, transactional wrapper. ``paramstyle`` is ``qmark`` (SQLite) or ``format`` (psycopg)."""

    def __init__(self, connect, *, paramstyle='qmark'):
        if paramstyle not in ('qmark', 'format'):
            raise ValueError('unsupported paramstyle')
        self._connect, self._style = connect, paramstyle
        self._lock = threading.Lock()
        self._conn = connect()
        with self.transaction() as tx:
            for statement in filter(str.strip, SCHEMA.split(';')):
                tx.execute(statement)

    @classmethod
    def sqlite(cls, path):
        def connect():
            conn = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=FULL')
            return conn
        return cls(connect)

    def close(self):
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            # Serverless databases close idle connections; open a fresh one when that happens.
            if getattr(self._conn, 'closed', False) or getattr(self._conn, 'broken', False):
                self._conn = self._connect()
            tx = _Tx(self._conn, self._style)
            tx.begin()
            try:
                yield tx
                tx.commit()
            except BaseException:
                tx.rollback()
                raise


class _Tx:
    def __init__(self, conn, style):
        self.conn, self.style = conn, style
        self.sqlite = isinstance(conn, sqlite3.Connection)

    def begin(self):
        if self.sqlite:
            self.conn.execute('BEGIN IMMEDIATE')

    def commit(self):
        if self.sqlite:
            self.conn.execute('COMMIT')
        else:
            self.conn.commit()

    def rollback(self):
        if self.sqlite:
            if self.conn.in_transaction:
                self.conn.execute('ROLLBACK')
        else:
            self.conn.rollback()

    def execute(self, sql, params=()):
        if self.style == 'format':
            sql = sql.replace('?', '%s')
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor

    def one(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def all(self, sql, params=()):
        return self.execute(sql, params).fetchall()
