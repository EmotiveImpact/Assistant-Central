# SPDX-License-Identifier: AGPL-3.0-only
"""Run the relay on this machine: ``python -m acrelay.local --db relay.sqlite``."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import MAX_BODY, Relay
from .store import SqlStore


def handler_for(relay):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'acrelay'
        sys_version = ''

        def _serve(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_BODY:
                status, headers, body = 413, {'Content-Type': 'application/json'}, b'{"error":"too_large"}'
            else:
                status, headers, body = relay.handle(self.command, self.path, dict(self.headers),
                                                     self.rfile.read(length))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_DELETE = _serve

        def log_message(self, *args):
            pass  # Never log paths, tokens or addresses.
    return Handler


def serve(relay, host='127.0.0.1', port=0):
    return ThreadingHTTPServer((host, port), handler_for(relay))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    server = serve(Relay(SqlStore.sqlite(args.db)), args.host, args.port)
    print(f'Relay listening on http://{args.host}:{server.server_port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
