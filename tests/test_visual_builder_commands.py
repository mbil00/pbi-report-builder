from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.properties import VISUAL_PROPERTIES, get_property
from pbi.project import Project
from tests.cli_regressions_support import make_project, write_model_table


class VisualBuilderCommandTests(unittest.TestCase):
    def test_visual_create_can_bind_roles_and_sort_in_one_command(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")
            write_model_table(
                root,
                "Date.tmdl",
                """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year
                """,
            )
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Amount
\t\tdataType: double
\t\tsourceColumn: Amount

\tmeasure Revenue = SUM ( Sales[Amount] )
\t\tformatString: #,0
                """,
            )

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "clusteredColumnChart",
                    "--name",
                    "revenueChart",
                    "--title",
                    "Revenue by Year",
                    "--bind",
                    "Category=Date.Year",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--sort",
                    "Date.Year",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn('Created clusteredColumnChart "revenueChart"', result.stdout)
            self.assertIn("Bindings:", result.stdout)
            self.assertIn("Category=Date.Year", result.stdout)
            self.assertIn("Y=Sales.Revenue", result.stdout)
            self.assertIn("Sort:", result.stdout)
            self.assertIn("Date.Year Ascending", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "revenueChart")
            self.assertEqual(
                reloaded.get_bindings(visual),
                [
                    ("Category", "Date", "Year", "column"),
                    ("Y", "Sales", "Revenue", "measure"),
                ],
            )
            self.assertEqual(
                reloaded.get_sort(visual),
                [("Date", "Year", "column", "Ascending")],
            )

    def test_visual_create_uses_common_type_default_sizes(self) -> None:
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
                    "clusteredColumnChart",
                    "--name",
                    "defaultSizedChart",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("@ 0,0 520x320", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "defaultSizedChart")
            self.assertEqual(visual.position["width"], 520)
            self.assertEqual(visual.position["height"], 320)

    def test_visual_create_builder_rejects_invalid_roles_for_role_backed_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Amount
\t\tdataType: double
\t\tsourceColumn: Amount
                """,
            )

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "tableEx",
                    "--name",
                    "badTable",
                    "--bind",
                    "Category=Sales.Amount",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Role "Category" is not modeled for tableEx', result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            with self.assertRaises(ValueError):
                reloaded.find_visual(page, "badTable")

    def test_visual_create_chart_preset_applies_chart_defaults(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")
            write_model_table(
                root,
                "Date.tmdl",
                """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year
                """,
            )
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure Revenue = 1
\t\tformatString: #,0
                """,
            )

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "clusteredColumnChart",
                    "--name",
                    "revenueChart",
                    "--bind",
                    "Category=Date.Year",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--preset",
                    "chart",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Preset:", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "revenueChart")
            self.assertTrue(get_property(visual.data, "background.show", VISUAL_PROPERTIES))
            self.assertTrue(get_property(visual.data, "border.show", VISUAL_PROPERTIES))
            self.assertEqual(get_property(visual.data, "border.radius", VISUAL_PROPERTIES), 6)
            self.assertFalse(get_property(visual.data, "header.show", VISUAL_PROPERTIES))
            self.assertFalse(get_property(visual.data, "legend.show", VISUAL_PROPERTIES))

    def test_visual_create_chart_preset_keeps_legend_for_series_bound_charts(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")
            write_model_table(
                root,
                "Date.tmdl",
                """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year
                """,
            )
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Region
\t\tdataType: string
\t\tsourceColumn: Region

\tmeasure Revenue = 1
\t\tformatString: #,0
                """,
            )

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "clusteredColumnChart",
                    "--name",
                    "seriesChart",
                    "--bind",
                    "Category=Date.Year",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--bind",
                    "Series=Sales.Region",
                    "--preset",
                    "chart",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "seriesChart")
            self.assertTrue(get_property(visual.data, "legend.show", VISUAL_PROPERTIES))

    def test_visual_create_slicer_preset_hides_visual_and_slicer_headers(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")
            write_model_table(
                root,
                "Date.tmdl",
                """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year
                """,
            )

            result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "slicer",
                    "--name",
                    "yearSlicer",
                    "--bind",
                    "Values=Date.Year",
                    "--preset",
                    "slicer",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "yearSlicer")
            self.assertFalse(get_property(visual.data, "header.show", VISUAL_PROPERTIES))
            self.assertFalse(get_property(visual.data, "slicerHeader.show", VISUAL_PROPERTIES))
            self.assertTrue(get_property(visual.data, "background.show", VISUAL_PROPERTIES))

    def test_visual_create_rejects_incompatible_preset(self) -> None:
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
                    "cardVisual",
                    "--name",
                    "badCard",
                    "--preset",
                    "table",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Preset "table" is not supported for cardVisual', result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            with self.assertRaises(ValueError):
                reloaded.find_visual(page, "badCard")


if __name__ == "__main__":
    unittest.main()
