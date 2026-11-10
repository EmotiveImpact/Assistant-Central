"""Standalone exact source-permission contract, not a runtime permission bypass.

A signature authenticates a pinned local key, not real-world source ownership.
Only observed withdrawals/versions can be enforced. This module does no network,
execution, transport receipt processing or result acceptance. See SOURCE_GRANTS.md.
"""
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
import re
import sqlite3
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .crypto import b64, fingerprint, unb64, validate_public, TransportDenied
from .provider import ENDPOINT

DOMAIN = 'assistant-central-source-grant/1'
MAX_BYTES = 16384
MAX_SOURCES = 16
MAX_LIFETIME = 600
_PROVISIONING = object()


class GrantDenied(ValueError):
    """Fixed local rejection, never evidence of remote non-disclosure."""


class GrantOutcomeUnknown(RuntimeError):
    """Inspect retained state. Never repeat a potentially consumed disclosure."""


def _need(condition, message='Invalid source-permission contract'):
    if not condition:
        raise GrantDenied(message)


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise GrantDenied('Invalid canonical source-permission data') from None


def _snapshot(value):
    count = 0
    def walk(item, depth):
        nonlocal count
        count += 1
        _need(depth <= 8 and count <= 2048, 'Source-permission data exceeds structural bounds')
        if type(item) is dict:
            _need(len(item) <= 128)
            for key, child in item.items():
                _need(type(key) is str and 0 < len(key) <= 128)
                walk(child, depth + 1)
        elif type(item) is list:
            _need(len(item) <= 128)
            for child in item:
                walk(child, depth + 1)
        elif type(item) is str:
            _need(len(item) <= MAX_BYTES)
        elif type(item) is int:
            _need(-(2**63) < item < 2**63)
        elif type(item) is float:
            _need(math.isfinite(item))
        else:
            _need(item is None or type(item) is bool)
    walk(value, 0)
    encoded = _canonical(value)
    _need(len(encoded) <= MAX_BYTES, 'Source-permission data exceeds byte bound')
    return json.loads(encoded)


def commitment(value):
    """SHA-256 of bounded exact canonical JSON, not arbitrary file bytes."""
    return hashlib.sha256(_canonical(_snapshot(value))).hexdigest()


def _fields(value, names):
    _need(type(value) is dict and set(value) == set(names.split()))


def _id(value):
    _need(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is not None)
    return value


def _hash(value):
    _need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)
    return value


def _integer(value):
    _need(type(value) is int and 0 < value < 2**63)
    return value


def _public(value):
    try:
        return validate_public(value)
    except (TransportDenied, TypeError, ValueError):
        raise GrantDenied('Invalid pinned source identity') from None


def disclosure_plan(value):
    """Closed exact scope. Labels are inert, never selectors or wildcard rights."""
    plan = _snapshot(value)
    _fields(plan, 'operation_id context executor recipient purpose destination payload_digest sources')
    _id(plan['operation_id'])
    for field in ('context', 'executor', 'recipient', 'payload_digest'):
        _hash(plan[field])
    _need(type(plan['purpose']) is str and 0 < len(plan['purpose'].encode('utf-8')) <= 1024)
    destination = plan['destination']
    if destination is not None:
        _need(plan['recipient'] == plan['executor'], 'Provider disclosure recipient must be its executor')
        _fields(destination, 'provider endpoint model max_output_tokens')
        _need(destination['provider'] == 'openai' and destination['endpoint'] == ENDPOINT,
              'Unsupported exact provider destination')
        _id(destination['model'])
        _need(type(destination['max_output_tokens']) is int and 16 <= destination['max_output_tokens'] <= 4096)
    sources = plan['sources']
    _need(type(sources) is list and 1 <= len(sources) <= MAX_SOURCES)
    keys = []
    for source in sources:
        _fields(source, 'owner source_id revision scope data_digest')
        _hash(source['owner']); _id(source['source_id']); _integer(source['revision']); _hash(source['data_digest'])
        scope = source['scope']
        _need(type(scope) is list and 1 <= len(scope) <= 16)
        for label in scope:
            _id(label)
        _need(scope == sorted(set(scope)), 'Scope labels must be sorted and unique')
        keys.append((source['owner'], source['source_id']))
    _need(keys == sorted(set(keys)), 'Source snapshots must be sorted and unique')
    return plan


