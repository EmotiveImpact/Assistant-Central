"""Durable local scheduling projection, serialized with consent and receipt.

No external side effects occur. Rebuild projections from committed transitions;
never manufacture owner approval during recovery. The local DB is trusted state.
"""
import json
import re
from network import Broker, Denied, canonical, context_digest, snapshot_envelope


class PersistentSession:
    def __init__(self, delivery, agents, meeting):
        self.delivery = delivery
        self.agents = tuple(agents)
        self.meeting = meeting
        self.context = context_digest(meeting)
        self.registry = {a.identity: a for a in self.agents}
        self.db = delivery.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, context TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS transitions (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, delivery_id TEXT UNIQUE NOT NULL,
                body TEXT NOT NULL);
        """)
        with delivery.transaction():
            self.db.execute("INSERT OR IGNORE INTO sessions VALUES (?,?)", (meeting.id, self.context))
            row = self.db.execute("SELECT context FROM sessions WHERE id=?", (meeting.id,)).fetchone()
            if row[0] != self.context:
                raise Denied("Existing session has a different meeting context")
            self._restore()

    def _restore(self):
        broker = Broker(self.agents, self.meeting)
        for row in self.db.execute("SELECT body FROM transitions WHERE session_id=? ORDER BY seq", (self.meeting.id,)):
            message = json.loads(row[0])
            broker._validate(message)
            broker._apply_validated(message)
            if len(broker._received) == len(self.agents):
                broker.propose(self.registry[self.meeting.coordinator])
        cancellation = self.db.execute("SELECT owner,cancelled_at FROM cancellations WHERE purpose=?", (self.context,)).fetchone()
        if cancellation:
            broker.cancellation = dict(cancellation)
        return broker

    def owner_cancel(self, owner):
        """Trusted local owner action, NOT an incoming agent tool or remote identity.

        Any registered participant can stop this local workflow. No cancellation
        message is sent, no disclosed information is recalled, and no external
        calendar event exists to cancel. A new meeting requires a new context.
        """
        with self.delivery.transaction():
            return self._cancel_in_transaction(owner)

    def _cancel_in_transaction(self, owner):
        if not self.db.in_transaction:
            raise Denied("Cancellation needs an active transaction")
        if self.registry.get(getattr(owner, "identity", None)) is not owner or owner is None:
            raise Denied("Only a registered local participant can cancel this meeting")
        existing = self.db.execute("SELECT owner,cancelled_at FROM cancellations WHERE purpose=?", (self.context,)).fetchone()
        if existing:
            return dict(existing)
        self.delivery._bound("cancellations")
        cancelled_at = self.delivery.clock()
        self.db.execute("INSERT INTO cancellations VALUES (?,?,?)", (self.context, owner.identity, cancelled_at))
        # Unused approvals are invalidated in the same transaction as the
        # terminal state. Already committed receipts stay available for retry.
        self.db.execute("DELETE FROM approvals WHERE purpose=? AND used=0", (self.context,))
        return {"owner": owner.identity, "cancelled_at": cancelled_at}

    def view(self):
        """Read-only local projection; no disclosure or authority is created."""
        with self.delivery.transaction():
            return self._restore()

    def submit(self, agent, envelope, approval):
        with self.delivery.transaction():
            return self._submit_in_transaction(agent, envelope, approval)

    def _submit_in_transaction(self, agent, envelope, approval):
        if not self.db.in_transaction:
            raise Denied("Submission needs an active transaction")
        message = snapshot_envelope(envelope)
        if type(approval) is not str or not re.fullmatch(r"[a-f0-9]{32}", approval):
            raise Denied("Invalid approval reference")
        if type(message) is not dict or type(message.get("sender")) is not str or self.registry.get(message["sender"]) is not agent:
            raise Denied("Local sender identity does not match this session")
        existing = self.db.execute("SELECT session_id,body FROM transitions WHERE delivery_id=?", (approval,)).fetchone()
        if existing:
            if existing["session_id"] != self.meeting.id or existing["body"] != canonical(message):
                raise Denied("Retry does not match committed transition")
            # A read-only retry returns the original receipt, even after consent
            # expiry/revocation. No new disclosure or processing occurs.
            return approval
        broker = self._restore()
        broker._validate(message)
        receipt = self.delivery._deliver_in_transaction(message, approval)
        self.db.execute("INSERT INTO transitions(session_id,delivery_id,body) VALUES (?,?,?)",
                        (self.meeting.id, receipt, canonical(message)))
        self.delivery.mark_processed(message["recipient"], receipt)
        return receipt
