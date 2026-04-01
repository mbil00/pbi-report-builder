from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from tests.cli_regressions_support import make_project, write_model_table


SALES_MODEL = """
table 'Sales'
    column 'Amount'
        dataType: int64
    column 'OrderDate'
        dataType: dateTime
    column 'Status'
        dataType: string
    measure 'Total Revenue' = SUM ( Sales[Amount] )
        formatString: #,0
"""


class CliSchemaGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _make_modeled_project(self, root: Path):
        project = make_project(root, with_model=True)
        write_model_table(root, "Sales.tmdl", SALES_MODEL)
        return project

    def test_visual_bind_rejects_unknown_model_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            visual.save()

            result = self.runner.invoke(
                app,
                [
                    "visual",
                    "bind",
                    "Demo",
                    "card1",
                    "Data",
                    "Sales.Total Reveneu",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Field "Total Reveneu" not found in table "Sales"', result.stdout)

    def test_page_drillthrough_set_rejects_unknown_model_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            project.create_page("Demo")

            result = self.runner.invoke(
                app,
                [
                    "page",
                    "drillthrough",
                    "set",
                    "Demo",
                    "Sales.OrderDat",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Field "OrderDat" not found in table "Sales"', result.stdout)

    def test_visual_format_measure_mode_requires_measure_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = self.runner.invoke(
                app,
                [
                    "visual",
                    "format",
                    "set",
                    "Demo",
                    "chart1",
                    "dataPoint.fill",
                    "--mode",
                    "measure",
                    "--source",
                    "Sales.Status",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('requires a measure source', result.stdout)

    def test_visual_format_gradient_requires_numeric_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = self.runner.invoke(
                app,
                [
                    "visual",
                    "format",
                    "set",
                    "Demo",
                    "chart1",
                    "dataPoint.fill",
                    "--mode",
                    "gradient",
                    "--source",
                    "Sales.Status",
                    "--min-color",
                    "#FF0000",
                    "--min-value",
                    "0",
                    "--max-color",
                    "#00FF00",
                    "--max-value",
                    "100",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('requires a numeric source', result.stdout)

    def test_visual_format_rejects_non_color_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_modeled_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "clusteredColumnChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = self.runner.invoke(
                app,
                [
                    "visual",
                    "format",
                    "set",
                    "Demo",
                    "chart1",
                    "legend.show",
                    "--mode",
                    "measure",
                    "--source",
                    "Sales.Total Revenue",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Conditional formatting target "legend.show"', result.stdout)
            self.assertIn("not a color property", result.stdout)

    def test_filter_create_relative_requires_date_time_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_modeled_project(root)

            result = self.runner.invoke(
                app,
                [
                    "filter",
                    "create",
                    "Sales.Status",
                    "--mode",
                    "relative",
                    "--operator",
                    "InLast",
                    "--count",
                    "7",
                    "--unit",
                    "Days",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Relative filters require a date/time column', result.stdout)

    def test_filter_create_rejects_unknown_model_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_modeled_project(root)

            result = self.runner.invoke(
                app,
                [
                    "filter",
                    "create",
                    "Sales.OrderDat",
                    "--mode",
                    "categorical",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Field "OrderDat" not found in table "Sales"', result.stdout)