def statement(value):
    body = _snapshot(value)
    _need(type(body) is dict and body.get('domain') == DOMAIN)
    kind = body.get('kind')
    if kind == 'grant':
        _fields(body, 'domain kind issuer operation_id revision issued_at expires_at plan')
        _integer(body['revision']); _integer(body['expires_at'])
        plan = disclosure_plan(body['plan'])
        _need(body['operation_id'] == plan['operation_id'])
        _need(body['issuer'] in {source['owner'] for source in plan['sources']},
              'Signer must own a declared source snapshot')
        _need(0 < body['expires_at'] - _integer(body['issued_at']) <= MAX_LIFETIME,
              'Source grants must expire within ten minutes')
    elif kind == 'withdrawal':
        # Terminal veto of this issuer's entire operation, including later versions.
        # No expiry: a delayed authenticated veto must not become harmless.
        _fields(body, 'domain kind issuer operation_id issued_at')
    else:
        raise GrantDenied('Unsupported source-permission statement')
    _hash(body['issuer']); _id(body['operation_id']); _integer(body['issued_at'])
    return body


def review_statement(value):
    body = statement(value)
    review = {'domain': DOMAIN + '/owner-review', 'statement': body}
    return {'review': review, 'review_digest': commitment(review)}


def sign_statement(auth, session, value, expected_review_digest):
    """Trusted owner UI only: explicitly approve this exact reviewed statement.

    An agent proposal or transport handler must not receive this capability.
    No authority database, source truth or human comprehension is inferred here.
    """
    body = statement(value)
    _need(review_statement(body)['review_digest'] == _hash(expected_review_digest), 'Stale source-permission review')
    try:
        with auth.authorised(session):
            public = _public(auth.public_identity())
            _need(body['issuer'] == fingerprint(public), 'Statement names another owner key')
            signed = {'statement': body, 'signature': b64(auth.sign(session, DOMAIN.encode() + b'\n' + _canonical(body)))}
            _snapshot(signed)  # The signed envelope, not only its body, must fit.
            auth.authenticate(session)
            return signed
    except PermissionError:
        raise GrantDenied('Current authenticated source-owner session required') from None


def verify_statement(signed, pinned_public):
    """Verify schema, key and signature only. This does NOT check current authority."""
    signed = _snapshot(signed)
    _fields(signed, 'statement signature')
    body = statement(signed['statement'])
    public = _public(pinned_public)
    _need(body['issuer'] == fingerprint(public), 'Source signer does not match the pinned identity')
    try:
        Ed25519PublicKey.from_public_bytes(unb64(public['signing_key'], 32)).verify(
            unb64(signed['signature'], 64), DOMAIN.encode() + b'\n' + _canonical(body))
    except (TransportDenied, InvalidSignature, ValueError):
        raise GrantDenied('Source-permission signature verification failed') from None
    return body


