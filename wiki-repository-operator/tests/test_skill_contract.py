import json
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_chat_supplied_pat_is_an_explicit_bootstrap_path(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        security = (SKILL_DIR / "references" / "security.md").read_text(encoding="utf-8")
        agent = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("user already supplied a `wkp_` PAT in the current conversation", skill)
        self.assertIn("feed that value to the CLI through the Agent runtime's stdin", skill)
        self.assertIn("incoming user chat message is an allowed PAT bootstrap channel", security)
        self.assertIn("configure it immediately through stdin", agent)

    def test_chat_bootstrap_does_not_allow_outgoing_token_repetition_or_argv(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Never put the PAT in a command argument", skill)
        self.assertIn("repeat it in an outgoing message", skill)

    def test_wiki_dependency_is_pinned_and_first_use_only(self):
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        manifest = json.loads((SKILL_DIR / "skill.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["namespace"], "global-skills")
        self.assertEqual(manifest["version"], "1.1.2")
        self.assertEqual(manifest["dependencies"][0]["coordinate"], "global-skills/wiki@1.0.0")
        self.assertEqual(manifest["dependencies"][0]["install"], "first-use-once")
        self.assertIn("later operator commands must not inspect the Wiki Skill directory", skill)
        self.assertIn("first command still performs the user's requested command after installation", skill)


if __name__ == "__main__":
    unittest.main()
