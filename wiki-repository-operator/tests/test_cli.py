import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wiki_repository.cli import main  # noqa: E402

TEST_PAT = "wkp_" + "bootstrap" + "token123456"
CREATED_PAT = "wkp_" + "created" + "childtoken123456789"


class PlatformHandler(BaseHTTPRequestHandler):
    create_calls = 0
    archive_calls = 0
    workspace_full_path = "pa2-2/t-mobile/teton"

    def do_GET(self):
        if self.path == "/service/meta":
            return self.respond(200, {"service_key": "kg-platform", "service_name": "Wiki Repository", "version": "2.1.0", "api_version": "4.0.0"})
        if self.path == "/api/health":
            return self.respond(200, {"status": "healthy", "readiness": "ready", "components": {"api": "ok", "db": "ok"}})
        if self.path == "/api/openapi.json":
            return self.respond(200, {"openapi": "3.1.0", "info": {"title": "Wiki Repository Platform API", "version": "4.0.0"}})
        if self.path == "/api/auth/me":
            if self.headers.get("Authorization") != f"Bearer {TEST_PAT}":
                return self.respond(401, {"error": "bad token", "code": "invalid_token"})
            return self.respond(200, {"id": 7, "name": "Agent Owner", "is_admin": True, "available_token_scopes": ["wiki:read", "tokens:manage"]})
        if self.path == "/api/projects/7/workspace?reconcile=false":
            return self.respond(200, {
                "namespaces": [{"id": 18, "full_path": type(self).workspace_full_path}],
                "repositories": [],
            })
        if self.path == "/api/archives":
            return self.respond(200, {"items": [{
                "kind": "namespace",
                "id": 18,
                "full_path": type(self).workspace_full_path,
            }]})
        return self.respond(404, {"error": "missing"})

    def do_POST(self):
        if self.path == "/api/access-tokens":
            type(self).create_calls += 1
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            return self.respond(201, {
                "id": "18356cea-2c7f-45c5-b8da-f715f8cb3386",
                "name": body["name"],
                "scopes": body["scopes"],
                "token": CREATED_PAT,
            })
        if self.path == "/api/archives/namespace/18/restore":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            return self.respond(200, {"ok": True, "received": body})
        return self.respond(404, {"error": "missing"})

    def do_DELETE(self):
        if self.path == "/api/projects/7/namespaces/18":
            type(self).archive_calls += 1
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            return self.respond(200, {"ok": True, "received": body})
        return self.respond(404, {"error": "missing"})

    def respond(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PlatformHandler.create_calls = 0
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PlatformHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def run_cli(self, arguments, *, stdin=""):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(stdin)),
            patch("wiki_repository.cli.ensure_wiki_skill_once", return_value=None),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_server_set_validates_before_saving_and_auth_token_uses_stdin(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
        }, clear=False):
            os.environ.pop("WIKI_REPOSITORY_URL", None)
            os.environ.pop("WIKI_REPOSITORY_TOKEN", None)
            code, output, error = self.run_cli(["server", "set", self.origin])
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(json.loads(output)["result"]["verified"]["api_version"], "4.0.0")

            code, output, error = self.run_cli(["auth", "set-token", "--stdin"], stdin=f"{TEST_PAT}\n")
            self.assertEqual((code, error), (0, ""))
            self.assertNotIn("bootstraptoken123456", output)
            result = json.loads(output)["result"]
            self.assertTrue(result["saved"])
            self.assertTrue(result["token_prefix"].startswith("wkp_"))
            self.assertNotEqual(result["token_prefix"], TEST_PAT)
            token_path = Path(temporary) / "config" / "token"
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

    def test_mutation_requires_exact_one_time_plan_and_never_prints_created_token(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
            "WIKI_REPOSITORY_URL": self.origin,
            "WIKI_REPOSITORY_TOKEN": TEST_PAT,
        }, clear=False):
            output_token = Path(temporary) / "child.token"
            body = json.dumps({"name": "Child Agent", "scopes": ["wiki:read"]})
            base_arguments = ["tokens", "create", "--json", body, "--save-token", str(output_token)]
            code, output, error = self.run_cli(base_arguments)
            self.assertEqual((code, error), (3, ""))
            plan = json.loads(output)["error"]["plan"]
            self.assertEqual(PlatformHandler.create_calls, 0)

            code, output, error = self.run_cli([*base_arguments, "--confirm", plan["id"]])
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(PlatformHandler.create_calls, 1)
            self.assertNotIn("createdchildtoken", output)
            self.assertEqual(output_token.read_text().strip(), CREATED_PAT)
            self.assertEqual(output_token.stat().st_mode & 0o777, 0o600)

            second_output = Path(temporary) / "second.token"
            code, _output, error = self.run_cli([
                "tokens", "create", "--json", body, "--save-token", str(second_output), "--confirm", plan["id"],
            ])
            self.assertEqual(code, 3)
            self.assertIn("confirmation_not_found", error)
            self.assertEqual(PlatformHandler.create_calls, 1)

    def test_sensitive_fields_are_rejected_from_generic_json(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
            "WIKI_REPOSITORY_URL": self.origin,
            "WIKI_REPOSITORY_TOKEN": TEST_PAT,
        }, clear=False):
            code, _output, error = self.run_cli([
                "projects", "create", "--json", '{"name":"Demo","token":"must-not-pass"}',
            ])
            self.assertEqual(code, 2)
            self.assertIn("sensitive_json_rejected", error)
            self.assertNotIn("must-not-pass", error)

    def test_required_mutation_body_is_rejected_before_a_plan_is_created(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
            "WIKI_REPOSITORY_URL": self.origin,
            "WIKI_REPOSITORY_TOKEN": TEST_PAT,
        }, clear=False):
            code, output, error = self.run_cli(["projects", "update", "--project-id", "7"])
            self.assertEqual(code, 2)
            self.assertEqual(output, "")
            self.assertIn("--json", error)
            self.assertFalse((Path(temporary) / "config" / "plans").exists())

    def test_archive_plan_binds_the_live_path_and_rejects_a_changed_target(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
            "WIKI_REPOSITORY_URL": self.origin,
            "WIKI_REPOSITORY_TOKEN": TEST_PAT,
        }, clear=False):
            PlatformHandler.archive_calls = 0
            PlatformHandler.workspace_full_path = "pa2-2/t-mobile/teton"
            arguments = [
                "workspace", "group-archive", "--project-id", "7", "--namespace-id", "18",
            ]
            code, output, error = self.run_cli(arguments)
            self.assertEqual((code, error), (3, ""))
            plan = json.loads(output)["error"]["plan"]
            self.assertEqual(
                plan["request"]["body"]["expected_full_path"],
                "pa2-2/t-mobile/teton",
            )

            PlatformHandler.workspace_full_path = "pa2-2/t-mobile/teton-renamed"
            code, _output, error = self.run_cli([*arguments, "--confirm", plan["id"]])
            self.assertEqual(code, 3)
            self.assertIn("confirmation_mismatch", error)
            self.assertEqual(PlatformHandler.archive_calls, 0)

    def test_restore_plan_binds_the_current_archive_path(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "WIKI_REPOSITORY_CONFIG_DIR": str(Path(temporary) / "config"),
            "WIKI_REPOSITORY_URL": self.origin,
            "WIKI_REPOSITORY_TOKEN": TEST_PAT,
        }, clear=False):
            PlatformHandler.workspace_full_path = "pa2-2/t-mobile/teton"
            code, output, error = self.run_cli([
                "archives", "restore", "--kind", "namespace", "--id", "18",
            ])
            self.assertEqual((code, error), (3, ""))
            plan = json.loads(output)["error"]["plan"]
            self.assertEqual(
                plan["request"]["body"]["expected_full_path"],
                "pa2-2/t-mobile/teton",
            )


if __name__ == "__main__":
    unittest.main()
