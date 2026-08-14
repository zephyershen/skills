import base64
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wiki_repository.cli import main  # noqa: E402
from wiki_repository.config import CredentialStore  # noqa: E402
from wiki_repository.dependencies import _install_archive, ensure_wiki_skill_once  # noqa: E402
from wiki_repository.errors import OperatorError  # noqa: E402

TEST_PAT = "wkp_" + "firstuse" + "token123456"


def build_wiki_package():
    files = {
        "SKILL.md": "---\nname: wiki\ndescription: Test company Wiki Skill\n---\n\n# Wiki\n",
        "references/templates.md": "# Templates\n",
        "references/wiki-location.md": "# Wiki location\n",
        "agents/openai.yaml": "interface:\n  display_name: Wiki\n",
        "skill.json": json.dumps({
            "namespace": "global-skills",
            "name": "wiki",
            "version": "1.0.0",
            "description": "Test company Wiki Skill",
        }),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    hashes = {
        name: hashlib.sha256(files[name].encode()).hexdigest()
        for name in ("SKILL.md", "references/templates.md", "references/wiki-location.md")
    }
    return output.getvalue(), hashes


PACKAGE, CORE_HASHES = build_wiki_package()
PACKAGE_SHA256 = hashlib.sha256(PACKAGE).hexdigest()


class CombinedHandler(BaseHTTPRequestHandler):
    skillhub_downloads = 0

    def do_GET(self):
        if self.path == "/service/meta":
            return self.respond(200, {
                "service_key": "kg-platform",
                "service_name": "Wiki Repository",
                "version": "2.1.0",
                "api_version": "4.0.0",
            })
        if self.path == "/api/health":
            return self.respond(200, {
                "status": "healthy",
                "readiness": "ready",
                "components": {"api": "ok", "db": "ok"},
            })
        if self.path == "/api/openapi.json":
            return self.respond(200, {
                "openapi": "3.1.0",
                "info": {"title": "Wiki Repository Platform API", "version": "4.0.0"},
            })
        if self.path == "/api/auth/me":
            if self.headers.get("Authorization") != f"Bearer {TEST_PAT}":
                return self.respond(401, {"error": "bad token", "code": "invalid_token"})
            return self.respond(200, {"id": 7, "name": "Agent Owner", "available_token_scopes": ["wiki:read"]})
        if self.path == "/api/projects":
            if self.headers.get("Authorization") != f"Bearer {TEST_PAT}":
                return self.respond(401, {"error": "bad token", "code": "invalid_token"})
            return self.respond(200, {"items": [{"id": 3, "name": "Product Wiki", "access_level": "read"}]})
        return self.respond(404, {"error": "missing"})

    def do_POST(self):
        expected = "/api/v1/skills/global-skills/wiki/versions/1.0.0/download"
        if self.path == expected:
            type(self).skillhub_downloads += 1
            return self.respond(201, {
                "code": 0,
                "msg": "ok",
                "data": {"content": base64.b64encode(PACKAGE).decode(), "encoding": "base64"},
            })
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


class DependencyBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CombinedHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        CombinedHandler.skillhub_downloads = 0

    def run_cli(self, arguments, *, operator_root, stdin=""):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(stdin)),
            patch("wiki_repository.dependencies.WIKI_PACKAGE_SHA256", PACKAGE_SHA256),
            patch("wiki_repository.dependencies.CORE_FILE_SHA256", CORE_HASHES),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main(arguments, operator_root=operator_root)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_first_call_installs_wiki_then_continues_and_later_calls_do_not_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operator_root = root / "agent-skills" / "wiki-repository-operator"
            config_dir = root / "config"
            environment = {
                "WIKI_REPOSITORY_CONFIG_DIR": str(config_dir),
                "WIKI_REPOSITORY_URL": self.origin,
                "WIKI_REPOSITORY_SKILLHUB_URL": self.origin,
            }
            with patch.dict(os.environ, environment, clear=False):
                code, output, error = self.run_cli(
                    ["auth", "set-token", "--stdin"],
                    operator_root=operator_root,
                    stdin=f"{TEST_PAT}\n",
                )
                self.assertEqual((code, error), (0, ""))
                payload = json.loads(output)
                self.assertEqual(payload["command"], "auth.set-token")
                self.assertEqual(payload["wiki_skill_bootstrap"]["status"], "installed")
                self.assertTrue((root / "agent-skills" / "wiki" / "SKILL.md").is_file())
                self.assertEqual(CombinedHandler.skillhub_downloads, 1)

                shutil.rmtree(root / "agent-skills" / "wiki")
                code, output, error = self.run_cli(["projects", "list"], operator_root=operator_root)
                self.assertEqual((code, error), (0, ""))
                payload = json.loads(output)
                self.assertEqual(payload["result"]["items"][0]["name"], "Product Wiki")
                self.assertNotIn("wiki_skill_bootstrap", payload)
                self.assertEqual(CombinedHandler.skillhub_downloads, 1)

    def test_existing_incompatible_wiki_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operator_root = root / "agent-skills" / "wiki-repository-operator"
            wiki = root / "agent-skills" / "wiki"
            wiki.mkdir(parents=True)
            (wiki / "SKILL.md").write_text("user-owned skill", encoding="utf-8")
            store = CredentialStore(root / "config")
            with (
                patch.dict(os.environ, {"WIKI_REPOSITORY_SKILLHUB_URL": self.origin}, clear=False),
                patch("wiki_repository.dependencies.CORE_FILE_SHA256", CORE_HASHES),
                self.assertRaises(OperatorError) as raised,
            ):
                ensure_wiki_skill_once(store, operator_root=operator_root, expected_checksum=PACKAGE_SHA256)
            self.assertEqual(raised.exception.code, "wiki_skill_install_conflict")
            self.assertEqual((wiki / "SKILL.md").read_text(encoding="utf-8"), "user-owned skill")
            self.assertEqual(CombinedHandler.skillhub_downloads, 0)

    def test_existing_compatible_local_wiki_is_marked_without_downloading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operator_root = root / "agent-skills" / "wiki-repository-operator"
            wiki = root / "agent-skills" / "wiki"
            wiki.mkdir(parents=True)
            with zipfile.ZipFile(io.BytesIO(PACKAGE)) as bundle:
                bundle.extractall(wiki)
            (wiki / "skill.json").unlink()
            store = CredentialStore(root / "config")
            with patch("wiki_repository.dependencies.CORE_FILE_SHA256", CORE_HASHES):
                result = ensure_wiki_skill_once(store, operator_root=operator_root, expected_checksum=PACKAGE_SHA256)
            self.assertEqual(result["status"], "already_installed")
            self.assertEqual(CombinedHandler.skillhub_downloads, 0)
            marker = store.read_settings()["wiki_skill_bootstrap"]
            self.assertEqual(marker["installed_kind"], "compatible_local")

    def test_checksum_mismatch_writes_no_completion_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operator_root = root / "agent-skills" / "wiki-repository-operator"
            store = CredentialStore(root / "config")
            with (
                patch.dict(os.environ, {"WIKI_REPOSITORY_SKILLHUB_URL": self.origin}, clear=False),
                self.assertRaises(OperatorError) as raised,
            ):
                ensure_wiki_skill_once(store, operator_root=operator_root, expected_checksum="0" * 64)
            self.assertEqual(raised.exception.code, "wiki_skill_checksum_mismatch")
            self.assertNotIn("wiki_skill_bootstrap", store.read_settings())
            self.assertFalse((root / "agent-skills" / "wiki").exists())

    def test_dependency_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as bundle:
                bundle.writestr("../outside", "must not be written")
            with self.assertRaises(OperatorError) as raised:
                _install_archive(output.getvalue(), root / "skills" / "wiki")
            self.assertEqual(raised.exception.code, "unsafe_wiki_skill_archive")
            self.assertFalse((root / "outside").exists())
            self.assertFalse((root / "skills" / "wiki").exists())


if __name__ == "__main__":
    unittest.main()
