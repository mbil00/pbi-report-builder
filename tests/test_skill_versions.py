"""Bundled skills must say which CLI version they were written for (#37)."""

import re
import unittest
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
REQUIRES = re.compile(r"^> Requires `pbi` (\d+)\.(\d+)\.(\d+) or newer\.", re.MULTILINE)


class SkillVersionTests(unittest.TestCase):
    def test_every_skill_declares_minimum_cli_version(self) -> None:
        skills = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        self.assertTrue(skills, "no bundled skills found")
        for skill in skills:
            with self.subTest(skill=skill.parent.name):
                self.assertRegex(skill.read_text(encoding="utf-8"), REQUIRES)


if __name__ == "__main__":
    unittest.main()
