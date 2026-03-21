from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.images import add_image
from pbi.project import _read_json, _write_json
from tests.cli_regressions_support import make_project, write_model_table


class ImageResourceRegressionTests(unittest.TestCase):
    def test_image_create_merges_into_existing_registered_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            report_path = project.definition_folder / "report.json"
            report = _read_json(report_path)
            report["resourcePackages"] = [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {
                            "type": "CustomTheme",
                            "name": "Contoso Retail.json",
                            "path": "Contoso Retail.json",
                        }
                    ],
                }
            ]
            _write_json(report_path, report)

            image_path = root / "logo.png"
            image_path.write_bytes(b"png")
            registered_name = add_image(project, image_path)

            report_after = _read_json(report_path)
            self.assertEqual(len(report_after["resourcePackages"]), 1)
            package = report_after["resourcePackages"][0]
            self.assertEqual(package["name"], "RegisteredResources")
            self.assertEqual(package["type"], "RegisteredResources")
            self.assertNotIn("resourcePackage", package)
            self.assertEqual(package["items"][0]["type"], "CustomTheme")
            image_items = [item for item in package["items"] if item["type"] == "Image"]
            self.assertEqual(len(image_items), 1)
            self.assertEqual(image_items[0]["name"], "logo.png")
            self.assertEqual(image_items[0]["path"], registered_name)

    def test_visual_set_image_source_uses_resource_package_item_payload(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "image")
            visual.data["name"] = "logo"
            visual.save()

            image_path = root / "logo.png"
            image_path.write_bytes(b"png")
            registered_name = add_image(project, image_path)

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "logo",
                    "chart:image.sourceFile=logo.png",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            visual_json = json.loads((visual.folder / "visual.json").read_text(encoding="utf-8-sig"))
            image_props = visual_json["visual"]["objects"]["image"][0]["properties"]
            self.assertEqual(
                image_props["sourceType"]["expr"]["Literal"]["Value"],
                "'image'",
            )
            resource_ref = image_props["sourceFile"]["image"]["url"]["expr"]["ResourcePackageItem"]
            self.assertEqual(resource_ref["PackageName"], "RegisteredResources")
            self.assertEqual(resource_ref["ItemName"], registered_name)
            self.assertEqual(
                image_props["sourceFile"]["image"]["name"]["expr"]["Literal"]["Value"],
                "'logo.png'",
            )

    def test_visual_create_image_accepts_registered_resource_name(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            image_path = root / "logo.png"
            image_path.write_bytes(b"png")
            registered_name = add_image(project, image_path)

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "--image",
                    "logo.png",
                    "--name",
                    "heroLogo",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            project.clear_caches()
            created = project.find_visual(project.find_page("Demo"), "heroLogo")
            self.assertEqual(created.visual_type, "image")
            props = created.data["visual"]["objects"]["image"][0]["properties"]["sourceFile"]["image"]
            self.assertEqual(
                props["url"]["expr"]["ResourcePackageItem"]["ItemName"],
                registered_name,
            )


class ModelRenameRegressionTests(unittest.TestCase):
    def test_model_table_create_rejects_reserved_measures_name(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                [
                    "model",
                    "table",
                    "create",
                    "Measures",
                    'ROW("x", 1)',
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn("reserved table name", result.stdout)

    def test_model_table_create_rejects_documented_reserved_device_name(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                [
                    "model",
                    "table",
                    "create",
                    "CON",
                    'ROW("x", 1)',
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn("reserved table name", result.stdout)

    def test_model_measure_and_column_create_reject_reserved_names(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            measure_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "create",
                    "Customers",
                    "PRN",
                    "1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            column_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "create",
                    "Customers",
                    "COM1",
                    "1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(measure_result.exit_code, 1)
            self.assertIn("reserved measure name", measure_result.stdout)
            self.assertEqual(column_result.exit_code, 1)
            self.assertIn("reserved column name", column_result.stdout)

    def test_model_table_rename_updates_model_and_visual_refs(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: amount
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount

\tmeasure Revenue = SUM(Sales[Amount])
                """,
            )
            write_model_table(
                root,
                "Metrics.tmdl",
                """
table Metrics
\tmeasure 'Revenue Copy' = SUM(Sales[Amount])
                """,
            )

            page = project.create_page("Demo")
            visual = project.create_visual(page, "tableEx")
            visual.data["name"] = "salesTable"
            visual.data["visual"]["query"]["queryState"] = {
                "Values": {
                    "projections": [
                        {
                            "field": {
                                "Column": {
                                    "Expression": {"SourceRef": {"Entity": "Sales"}},
                                    "Property": "Amount",
                                }
                            },
                            "queryRef": "Sales.Amount",
                        }
                    ]
                }
            }
            visual.save()

            result = runner.invoke(
                app,
                [
                    "model",
                    "table",
                    "rename",
                    "Sales",
                    "Revenue Sales",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            renamed_path = root / "Sample.SemanticModel" / "definition" / "tables" / "Revenue_Sales.tmdl"
            self.assertTrue(renamed_path.exists())
            self.assertFalse((root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl").exists())
            renamed_content = renamed_path.read_text(encoding="utf-8-sig")
            self.assertIn("table 'Revenue Sales'", renamed_content)
            self.assertIn("SUM('Revenue Sales'[Amount])", renamed_content)
            metrics_content = (root / "Sample.SemanticModel" / "definition" / "tables" / "Metrics.tmdl").read_text(encoding="utf-8-sig")
            self.assertIn("SUM('Revenue Sales'[Amount])", metrics_content)

            visual_data = json.loads((visual.folder / "visual.json").read_text(encoding="utf-8-sig"))
            projection = visual_data["visual"]["query"]["queryState"]["Values"]["projections"][0]
            self.assertEqual(projection["queryRef"], "Revenue Sales.Amount")
            self.assertEqual(
                projection["field"]["Column"]["Expression"]["SourceRef"]["Entity"],
                "Revenue Sales",
            )


class FilterAndVisualTypeRegressionTests(unittest.TestCase):
    def test_filter_create_uses_double_literal_for_currency_measure(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Measures_Table.tmdl",
                """
table 'Measures Table'
\tmeasure 'Total Revenue' = 1
\t\tformatString: $#,##0
                """,
            )

            result = runner.invoke(
                app,
                [
                    "filter",
                    "create",
                    "Measures Table.Total Revenue",
                    "--mode",
                    "advanced",
                    "--operator",
                    "greater-than",
                    "--value",
                    "0",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            report = _read_json(root / "Sample.Report" / "definition" / "report.json")
            literal = (
                report["filterConfig"]["filters"][0]["filter"]["Where"][0]["Condition"]["Comparison"]["Right"]["Literal"]["Value"]
            )
            self.assertEqual(literal, "0.0D")

    def test_visual_create_stacked_bar_uses_clustered_bar_internal_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "stackedBarChart",
                    "--name",
                    "chart1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            project.clear_caches()
            visual = project.find_visual(project.find_page("Demo"), "chart1")
            self.assertEqual(visual.visual_type, "clusteredBarChart")

    def test_visual_set_type_changes_visual_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "tableEx")
            visual.data["name"] = "grid"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "grid",
                    "type=clusteredColumnChart",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = json.loads((visual.folder / "visual.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(updated["visual"]["visualType"], "clusteredColumnChart")
