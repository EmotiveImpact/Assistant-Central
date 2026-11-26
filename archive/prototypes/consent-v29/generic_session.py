"""Durable inert task projection using existing exact-consent delivery storage.

The `meeting` alias is a temporary scope compatibility shim for existing gateway,
identity registry and encrypted outbox consumers: it exposes Task.id/participants,
never candidates or scheduling semantics. Legacy cancellation proof field `meeting`
names this task ID; a future owner-decision version should name scope explicitly.
All inherited owner entry points remain trusted-local-only, never agent tools.
"""
import json
from network import Denied, canonical, digest
from generic_protocol import Task, task_context_digest, validate_task_scope
from session import PersistentSession
from generic_capabilities import validate_result_against_request


class GenericTaskProjection:
    def __init__(self, task):
        if type(task) is not Task:
            raise Denied('Expected v2 task')
        self.task = task
        self.request = None
        self.result = None
        self.cancellation = None

    @property
    def state(self):
        if self.cancellation:
            return 'cancelled'
        if self.result is not None:
            return 'completed'
        return 'requested' if self.request is not None else 'created'

    def _validate(self, envelope):
        message = validate_task_scope(self.task, envelope)
        if self.cancellation or self.result is not None:
            raise Denied('Task is terminal')
        if message['type'] == 'request':
            if self.request is not None:
                raise Denied('Task already has a request')
        else:
            if self.request is None or message['reply_to'] != digest(self.request):
                raise Denied('Result is not linked to the exact committed request')
            validate_result_against_request(self.task.capability, self.request['payload'], message['payload'])
        return message

    def _apply_validated(self, envelope):
        # Revalidate even for trusted replay callers, preserving detached storage.
        message = self._validate(envelope)
        if message['type'] == 'request':
            self.request = message
        else:
            self.result = message


class GenericPersistentSession(PersistentSession):
    """Reuse atomic submit/cancel/view machinery, not the scheduling projection."""
    def __init__(self, delivery, agents, task):
        if type(task) is not Task:
            raise Denied('Expected explicit generic Task, no automatic migration')
        self.delivery, self.db = delivery, delivery.db
        self.task, self.conversation = task, task.conversation
        self.meeting = task  # Narrow compatibility scope alias, see module docstring.
        self.context = task_context_digest(task)
        self.agents = tuple(agents)
        self.registry = {a.identity: a for a in self.agents}
        if len(self.registry) != len(self.agents) or set(self.registry) != set(task.participants):
            raise Denied('Task actor registry must exactly match its two peers')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, context TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS transitions (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, delivery_id TEXT UNIQUE NOT NULL,
                body TEXT NOT NULL);
        ''')
        with delivery.transaction():
            row = self.db.execute('SELECT context FROM sessions WHERE id=?', (task.id,)).fetchone()
            if row and row[0] != self.context:
                raise Denied('Existing session has another immutable context')
            if row is None:
                if self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] >= delivery.max_records:
                    raise Denied('Task session limit reached')
                self.db.execute('INSERT INTO sessions VALUES (?,?)', (task.id, self.context))
            self._restore()

    def _restore(self):
        # Every projection consumer must prove the durable immutable scope,
        # including reads on an already-open session after local corruption.
        row = self.db.execute('SELECT context FROM sessions WHERE id=?',
                              (self.task.id,)).fetchone()
        if (self.context != task_context_digest(self.task)
                or row is None or row['context'] != self.context):
            raise Denied('Expected the exact immutable task context')
        projection = GenericTaskProjection(self.task)
        for row in self.db.execute('SELECT body FROM transitions WHERE session_id=? ORDER BY seq', (self.task.id,)):
            projection._apply_validated(json.loads(row[0]))
        row = self.db.execute('SELECT owner,cancelled_at FROM cancellations WHERE purpose=?', (self.context,)).fetchone()
        if row:
            projection.cancellation = dict(row)
        return projection
