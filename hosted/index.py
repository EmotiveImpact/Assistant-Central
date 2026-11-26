"""Hosted Parlu demo: the real web app, with a fictional workspace, on Vercel.

Each warm function instance seeds the same fictional workspace that
``python -m workspace_ui.demo`` makes, starts the unchanged owner server on a
private loopback port, and passes each request to it. Nothing about sign-in,
sessions, exact review or the security headers changes: requests are only
re-addressed so the loopback Host and Origin checks still hold.

This holds no real person's keys or records. The workspace lives in the
instance's temporary folder and starts fresh when Vercel recycles the
instance. A real person's own Parlu still runs on their own computer.
"""
import http.client
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from workspace_ui.demo import PASSWORD, seed_workspace  # noqa: E402
from workspace_ui.server import WorkspaceHTTPServer  # noqa: E402

FUNCTION_PATH = '/hosted/index.py'
# Vercel always serves HTTPS. Only a local check of this file sets http.
SCHEME = os.environ.get('PARLU_DEMO_SCHEME', 'https')
MAX_BODY = 64 * 1024
# Only what the browser needs is passed on. Hop-by-hop and Vercel headers stay here.
FORWARD = ('authorization', 'content-type', 'accept', 'accept-language')
RETURN_SKIP = ('connection', 'transfer-encoding', 'content-length')
HERE = os.path.dirname(os.path.abspath(__file__))
# Demo-only files served by this wrapper. The app's own files come from its server.
DEMO_FILES = {
    '/hosted-demo.mjs': ('demo.mjs', 'text/javascript; charset=utf-8'),
    '/hosted-demo.css': ('demo.css', 'text/css; charset=utf-8'),
}
PAGE_EDITS = (
    # Load the demo entrance with the page (same-origin files, so the CSP is unchanged).
    (b'<link rel="stylesheet" href="/style.css">',
     b'<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/hosted-demo.css">'
     b'<script type="module" src="/hosted-demo.mjs"></script>'),
    # A one-tap way in, at the very top, before any marketing words.
    (b'<div class="login-layout">',
     b'<div class="demo-entry"><div><strong>Try Parlu now</strong><p>No sign-up and no password. '
     b'You will be Blair, with three made-up people and their assistants. Anything you do resets '
     b'after a while.</p></div><button type="button" data-demo-enter>Open the demo</button></div>'
     b'<div class="login-layout">'),
    (b'<h2 id="login-heading">Welcome to your workspace</h2><p>Your assistant. Your decisions.</p>',
     b'<h2 id="login-heading">Welcome to the Parlu demo</h2><p>Tap the button to go straight in.</p>'
     b'<button class="demo-card-button" type="button" data-demo-enter>Open the demo</button>'
     b'<span class="demo-or">or type the demo password: ' + PASSWORD.encode() + b'</span>'),
    (b'<strong>Synthetic workspace</strong><span>Fictional content. Live provider calls disabled.</span>',
     b'<strong>Public demo with made-up people</strong><span>Everyone shares it, and it starts fresh '
     b'after a quiet spell. Your own Parlu runs on your computer.</span>'),
)

_lock = threading.Lock()
_server = None


def _owner_server():
    global _server
    with _lock:
        if _server is None:
            directory = tempfile.mkdtemp(prefix='parlu-demo-')
            owner = seed_workspace(directory)
            server = WorkspaceHTTPServer(owner, 0, synthetic_workflow=True,
                                         relay_url=os.environ.get('PARLU_RELAY_URL') or None)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            _server = server
        return _server


def original_target(path):
    """Rebuild the browser's own path from Vercel's routed address."""
    base, _, query = path.partition('?')
    items = [item for item in query.split('&') if item] if query else []
    routed = [item for item in items if item.startswith('parlu_path=')]
    rest = [item for item in items if not item.startswith('parlu_path=')]
    if base == FUNCTION_PATH:
        if len(routed) != 1:
            return None
        base = '/' + unquote(routed[0][len('parlu_path='):])
        if '?' in base or '#' in base:
            return None
    return base + ('?' + '&'.join(rest) if rest else '')


class handler(BaseHTTPRequestHandler):
    def _fail(self, status, text):
        body = ('{"error":"' + text + '"}').encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _serve(self):
        target = original_target(self.path)
        if target in DEMO_FILES and self.command == 'GET':
            name, kind = DEMO_FILES[target]
            with open(os.path.join(HERE, name), 'rb') as stream:
                data = stream.read()
            self.send_response(200)
            for key, value in (('Content-Type', kind), ('Content-Length', str(len(data))),
                               ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')):
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)
            return
        if target is None or target.startswith('/peer/'):
            # Loopback peer mailboxes belong to a person's own computer, not the demo.
            return self._fail(404, 'not_found')
        length = int(self.headers.get('Content-Length') or 0)
        if length < 0 or length > MAX_BODY:
            return self._fail(413, 'too_large')
        body = self.rfile.read(length) if length else None
        public_host = self.headers.get('Host', '')
        origins = self.headers.get_all('Origin', [])
        if len(origins) > 1 or (origins and origins[0] != SCHEME + '://' + public_host):
            return self._fail(400, 'Invalid request origin')
        server = _owner_server()
        headers = {name: value for name, value in self.headers.items() if name.lower() in FORWARD}
        headers['Host'] = server.host_header
        if origins:
            headers['Origin'] = server.origin
        if body is not None:
            headers['Content-Length'] = str(len(body))
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=25)
        try:
            connection.putrequest(self.command, target, skip_host=True, skip_accept_encoding=True)
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.endheaders(body)
            response = connection.getresponse()
            payload = response.read()
            status, reply_headers = response.status, response.getheaders()
        finally:
            connection.close()
        if target in ('/', '/index.html') and status == 200:
            for before, after in PAGE_EDITS:
                payload = payload.replace(before, after, 1)
        self.send_response(status)
        for name, value in reply_headers:
            if name.lower() not in RETURN_SKIP:
                self.send_header(name, value)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _serve

    def do_OPTIONS(self):
        self._fail(403, 'Cross-origin access is disabled.')

    def log_message(self, *args):
        pass
