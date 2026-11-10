"""One explicit HTTPS send of an exported packet. No retry or owner authority."""
import hashlib
import re
import socket
import ssl
import time
from urllib.parse import urlsplit

from .crypto import MAX_PACKET, digest
from .file_exchange import require
from .https_mailbox import ACK, MEDIA, ROUTE, parse_packet, read_private


class CarrierOutcomeUnknown(RuntimeError):
    """The peer may have stored bytes. Inspect before choosing another send."""


def send_file(source, target, recipient, *, ca_file=None):
    """Target must be owner-chosen; never extract a destination from packet content.

    HTTP acknowledgement is untrusted quarantine information only. Import a signed
    receipt through FileExchange to change delivery state. This API never does so.
    """
    require(type(target) is str and len(target) <= 512
            and all(33 <= ord(char) <= 126 for char in target))
    url = urlsplit(target)
    require(url.scheme == 'https' and url.path == ROUTE and not url.query and not url.fragment
            and url.username is None and url.password is None and url.hostname is not None)
    require(re.fullmatch(r'[A-Za-z0-9.-]+', url.hostname) is not None)
    require(url.port is None or 1 <= url.port <= 65535)
    require(url.netloc == url.hostname or url.netloc == f'{url.hostname}:{url.port}')
    require(type(recipient) is str and re.fullmatch('[0-9a-f]{64}', recipient) is not None)
    raw = read_private(source, MAX_PACKET)
    packet = parse_packet(raw)
    require(packet['header']['recipient'] == recipient)
    context = ssl.create_default_context(cafile=ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    request = (f'POST {ROUTE} HTTP/1.1\r\nHost: {url.netloc}\r\nContent-Type: {MEDIA}\r\n'
               f'Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n').encode('ascii') + raw
    acknowledged = False
    try:
        with socket.create_connection((url.hostname, url.port or 443), timeout=3) as tcp:
            with context.wrap_socket(tcp, server_hostname=url.hostname) as tls:
                tls.sendall(request)
                deadline = time.monotonic() + 3
                # Bounded fixed response; never parse or expose arbitrary peer JSON/headers.
                response = bytearray()
                while len(response) <= len(ACK):
                    remaining = deadline - time.monotonic()
                    require(remaining > 0)
                    tls.settimeout(remaining)
                    value = tls.recv(len(ACK) + 1 - len(response))
                    if not value:
                        break
                    response.extend(value)
                acknowledged = bytes(response) == ACK
    except Exception:
        raise CarrierOutcomeUnknown('Transfer outcome unknown; no automatic retry was made.') from None
    return {'transport_acknowledged': acknowledged, 'delivery': 'uncertain',
            'owner_acceptance': 'not_established', 'authorises_execution': False,
            'packet_digest': digest(packet), 'file_digest': hashlib.sha256(raw).hexdigest(),
            'recipient': recipient}
