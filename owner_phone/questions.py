"""Questions an assistant asks its own owner, answered from a phone or from Central.

Borrowed idea (ericscalibur/Parley): when the assistant is unsure, it asks its
human, who can answer by phone. Here a question is a short choice between two to
four options. The answer is information for the assistant. It is never an
approval to send, share, run or spend: those keep their own exact owner reviews.

Questions and answers are sealed to the owner's own key and never enter the
conversation.
"""
import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path

from pilot.auth import _create_private_file, _private_path
from pilot.crypto import canonical
from pilot.storage import RecordStorage

from conversation.inbox import AssistantLease, InboxStore
from conversation.ledger import ConversationDenied, bounded_text, identifier, need
from conversation.timeline import record_safely

VERSION = 'assistant-central-owner-questions/1'
MAX_QUESTION_BYTES = 1024
MAX_OPTION_BYTES = 64
MAX_OPEN_QUESTIONS = 64
MAX_QUESTIONS = 4096
MAX_QUESTION_SECONDS = 7 * 86400
PAIRING_SECONDS = 600


class _QuestionStorage(RecordStorage):
    def _context(self, table, row_id, column):
        need(table == 'owner_questions' and column == 'body' and type(row_id) is str)
        return canonical([VERSION + '/encrypted-record', self.owner, table, row_id, column])


