from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.schema_refs import REPORT_SCHEMA


class ReportCommandTests(unittest.TestCase):
    def test_report_set_updates_report_json(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path = root / "Sample.pbip"
            report_folder = root / "Sample.Report"
            definition = report_folder / "definition"
            definition.mkdir(parents=True)

            pbip_path.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {"report": {"path": "Sample.Report"}}
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report_path = definition / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "$schema": REPORT_SCHEMA,
                        "layoutOptimization": "None",
                        "themeCollection": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "report",
                    "set",
                    "settings.useEnhancedTooltips=true",
                    "settings.pagesPosition=Bottom",
                    "--project",
                    str(pbip_path),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertTrue(report["settings"]["useEnhancedTooltips"])
            self.assertEqual(report["settings"]["pagesPosition"], "Bottom")


if __name__ == "__main__":
    unittest.main()