class SourceGrantLedger:
    """One trusted executor, immutable pins, bounded durable local observations.

    The host owns the SQLite connection, filesystem protection and lifecycle.
    This standalone ledger cannot authorise existing pilot runtime/provider APIs.
    Never use multiple independent ledgers to enforce a single-use operation.
    """
    def __init__(self, connection, auth, pinned_publics, *, clock=time.time, max_records=1000):
        _need(type(connection) is sqlite3.Connection and callable(clock))
        _need(type(max_records) is int and 1 <= max_records <= 10000)
        _need(type(pinned_publics) is list and 1 <= len(pinned_publics) <= 32)
        self.db, self.auth, self.clock, self.max_records = connection, auth, clock, max_records
        self.identity = _public(auth.public_identity())
        self.executor = fingerprint(self.identity)
        publics = [_public(public) for public in pinned_publics]
        _need(len({p['signing_key'] for p in publics}) == len(publics), 'Pinned identities must use distinct signing keys')
        self.pins = {fingerprint(public): public for public in publics}
        _need(self.executor in self.pins, 'Executor identity must be explicitly pinned')
        self._configuration = _canonical({'domain': DOMAIN, 'executor': self.executor,
            'pins': self.pins, 'max_records': max_records}).decode()
        with self._transaction():
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1), configuration TEXT NOT NULL, last_now REAL NOT NULL, fenced INTEGER NOT NULL DEFAULT 0)')
            row = self.db.execute('SELECT configuration FROM source_grant_meta').fetchone()
            _need(row is None or row[0] == self._configuration, 'Source-grant trust roots or policy changed')
            if row is None:
                self.db.execute('INSERT INTO source_grant_meta(singleton,configuration,last_now) VALUES(1,?,?)', (self._configuration, self._now()))
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_observations(issuer TEXT NOT NULL, operation TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL, conflicted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(issuer,operation))')
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_withdrawals(issuer TEXT NOT NULL, operation TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(issuer,operation))')
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_claims(operation TEXT PRIMARY KEY, plan_digest TEXT NOT NULL, grants TEXT NOT NULL, claimed_at REAL NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_cancellations(operation TEXT PRIMARY KEY)')
            self.db.execute('CREATE TABLE IF NOT EXISTS source_grant_revocations(issuer TEXT PRIMARY KEY)')

    def _now(self):
        value = self.clock()
        _need(type(value) in (int, float) and math.isfinite(value) and value > 0, 'Invalid source-grant clock')
        return value

    @contextmanager
    def _transaction(self, session=_PROVISIONING, *, before_commit=None):
        _need(not self.db.in_transaction, 'Source-grant operation needs its own transaction')
        try:
            with self.auth.authorised(session) if session is not _PROVISIONING else nullcontext():
                if session is not _PROVISIONING:
                    self._authenticate(session)
                self.db.execute('BEGIN IMMEDIATE')
                try:
                    now = self._now()
                    if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_grant_meta'").fetchone():
                        row = self.db.execute('SELECT configuration,last_now FROM source_grant_meta').fetchone()
                        _need(row is not None and row[0] == self._configuration and now >= row[1], 'Source-grant configuration or clock rollback')
                    yield now
                    if session is not _PROVISIONING:
                        self._authenticate(session)
                    end = self._now()
                    _need(end >= now, 'Source-grant clock moved backwards')
                    if before_commit is not None:
                        before_commit(end)
                    self.db.execute('UPDATE source_grant_meta SET last_now=? WHERE singleton=1', (end,))
                    self.db.execute('COMMIT')
                except BaseException:
                    if self.db.in_transaction:
                        self.db.execute('ROLLBACK')
                    raise
        except GrantDenied:
            raise
        except PermissionError:
            raise GrantDenied('Current authenticated executor session required') from None
        except Exception:
            raise GrantOutcomeUnknown('Source-grant state outcome unavailable; inspect the original operation.') from None

    def _authenticate(self, session):
        identity = self.auth.authenticate(session)
        _need((identity['owner_id'], identity['agent_id']) == (self.identity['owner_id'], self.identity['agent_id'])
              and _public(self.auth.public_identity()) == self.identity, 'Executor identity changed')

    def _bound(self, table):
        _need(self.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] < self.max_records,
              'Source-grant history capacity reached; history cannot be evicted')

    def _veto_capacity(self, table):
        # Failing to retain a received veto must not leave old grants usable.
        if self.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] >= self.max_records:
            self.db.execute('UPDATE source_grant_meta SET fenced=1 WHERE singleton=1')
            return False
        return True

    def _pinned(self, issuer):
        _hash(issuer)
        _need(issuer in self.pins, 'Source identity is not pinned')
        _need(not self.db.execute('SELECT 1 FROM source_grant_revocations WHERE issuer=?', (issuer,)).fetchone(),
              'Source identity was locally revoked')
        return self.pins[issuer]

    def observe(self, session, signed):
        """Explicit authenticated import. Duplicate observation is not a second use."""
        signed = _snapshot(signed)
        _fields(signed, 'statement signature')
        body = statement(signed['statement'])
        issuer, operation = body['issuer'], body['operation_id']
        digest = commitment(body)
        conflict = False
        ineligible = None
        with self._transaction(session) as now:
            verify_statement(signed, self._pinned(issuer))
            if body['kind'] == 'withdrawal':
                _need(body['issued_at'] <= now, 'Source statement is future-dated')
                if not self.db.execute('SELECT 1 FROM source_grant_withdrawals WHERE issuer=? AND operation=?', (issuer, operation)).fetchone():
                    if not self._veto_capacity('source_grant_withdrawals'):
                        return {'operation_id': operation, 'issuer': issuer, 'state': 'ledger-fenced'}
                    self.db.execute('INSERT INTO source_grant_withdrawals VALUES(?,?,?)', (issuer, operation, digest))
                return {'operation_id': operation, 'issuer': issuer, 'state': 'withdrawn'}
            old = self.db.execute('SELECT revision,digest,conflicted FROM source_grant_observations WHERE issuer=? AND operation=?', (issuer, operation)).fetchone()
            if old:
                _need(not old[2], 'Conflicting owner revisions permanently fenced this operation')
                _need(body['revision'] >= old[0], 'Stale source-grant revision')
                if body['revision'] == old[0]:
                    if digest != old[1]:
                        # Retain the veto before reporting denial. Rollback would revive the old grant.
                        self.db.execute('UPDATE source_grant_observations SET conflicted=1 WHERE issuer=? AND operation=?', (issuer, operation))
                        conflict = True
                else:
                    self.db.execute('UPDATE source_grant_observations SET revision=?,digest=? WHERE issuer=? AND operation=?',
                                    (body['revision'], digest, issuer, operation))
            else:
                self._bound('source_grant_observations')
                self.db.execute('INSERT INTO source_grant_observations(issuer,operation,revision,digest) VALUES(?,?,?,?)',
                                (issuer, operation, body['revision'], digest))
            # A signed newer revision supersedes old authority even if the new
            # grant is expired, future-dated or addressed elsewhere. Eligibility
            # failures must not roll back the authenticated revision high-water.
            try:
                self._eligible(body, now)
            except GrantDenied as error:
                ineligible = str(error)
        _need(not conflict, 'Conflicting owner revisions permanently fenced this operation')
        if ineligible is not None:
            raise GrantDenied(ineligible)
        return {'operation_id': operation, 'issuer': issuer, 'revision': body['revision'], 'state': 'observed'}

    def _eligible(self, body, now):
        plan = body['plan']
        _need(plan['executor'] == self.executor, 'Source grant belongs to another executor')
        _need(body['issued_at'] <= now < body['expires_at'], 'Source grant is not current')
        _need(not self.db.execute('SELECT 1 FROM source_grant_withdrawals WHERE issuer=? AND operation=?',
                                 (body['issuer'], body['operation_id'])).fetchone(), 'Source owner withdrew this operation')
        _need(not self.db.execute('SELECT 1 FROM source_grant_cancellations WHERE operation=?',
                                 (body['operation_id'],)).fetchone(), 'Executor cancelled this operation')
        self._pinned(plan['recipient'])
        for source in plan['sources']:
            self._pinned(source['owner'])

    def cancel(self, session, operation_id):
        """Local executor veto, terminal even when no grant has arrived yet."""
        operation = _id(operation_id)
        with self._transaction(session):
            if not self.db.execute('SELECT 1 FROM source_grant_cancellations WHERE operation=?', (operation,)).fetchone():
                if self._veto_capacity('source_grant_cancellations'):
                    self.db.execute('INSERT INTO source_grant_cancellations VALUES(?)', (operation,))
            return self._status(operation)

    def revoke_pin(self, session, issuer):
        """Local permanent distrust; never silently substitutes a replacement key."""
        _hash(issuer)
        _need(issuer in self.pins, 'Source identity is not pinned')
        with self._transaction(session):
            self.db.execute('INSERT OR IGNORE INTO source_grant_revocations VALUES(?)', (issuer,))

    def _current(self, plan, bodies, now):
        _need(not self.db.execute('SELECT fenced FROM source_grant_meta').fetchone()[0],
              'Source-grant ledger permanently fenced after veto capacity exhaustion')
        operation = plan['operation_id']
        self._pinned(self.executor); self._pinned(plan['recipient'])
        _need(not self.db.execute('SELECT 1 FROM source_grant_claims WHERE operation=?', (operation,)).fetchone(),
              'Operation already consumed; never repeat a potentially disclosed payload')
        _need(not self.db.execute('SELECT 1 FROM source_grant_cancellations WHERE operation=?', (operation,)).fetchone(), 'Executor cancelled this operation')
        for issuer, body in bodies.items():
            self._pinned(issuer)
            _need(not self.db.execute('SELECT 1 FROM source_grant_withdrawals WHERE issuer=? AND operation=?', (issuer, operation)).fetchone(), 'Source owner withdrew this operation')
            row = self.db.execute('SELECT digest,conflicted,revision FROM source_grant_observations WHERE issuer=? AND operation=?', (issuer, operation)).fetchone()
            _need(row is not None and not row[1] and row[0] == commitment(body)
                  and row[2] == body['revision'], 'Missing, stale or conflicting source grant')
        self._fresh(bodies, now)

    @staticmethod
    def _fresh(bodies, now):
        for body in bodies.values():
            _need(body['issued_at'] <= now < body['expires_at'], 'Source grant is not current')

    def consume(self, session, plan, payload, fragments, signed_grants):
        """Burn one source-permission attempt before any separately approved effect.

        Success is metadata, NOT execution/release authority. There is no rollback
        or retry API once committed, even if a later effect never occurs. Original
        signed grants must be supplied; the ledger stores only their commitments.
        """
        plan = disclosure_plan(plan)
        _need(plan['executor'] == self.executor, 'Source grant belongs to another executor')
        _need(commitment(payload) == plan['payload_digest'], 'Exact disclosed payload changed')
        fragments = _snapshot(fragments)
        _need(type(fragments) is list and len(fragments) == len(plan['sources']), 'Exact source snapshots required')
        for source, fragment in zip(plan['sources'], fragments):
            _fields(fragment, 'owner source_id value')
            _need((fragment['owner'], fragment['source_id']) == (source['owner'], source['source_id'])
                  and commitment(fragment['value']) == source['data_digest'], 'Source snapshot changed')
        _need(type(signed_grants) is dict and set(signed_grants) == {source['owner'] for source in plan['sources']},
              'Exactly one current grant per source owner required')
        # Each bounded envelope is copied/verified separately. A legitimate
        # multi-owner bundle can exceed the per-envelope byte bound.
        bodies = {}
        for issuer, signed in signed_grants.items():
            _need(issuer in self.pins, 'Source identity is not pinned')
            body = verify_statement(signed, self.pins[issuer])
            _need(body['kind'] == 'grant' and body['issuer'] == issuer and body['plan'] == plan,
                  'Source grant does not match exact disclosure')
            bodies[issuer] = body
        expected = {issuer: commitment(body) for issuer, body in bodies.items()}
        with self._transaction(session, before_commit=lambda now: self._fresh(bodies, now)) as now:
            self._current(plan, bodies, now)
            self._bound('source_grant_claims')
            self.db.execute('INSERT INTO source_grant_claims VALUES(?,?,?,?)',
                            (plan['operation_id'], commitment(plan), _canonical(expected).decode(), now))
            result = self._status(plan['operation_id'])
        return result

    def _status(self, operation):
        row = self.db.execute('SELECT plan_digest,claimed_at FROM source_grant_claims WHERE operation=?', (operation,)).fetchone()
        cancelled = bool(self.db.execute('SELECT 1 FROM source_grant_cancellations WHERE operation=?', (operation,)).fetchone())
        withdrawals = self.db.execute('SELECT issuer FROM source_grant_withdrawals WHERE operation=? ORDER BY issuer', (operation,)).fetchall()
        return {'operation_id': operation, 'consumed': row is not None,
                'plan_digest': row[0] if row else None, 'claimed_at': row[1] if row else None,
                'cancelled': cancelled, 'observed_withdrawals': [item[0] for item in withdrawals],
                'ledger_fenced': bool(self.db.execute('SELECT fenced FROM source_grant_meta').fetchone()[0]),
                'retry_allowed': False, 'execution_approved': False, 'recipient_accepted': False,
                'remote_revocation_known': False}

    def status(self, session, operation_id):
        """Historical local metadata only, not an active/retry/remote success claim."""
        operation = _id(operation_id)
        with self._transaction(session):
            return self._status(operation)
