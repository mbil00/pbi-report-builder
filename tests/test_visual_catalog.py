from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.project import Project
from pbi.roles import (
    get_visual_type_info,
    is_known_visual_type,
    normalize_visual_role,
    normalize_visual_type,
)
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA


class VisualCatalogTests(unittest.TestCase):
    def test_aliases_normalize_to_canonical_visual_types(self) -> None:
        self.assertEqual(normalize_visual_type("card"), "cardVisual")
        self.assertEqual(normalize_visual_type("table"), "tableEx")
        self.assertEqual(normalize_visual_type("matrix"), "pivotTable")
        self.assertEqual(normalize_visual_type("button"), "actionButton")

    def test_sample_backed_visual_types_are_known(self) -> None:
        self.assertTrue(is_known_visual_type("textSlicer"))
        self.assertTrue(is_known_visual_type("qnaVisual"))

        text_slicer = get_visual_type_info("textSlicer")
        self.assertIsNotNone(text_slicer)
        self.assertEqual(text_slicer.status, "role-backed")
        self.assertEqual([role["name"] for role in text_slicer.roles], ["Values"])

        qna = get_visual_type_info("qnaVisual")
        self.assertIsNotNone(qna)
        self.assertEqual(qna.status, "sample-backed")
        self.assertEqual(qna.roles, [])

        chart = get_visual_type_info("clusteredColumnChart")
        self.assertIsNotNone(chart)
        self.assertEqual(chart.status, "role-backed")
        self.assertTrue(chart.roles)

    def test_role_aliases_normalize_to_exported_role_names(self) -> None:
        self.assertEqual(normalize_visual_role("cardVisual", "Values"), "Data")
        self.assertEqual(normalize_visual_role("cardVisual", "data"), "Data")
        self.assertEqual(normalize_visual_role("textSlicer", "values"), "Values")
        self.assertEqual(normalize_visual_role("qnaVisual", "Question"), "Question")


class VisualCatalogCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pbip_path = self.root / "Sample.pbip"
        self.report_folder = self.root / "Sample.Report"
        self.definition = self.report_folder / "definition"
        self.pages_dir = self.definition / "pages"
        self.page_dir = self.pages_dir / "page001"
        (self.page_dir / "visuals").mkdir(parents=True)

        self.pbip_path.write_text(
            json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
            encoding="utf-8",
        )
        (self.page_dir / "page.json").write_text(
            json.dumps(
                {
                    "$schema": PAGE_SCHEMA,
                    "name": "page001",
                    "displayName": "Sales",
                    "displayOption": "FitToPage",
                    "width": 1280,
                    "height": 720,
                    "visibility": "AlwaysVisible",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.pages_dir / "pages.json").write_text(
            json.dumps(
                {
                    "$schema": PAGES_METADATA_SCHEMA,
                    "pageOrder": ["page001"],
                    "activePageName": "page001",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_visual_types_reports_sample_backed_catalog_entry(self) -> None:
        result = self.runner.invoke(app, ["visual", "types", "qnaVisual"])

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("qnaVisual", result.stdout)
        self.assertIn("sample-backed", result.stdout)

    def test_visual_create_uses_canonical_type_for_alias(self) -> None:
        result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "card", "--project", str(self.pbip_path)],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("Using canonical visual type cardVisual", result.stdout)
        self.assertIn('Created cardVisual "', result.stdout)

        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visuals = project.get_visuals(page)
        self.assertEqual(len(visuals), 1)
        self.assertEqual(visuals[0].visual_type, "cardVisual")

    def test_visual_create_accepts_sample_backed_type(self) -> None:
        result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "qnaVisual", "--project", str(self.pbip_path)],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertNotIn("not in the CLI visual catalog", result.stdout)

        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visuals = project.get_visuals(page)
        self.assertEqual(len(visuals), 1)
        self.assertEqual(visuals[0].visual_type, "qnaVisual")

    def test_visual_create_card_uses_minimal_theme_backed_payload(self) -> None:
        result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "card", "--project", str(self.pbip_path)],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)

        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visual = project.find_visual(page, "cardVisual")
        self.assertEqual(visual.data["visual"]["objects"], {})
        self.assertNotIn("visualContainerObjects", visual.data["visual"])

    def test_visual_column_rename_supports_projection_backed_multi_row_cards(self) -> None:
        create_result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "multiRowCard", "--project", str(self.pbip_path)],
        )
        self.assertEqual(create_result.exit_code, 0, create_result.stdout)

        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visual = project.find_visual(page, "multiRowCard")
        visual.data["name"] = "headerDevice"
        visual.save()
        Project.add_binding(visual, "Values", "Devices", "DeviceName")

        rename_result = self.runner.invoke(
            app,
            [
                "visual",
                "column",
                "Sales",
                "headerDevice",
                "Devices.DeviceName",
                "--rename",
                "Device Name",
                "--project",
                str(self.pbip_path),
            ],
        )

        self.assertEqual(rename_result.exit_code, 0, rename_result.stdout)
        updated = Project.find(self.pbip_path).find_visual(Project.find(self.pbip_path).find_page("Sales"), "headerDevice")
        projection = updated.data["visual"]["query"]["queryState"]["Values"]["projections"][0]
        self.assertEqual(projection["displayName"], "Device Name")

    def test_visual_bind_normalizes_card_role_alias_to_data(self) -> None:
        create_result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "card", "--project", str(self.pbip_path)],
        )
        self.assertEqual(create_result.exit_code, 0, create_result.stdout)

        bind_result = self.runner.invoke(
            app,
            [
                "visual",
                "bind",
                "Sales",
                "cardVisual",
                "Values",
                "Sales.Total Revenue",
                "--field-type",
                "measure",
                "--project",
                str(self.pbip_path),
            ],
        )

        self.assertEqual(bind_result.exit_code, 0, bind_result.stdout)
        self.assertIn("Using canonical role Data", bind_result.stdout)
        self.assertIn('cardVisual role "Data"', bind_result.stdout)

        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visual = project.find_visual(page, "cardVisual")
        query_state = visual.data["visual"]["query"]["queryState"]
        self.assertIn("Data", query_state)
        self.assertNotIn("Values", query_state)
        self.assertEqual(
            query_state["Data"]["projections"][0]["queryRef"],
            "Sales.Total Revenue",
        )

    def test_visual_bind_rejects_schema_invalid_role(self) -> None:
        create_result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "table", "--project", str(self.pbip_path)],
        )
        self.assertEqual(create_result.exit_code, 0, create_result.stdout)

        bind_result = self.runner.invoke(
            app,
            [
                "visual",
                "bind",
                "Sales",
                "tableEx",
                "Category",
                "Sales.Product",
                "--field-type",
                "column",
                "--project",
                str(self.pbip_path),
            ],
        )

        self.assertEqual(bind_result.exit_code, 1, bind_result.stdout)
        self.assertIn('Role "Category" is not supported for tableEx', bind_result.stdout)

    def test_visual_bind_allows_incremental_chart_binding(self) -> None:
        create_result = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "lineChart", "--project", str(self.pbip_path)],
        )
        self.assertEqual(create_result.exit_code, 0, create_result.stdout)

        category_result = self.runner.invoke(
            app,
            [
                "visual",
                "bind",
                "Sales",
                "lineChart",
                "Category",
                "Sales.OrderDate",
                "--field-type",
                "column",
                "--project",
                str(self.pbip_path),
            ],
        )
        self.assertEqual(category_result.exit_code, 0, category_result.stdout)

        value_result = self.runner.invoke(
            app,
            [
                "visual",
                "bind",
                "Sales",
                "lineChart",
                "Y",
                "Sales.Total Revenue",
                "--field-type",
                "measure",
                "--project",
                str(self.pbip_path),
            ],
        )
        self.assertEqual(value_result.exit_code, 0, value_result.stdout)


if __name__ == "__main__":
    unittest.main()
