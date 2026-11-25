# SPDX-License-Identifier: AGPL-3.0-only
"""Owner-side client for the relay. Standard library HTTPS plus the shared protocol."""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .protocol import MailboxKey, RelayError, b64d, b64e, invite_link, new_send_token, parse_invite, token_hash


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _post_json(url, method, body, headers, timeout):
    request = urllib.request.Request(url, data=body if method != 'GET' else None, method=method,
                                     headers={'Content-Type': 'application/octet-stream', **headers})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status, data = response.status, response.read(1_048_576)
    try:
        value = json.loads(data)
    except ValueError:
        raise RelayError(502, 'bad_relay_response') from None
    if status >= 400:
        raise RelayError(status, value.get('error', 'error') if type(value) is dict else 'error')
    return value


class RelayClient:
    """One owner's mailbox on one relay."""

    def __init__(self, relay_url, key=None, *, timeout=20, transport=_post_json, clock=time.time):
        parts = urlsplit(relay_url)
        if parts.scheme != 'https' and parts.hostname not in ('127.0.0.1', 'localhost'):
            raise RelayError(400, 'relay_must_use_https')
        self.url, self.key = relay_url.rstrip('/'), key or MailboxKey()
        self._send, self.timeout, self.clock = transport, timeout, clock

    @property
    def mailbox(self):
        return self.key.mailbox

    def _signed(self, method, path, body=b''):
        headers = self.key.headers(method, path, body, now=self.clock())
        return self._send(self.url + path, method, body, headers, self.timeout)

    def register(self):
        body = json.dumps({'public_key': b64e(self.key.public_bytes)}).encode()
        return self._signed('POST', '/v1/mailboxes', body)

    def create_invite(self, identity_fingerprint, *, label='', seconds=7 * 86400, packets=20):
        """A link to give one person. They can send up to ``packets`` packets until it expires."""
        token = new_send_token()
        grant = self.grant(token, seconds=seconds, packets=packets)
        return {'link': invite_link(self.url, self.mailbox, token, identity_fingerprint, label),
                'grant_id': grant['grant_id'], 'expires': grant['expires']}

    def grant(self, token, *, seconds, packets):
        body = json.dumps({'token_hash': token_hash(token), 'expires': int(self.clock()) + seconds,
                           'packets': packets}).encode()
        return self._signed('POST', f'/v1/mailboxes/{self.mailbox}/grants', body)

    def revoke(self, grant_id):
        return self._signed('DELETE', f'/v1/mailboxes/{self.mailbox}/grants/{grant_id}')

    def fetch(self, after=0, limit=50):
        value = self._signed('GET', f'/v1/mailboxes/{self.mailbox}/packets?after={int(after)}&limit={int(limit)}')
        for packet in value['packets']:
            packet['body'] = b64d(packet['body'])
        return value

    def acknowledge(self, through_seq):
        return self._signed('DELETE', f'/v1/mailboxes/{self.mailbox}/packets?through={int(through_seq)}')


def send_with_invite(link_or_parsed, packet, *, timeout=20, transport=_post_json):
    """Deliver one opaque packet using the send token from an invite (or a later grant)."""
    invite = parse_invite(link_or_parsed) if isinstance(link_or_parsed, str) else link_or_parsed
    if type(packet) is not bytes or not packet:
        raise RelayError(400, 'bad_packet')
    url = f"{invite['relay_url']}/v1/mailboxes/{invite['mailbox']}/packets"
    return transport(url, 'POST', packet, {'Authorization': 'Bearer ' + invite['send_token']}, timeout)
