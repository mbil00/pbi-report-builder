from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.schema_refs import REPORT_SCHEMA


class ReportCommandTests(unittest.TestCase):
    def _make_report_project(self, root: Path) -> tuple[Path, Path]:
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
        return pbip_path, report_path

    def test_report_set_updates_report_json(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)

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

    def test_report_annotation_set_get_list_and_delete(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)

            set_result = runner.invoke(
                app,
                ["report", "annotation", "set", "README", "Owned by BI team", "--project", str(pbip_path)],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)
            self.assertIn('Created report annotation "README"', set_result.stdout)

            get_result = runner.invoke(
                app,
                ["report", "annotation", "get", "README", "--project", str(pbip_path)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Owned by BI team", get_result.stdout)

            list_result = runner.invoke(
                app,
                ["report", "annotation", "list", "--json", "--project", str(pbip_path)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(rows, [{"name": "README", "value": "Owned by BI team"}])

            delete_result = runner.invoke(
                app,
                ["report", "annotation", "delete", "README", "--force", "--project", str(pbip_path)],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertNotIn("annotations", report)

    def test_report_object_list_get_set_and_clear(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)

            payload_path = root / "objects.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "section": [
                            {
                                "properties": {
                                    "verticalAlignment": {
                                        "expr": {"Literal": {"Value": "'Middle'"}}
                                    }
                                }
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            set_result = runner.invoke(
                app,
                ["report", "object", "set", "objects", "--from-file", str(payload_path), "--project", str(pbip_path)],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            list_result = runner.invoke(
                app,
                ["report", "object", "list", "--json", "--project", str(pbip_path)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            objects_row = next(row for row in rows if row["name"] == "objects")
            self.assertTrue(objects_row["present"])
            self.assertEqual(objects_row["type"], "object")

            get_result = runner.invoke(
                app,
                ["report", "object", "get", "objects", "--raw", "--project", str(pbip_path)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            value = json.loads(get_result.stdout)
            self.assertEqual(value["section"][0]["properties"]["verticalAlignment"]["expr"]["Literal"]["Value"], "'Middle'")

            clear_result = runner.invoke(
                app,
                ["report", "object", "clear", "objects", "--force", "--project", str(pbip_path)],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertNotIn("objects", report)

    def test_report_object_set_normalizes_resource_packages(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)

            payload = json.dumps(
                [
                    {
                        "resourcePackage": {
                            "name": "RegisteredResources",
                            "type": 1,
                            "items": [
                                {"name": "logo.png", "path": "RegisteredResources/logo.png", "type": 202}
                            ],
                        }
                    }
                ]
            )

            result = runner.invoke(
                app,
                ["report", "object", "set", "resourcePackages", payload, "--project", str(pbip_path)],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(
                report["resourcePackages"],
                [
                    {
                        "name": "RegisteredResources",
                        "type": "RegisteredResources",
                        "items": [
                            {"name": "logo.png", "path": "logo.png", "type": "Image"}
                        ],
                    }
                ],
            )

    def test_report_resource_package_create_list_get_and_delete(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)

            create_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "package",
                    "create",
                    "BrandAssets",
                    "--type",
                    "RegisteredResources",
                    "--project",
                    str(pbip_path),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            list_result = runner.invoke(
                app,
                ["report", "resource", "package", "list", "--json", "--project", str(pbip_path)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            package_row = next(row for row in rows if row["name"] == "BrandAssets")
            self.assertEqual(package_row["type"], "RegisteredResources")
            self.assertEqual(package_row["items"], 0)

            get_result = runner.invoke(
                app,
                ["report", "resource", "package", "get", "BrandAssets", "--raw", "--project", str(pbip_path)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            pkg = json.loads(get_result.stdout)
            self.assertEqual(pkg["name"], "BrandAssets")
            self.assertEqual(pkg["type"], "RegisteredResources")

            delete_result = runner.invoke(
                app,
                ["report", "resource", "package", "delete", "BrandAssets", "--force", "--project", str(pbip_path)],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertNotIn("resourcePackages", report)

    def test_report_resource_item_set_list_get_and_delete_with_file_copy(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pbip_path, report_path = self._make_report_project(root)
            source = root / "legend.svg"
            source.write_text("<svg></svg>\n", encoding="utf-8")

            set_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "set",
                    "RegisteredResources",
                    "legend.svg",
                    "--type",
                    "Image",
                    "--name",
                    "Legend",
                    "--from-file",
                    str(source),
                    "--project",
                    str(pbip_path),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            registered = root / "Sample.Report" / "StaticResources" / "RegisteredResources" / "legend.svg"
            self.assertTrue(registered.exists())

            list_result = runner.invoke(
                app,
                ["report", "resource", "item", "list", "RegisteredResources", "--json", "--project", str(pbip_path)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(
                rows,
                [
                    {
                        "package": "RegisteredResources",
                        "name": "Legend",
                        "path": "legend.svg",
                        "type": "Image",
                    }
                ],
            )

            get_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "get",
                    "RegisteredResources",
                    "legend.svg",
                    "--raw",
                    "--project",
                    str(pbip_path),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertEqual(
                json.loads(get_result.stdout),
                {"name": "Legend", "path": "legend.svg", "type": "Image"},
            )

            delete_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "delete",
                    "RegisteredResources",
                    "legend.svg",
                    "--drop-file",
                    "--force",
                    "--project",
                    str(pbip_path),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertFalse(registered.exists())

            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(report["resourcePackages"][0]["items"], [])


if __name__ == "__main__":
    unittest.main()
