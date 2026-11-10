"""Actual HTTP checks for the optional static frontend and inherited owner API."""
import http.client
import json
import re
from urllib.parse import urljoin
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.server import PilotHandler, WEB
from workspace_ui.demo import PASSWORD, seed_workspace
from workspace_ui.server import MAX_STATIC_BYTES, STATIC_FILES, WorkspaceHTTPServer, main


class WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="central-workspace-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.owner = seed_workspace(self.root)
        self.server = WorkspaceHTTPServer(self.owner, 0, synthetic_workflow=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, method, path, value=None, token=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = dict(headers or {})
        if token:
            request_headers["Authorization"] = "Bearer " + token
        body = None
        if value is not None:
            body = json.dumps(value)
            request_headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def login(self):
        status, _, body = self.request("POST", "/api/session", {"password": PASSWORD})
        self.assertEqual(status, 200)
        return json.loads(body)["token"]

    def test_authoritative_model_and_security_headers_are_preserved(self):
        status, headers, body = self.request("GET", "/model.mjs")
        self.assertEqual(status, 200)
        self.assertEqual(body, (WEB / "model.mjs").read_bytes())
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_recursive_browser_module_graph_is_available_over_http(self):
        # Follow imports from the HTML entrypoint over the actual HTTP server.
        # This catches transitive dependencies added to shared pilot modules.
        status, _, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        pending = re.findall(r'<script[^>]+src="([^"]+\.mjs)"', html.decode())
        self.assertTrue(pending)
        visited = set()
        while pending:
            route = pending.pop()
            if route in visited:
                continue
            visited.add(route)
            status, headers, body = self.request("GET", route)
            self.assertEqual(status, 200, route)
            self.assertIn("javascript", headers["Content-Type"])
            for dependency in re.findall(r"(?:from\s*|import\s*\(?\s*)['\"](\.[^'\"]+)['\"]", body.decode()):
                pending.append(urljoin(route, dependency))
        self.assertIn("/model.mjs", visited)
        self.assertIn("/transfers.mjs", visited)
        self.assertEqual(self.request("GET", "/transfers.mjs")[2], (WEB / "transfers.mjs").read_bytes())

    def test_transfer_config_is_disabled_by_default_and_only_trusted_cli_loaded(self):
        token = self.login()
        state = json.loads(self.request("GET", "/api/state", token=token)[2])
        self.assertFalse(state["transfers"]["enabled"])
        self.assertEqual(state["transfers"]["connections"], [])
        with patch("workspace_ui.server.WorkspaceHTTPServer") as factory, patch("workspace_ui.server.load_config") as load:
            factory.return_value.origin = "http://127.0.0.1:8877"
            main(["serve", "--directory", str(self.owner), "--port", "0"])
            load.assert_not_called()
            self.assertIsNone(factory.call_args.kwargs["transfer_config"])
            main(["serve", "--directory", str(self.owner), "--port", "0", "--transfer-config", "/private/host.json"])
            load.assert_called_once_with("/private/host.json")
            self.assertIs(factory.call_args.kwargs["transfer_config"], load.return_value)
        with patch("workspace_ui.server.WorkspaceHTTPServer") as factory, patch("workspace_ui.server.load_config", side_effect=ValueError("invalid configuration")):
            with self.assertRaises(ValueError):
                main(["serve", "--directory", str(self.owner), "--port", "0", "--transfer-config", "/private/invalid.json"])
            factory.assert_not_called()

    def test_static_allowlist_refuses_traversal_query_and_non_assets(self):
        for path in ("/server.py", "/demo.py", "/README.md", "/../pilot/auth.py",
                     "/%2e%2e/pilot/auth.py", "/model.mjs?source=1", "//model.mjs", "/unknown.svg"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 400)

    def test_static_files_are_descriptor_pinned_bounded_and_not_symlinks(self):
        target = self.root / "temporary-model.mjs"
        target.write_text("private data must not become a static asset")
        link = self.root / "linked-model.mjs"
        link.symlink_to(target)
        with patch.dict(STATIC_FILES, {"/model.mjs": (link, "text/javascript")}):
            self.assertEqual(self.request("GET", "/model.mjs")[0], 400)
        with target.open("wb") as stream:
            stream.truncate(MAX_STATIC_BYTES + 1)
        with patch.dict(STATIC_FILES, {"/model.mjs": (target, "text/javascript")}):
            self.assertEqual(self.request("GET", "/model.mjs")[0], 400)
        with patch.dict(STATIC_FILES, {"/model.mjs": (self.root, "text/javascript")}):
            self.assertEqual(self.request("GET", "/model.mjs")[0], 400)

    def test_foreign_host_origin_and_preflight_are_refused(self):
        for path in ("/model.mjs", "/api/state"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path, headers={"Host": "attacker.invalid"})[0], 400)
                self.assertEqual(self.request("GET", path, headers={"Origin": "https://attacker.invalid"})[0], 400)
        self.assertEqual(self.request("OPTIONS", "/api/state")[0], 403)

    def test_seeded_state_is_actual_authenticated_runtime_not_static_demo_data(self):
        self.assertEqual(self.request("GET", "/api/state")[0], 401)
        token = self.login()
        status, _, body = self.request("GET", "/api/state", token=token)
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(state["identity"]["owner_id"], "blair")
        self.assertEqual(len(state["peers"]), 3)
        self.assertEqual(len(state["items"]), 9)
        self.assertFalse(state["provider"]["live_enabled"])
        self.assertTrue(state["workflow"]["enabled"])
        self.assertEqual(len([x for x in state["items"] if x["state"] == "pending"]), 3)
        self.assertEqual(len([x for x in state["items"] if x["kind"] == "artifact"]), 1)
        self.assertEqual(self.request("DELETE", "/api/session", {}, token)[0], 200)
        self.assertEqual(self.request("GET", "/api/state", token=token)[0], 401)

    def test_exact_review_decision_and_terminal_rejection_use_inherited_api(self):
        # Static selection does not replace or wrap the authority-changing paths.
        self.assertIs(self.server.RequestHandlerClass.do_POST, PilotHandler.do_POST)
        token = self.login()
        state = json.loads(self.request("GET", "/api/state", token=token)[2])
        item = next(x for x in state["items"] if x["title"] == "Review the research brief")
        route = "/api/items/" + item["id"]
        review = json.loads(self.request("GET", route + "/review", token=token)[2])
        self.assertEqual(self.request("POST", route + "/decision", {"review_digest": "0" * 64,
            "decision": "accept"}, token)[0], 400)
        exact = {"review_digest": review["review_digest"], "decision": "reject"}
        status, _, body = self.request("POST", route + "/decision", exact, token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["state"], "rejected")
        exact["decision"] = "accept"
        self.assertEqual(self.request("POST", route + "/decision", exact, token)[0], 400)

    def test_cli_refuses_to_create_a_new_owner(self):
        absent = self.root / "not-provisioned"
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            main(["serve", "--directory", str(absent), "--port", "0"])
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