class OwnerQuestions:
    """One owner's assistant questions, plus a single paired phone chat."""

    def __init__(self, directory, inbox, principal, timeline=None):
        self.timeline = timeline
        need(type(inbox) is InboxStore and type(principal) is str and principal in inbox.ledger.actors)
        self.inbox, self.principal = inbox, principal
        self.auth = inbox.ledger.actors[principal]
        self.clock = inbox.ledger.clock
        self._lock = threading.RLock()
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private_path(self.directory, directory=True)
        path = self.directory / 'questions.sqlite'
        _create_private_file(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.storage = _QuestionStorage(self.db, self.auth, create=True)
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS question_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,owner TEXT NOT NULL,tag_key TEXT NOT NULL,observed REAL NOT NULL,chat_id TEXT,pairing_digest TEXT,pairing_expires REAL);
                CREATE TABLE IF NOT EXISTS owner_questions(id TEXT PRIMARY KEY,assistant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,request_id TEXT NOT NULL,request_digest TEXT NOT NULL,options INTEGER NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,answer INTEGER,answered_via TEXT,phone_sent INTEGER NOT NULL DEFAULT 0,body TEXT NOT NULL,UNIQUE(assistant_id,conversation_id,request_id));
            ''')
            with self._lock:
                self.db.execute('BEGIN IMMEDIATE')
                # When the current chat was paired, so a replacement attempt can tell it worked.
                if 'paired_at' not in {column[1] for column in self.db.execute('PRAGMA table_info(question_meta)')}:
                    self.db.execute('ALTER TABLE question_meta ADD COLUMN paired_at REAL')
                row = self.db.execute('SELECT * FROM question_meta WHERE singleton=1').fetchone()
                if row is None:
                    self.db.execute('INSERT INTO question_meta(singleton,version,owner,tag_key,observed) VALUES(1,?,?,?,0)',
                                    (VERSION, principal, secrets.token_hex(32)))
                else:
                    need(row['version'] == VERSION and row['owner'] == principal)
                self.db.execute('COMMIT')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            self.db.close()

    # Internals --------------------------------------------------------------

    def _meta(self):
        return self.db.execute('SELECT * FROM question_meta WHERE singleton=1').fetchone()

    def _now(self):
        value = self.clock()
        need(type(value) in (int, float) and math.isfinite(value) and value > 0)
        need(value >= self._meta()['observed'])
        self.db.execute('UPDATE question_meta SET observed=? WHERE singleton=1', (value,))
        return value

    def _owner(self, session):
        need(self.auth.authenticate(session)['identity_fingerprint'] == self.principal)

    def _txn(self):
        return _Txn(self.db)

    def _body(self, row):
        return json.loads(self.storage.open('owner_questions', row['id'], 'body', row['body']))

    def _view(self, row, now):
        body = self._body(row)
        state = 'answered' if row['answer'] is not None else ('expired' if now >= row['expires'] else 'waiting')
        return {'question_id': row['id'], 'request_id': row['request_id'], 'question': body['question'],
                'options': body['options'], 'state': state,
                'answer': None if row['answer'] is None else body['options'][row['answer']],
                'answered_via': row['answered_via'], 'expires_at': row['expires'],
                'authority': 'information-only'}

    def tag(self, question_id, option):
        """Short keyed tag that binds a phone button to one question and option."""
        message = f'{question_id}:{option}'.encode()
        return hmac.new(bytes.fromhex(self._meta()['tag_key']), message, hashlib.sha256).hexdigest()[:16]

    # Assistant --------------------------------------------------------------

    def ask(self, session, lease, *, request_id, question, options, seconds=86400):
        identifier(request_id); bounded_text(question, MAX_QUESTION_BYTES)
        need(type(options) in (list, tuple) and 2 <= len(options) <= 4)
        for option in options:
            bounded_text(option, MAX_OPTION_BYTES)
        need(len(set(options)) == len(options))
        need(type(seconds) in (int, float) and math.isfinite(seconds) and 60 <= seconds <= MAX_QUESTION_SECONDS)
        body = {'question': question, 'options': list(options)}
        request_digest = hashlib.sha256(canonical(body)).hexdigest()
        need(type(lease) is AssistantLease and lease.principal == self.principal)
        with self._lock:
            self.inbox.check_lease(session, lease)
            with self._txn():
                now = self._now()
                row = self.db.execute('SELECT * FROM owner_questions WHERE assistant_id=? AND conversation_id=? AND request_id=?',
                                      (lease.assistant_id, lease.conversation_id, request_id)).fetchone()
                if row is not None:
                    need(row['request_digest'] == request_digest)
                    return self._view(row, now)
                need(self.db.execute('SELECT COUNT(*) FROM owner_questions').fetchone()[0] < MAX_QUESTIONS)
                need(self.db.execute('SELECT COUNT(*) FROM owner_questions WHERE answer IS NULL AND expires>?',
                                     (now,)).fetchone()[0] < MAX_OPEN_QUESTIONS)
                question_id = uuid.uuid4().hex
                self.db.execute('INSERT INTO owner_questions(id,assistant_id,conversation_id,request_id,request_digest,options,created,expires,body) VALUES(?,?,?,?,?,?,?,?,?)',
                                (question_id, lease.assistant_id, lease.conversation_id, request_id, request_digest,
                                 len(options), now, now + seconds,
                                 self.storage.seal('owner_questions', question_id, 'body', canonical(body).decode())))
                view = self._view(self._row(question_id), now)
            record_safely(self.timeline, 'question_asked', lease.conversation_id, role='your_assistant',
                          ref='question:' + question_id,
                          detail={'question_id': question_id, 'assistant_id': lease.assistant_id})
            return view

    def answer_for(self, session, lease, request_id):
        identifier(request_id)
        need(type(lease) is AssistantLease and lease.principal == self.principal)
        with self._lock:
            self.inbox.check_lease(session, lease)
            with self._txn():
                row = self.db.execute('SELECT * FROM owner_questions WHERE assistant_id=? AND conversation_id=? AND request_id=?',
                                      (lease.assistant_id, lease.conversation_id, request_id)).fetchone()
                need(row is not None)
                return self._view(row, self._now())

    def _row(self, question_id):
        identifier(question_id)
        row = self.db.execute('SELECT * FROM owner_questions WHERE id=?', (question_id,)).fetchone()
        need(row is not None)
        return row

    # Owner, in Central ------------------------------------------------------

    def waiting(self, session):
        with self._lock:
            self._owner(session)
            with self._txn():
                now = self._now()
                rows = self.db.execute('SELECT * FROM owner_questions WHERE answer IS NULL AND expires>? ORDER BY created,id',
                                       (now,)).fetchall()
                return [{**self._view(row, now), 'assistant_id': row['assistant_id'],
                         'conversation_id': row['conversation_id']} for row in rows]

    def answer(self, session, question_id, option):
        with self._lock:
            self._owner(session)
            return self._record(question_id, option, 'central')

    def _record(self, question_id, option, via):
        with self._txn():
            now = self._now()
            row = self._row(question_id)
            need(type(option) is int and 0 <= option < row['options'])
            if row['answer'] is not None:
                # Repeated taps of the same button are harmless; a different answer is refused.
                need(row['answer'] == option)
                return self._view(row, now)
            need(now < row['expires'])
            self.db.execute('UPDATE owner_questions SET answer=?,answered_via=? WHERE id=?', (option, via, question_id))
            view = self._view(self._row(question_id), now)
        record_safely(self.timeline, 'question_answered', row['conversation_id'], role='you',
                      ref='question:' + question_id, detail={'question_id': question_id, 'via': via})
        return view

    # Phone pairing -----------------------------------------------------------

    def start_pairing(self, session):
        """A one-time code the owner sends to the bot as ``/start <code>``."""
        with self._lock:
            self._owner(session)
            code = secrets.token_hex(8)
            with self._txn():
                now = self._now()
                self.db.execute('UPDATE question_meta SET pairing_digest=?,pairing_expires=? WHERE singleton=1',
                                (hashlib.sha256(code.encode()).hexdigest(), now + PAIRING_SECONDS))
            return {'code': code, 'started_at': now, 'expires_at': now + PAIRING_SECONDS}

    def unpair(self, session):
        with self._lock:
            self._owner(session)
            with self._txn():
                self._now()
                self.db.execute('UPDATE question_meta SET chat_id=NULL,paired_at=NULL,pairing_digest=NULL,pairing_expires=NULL WHERE singleton=1')

    def phone_status(self, session):
        with self._lock:
            self._owner(session)
            meta = self._meta()
            # No secret here: whether a chat is paired, since when, and whether a code is still open.
            return {'paired': meta['chat_id'] is not None, 'paired_at': meta['paired_at'],
                    'pairing_open': meta['pairing_digest'] is not None and self.clock() < meta['pairing_expires']}

    # Channel side (called by a phone adapter, never by a model) --------------

    def complete_pairing(self, chat_id, code):
        need(type(chat_id) is str and 0 < len(chat_id) <= 64 and type(code) is str and len(code) <= 64)
        with self._lock, self._txn():
            now = self._now()
            meta = self._meta()
            need(meta['pairing_digest'] is not None and now < meta['pairing_expires'])
            need(hmac.compare_digest(meta['pairing_digest'], hashlib.sha256(code.encode()).hexdigest()))
            self.db.execute('UPDATE question_meta SET chat_id=?,paired_at=?,pairing_digest=NULL,pairing_expires=NULL WHERE singleton=1',
                            (chat_id, now))

    def paired_chat(self):
        with self._lock:
            return self._meta()['chat_id']

    def unsent_for_phone(self):
        with self._lock, self._txn():
            now = self._now()
            rows = self.db.execute('SELECT * FROM owner_questions WHERE answer IS NULL AND phone_sent=0 AND expires>? ORDER BY created,id',
                                   (now,)).fetchall()
            return [self._view(row, now) for row in rows]

    def mark_sent_to_phone(self, question_id):
        with self._lock, self._txn():
            self._now()
            self._row(question_id)
            self.db.execute('UPDATE owner_questions SET phone_sent=1 WHERE id=?', (question_id,))

    def answer_from_phone(self, chat_id, question_id, option, tag):
        with self._lock:
            paired = self._meta()['chat_id']
            need(paired is not None and type(chat_id) is str and hmac.compare_digest(paired, chat_id))
            need(type(tag) is str and type(option) is int and hmac.compare_digest(self.tag(question_id, option), tag))
            # Recorded by its number alone, so a tap still counts while Parlu is locked: the
            # question text stays sealed, and the paired chat and keyed tag prove the tap is the owner's.
            with self._txn():
                now = self._now()
                row = self._row(question_id)
                need(0 <= option < row['options'])
                if row['answer'] is not None:
                    need(row['answer'] == option)
                    return {'saved': True, 'option': option}
                need(now < row['expires'])
                self.db.execute("UPDATE owner_questions SET answer=?,answered_via='phone' WHERE id=?", (option, question_id))
            record_safely(self.timeline, 'question_answered', row['conversation_id'], role='you',
                          ref='question:' + question_id, detail={'question_id': question_id, 'via': 'phone'})
            return {'saved': True, 'option': option}


class _Txn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute('BEGIN IMMEDIATE')

    def __exit__(self, kind, error, trace):
        if self.db.in_transaction:
            self.db.execute('ROLLBACK' if kind else 'COMMIT')
        if isinstance(error, sqlite3.Error):
            raise ConversationDenied('Question store unavailable') from None
        return False


class QuestionAccess:
    """Assistant-facing handle: fixed lease, owner session from a host callback."""

    def __init__(self, questions, lease, session_provider):
        need(type(questions) is OwnerQuestions and type(lease) is AssistantLease and callable(session_provider))
        self._questions, self._lease, self._session = questions, lease, session_provider

    def ask(self, request_id, question, options):
        return self._questions.ask(self._session(), self._lease, request_id=request_id,
                                   question=question, options=options)

    def answer(self, request_id):
        return self._questions.answer_for(self._session(), self._lease, request_id)
