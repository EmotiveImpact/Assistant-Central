"""Mission budgets as owner-signed spending mandates.

The shape follows the "intent mandate" idea from AP2 (Agent Payments Protocol, Apache-2.0)
and Mastercard's Verifiable Intent: before an agent may spend on someone's behalf, the
owner signs a bounded statement of what may be spent, on what, for whom and until when.
No payment rail is involved here. The ledger only decides whether a proposed charge fits
the mandate, so a real rail (Stripe, x402, MPP) can be added later behind the same check.
Nothing is copied from AP2; the mandate fields are our own, written to map onto it.
"""
import threading

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pilot.crypto import canonical

from . import receipts
from .text import CardError, bounded, ident, need

MANDATE_TYPE = 'https://github.com/EmotiveImpact/Assistant-Central/receipts/spending-mandate/v1'
CURRENCIES = frozenset({'GBP', 'USD', 'EUR'})
MAX_MINOR = 10_000_000  # 100,000.00 in major units; anything larger needs a different flow


def _amount(value, what):
    need(type(value) is int and 0 < value <= MAX_MINOR, f'{what} must be a whole number of minor units')
    return value


def mandate(owner: str, mission_id: str, card_digest: str, payee: str, currency: str,
            total_minor: int, per_charge_minor: int, expires: int, purpose: str) -> dict:
    ident(owner, 'owner')
    ident(mission_id, 'mission')
    ident(payee, 'payee')
    need(owner != payee, 'An owner cannot give themselves a spending mandate')
    need(type(card_digest) is str and len(card_digest) == 64, 'Invalid card fingerprint')
    need(currency in CURRENCIES, 'Unsupported currency')
    _amount(total_minor, 'Total')
    _amount(per_charge_minor, 'Per-charge limit')
    need(per_charge_minor <= total_minor, 'Per-charge limit cannot exceed the total')
    need(type(expires) is int and expires > 0, 'Invalid expiry')
    bounded(purpose, 280, 'purpose')
    return {'_type': receipts.STATEMENT_TYPE,
            'subject': [{'name': f'mission/{mission_id}/card', 'digest': {'sha256': card_digest}}],
            'predicateType': MANDATE_TYPE,
            'predicate': {'mission_id': mission_id, 'actor': owner, 'payee': payee, 'currency': currency,
                          'total_minor': total_minor, 'per_charge_minor': per_charge_minor,
                          'expires': expires, 'purpose': purpose}}


def sign_mandate(statement: dict, private_key: Ed25519PrivateKey) -> dict:
    """Run on the owner's own device."""
    return receipts.sign(statement, private_key)


class BudgetLedger:
    """Checks proposed charges against one verified mandate and keeps the running total."""

    def __init__(self, envelope: dict, owner_keys: dict, mission_id: str, card_digest: str):
        statement = receipts.verify(envelope, owner_keys, predicate_type=MANDATE_TYPE)
        terms = statement['predicate']
        need(terms['mission_id'] == mission_id, 'Mandate belongs to a different mission')
        need(statement['subject'][0]['digest']['sha256'] == card_digest,
             'Mandate was signed for a different version of the card')
        self.terms = dict(terms)
        self._lock = threading.Lock()
        self._charges: list[dict] = []

    def spent(self) -> int:
        with self._lock:
            return sum(c['amount_minor'] for c in self._charges)

    def remaining(self) -> int:
        return self.terms['total_minor'] - self.spent()

    def charge(self, payee: str, currency: str, amount_minor: int, description: str, now: int) -> dict:
        """Record a charge if, and only if, it fits the mandate. Nothing is paid here."""
        _amount(amount_minor, 'Amount')
        bounded(description, 280, 'description')
        need(type(now) is int, 'Invalid time')
        need(now < self.terms['expires'], 'The spending mandate has expired')
        need(payee == self.terms['payee'], 'This payee is not covered by the mandate')
        need(currency == self.terms['currency'], 'Wrong currency for this mandate')
        need(amount_minor <= self.terms['per_charge_minor'], 'Charge is above the per-charge limit')
        with self._lock:
            spent = sum(c['amount_minor'] for c in self._charges)
            need(spent + amount_minor <= self.terms['total_minor'], 'Charge would exceed the mission budget')
            entry = {'seq': len(self._charges), 'payee': payee, 'currency': currency,
                     'amount_minor': amount_minor, 'description': description, 'at': now}
            self._charges.append(entry)
            return {**entry, 'remaining_minor': self.terms['total_minor'] - spent - amount_minor}

    def charges(self) -> list[dict]:
        with self._lock:
            return [dict(c) for c in self._charges]


__all__ = ['mandate', 'sign_mandate', 'BudgetLedger', 'CardError', 'canonical']
