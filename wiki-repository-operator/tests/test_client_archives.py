import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wiki_repository.archives import create_directory_zip, extract_zip_safely  # noqa: E402
from wiki_repository.client import PlatformClient  # noqa: E402
from wiki_repository.config import normalize_server  # noqa: E402
from wiki_repository.errors import ApiError, OperatorError  # noqa: E402


class RetryHandler(BaseHTTPRequestHandler):
    get_calls = 0
    post_calls = 0
    redirected_calls = 0

    def do_GET(self):
        if self.path == "/api/redirect":
            self.send_response(302)
            self.send_header("Location", "/api/redirect-target")
            self.end_headers()
            return
        if self.path == "/api/redirect-target":
            type(self).redirected_calls += 1
            return self.respond(200, {"leaked": True})
        type(self).get_calls += 1
        if type(self).get_calls == 1:
            self.respond(503, {"error": "temporary", "code": "temporary"})
        else:
            self.respond(200, {"ok": True})

    def do_POST(self):
        type(self).post_calls += 1
        self.respond(503, {"error": "do not retry", "code": "write_failed"})

    def respond(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


class ClientArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RetryHandler.get_calls = 0
        RetryHandler.post_calls = 0
        RetryHandler.redirected_calls = 0
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RetryHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_only_get_requests_retry(self):
        client = PlatformClient(normalize_server(self.origin), "wkp_" + "testtoken123456", timeout=2)
        self.assertEqual(client.api("GET", "/flaky"), {"ok": True})
        self.assertEqual(RetryHandler.get_calls, 2)
        with self.assertRaises(ApiError):
            client.api("POST", "/write", body={"name": "test"}, retry=True)
        self.assertEqual(RetryHandler.post_calls, 1)

    def test_authenticated_requests_never_follow_redirects(self):
        client = PlatformClient(normalize_server(self.origin), "wkp_" + "testtoken123456", timeout=2)
        with self.assertRaises(ApiError):
            client.api("GET", "/redirect", retry=False)
        self.assertEqual(RetryHandler.redirected_calls, 0)

    def test_directory_upload_zip_drops_git_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "wiki"
            (root / ".git").mkdir(parents=True)
            (root / ".git" / "config").write_text("secret", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "readme.md").write_text("hello", encoding="utf-8")
            archive, stats = create_directory_zip(root)
            try:
                with zipfile.ZipFile(archive) as bundle:
                    self.assertEqual(bundle.namelist(), ["docs/readme.md"])
                self.assertEqual(stats["files"], 1)
            finally:
                archive.unlink(missing_ok=True)

    def test_safe_extract_rejects_traversal_and_never_creates_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "malicious.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "bad")
            target = Path(temporary) / "result"
            with self.assertRaises(OperatorError):
                extract_zip_safely(archive, target)
            self.assertFalse(target.exists())
            self.assertFalse((Path(temporary).parent / "escape.txt").exists())

    def test_safe_extract_writes_private_files_to_new_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "safe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("docs/readme.md", "hello")
            target = Path(temporary) / "result"
            result = extract_zip_safely(archive, target)
            self.assertEqual(result["files"], 1)
            self.assertEqual((target / "docs" / "readme.md").read_text(), "hello")
            self.assertEqual(os.stat(target / "docs" / "readme.md").st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
