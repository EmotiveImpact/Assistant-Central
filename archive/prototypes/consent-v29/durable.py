"""Local SQLite consent and delivery sandbox; no network or identity credentials.

Owner methods belong to a trusted UI boundary, never the incoming agent surface.
This stores synthetic message bodies in plaintext. Do not use real personal data.
"""
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from network import Denied, canonical, digest, snapshot_envelope
from vendor.a4a.sanitize import wrap_untrusted


class LocalDelivery:
    def __init__(self, path, clock=time.time, max_records=10000):
        if type(max_records) is not int or not 1 <= max_records <= 100000:
            raise Denied("Invalid storage record limit")
        self.max_records = max_records
        self.clock = clock
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS contacts (
                owner TEXT, peer TEXT, purpose TEXT, expires REAL,
                PRIMARY KEY(owner, peer, purpose));
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY, sender TEXT, recipient TEXT, purpose TEXT,
                digest TEXT, expires REAL, used INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY, sender TEXT, recipient TEXT, purpose TEXT,
                body TEXT, state TEXT CHECK(state IN ('received', 'processed')));
            CREATE TABLE IF NOT EXISTS cancellations (
                purpose TEXT PRIMARY KEY, owner TEXT NOT NULL, cancelled_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS contact_versions (
                owner TEXT, peer TEXT, purpose TEXT, version INTEGER NOT NULL,
                PRIMARY KEY(owner, peer, purpose));
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _bound(self, table):
        if table not in ("contacts", "approvals", "deliveries", "cancellations", "contact_versions"):
            raise Denied("Unknown table")
        if self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] >= self.max_records:
            raise Denied("Local record limit reached; no implicit deletion")

    def owner_pair(self, owner, peer, purpose, ttl=3600):
        """One owner approves a contact for one exact meeting context, not all data."""
        with self.transaction():
            self._owner_pair_in_transaction(owner, peer, purpose, ttl)

    def _owner_pair_in_transaction(self, owner, peer, purpose, ttl=3600):
        if not self.db.in_transaction:
            raise Denied("Pairing needs an active transaction")
        if any(type(v) is not str or not re.fullmatch(r"[a-z0-9_-]{1,64}", v) for v in (owner, peer)):
            raise Denied("Invalid local identity")
        if type(purpose) is not str or not re.fullmatch(r"[0-9a-f]{64}", purpose):
            raise Denied("Purpose must be the reviewed meeting-context digest")
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise Denied("Pairing must expire within one day")
        self._require_active(purpose)
        if self.db.execute("SELECT 1 FROM contacts WHERE owner=? AND peer=? AND purpose=?", (owner, peer, purpose)).fetchone() is None:
            self._bound("contacts")
        self._bump_contact_version(owner, peer, purpose)
        self.db.execute("INSERT OR REPLACE INTO contacts VALUES (?,?,?,?)", (owner, peer, purpose, self.clock() + ttl))

    def owner_revoke(self, owner, peer, purpose):
        with self.transaction():
            self._owner_revoke_in_transaction(owner, peer, purpose)

    def _owner_revoke_in_transaction(self, owner, peer, purpose):
        if not self.db.in_transaction:
            raise Denied("Revocation needs an active transaction")
        self._bump_contact_version(owner, peer, purpose)
        self.db.execute("DELETE FROM contacts WHERE owner=? AND peer=? AND purpose=?", (owner, peer, purpose))
        # Re-pairing later must not resurrect old message approvals.
        self.db.execute("DELETE FROM approvals WHERE purpose=? AND used=0 AND ((sender=? AND recipient=?) OR (sender=? AND recipient=?))",
                        (purpose, owner, peer, peer, owner))

    def contact_version(self, owner, peer, purpose):
        row = self.db.execute("SELECT version FROM contact_versions WHERE owner=? AND peer=? AND purpose=?",
                              (owner, peer, purpose)).fetchone()
        return row[0] if row else 0

    def _bump_contact_version(self, owner, peer, purpose):
        version = self.contact_version(owner, peer, purpose)
        if version == 0:
            self._bound("contact_versions")
        if version >= 2**63 - 1:
            raise Denied("Contact version exhausted")
        self.db.execute("INSERT OR REPLACE INTO contact_versions VALUES (?,?,?,?)", (owner, peer, purpose, version + 1))

    def _paired(self, sender, recipient, purpose):
        self._require_active(purpose)
        for a, b in ((sender, recipient), (recipient, sender)):
            row = self.db.execute("SELECT expires FROM contacts WHERE owner=? AND peer=? AND purpose=?", (a, b, purpose)).fetchone()
            if row is None or row[0] <= self.clock():
                raise Denied("Both owners must approve this contact and exact purpose")

    def _require_active(self, purpose):
        if self.db.execute("SELECT 1 FROM cancellations WHERE purpose=?", (purpose,)).fetchone():
            raise Denied("Meeting cancelled; no new pairing, approval or delivery is allowed")

    def owner_approve(self, envelope, ttl=300):
        envelope = snapshot_envelope(envelope)
        if type(ttl) is not int or not 1 <= ttl <= 600:
            raise Denied("Message approval must expire within ten minutes")
        sender, recipient, purpose = envelope["sender"], envelope["recipient"], envelope["context"]
        approval = secrets.token_hex(16)
        with self.transaction():
            self._paired(sender, recipient, purpose)
            self._bound("approvals")
            self.db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,0)",
                            (approval, sender, recipient, purpose, digest(envelope), self.clock() + ttl))
        return approval

    def owner_revoke_approval(self, approval):
        self.db.execute("DELETE FROM approvals WHERE id=?", (approval,))

    def deliver(self, envelope, approval):
        """Atomic local receipt + single-use consent; duplicate retries return same ID.

        Caller must validate its closed application schema before this method.
        It does not claim a receiver processed anything or create an external ACK.
        """
        envelope = snapshot_envelope(envelope)
        body = canonical(envelope)
        if len(body.encode()) > 8192:
            raise Denied("Message too large")
        with self.transaction():
            return self._deliver_in_transaction(envelope, approval)

    def _deliver_in_transaction(self, envelope, approval):
        envelope = snapshot_envelope(envelope)
        if type(approval) is not str or not re.fullmatch(r"[a-f0-9]{32}", approval):
            raise Denied("Invalid approval reference")
        if not self.db.in_transaction:
            raise Denied("Delivery needs an active transaction")
        body = canonical(envelope)
        if len(body.encode()) > 8192:
            raise Denied("Message too large")
        grant = self.db.execute("SELECT * FROM approvals WHERE id=?", (approval,)).fetchone()
        if grant is None or digest(envelope) != grant["digest"]:
            raise Denied("No exact owner approval")
        self._paired(grant["sender"], grant["recipient"], grant["purpose"])
        if grant["used"]:
            result = self.db.execute("SELECT id FROM deliveries WHERE id=?", (approval,)).fetchone()
            if result is None:
                raise Denied("Approval consumed without a receipt")
        else:
            if grant["expires"] <= self.clock():
                raise Denied("Approval expired")
            self._bound("deliveries")
            self.db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,'received')",
                            (approval, grant["sender"], grant["recipient"], grant["purpose"], body))
            self.db.execute("UPDATE approvals SET used=1 WHERE id=?", (approval,))
        return approval

    def owner_inbox(self, owner):
        """Local human view; owner identity must be authenticated by a future UI."""
        return [dict(row) for row in self.db.execute("SELECT id,body,state FROM deliveries WHERE recipient=? ORDER BY rowid", (owner,))]

    def mark_processed(self, owner, delivery_id):
        cursor = self.db.execute("UPDATE deliveries SET state='processed' WHERE id=? AND recipient=?", (delivery_id, owner))
        if cursor.rowcount != 1:
            raise Denied("No delivery for this recipient")


def quarantine_preview(text, claimed_sender):
    """Upstream A4A framing is display hygiene, NOT authorization or an injection proof."""
    if type(text) is not str or len(text.encode()) > 4096:
        raise Denied("Contact request exceeds quarantine limit")
    if type(claimed_sender) is not str or len(claimed_sender) > 128:
        raise Denied("Invalid contact label")
    return wrap_untrusted(text, source=claimed_sender, origin_label="unverified_contact", trust_level=0)
