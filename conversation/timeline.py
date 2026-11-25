"""One owner-side timeline of what happened, in the order it happened.

Borrowed idea (ericscalibur/Parley): a single timeline where the owner can see
everything their assistant saw and did. Here the timeline is a local journal,
one per owner, kept beside the other stores:

* Entries are appended by the owner's own host components (inbox, desk, shared
  drafts, questions, mission activity) at the moment something happens.
* Each entry is idempotent by ``(kind, ref)``, so a retried step is not listed twice.
* Entries are hash-chained, and the details are sealed to the owner's key.
* Entries hold references and states, never message or draft text. The owner's
  screen fetches text through the store that owns it, with its own checks.
* Only the owner's session can read it. It never enters the conversation.
"""
import json
import math
import sqlite3
import threading
from pathlib import Path

from pilot.auth import _create_private_file, _private_path
from pilot.crypto import canonical, digest
from pilot.storage import RecordStorage

from .ledger import ConversationDenied, identifier, need

VERSION = 'assistant-central-owner-timeline/1'
GENESIS = '0' * 64
ROLES = ('you', 'your_assistant', 'someone_else', 'system')
KINDS = (
    'message_received',
    'message_proposed', 'message_sent_by_assistant', 'message_approved', 'message_declined', 'message_failed',
    'policy_changed', 'guidance_changed',
    'draft_started', 'draft_revised', 'draft_suggested',
    'question_asked', 'question_answered',
    'mission_activity',
)
MAX_ENTRIES = 200000
MAX_DETAIL_BYTES = 2048


class _TimelineStorage(RecordStorage):
    def _context(self, table, row_id, column):
        need(table == 'timeline' and column == 'detail' and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class OwnerTimeline:
    def __init__(self, directory, auth, principal, clock):
        need(type(principal) is str and callable(clock))
        self.auth, self.principal, self.clock = auth, principal, clock
        self._lock = threading.RLock()
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private_path(self.directory, directory=True)
        path = self.directory / 'timeline.sqlite'
        _create_private_file(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.storage = _TimelineStorage(self.db, auth, create=True)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS timeline_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS timeline(seq INTEGER PRIMARY KEY,at REAL NOT NULL,conversation_id TEXT NOT NULL,role TEXT NOT NULL,kind TEXT NOT NULL,ref TEXT NOT NULL,prev TEXT NOT NULL,hash TEXT NOT NULL,detail TEXT NOT NULL,UNIQUE(kind,ref));
            ''')
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM timeline_meta').fetchone()
            if row is None:
                self.db.execute('INSERT INTO timeline_meta VALUES(1,?,?)', (VERSION, principal))
            else:
                need(row['version'] == VERSION and row['owner'] == principal)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            self.db.close()

    # Host components ---------------------------------------------------------

    def record(self, kind, conversation_id, *, role, ref, detail=None):
        """Append one entry, or return the existing one for the same ``(kind, ref)``.

        Called by trusted host components after their own checks, never by a model.
        """
        need(kind in KINDS and role in ROLES)
        identifier(conversation_id)
        need(type(ref) is str and 0 < len(ref) <= 160 and all(c.isalnum() or c in '_-:.' for c in ref))
        detail = {} if detail is None else detail
        need(type(detail) is dict)
        encoded = canonical(detail)
        need(len(encoded) <= MAX_DETAIL_BYTES)
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                existing = self.db.execute('SELECT seq FROM timeline WHERE kind=? AND ref=?', (kind, ref)).fetchone()
                if existing is not None:
                    self.db.execute('COMMIT')
                    return existing['seq']
                last = self.db.execute('SELECT seq,at,hash FROM timeline ORDER BY seq DESC LIMIT 1').fetchone()
                need(last is None or last['seq'] < MAX_ENTRIES)
                at = self.clock()
                need(type(at) in (int, float) and math.isfinite(at))
                at = max(at, last['at']) if last else at  # Never runs backwards.
                seq = 1 if last is None else last['seq'] + 1
                prev = GENESIS if last is None else last['hash']
                entry = {'domain': VERSION, 'owner': self.principal, 'seq': seq, 'at': at,
                         'conversation_id': conversation_id, 'role': role, 'kind': kind, 'ref': ref,
                         'prev': prev, 'detail_digest': digest(detail)}
                entry_hash = digest(entry)
                self.db.execute('INSERT INTO timeline VALUES(?,?,?,?,?,?,?,?,?)',
                                (seq, at, conversation_id, role, kind, ref, prev, entry_hash,
                                 self.storage.seal('timeline', str(seq), 'detail', encoded.decode())))
                self.db.execute('COMMIT')
                return seq
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def record_mission_activity(self, conversation_id, log, *, owner_label):
        """Import a ``mission_cards`` activity log. Message bodies are not copied."""
        count = 0
        for event in log.list_activity():
            role = 'you' if event['actor'] == owner_label else 'someone_else'
            self.record('mission_activity', conversation_id, role=role,
                        ref=f"{event['anchor']}:{event['seq']}",
                        detail={'mission': event['anchor'], 'event': event['kind'], 'at': event['at'],
                                'hash': event['hash']})
            count += 1
        return count

    # Owner -----------------------------------------------------------------

    def read(self, session, *, conversation_id=None, after=0, limit=50):
        need(self.auth.authenticate(session)['identity_fingerprint'] == self.principal)
        need(type(after) is int and after >= 0 and type(limit) is int and 1 <= limit <= 200)
        if conversation_id is not None:
            identifier(conversation_id)
        with self._lock:
            self.verify()
            query = 'SELECT * FROM timeline WHERE seq>?' + (' AND conversation_id=?' if conversation_id else '')
            params = (after, conversation_id) if conversation_id else (after,)
            rows = self.db.execute(query + ' ORDER BY seq LIMIT ?', (*params, limit + 1)).fetchall()
            entries = [{'seq': r['seq'], 'at': r['at'], 'conversation_id': r['conversation_id'], 'role': r['role'],
                        'kind': r['kind'], 'ref': r['ref'], 'detail': self._detail(r)} for r in rows[:limit]]
            return {'entries': entries, 'more': len(rows) > limit,
                    'next_after': entries[-1]['seq'] if entries else after, 'audience': 'owner-only'}

    def _detail(self, row):
        return json.loads(self.storage.open('timeline', str(row['seq']), 'detail', row['detail']))

    def verify(self):
        """Check the whole chain: complete, in order and unaltered. Refuses otherwise."""
        with self._lock:
            prev, expected = GENESIS, 1
            for row in self.db.execute('SELECT * FROM timeline ORDER BY seq'):
                need(row['seq'] == expected and row['prev'] == prev)
                entry = {'domain': VERSION, 'owner': self.principal, 'seq': row['seq'], 'at': row['at'],
                         'conversation_id': row['conversation_id'], 'role': row['role'], 'kind': row['kind'],
                         'ref': row['ref'], 'prev': prev, 'detail_digest': digest(self._detail(row))}
                need(digest(entry) == row['hash'])
                prev, expected = row['hash'], expected + 1
            return True


def record_safely(timeline, kind, conversation_id, **kwargs):
    """Hooks must never break the action they describe. A failed record is dropped."""
    if timeline is None:
        return None
    try:
        return timeline.record(kind, conversation_id, **kwargs)
    except (ConversationDenied, sqlite3.Error, ValueError, TypeError):
        return None
