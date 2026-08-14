import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wiki_repository.config import (  # noqa: E402
    DEFAULT_ORIGIN,
    CredentialStore,
    normalize_server,
)
from wiki_repository.errors import ConfirmationRequired, OperatorError  # noqa: E402
from wiki_repository.security import SafetyGate, redact  # noqa: E402


class ConfigSecurityTests(unittest.TestCase):
    def test_server_normalization_supports_bare_ip_and_api_url(self):
        self.assertEqual(normalize_server("10.40.2.178").origin, DEFAULT_ORIGIN)
        endpoint = normalize_server("https://Wiki.Example:8443/api/")
        self.assertEqual(endpoint.origin, "https://wiki.example:8443")
        self.assertEqual(endpoint.api_url, "https://wiki.example:8443/api")
        for invalid in ("wiki.example", "file:///tmp/wiki", "http://user:pass@wiki.example", "http://wiki.example/other"):
            with self.assertRaises(OperatorError):
                normalize_server(invalid)

    def test_config_and_token_are_private_and_environment_overrides_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CredentialStore(Path(temporary) / "config")
            store.save_endpoint(normalize_server("10.40.2.99"))
            store.save_token("wkp_" + "abcdefghijklmnopqrstuvwxyz")
            self.assertEqual(stat.S_IMODE(store.config_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(store.settings_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(store.token_path.stat().st_mode), 0o600)
            self.assertEqual(store.endpoint()[0].origin, "http://10.40.2.99:4004")
            with patch.dict(os.environ, {
                "WIKI_REPOSITORY_URL": "10.40.2.88",
                "WIKI_REPOSITORY_TOKEN": "wkp_" + "environmenttoken123456",
            }):
                self.assertEqual(store.endpoint(), (normalize_server("10.40.2.88"), "environment"))
                self.assertEqual(store.token()[1], "environment")

    def test_restricted_secret_file_rejects_group_read_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "secret"
            path.write_text("jira-token", encoding="utf-8")
            os.chmod(path, 0o640)
            with self.assertRaisesRegex(OperatorError, "600"):
                CredentialStore(Path(temporary) / "config").read_restricted_file(path)

    def test_redaction_hides_credentials_but_keeps_scope_and_prefix_metadata(self):
        value = redact({
            "token": "wkp_" + "fullsecretvalue123",
            "token_prefix": "wkp_1234",
            "token_scopes": ["wiki:read"],
            "message": "Bearer " + "wkp_" + "anothersecret1234",
        })
        self.assertEqual(value["token"], "<redacted>")
        self.assertEqual(value["token_prefix"], "wkp_1234")
        self.assertEqual(value["token_scopes"], ["wiki:read"])
        self.assertNotIn("anothersecret", value["message"])

    def test_confirmation_plan_is_private_secret_free_exact_and_one_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CredentialStore(Path(temporary) / "config")
            gate = SafetyGate(store, ttl_seconds=600)
            arguments = dict(
                operation="gitlab.apply",
                endpoint="http://10.40.2.178:4004",
                risk="critical",
                scope="integrations:manage",
                method="PUT",
                path="/integrations/gitlab/settings",
                query={},
                body={"base_url": "http://gitlab.example", "token": "private-gitlab-token"},
                required_text="APPLY GITLAB SETTINGS",
            )
            with self.assertRaises(ConfirmationRequired) as raised:
                gate.authorize(**arguments)
            plan = raised.exception.details["plan"]
            plan_path = store.plans_dir / f"{plan['id']}.json"
            self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
            self.assertNotIn("private-gitlab-token", plan_path.read_text(encoding="utf-8"))
            stored = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["request"]["body"]["token"], "<redacted>")
            with self.assertRaisesRegex(OperatorError, "短语"):
                gate.authorize(**arguments, confirmation_id=plan["id"], confirmation_text="wrong")
            gate.authorize(
                **arguments,
                confirmation_id=plan["id"],
                confirmation_text="APPLY GITLAB SETTINGS",
            )
            self.assertFalse(plan_path.exists())
            with self.assertRaisesRegex(OperatorError, "不存在"):
                gate.authorize(
                    **arguments,
                    confirmation_id=plan["id"],
                    confirmation_text="APPLY GITLAB SETTINGS",
                )


if __name__ == "__main__":
    unittest.main()
