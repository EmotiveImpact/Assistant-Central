"""Carry exported packets through the hosted relay. No retry or owner authority.

The relay is only a mailbox. A sender posts the exact exported packet bytes
with the send token from the recipient's invite. The recipient fetches them
into the same private quarantine the HTTPS mailbox uses, and imports them with
the authenticated file-exchange step as usual. Nothing here imports, accepts
or runs anything, and nothing a relay says is treated as delivery.
"""
import hashlib

from relay.acrelay.client import send_with_invite
from relay.acrelay.protocol import RelayError, parse_invite

from .crypto import MAX_PACKET, digest
from .file_exchange import require
from .https_mailbox import parse_packet, read_private

MAX_FETCH_ROUNDS = 20


class RelayOutcomeUnknown(RuntimeError):
    """The relay may have stored the packet. Inspect before choosing another send."""


def send_file(source, invite, recipient, *, transport=None):
    """Send one exported packet to the mailbox named by an owner-chosen invite.

    ``recipient`` is the identity fingerprint the owner compared out of band. The
    invite must name the same fingerprint and the packet must be addressed to it.
    """
    require(type(recipient) is str and len(recipient) == 64)
    try:
        target = parse_invite(invite)
    except RelayError:
        require(False)
    require(target['identity_fingerprint'] == recipient)
    raw = read_private(source, MAX_PACKET)
    packet = parse_packet(raw)
    require(packet['header']['recipient'] == recipient)
    try:
        kwargs = {} if transport is None else {'transport': transport}
        stored = send_with_invite(target, raw, **kwargs)
    except RelayError as error:
        if error.status in (400, 401, 404, 413, 507):
            # Refused before storage: unknown, used-up or revoked invite, or a full mailbox.
            return {'relay_stored': False, 'refused': error.code, 'delivery': 'not_sent',
                    'owner_acceptance': 'not_established', 'authorises_execution': False}
        raise RelayOutcomeUnknown('Relay outcome unknown; no automatic retry was made.') from None
    except Exception:
        raise RelayOutcomeUnknown('Relay outcome unknown; no automatic retry was made.') from None
    return {'relay_stored': type(stored) is dict and 'packet_id' in stored, 'delivery': 'uncertain',
            'owner_acceptance': 'not_established', 'authorises_execution': False,
            'packet_digest': digest(packet), 'file_digest': hashlib.sha256(raw).hexdigest(),
            'recipient': recipient}


def fetch_into(client, quarantine, *, limit=50):
    """Move waiting packets from the owner's relay mailbox into quarantine.

    A packet is acknowledged (deleted from the relay) only after it is durably
    stored, or after it is found to be malformed or addressed to someone else,
    which can never become valid. If quarantine is full, fetching stops and the
    remaining packets stay on the relay for next time.
    """
    stored, rejected, after = [], 0, 0
    for _ in range(MAX_FETCH_ROUNDS):
        page = client.fetch(after=after, limit=limit)
        done_through = None
        for item in page['packets']:
            try:
                parse_packet(item['body'])
                ok = True
            except Exception:
                ok = False
            if ok:
                try:
                    name = quarantine.store(item['body'])
                except Exception:
                    # Wrong recipient is permanent; capacity is not. Tell them apart.
                    if parse_packet(item['body'])['header']['recipient'] != quarantine.recipient:
                        rejected += 1
                        done_through = item['seq']
                        continue
                    if done_through is not None:
                        client.acknowledge(done_through)
                    return {'stored': stored, 'rejected': rejected, 'more': True, 'quarantine_full': True}
                stored.append(name)
            else:
                rejected += 1
            done_through = item['seq']
        if done_through is not None:
            client.acknowledge(done_through)
            after = done_through
        if not page['more']:
            return {'stored': stored, 'rejected': rejected, 'more': False, 'quarantine_full': False}
    return {'stored': stored, 'rejected': rejected, 'more': True, 'quarantine_full': False}
