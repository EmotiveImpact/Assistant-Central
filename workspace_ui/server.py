"""Serve the optional workspace without changing any owner API or authority.

Only static GET is specialised. Every authenticated operation, peer packet,
request-origin check, security header and owner worker uses the pilot server.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from pilot.server import PilotHTTPServer, PilotHandler, RequestDenied, WEB
from pilot.owner_transfer import load_config
from workspace_ui.host_draft_service import HostDraftService, load_host_draft_config
from workspace_ui.conversation_service import ConversationService, load_conversation_config


ROOT = Path(__file__).resolve().parent
STATIC_FILES = {
    "/": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/index.html": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/style.css": (ROOT / "style.css", "text/css; charset=utf-8"),
    "/app.mjs": (ROOT / "app.mjs", "text/javascript; charset=utf-8"),
    "/operations.mjs": (ROOT / "operations.mjs", "text/javascript; charset=utf-8"),
    "/host_drafts.mjs": (ROOT / "host_drafts.mjs", "text/javascript; charset=utf-8"),
    "/projections.mjs": (ROOT / "projections.mjs", "text/javascript; charset=utf-8"),
    "/model.mjs": (WEB / "model.mjs", "text/javascript; charset=utf-8"),
    "/conversations.mjs": (ROOT / "conversations.mjs", "text/javascript; charset=utf-8"),
    "/transfers.mjs": (WEB / "transfers.mjs", "text/javascript; charset=utf-8"),
}
MAX_STATIC_BYTES = 2 * 1024 * 1024


class WorkspaceHandler(PilotHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            return super().do_GET()
        try:
            self._headers()
            if self.requestline.split()[1] != self.path:
                raise RequestDenied("Noncanonical workspace resource")
            if self.path not in STATIC_FILES:
                raise RequestDenied("Unknown workspace resource")
            path, content_type = STATIC_FILES[self.path]
            # Exact package-owned paths only, with descriptor-pinned final files.
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATIC_BYTES:
                    raise RequestDenied("Invalid workspace resource")
                body = stream.read(MAX_STATIC_BYTES + 1)
                if len(body) > MAX_STATIC_BYTES:
                    raise RequestDenied("Workspace resource exceeds bound")
            return self._reply(200, body, content_type)
        except (RequestDenied, OSError, ValueError):
            return self._reply(400, {"error": "Workspace resource unavailable."})


class WorkspaceHTTPServer(PilotHTTPServer):
    def __init__(self, directory, port=0, *, synthetic_workflow=False, transfer_config=None, conversation_config=None, host_draft_config=None):
        super().__init__(directory, port, synthetic_workflow=synthetic_workflow, transfer_config=transfer_config)
        try:
            if conversation_config is not None:
                self.owner = self.owner_worker.submit(ConversationService, self.owner, conversation_config).result()
        except BaseException:
            self.server_close()
            raise
        # Construction does not accept requests; use the specialised handler
        # before the caller starts serve_forever. No module globals are patched.
        self.RequestHandlerClass = WorkspaceHandler
        if host_draft_config is not None:
            try:
                self.owner = self.owner_worker.submit(HostDraftService, self.owner, host_draft_config).result()
            except BaseException:
                self.server_close()
                raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Central workspace for an existing synthetic pilot owner")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Open an existing owner on loopback only")
    serve.add_argument("--directory", required=True)
    serve.add_argument("--port", type=int, default=8877)
    serve.add_argument("--synthetic-workflow", action="store_true",
                       help="Enable only the fixed fictional result fixture, with no model calls")
    serve.add_argument("--transfer-config", help="Private host-selected HTTPS connection JSON; no automatic transfer")
    serve.add_argument("--conversation-config", help="Private host configuration for existing local owner accounts; disabled by default")
    serve.add_argument("--host-draft-config", help="Private host-selected inert draft review configuration; no automatic action")
    args = parser.parse_args(argv)
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error("Choose a loopback port from 1024 to 65535, or 0 for an ephemeral port")
    # Require an existing account. Provisioning and password operations remain
    # the pilot's separately reviewed terminal flows.
    directory = Path(args.directory)
    if not directory.is_dir() or not (directory / "auth.sqlite").is_file():
        parser.error("An existing pilot owner directory is required")
    server = WorkspaceHTTPServer(directory, args.port, synthetic_workflow=args.synthetic_workflow,
                                 transfer_config=load_config(args.transfer_config) if args.transfer_config else None,
                                 conversation_config=load_conversation_config(args.conversation_config) if args.conversation_config else None,
                                 host_draft_config=load_host_draft_config(args.host_draft_config) if args.host_draft_config else None)
    print(json.dumps({"url": server.origin, "synthetic_only": True,
                      "live_provider_enabled": False,
                      "synthetic_workflow_enabled": args.synthetic_workflow}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
