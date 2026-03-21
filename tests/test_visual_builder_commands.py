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
            self.assertIn("Title:", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "revenueChart")
            self.assertTrue(get_property(visual.data, "title.show", VISUAL_PROPERTIES))
            self.assertEqual(get_property(visual.data, "title.text", VISUAL_PROPERTIES), "Revenue by Year")
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
            self.assertTrue(get_property(visual.data, "title.show", VISUAL_PROPERTIES))
            self.assertEqual(get_property(visual.data, "title.text", VISUAL_PROPERTIES), "Year")
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

    def test_visual_create_donut_builders_require_category_and_measure_value(self) -> None:
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
                    "donutChart",
                    "--name",
                    "revenueDonut",
                    "--bind",
                    "Category=Sales.Region",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--preset",
                    "chart",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "revenueDonut")
            self.assertTrue(get_property(visual.data, "legend.show", VISUAL_PROPERTIES))
            self.assertEqual(get_property(visual.data, "title.text", VISUAL_PROPERTIES), "Revenue by Region")

    def test_visual_create_slicer_rejects_measure_bindings(self) -> None:
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
                    "slicer",
                    "--name",
                    "badSlicer",
                    "--bind",
                    "Values=Sales.Revenue",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Role "Values" must use a column', result.stdout)

    def test_visual_create_card_rejects_column_data_bindings(self) -> None:
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
                    "cardVisual",
                    "--name",
                    "badCard",
                    "--bind",
                    "Data=Date.Year",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn('Role "Data" must use a measure', result.stdout)

    def test_visual_create_auto_sorts_chart_category_from_sort_by_column(self) -> None:
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
\tcolumn MonthName
\t\tdataType: string
\t\tsourceColumn: MonthName
\t\tsortByColumn: MonthNumber

\tcolumn MonthNumber
\t\tdataType: int64
\t\tsourceColumn: MonthNumber
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
                    "monthlyRevenue",
                    "--bind",
                    "Category=Date.MonthName",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Date.MonthNumber Ascending", result.stdout)
            self.assertIn("(auto)", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "monthlyRevenue")
            self.assertEqual(
                reloaded.get_sort(visual),
                [("Date", "MonthNumber", "column", "Ascending")],
            )

    def test_visual_create_auto_sorts_slicer_values_from_sort_by_column(self) -> None:
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
\tcolumn MonthName
\t\tdataType: string
\t\tsourceColumn: MonthName
\t\tsortByColumn: MonthNumber

\tcolumn MonthNumber
\t\tdataType: int64
\t\tsourceColumn: MonthNumber
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
                    "monthSlicer",
                    "--bind",
                    "Values=Date.MonthName",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Date.MonthNumber Ascending", result.stdout)
            self.assertIn("(auto)", result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            visual = reloaded.find_visual(page, "monthSlicer")
            self.assertEqual(
                reloaded.get_sort(visual),
                [("Date", "MonthNumber", "column", "Ascending")],
            )

    def test_visual_create_explicit_sort_and_no_auto_sort_override_default_inference(self) -> None:
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
\tcolumn MonthName
\t\tdataType: string
\t\tsourceColumn: MonthName
\t\tsortByColumn: MonthNumber

\tcolumn MonthNumber
\t\tdataType: int64
\t\tsourceColumn: MonthNumber
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

            explicit_result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "clusteredColumnChart",
                    "--name",
                    "explicitSortChart",
                    "--bind",
                    "Category=Date.MonthName",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--sort",
                    "Date.MonthName",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(explicit_result.exit_code, 0, explicit_result.stdout)
            self.assertIn("Sort: Date.MonthName Ascending", explicit_result.stdout)
            self.assertNotIn("Sort: Date.MonthName Ascending (auto)", explicit_result.stdout)

            disabled_result = runner.invoke(
                app,
                [
                    "visual",
                    "create",
                    "Demo",
                    "clusteredColumnChart",
                    "--name",
                    "manualChart",
                    "--bind",
                    "Category=Date.MonthName",
                    "--bind",
                    "Y=Sales.Revenue",
                    "--no-auto-sort",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(disabled_result.exit_code, 0, disabled_result.stdout)
            self.assertNotIn("Sort:", disabled_result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            page = reloaded.find_page("Demo")
            explicit = reloaded.find_visual(page, "explicitSortChart")
            manual = reloaded.find_visual(page, "manualChart")
            self.assertEqual(
                reloaded.get_sort(explicit),
                [("Date", "MonthName", "column", "Ascending")],
            )
            self.assertEqual(reloaded.get_sort(manual), [])


if __name__ == "__main__":
    unittest.main()
