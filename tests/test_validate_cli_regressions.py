from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from tests.cli_regressions_support import make_project


class ValidateCliRegressionTests(unittest.TestCase):
    def test_validate_can_ignore_schema_warnings_and_strictly_fail_on_them(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["visual"]["objects"] = {
                "legend": [
                    {
                        "properties": {
                            "definitelyWrong": {
                                "expr": {"Literal": {"Value": "true"}},
                            }
                        }
                    }
                ]
            }
            visual.save()

            result = runner.invoke(app, ["validate", "--project", str(root / "Sample.pbip")])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Schema:", result.stdout)

            strict_result = runner.invoke(
                app,
                ["validate", "--strict", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(strict_result.exit_code, 1, strict_result.stdout)

            ignored_result = runner.invoke(
                app,
                ["validate", "--ignore-schema-warnings", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(ignored_result.exit_code, 0, ignored_result.stdout)
            self.assertIn("No issues found.", ignored_result.stdout)
