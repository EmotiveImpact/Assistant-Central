# SPDX-License-Identifier: AGPL-3.0-only
"""Vercel Python function entry point. All routes are rewritten here by vercel.json.

Set DATABASE_URL to a Postgres connection string (for example Vercel Postgres
or Neon). psycopg is listed in requirements.txt for this deployment only.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from acrelay.service import MAX_BODY, Relay  # noqa: E402
from acrelay.store import SqlStore  # noqa: E402

_relay = None


def _get_relay():
    global _relay
    if _relay is None:
        import psycopg
        url = os.environ['DATABASE_URL']
        _relay = Relay(SqlStore(lambda: psycopg.connect(url), paramstyle='format'),
                       source_url=os.environ.get('RELAY_SOURCE_URL', 'https://github.com/EmotiveImpact/Assistant-Central/tree/main/relay'))
    return _relay


def original_target(path):
    """Rebuild the address the client signed.

    Vercel hands a rewritten function ``/api/index?...``: the original query is
    kept in order, and vercel.json adds the original path as ``relay_path``.
    """
    base, _, query = path.partition('?')
    if base != '/api/index':
        return path  # Not rewritten (local runs or direct calls).
    items = query.split('&') if query else []
    paths = [item for item in items if item.startswith('relay_path=')]
    if len(paths) != 1:
        return None
    rest = [item for item in items if not item.startswith('relay_path=')]
    original = '/' + unquote(paths[0][len('relay_path='):])
    if '?' in original or '#' in original:
        return None
    return original + ('?' + '&'.join(rest) if rest else '')


class handler(BaseHTTPRequestHandler):
    def _serve(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            status, headers, body = 413, {'Content-Type': 'application/json'}, b'{"error":"too_large"}'
        else:
            target = original_target(self.path)
            if target is None:
                status, headers, body = 400, {'Content-Type': 'application/json'}, b'{"error":"bad_request"}'
            else:
                status, headers, body = _get_relay().handle(self.command, target, dict(self.headers),
                                                            self.rfile.read(length))
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_DELETE = _serve

    def log_message(self, *args):
        pass
