"""Invite links and relay delivery for one owner, on the existing owner worker.

The host chooses the relay when it starts Parlu. Every route here needs the
owner's own session. Nothing is fetched or sent in the background: the browser
asks for a sync while the owner is signed in, and a released packet is posted
once, when the owner asks.
"""
import re

from pilot.relay_link import LinkDenied, RelayLink
from pilot.server import RequestDenied, exact

INVITE = re.compile(r'/api/invites/([0-9a-f]{32})(?:/(revoke|joiner))?')


class RelayService:
    """Wrap, do not replace, the owner service. Unknown routes pass straight through."""

    def __init__(self, primary, relay_url, *, timeout=6):
        self.primary = primary
        self.link = RelayLink(primary.auth.directory, primary.auth, primary.runtime, relay_url, timeout=timeout)

    def __getattr__(self, name):
        # Peer ingress, the runtime and the authenticator stay the wrapped owner's own.
        return getattr(self.primary, name)

    def close(self):
        try:
            self.link.close()
        finally:
            self.primary.close()

    def call(self, method, path, token, body):
        try:
            return self._call(method, path, token, body)
        except LinkDenied:
            raise RequestDenied('Invite or relay request denied') from None

    def _call(self, method, path, token, body):
        link = self.link
        if path == '/api/state' and method == 'GET':
            result = self.primary.call(method, path, token, body)
            result['relay'] = link.snapshot(token)
            return result
        if path == '/api/invites' and method == 'POST':
            exact(body, (), ('label', 'hours'))
            return link.create_invite(token, body.get('label', ''), hours=body.get('hours', 24))
        if path == '/api/invites/open' and method == 'POST':
            exact(body, ('link',))
            return link.open_invite(token, body['link'])
        if path == '/api/invites/accept' and method == 'POST':
            exact(body, ('link', 'review_digest'))
            return link.accept_invite(token, body['link'], body['review_digest'])
        if path == '/api/relay/sync' and method == 'POST':
            exact(body, ('send',))
            return link.sync(token, send=body['send'])
        invite = INVITE.fullmatch(path)
        if invite:
            invite_id, action = invite.groups()
            if action is None and method == 'GET':
                return link.show_invite(token, invite_id)
            if action == 'revoke' and method == 'POST':
                exact(body, ())
                return link.revoke_invite(token, invite_id)
            if action == 'joiner' and method == 'POST':
                exact(body, ('decision', 'review_digest'))
                return link.decide_joiner(token, invite_id, body['review_digest'], body['decision'])
            raise RequestDenied('Unknown invite operation')
        return self.primary.call(method, path, token, body)
