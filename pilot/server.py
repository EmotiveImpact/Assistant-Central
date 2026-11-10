"""Loopback pilot UI and bounded opaque peer mailbox.

All authenticated runtime work executes in one owner thread. Peer mailbox HTTP
requests never receive a session and never become acceptance decisions. The
owner explicitly synchronises queued messages after signing in. No background
unlock, internet listener, provider activation or external callback is exposed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import getpass
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from urllib.parse import urlsplit

from .auth import LocalOwnerAuth, AuthError
from .crypto import packet_header
from .runtime import PilotRuntime

MAX_BODY = 33792
MAX_PACKET = 32768
MAX_QUARANTINE = 64
MAX_QUARANTINE_BYTES = 4 * 1024 * 1024
MAX_SYNC_BATCH = 8
WEB = Path(__file__).resolve().parent / "web"
PEER_HEADER = "packet-v1"


class RequestDenied(ValueError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RequestDenied("Duplicate JSON member")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(RequestDenied("Invalid number")))
        if type(value) is not dict:
            raise RequestDenied("Expected object")
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise RequestDenied("Invalid JSON object") from None


def exact(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise RequestDenied("Unexpected request fields")


def peer_endpoint(value):
    if type(value) is not str or len(value) > 80:
        raise RequestDenied("Expected loopback peer endpoint")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise RequestDenied("Expected loopback peer endpoint") from None
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username is not None or parsed.password is not None
            or not port or not 1024 <= port <= 65535 or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or parsed.netloc != "127.0.0.1:" + str(port)):
        raise RequestDenied("Only exact loopback peer endpoints are supported")
    return "http://127.0.0.1:" + str(port)


class Mailbox:
    """Quarantine only: these rows cannot establish authenticated peer authority."""

    def __init__(self, directory):
        self.path = Path(directory) / "http.sqlite"
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600)
        except FileExistsError:
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.geteuid() or info.st_nlink != 1):
                raise RequestDenied("Private mailbox unavailable")
        else:
            os.close(descriptor)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS quarantine(
                    digest TEXT PRIMARY KEY, packet BLOB NOT NULL, received REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS endpoints(
                    peer_id TEXT PRIMARY KEY, endpoint TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS http_outbox(
                    digest TEXT PRIMARY KEY, peer_id TEXT NOT NULL, packet BLOB NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def store(self, packet):
        if type(packet) is not dict:
            raise RequestDenied("Expected opaque packet object")
        raw = encode(packet)
        if not raw or len(raw) > MAX_PACKET:
            raise RequestDenied("Packet exceeds bound")
        key = hashlib.sha256(raw).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute("SELECT 1 FROM quarantine WHERE digest=?", (key,)).fetchone()
            if duplicate:
                return {"stored": True, "duplicate": True, "authenticated_receipt": False}
            count, size = db.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(packet)),0) FROM quarantine").fetchone()
            if count >= MAX_QUARANTINE or size + len(raw) > MAX_QUARANTINE_BYTES:
                raise RequestDenied("Quarantine is full")
            db.execute("INSERT INTO quarantine VALUES(?,?,?)", (key, raw, time.time()))
        return {"stored": True, "duplicate": False, "authenticated_receipt": False}

    def pending(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM quarantine ORDER BY received,digest")]

    def discard(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM quarantine WHERE digest=?", (key,))

    def set_endpoint(self, peer_id, endpoint):
        endpoint = peer_endpoint(endpoint)
        with self.connect() as db:
            old = db.execute("SELECT endpoint FROM endpoints WHERE peer_id=?", (peer_id,)).fetchone()
            if old and old[0] != endpoint:
                raise RequestDenied("Peer endpoint replacement requires a new reviewed configuration")
            db.execute("INSERT OR IGNORE INTO endpoints VALUES(?,?)", (peer_id, endpoint))

    def endpoints(self):
        with self.connect() as db:
            return {row["peer_id"]: row["endpoint"] for row in db.execute("SELECT * FROM endpoints")}

    def queue_receipt(self, peer_id, packet):
        raw = encode(packet)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            key = hashlib.sha256(raw).hexdigest()
            if not db.execute("SELECT 1 FROM http_outbox WHERE digest=?", (key,)).fetchone():
                if db.execute("SELECT COUNT(*) FROM http_outbox").fetchone()[0] >= 128:
                    raise RequestDenied("Receipt outbox full; inspect retained history")
                db.execute("INSERT INTO http_outbox VALUES(?,?,?)", (key, peer_id, raw))

    def receipts(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM http_outbox ORDER BY digest")]

    def receipt_sent(self, digest):
        with self.connect() as db:
            db.execute("DELETE FROM http_outbox WHERE digest=?", (digest,))


def post_packet(endpoint, packet):
    """An HTTP acknowledgement is only mailbox storage, never peer acceptance."""
    endpoint = peer_endpoint(endpoint)
    port = urlsplit(endpoint).port
    raw = encode({"packet": packet})
    if len(raw) > MAX_BODY:
        raise RequestDenied("Outbound packet exceeds bound")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("POST", "/peer/inbox", body=raw,
                           headers={"Content-Type": "application/json", "X-Assistant-Central-Peer": PEER_HEADER})
        response = connection.getresponse()
        payload = response.read(4097)
        if response.status != 200 or len(payload) > 4096:
            raise RequestDenied("Peer mailbox did not acknowledge storage")
        result = strict_json(payload)
        if result.get("stored") is not True or result.get("authenticated_receipt") is not False:
            raise RequestDenied("Unexpected mailbox response")
        return result
    finally:
        connection.close()


class OwnerService:
    """Construct and use this object only on its dedicated owner worker thread."""

    def __init__(self, directory):
        self.auth = LocalOwnerAuth(directory)
        self.runtime = PilotRuntime(directory, self.auth)
        self.mailbox = Mailbox(directory)

    def close(self):
        if hasattr(self.runtime, "close"):
            self.runtime.close()
        self.auth.close()

    def state(self, token):
        state = self.runtime.state(token)
        state["endpoints"] = self.mailbox.endpoints()
        state["provider"] = {"name": "OpenAI Responses", "enabled": False, "live_enabled": False, "live_verified": False,
                             "status": "Adapter available for explicit synthetic testing; live calls disabled"}
        state["pilot"] = {"loopback_only": True, "real_person_verification": False,
                          "background_unlock": False, "quarantined_packets": len(self.mailbox.pending())}
        return state

    def exchange(self, token):
        self.auth.authenticate(token)
        accepted, rejected, sent, unavailable = 0, 0, 0, 0
        for stored in self.mailbox.pending()[:MAX_SYNC_BATCH]:
            try:
                result = self.runtime.receive(token, strict_json(stored["packet"]))
            except AuthError:
                raise
            except (ValueError, PermissionError):
                # An unauthenticated quarantined packet is not a decision. A bad
                # packet cannot evict another queued packet or reset peer history.
                self.mailbox.discard(stored["digest"])
                rejected += 1
                continue
            receipt = result.get("receipt")
            if receipt is not None:
                self.mailbox.queue_receipt(packet_header(strict_json(stored["packet"]))["sender"], receipt)
            self.mailbox.discard(stored["digest"])
            accepted += 1
        endpoints = self.mailbox.endpoints()
        for item in self.runtime.state(token).get("outbox", [])[:MAX_SYNC_BATCH]:
            if item.get("state") in ("acknowledged", "received", "cancelled"):
                continue
            peer = item.get("peer_id", item.get("peer", item.get("recipient")))
            if peer not in endpoints:
                unavailable += 1
                continue
            try:
                packet = self.runtime.prepare_delivery(token, item["message_id"])
                post_packet(endpoints[peer], packet)
                sent += 1
            except (OSError, TimeoutError, http.client.HTTPException, RequestDenied):
                unavailable += 1
        for item in self.mailbox.receipts()[:MAX_SYNC_BATCH]:
            if item["peer_id"] not in endpoints:
                unavailable += 1
                continue
            try:
                post_packet(endpoints[item["peer_id"]], strict_json(item["packet"]))
            except (OSError, TimeoutError, http.client.HTTPException, RequestDenied):
                unavailable += 1
            else:
                self.mailbox.receipt_sent(item["digest"])
                sent += 1
        return {"received": accepted, "rejected_packets": rejected, "stored_at_peer": sent,
                "unavailable": unavailable, "external_provider_calls": 0,
                "note": "Peer mailbox storage is not recipient acceptance or task execution."}

    def call(self, method, path, token, body):
        if path == "/api/session" and method == "POST":
            exact(body, ("password",))
            token = self.auth.login(body["password"])
            return {"token": token, "identity": self.auth.public_identity()}
        self.auth.authenticate(token)
        if path == "/api/session" and method == "DELETE":
            exact(body, ())
            self.auth.logout(token)
            return {"signed_out": True}
        if path == "/api/state" and method == "GET":
            return self.state(token)
        if path == "/api/exchange" and method == "POST":
            exact(body, ())
            return self.exchange(token)
        if path == "/api/peers" and method == "POST":
            exact(body, ("public_identity", "expected_fingerprint", "endpoint"))
            endpoint = peer_endpoint(body["endpoint"])
            peer = self.runtime.enrol_peer(token, body["public_identity"], body["expected_fingerprint"])
            peer_id = peer.get("peer_id", body["expected_fingerprint"])
            self.mailbox.set_endpoint(peer_id, endpoint)
            return peer
        if path == "/api/proposals" and method == "POST":
            exact(body, ("peer_id", "kind", "title", "text", "context", "task_id", "expires"),
                  ("parent_id", "provider_disclosure", "source_permissions"))
            return self.runtime.propose(token, **body)
        match = re.fullmatch(r"/api/items/([A-Za-z0-9_.-]{1,128})/(review|decision|release|cancel)", path)
        if match:
            item_id, action = match.groups()
            if action == "review" and method == "GET":
                return {**self.runtime.review(token, item_id), "item_id": item_id}
            if action == "decision" and method == "POST":
                exact(body, ("review_digest", "decision"))
                return self.runtime.decide(token, item_id, body["review_digest"], body["decision"])
            if action in ("release", "cancel") and method == "POST":
                exact(body, ("review_digest",))
                return getattr(self.runtime, action)(token, item_id, body["review_digest"])
        raise RequestDenied("Unknown owner operation")


class PilotHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, directory, port=0):
        self.connection_slots = threading.BoundedSemaphore(16)
        self.owner_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pilot-owner")
        self.owner = None
        self.directory = Path(directory)
        try:
            self.owner = self.owner_worker.submit(OwnerService, directory).result()
            super().__init__(("127.0.0.1", port), PilotHandler)
            self.origin = "http://127.0.0.1:" + str(self.server_port)
            self.host_header = "127.0.0.1:" + str(self.server_port)
        except BaseException:
            self.server_close()
            raise

    def process_request(self, request, client_address):
        if not self.connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()

    def handle_error(self, request, client_address):
        pass  # Broken connections cannot dump request/credential details to stderr.

    def server_close(self):
        if getattr(self, "socket", None) is not None:
            super().server_close()
        if self.owner is not None:
            self.owner_worker.submit(self.owner.close).result()
            self.owner = None
        self.owner_worker.shutdown(wait=True)


class PilotHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AssistantCentralPilot"
    sys_version = ""

    def log_message(self, *_):
        pass  # Request URLs, bearer values and bodies never enter access logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def _headers(self):
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        if hosts != [self.server.host_header] or len(origins) > 1 or (origins and origins[0] != self.server.origin):
            raise RequestDenied("Invalid request origin")
        if self.headers.get("Transfer-Encoding") is not None:
            raise RequestDenied("Chunked requests are not supported")
        if "?" in self.path or "#" in self.path or len(self.path) > 256:
            raise RequestDenied("Unexpected request target")

    def _body(self):
        lengths = self.headers.get_all("Content-Length", [])
        types = self.headers.get_all("Content-Type", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,6}", lengths[0]) or types != ["application/json"]:
            raise RequestDenied("JSON with one exact content length is required")
        length = int(lengths[0])
        if not 2 <= length <= MAX_BODY:
            raise RequestDenied("Request body exceeds bound")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestDenied("Incomplete request")
        return strict_json(raw)

    def _token(self):
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or not values[0].startswith("Bearer ") or len(values[0]) > 128:
            raise AuthError("Authentication required")
        return values[0][7:]

    def _reply(self, status, value, content_type="application/json"):
        body = value if type(value) is bytes else encode(value)
        self.send_response(status)
        for key, val in (("Content-Type", content_type), ("Content-Length", str(len(body))),
                         ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                         ("Referrer-Policy", "no-referrer"), ("Connection", "close"),
                         ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")):
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _handle(self, method):
        try:
            self._headers()
            if method == "GET" and not self.path.startswith("/api/"):
                name = "index.html" if self.path == "/" else self.path.removeprefix("/")
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.(html|css|js|mjs|svg)", name):
                    raise RequestDenied("Unknown static resource")
                path = WEB / name
                if not path.is_file() or path.is_symlink():
                    raise RequestDenied("Unknown static resource")
                kind = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                        ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
                        ".svg": "image/svg+xml"}[path.suffix]
                return self._reply(200, path.read_bytes(), kind)
            body = self._body() if method in ("POST", "DELETE") else {}
            if self.path == "/peer/inbox" and method == "POST":
                if self.headers.get_all("X-Assistant-Central-Peer", []) != [PEER_HEADER]:
                    raise RequestDenied("Explicit peer packet header required")
                exact(body, ("packet",))
                return self._reply(200, self.server.owner.mailbox.store(body["packet"]))
            token = None if self.path == "/api/session" and method == "POST" else self._token()
            result = self.server.owner_worker.submit(self.server.owner.call, method, self.path, token, body).result(timeout=60)
            self._reply(200, result)
        except AuthError:
            self._reply(401, {"error": "Authentication required or session expired."})
        except (RequestDenied, ValueError, PermissionError):
            self._reply(400, {"error": "Request denied. Check the exact review, peer and current permissions."})
        except Exception:
            self._reply(503, {"error": "Outcome unavailable. Inspect retained history before retrying a decision."})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_OPTIONS(self):
        self._reply(403, {"error": "Cross-origin access is disabled."})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assistant-Central local pilot, synthetic data only")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Provision one local owner; password is entered privately")
    init.add_argument("--directory", required=True)
    init.add_argument("--owner", required=True)
    init.add_argument("--agent", required=True)
    serve = sub.add_parser("serve", help="Run one loopback-only assistant")
    serve.add_argument("--directory", required=True)
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.command == "init":
        password = getpass.getpass("Local owner password (at least 12 characters): ")
        if password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        auth = LocalOwnerAuth(args.directory)
        try:
            print(json.dumps({"public_identity": auth.bootstrap(args.owner, args.agent, password)}, indent=2))
        finally:
            auth.close()
        return
    if args.port != 0 and not 1024 <= args.port <= 65535:
        raise SystemExit("Choose a loopback port from 1024 to 65535, or 0 for an ephemeral port")
    server = PilotHTTPServer(args.directory, args.port)
    print(json.dumps({"url": server.origin, "synthetic_only": True, "live_provider_enabled": False}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
