"""Mission cards: every owner's written constraints, kept in view until the end.

Anthropic's multi-user study ("Worse Together", November 2026) found that when separate
assistants work on a shared job, one person's requirements are often silently dropped.
A mission card makes that structurally hard:

1. Each owner writes their own constraints ("must" or "must not") while the card is a draft.
2. Every owner acknowledges the exact card (its digest). Any change clears all
   acknowledgements, so nobody is held to text they did not see.
3. A delivery must account for every constraint by id as met or not met. A delivery
   that skips any constraint is refused outright.
4. Each other owner accepts. An owner whose own constraint was reported as not met
   must waive it explicitly to accept, or return the delivery for changes.

Every step is written to the mission's append-only activity log.
"""
import threading
from typing import Callable

from pilot.crypto import digest

from .log import ActivityLog
from .text import CardError, bounded, clean, ident, need

CARD_DOMAIN = 'assistant-central/mission-card/1'
MAX_CONSTRAINTS = 24
KIND_WORDS = {'must': 'Must', 'must_not': 'Must not'}


class MissionCard:
    def __init__(self, mission_id: str, goal: str, owners: dict, clock: Callable[[], int]):
        self.mission_id = ident(mission_id, 'mission')
        self.goal = bounded(goal, 512, 'goal')
        need(type(owners) is dict and len(owners) >= 2, 'A mission card needs at least two owners')
        self.owners = {ident(o, 'owner'): bounded(label, 64, 'owner label') for o, label in owners.items()}
        self._clock = clock
        self._lock = threading.RLock()
        self._constraints: list[dict] = []
        self._acks: set[str] = set()
        self._delivery: dict | None = None
        self._accepted: dict[str, list[str]] = {}
        self.log = ActivityLog(self.mission_id, set(self.owners), clock)
        first = next(iter(self.owners))
        self.log.append(self.mission_id, first, 'card_created', {'goal': goal, 'owners': dict(self.owners)})

    # Reading

    def snapshot(self) -> dict:
        with self._lock:
            return {'domain': CARD_DOMAIN, 'mission_id': self.mission_id, 'goal': self.goal,
                    'owners': dict(self.owners), 'constraints': [dict(c) for c in self._constraints]}

    def digest(self) -> str:
        return digest(self.snapshot())

    def state(self) -> str:
        with self._lock:
            if self._delivery is None:
                return 'agreed' if self._acks == set(self.owners) else 'drafting'
            waiting = set(self.owners) - {self._delivery['by']} - set(self._accepted)
            return 'delivered' if waiting else 'accepted'

    def outstanding(self, owner: str) -> list[str]:
        """Plain-language list of what is waiting on this owner, so nothing is forgotten."""
        with self._lock:
            self._owner(owner)
            state = self.state()
            if state == 'drafting' and owner not in self._acks:
                return ['Review and acknowledge the mission card']
            if state == 'delivered' and owner != self._delivery['by'] and owner not in self._accepted:
                gaps = self._gaps_for(owner)
                if gaps:
                    return [f'Your constraint {cid} was reported as not met: waive it or return the delivery'
                            for cid in gaps]
                return ['Review the delivery and accept it or return it']
            return []

    def render(self) -> str:
        """Card text for an owner's assistant. Constraint text is shown as each owner wrote it."""
        with self._lock:
            lines = [f'Mission {self.mission_id}: {clean(self.goal)}',
                     f'Card fingerprint {self.digest()}', f'Status: {self.state()}', 'Constraints:']
            if not self._constraints:
                lines.append('  (none yet)')
            for owner, label in self.owners.items():
                mine = [c for c in self._constraints if c['owner'] == owner]
                if mine:
                    lines.append(f'  From {clean(label)}:')
                    lines += [f'    {c["id"]}. {KIND_WORDS[c["kind"]]}: {clean(c["text"])}' for c in mine]
            if self._delivery is not None:
                lines.append('Delivery report:')
                for c in self._constraints:
                    entry = self._delivery['accounts'][c['id']]
                    lines.append(f'  {c["id"]}: {entry["status"].replace("_", " ")}, {clean(entry["note"])}')
            return '\n'.join(lines)

    # Changing

    def add_constraint(self, owner: str, text: str, kind: str = 'must') -> str:
        with self._lock:
            self._owner(owner)
            need(self._delivery is None, 'Constraints cannot change after delivery')
            need(kind in KIND_WORDS, 'Constraint kind must be "must" or "must_not"')
            bounded(text, 280, 'constraint')
            need(len(self._constraints) < MAX_CONSTRAINTS, 'Too many constraints on one card')
            cid = f'c{len(self._constraints) + 1}'
            self._constraints.append({'id': cid, 'owner': owner, 'kind': kind, 'text': text})
            cleared = sorted(self._acks)
            self._acks.clear()
            self.log.append(self.mission_id, owner, 'constraint_added',
                            {'id': cid, 'kind': kind, 'text': text, 'cleared_acknowledgements': cleared})
            return cid

    def acknowledge(self, owner: str, card_digest: str) -> str:
        with self._lock:
            self._owner(owner)
            need(self._delivery is None, 'The card was already delivered')
            need(card_digest == self.digest(), 'The card changed since you reviewed it; review it again')
            self._acks.add(owner)
            self.log.append(self.mission_id, owner, 'acknowledged', {'card_digest': card_digest})
            return self.state()

    def deliver(self, owner: str, card_digest: str, summary: str, accounts: dict) -> str:
        with self._lock:
            self._owner(owner)
            need(self.state() == 'agreed', 'Every owner must acknowledge the card before delivery')
            need(card_digest == self.digest(), 'The card changed; review it again before delivering')
            bounded(summary, 2048, 'delivery summary')
            need(type(accounts) is dict, 'Account for every constraint by id')
            expected = {c['id'] for c in self._constraints}
            missing = sorted(expected - set(accounts), key=lambda c: int(c[1:]))
            need(not missing, 'Delivery skips constraints: ' + ', '.join(missing))
            need(set(accounts) == expected, 'Delivery names constraints that are not on the card')
            clean_accounts = {}
            for cid, entry in accounts.items():
                need(type(entry) is dict and set(entry) == {'status', 'note'}, f'Invalid account for {cid}')
                need(entry['status'] in ('met', 'not_met'), f'Status for {cid} must be "met" or "not_met"')
                bounded(entry['note'], 280, f'note for {cid}')
                clean_accounts[cid] = {'status': entry['status'], 'note': entry['note']}
            self._delivery = {'by': owner, 'card_digest': card_digest, 'summary': summary,
                              'accounts': clean_accounts}
            self.log.append(self.mission_id, owner, 'delivered', dict(self._delivery))
            return self.state()

    def accept(self, owner: str, card_digest: str, waive: tuple = ()) -> str:
        with self._lock:
            self._owner(owner)
            need(self.state() == 'delivered', 'There is no delivery waiting for acceptance')
            need(owner != self._delivery['by'], 'The owner who delivered cannot accept their own delivery')
            need(owner not in self._accepted, 'You already accepted this delivery')
            need(card_digest == self._delivery['card_digest'], 'This is not the delivered card')
            gaps = self._gaps_for(owner)
            waived = sorted(set(waive))
            need(set(waived) <= set(gaps), 'You can only waive your own constraints that were not met')
            unwaived = [cid for cid in gaps if cid not in waived]
            need(not unwaived, 'Not met and not waived: ' + ', '.join(unwaived))
            self._accepted[owner] = waived
            self.log.append(self.mission_id, owner, 'accepted', {'card_digest': card_digest, 'waived': waived})
            return self.state()

    def return_delivery(self, owner: str, reason: str) -> str:
        with self._lock:
            self._owner(owner)
            need(self.state() == 'delivered', 'There is no delivery to return')
            need(owner != self._delivery['by'], 'The owner who delivered cannot return their own delivery')
            bounded(reason, 512, 'reason')
            self._delivery = None
            self._accepted.clear()
            self.log.append(self.mission_id, owner, 'returned', {'reason': reason})
            return self.state()

    # Internal

    def _owner(self, owner):
        need(owner in self.owners, 'Unknown owner for this mission')

    def _gaps_for(self, owner):
        return [c['id'] for c in self._constraints if c['owner'] == owner
                and self._delivery['accounts'][c['id']]['status'] == 'not_met']


__all__ = ['MissionCard', 'CardError']
