# SPDX-License-Identifier: Apache-2.0
"""Talk to a Parlu relay: make a mailbox, invite someone, send, fetch.

The relay only stores opaque encrypted packets. Mailbox calls are signed with
a mailbox key that is separate from your identity key.
"""
from .client import RelayClient, send_with_invite  # noqa: F401
from .protocol import MailboxKey, RelayError, invite_link, parse_invite  # noqa: F401

DEFAULT_RELAY = 'https://parlu-relay.vercel.app'
