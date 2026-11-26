# SPDX-License-Identifier: Apache-2.0
"""Parlu SDK: let any agent or app take part in Parlu.

- ``parlu.ParluAgent``: an assistant's connection to its owner's Central over MCP
  (inbox and wake-ups, proposing messages, shared drafts, asking the owner).
- ``parlu.web``: the same calls as plain JSON over HTTP, for any language.
- ``parlu.relay``: the relay client and protocol.

Nothing here grants authority. Anything that leaves an owner's copy still needs
that owner's approval or a standing permission they set.
"""
from .agent import INBOX_URI, ParluAgent, ParluError  # noqa: F401

__version__ = '0.1.0'
