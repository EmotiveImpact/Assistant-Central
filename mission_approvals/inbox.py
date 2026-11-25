"""Owner-local inbox of incoming mission offers and the owner's recorded decisions.

The inbox is trusted host state. Offers arrive from a peer (in the pilot, through a
released and verified packet) and are added by the trusted host, never by model
input. Decisions are recorded once, bound to the digest of the exact offer that was
shown, and are never changed afterwards.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Callable

from pilot.crypto import digest
from pilot.mission import bounded, terms

OFFER_DOMAIN = 'assistant-central/incoming-mission-offer/1'
CONSENT_LEVEL = 'host-elicited'
ID_PATTERN = re.compile(r'[A-Za-z0-9_-]{1,64}')
LABEL_LIMIT = 64
BRIEF_LIMIT = 4096


class InboxError(Exception):
    """A request the inbox refuses. The message is safe to show to the model."""


@dataclass(frozen=True)
class Decision:
    offer_id: str
    offer_digest: str
    decision: str  # 'accepted' or 'declined'
    decided_at: int
    consent_level: str = CONSENT_LEVEL

    def as_dict(self) -> dict:
        return {'offer_id': self.offer_id, 'offer_digest': self.offer_digest,
                'decision': self.decision, 'decided_at': self.decided_at,
                'consent_level': self.consent_level}


def _offer_id(value: object) -> str:
    if type(value) is not str or not ID_PATTERN.fullmatch(value):
        raise InboxError('Unknown mission offer')
    return value


def offer_record(offer_id: str, sender_label: str, brief: str, agreed: dict, expires: int) -> dict:
    """Validate and freeze one offer in a canonical shape."""
    if type(offer_id) is not str or not ID_PATTERN.fullmatch(offer_id):
        raise ValueError('Invalid offer identifier')
    bounded(sender_label, LABEL_LIMIT)
    bounded(brief, BRIEF_LIMIT)
    if type(expires) is not int or expires <= 0:
        raise ValueError('Invalid expiry')
    return {'domain': OFFER_DOMAIN, 'offer_id': offer_id, 'sender_label': sender_label,
            'brief': brief, 'terms': terms(agreed), 'expires': expires}


class OfferInbox:
    """In-memory, thread-safe inbox for one owner. Persistence is a later step."""

    def __init__(self, clock: Callable[[], int]):
        self._clock = clock
        self._lock = threading.Lock()
        self._offers: dict[str, dict] = {}
        self._decisions: dict[str, Decision] = {}

    # Trusted host operations (never exposed as tools)

    def add_offer(self, offer_id, sender_label, brief, agreed, expires) -> str:
        record = offer_record(offer_id, sender_label, brief, agreed, expires)
        with self._lock:
            existing = self._offers.get(offer_id)
            if existing is not None and existing != record:
                raise ValueError('A different offer already uses this identifier')
            self._offers[offer_id] = record
        return digest(record)

    def replace_offer_for_test(self, offer_id, record) -> None:
        """Simulates a host-side change between review and decision (tests only)."""
        with self._lock:
            self._offers[offer_id] = record

    # Operations reachable through tools

    def status(self, offer_id: str) -> str:
        with self._lock:
            return self._status_locked(_offer_id(offer_id))

    def _status_locked(self, offer_id: str) -> str:
        if offer_id not in self._offers:
            raise InboxError('Unknown mission offer')
        decision = self._decisions.get(offer_id)
        if decision is not None:
            return decision.decision
        if self._offers[offer_id]['expires'] <= self._clock():
            return 'expired'
        return 'awaiting_owner'

    def summaries(self) -> list[dict]:
        with self._lock:
            return [{'offer_id': oid, 'from': rec['sender_label'], 'goal': rec['terms']['goal'],
                     'status': self._status_locked(oid)} for oid, rec in sorted(self._offers.items())]

    def pending(self, offer_id: str) -> tuple[dict, str]:
        """Return the offer and its digest if it is still awaiting the owner."""
        with self._lock:
            oid = _offer_id(offer_id)
            state = self._status_locked(oid)
            if state != 'awaiting_owner':
                raise InboxError(f'Mission offer is {state.replace("_", " ")}; nothing to review')
            record = self._offers[oid]
            return record, digest(record)

    def decision(self, offer_id: str) -> Decision | None:
        with self._lock:
            return self._decisions.get(_offer_id(offer_id))

    def record(self, offer_id: str, shown_digest: str, accepted: bool) -> Decision:
        """Record one decision against the digest that was shown to the owner."""
        with self._lock:
            oid = _offer_id(offer_id)
            state = self._status_locked(oid)
            if state != 'awaiting_owner':
                raise InboxError(f'Mission offer is {state.replace("_", " ")}; no decision recorded')
            if digest(self._offers[oid]) != shown_digest:
                raise InboxError('The offer changed after it was shown; no decision recorded')
            result = Decision(oid, shown_digest, 'accepted' if accepted else 'declined', self._clock())
            self._decisions[oid] = result
            return result
