# SPDX-License-Identifier: AGPL-3.0-only
"""Vercel Python function entry point. All routes are rewritten here by vercel.json.

Set DATABASE_URL to a Postgres connection string (for example Vercel Postgres
or Neon). psycopg is listed in requirements.txt for this deployment only.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler

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


class handler(BaseHTTPRequestHandler):
    def _serve(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            status, headers, body = 413, {'Content-Type': 'application/json'}, b'{"error":"too_large"}'
        else:
            status, headers, body = _get_relay().handle(self.command, self.path, dict(self.headers),
                                                        self.rfile.read(length))
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_DELETE = _serve

    def log_message(self, *args):
        pass
