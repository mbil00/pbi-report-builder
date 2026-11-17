from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.filters import (
    TupleField,
    _format_literal,
    add_range_filter,
    add_tuple_filter,
    get_filters,
    parse_filter,
    remove_filter,
)
from pbi.model import _parse_tmdl_name
from pbi.project import Project
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from pbi.report_authoring import ReportAuthoring
from tests.support import make_project


class FilterModelRegressionTests(unittest.TestCase):
    def test_tuple_filter_can_be_removed_by_component_field(self) -> None:
        data: dict = {}
        add_tuple_filter(
            data,
            [[TupleField("Product", "Color", "Red"), TupleField("Product", "Size", "Large")]],
        )

        self.assertEqual(remove_filter(data, "Product.Color"), 1)

    def test_range_filter_respects_locked_flag(self) -> None:
        data: dict = {}
        add_range_filter(data, "Sales", "Revenue", min_val="1", is_locked=True)
        self.assertTrue(data["filterConfig"]["filters"][0]["isLockedInViewMode"])

    def test_parse_filter_understands_aggregation_field_refs(self) -> None:
        filter_obj = {
            "name": "aggFilter",
            "type": "Advanced",
            "field": {
                "Aggregation": {
                    "Expression": {
                        "Measure": {
                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                            "Property": "Total Revenue",
                        }
                    },
                    "Function": 0,
                }
            },
            "filter": {"Where": []},
        }

        info = parse_filter(filter_obj)
        self.assertEqual(info.field_entity, "Sales")
        self.assertEqual(info.field_prop, "Total Revenue")

    def test_untyped_literals_stay_strings(self) -> None:
        self.assertEqual(_format_literal("00123"), "'00123'")
        self.assertEqual(_format_literal("2025-01-01"), "'2025-01-01'")

    def test_parse_tmdl_name_handles_escaped_apostrophes(self) -> None:
        self.assertEqual(_parse_tmdl_name("'Bob''s Revenue' ="), "Bob's Revenue")

    def test_filter_create_uses_named_scope_and_repeatable_values(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            ReportAuthoring(project).create_page("Demo")

            result = runner.invoke(
                app,
                [
                    "filter",
                    "create",
                    "Product.Category",
                    "--mode",
                    "include",
                    "--value",
                    "Bikes",
                    "--value",
                    "Accessories",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            report_data = Project.find(root / "Sample.pbip").get_report_meta()
            filters = get_filters(report_data)
            self.assertEqual(len(filters), 1)
            info = parse_filter(filters[0], "report")
            self.assertEqual(info.filter_type, "Include")

    def test_filter_delete_accepts_force(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            ReportAuthoring(project).create_page("Demo")

            create_result = runner.invoke(
                app,
                [
                    "filter",
                    "create",
                    "Product.Category",
                    "--mode",
                    "include",
                    "--value",
                    "Bikes",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            delete_result = runner.invoke(
                app,
                [
                    "filter",
                    "delete",
                    "Product.Category",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            report_data = Project.find(root / "Sample.pbip").get_report_meta()
            self.assertEqual(get_filters(report_data), [])


class DrillthroughRegressionTests(unittest.TestCase):
    def test_cli_uses_canonical_table_name_for_drillthrough_fields(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            ReportAuthoring(project).create_page("Demo")

            result = runner.invoke(
                app,
                [
                    "page",
                    "drillthrough",
                    "set",
                    "Demo",
                    "cust.Region",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            page = Project.find(root / "Sample.pbip").find_page("Demo")
            entity = page.data["pageBinding"]["parameters"][0]["fieldExpr"]["Column"]["Expression"]["SourceRef"]["Entity"]
            self.assertEqual(entity, "Customers")


class VisualSetRegressionTests(unittest.TestCase):
    def test_visual_move_and_resize_use_named_geometry_options(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual", x=0, y=0, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            move_result = runner.invoke(
                app,
                [
                    "visual",
                    "move",
                    "Demo",
                    "card1",
                    "--x",
                    "25",
                    "--y",
                    "40",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(move_result.exit_code, 0, move_result.stdout)

            resize_result = runner.invoke(
                app,
                [
                    "visual",
                    "resize",
                    "Demo",
                    "card1",
                    "--width",
                    "220",
                    "--height",
                    "120",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(resize_result.exit_code, 0, resize_result.stdout)

            updated = Project.find(root / "Sample.pbip").find_visual(Project.find(root / "Sample.pbip").find_page("Demo"), "card1")
            self.assertEqual(updated.position["x"], 25)
            self.assertEqual(updated.position["y"], 40)
            self.assertEqual(updated.position["width"], 220)
            self.assertEqual(updated.position["height"], 120)

    def test_visual_paste_style_supports_batch_targeting_by_visual_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source_page = ReportAuthoring(project).create_page("Source")
            target_page = ReportAuthoring(project).create_page("Target")

            source = ReportAuthoring(project).create_visual(source_page, "cardVisual")
            source.data["name"] = "sourceCard"
            set_property(source.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(source.data, "title.show", "true", VISUAL_PROPERTIES)
            source.save()

            for name in ("targetA", "targetB"):
                visual = ReportAuthoring(project).create_visual(target_page, "cardVisual")
                visual.data["name"] = name
                visual.save()

            chart = ReportAuthoring(project).create_visual(target_page, "barChart")
            chart.data["name"] = "chart1"
            chart.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "paste-style",
                    "Source",
                    "sourceCard",
                    "--to-page",
                    "Target",
                    "--visual-type",
                    "cardVisual",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn('2', result.stdout)
            updated = Project.find(root / "Sample.pbip")
            target_page = updated.find_page("Target")
            for name in ("targetA", "targetB"):
                visual = updated.find_visual(target_page, name)
                self.assertEqual(
                    get_property(visual.data, "background.color", VISUAL_PROPERTIES),
                    "#123456",
                )
                self.assertTrue(get_property(visual.data, "title.show", VISUAL_PROPERTIES))
            chart = updated.find_visual(target_page, "chart1")
            self.assertIsNone(get_property(chart.data, "background.color", VISUAL_PROPERTIES))

    def test_visual_arrange_row_positions_visuals_left_to_right(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            specs = [("card1", 100), ("card2", 120), ("card3", 80)]
            for name, width in specs:
                visual = ReportAuthoring(project).create_visual(page, "cardVisual", width=width, height=50)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "row",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "--x",
                    "10",
                    "--y",
                    "20",
                    "--gap",
                    "15",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card2").position["x"], 125)
            self.assertEqual(updated.find_visual(page, "card3").position["x"], 260)

    def test_visual_arrange_grid_wraps_rows_using_visual_sizes(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            specs = [
                ("card1", 100, 50),
                ("card2", 120, 60),
                ("card3", 80, 40),
                ("card4", 90, 70),
            ]
            for name, width, height in specs:
                visual = ReportAuthoring(project).create_visual(page, "cardVisual", width=width, height=height)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "grid",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "card4",
                    "--columns",
                    "2",
                    "--x",
                    "10",
                    "--y",
                    "20",
                    "--column-gap",
                    "15",
                    "--row-gap",
                    "25",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card2").position["x"], 125)
            self.assertEqual(updated.find_visual(page, "card2").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card3").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card3").position["y"], 105)
            self.assertEqual(updated.find_visual(page, "card4").position["x"], 105)
            self.assertEqual(updated.find_visual(page, "card4").position["y"], 105)

    def test_visual_arrange_column_positions_visuals_top_to_bottom(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            specs = [("card1", 50), ("card2", 60), ("card3", 40)]
            for name, height in specs:
                visual = ReportAuthoring(project).create_visual(page, "cardVisual", width=100, height=height)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "column",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "--x",
                    "30",
                    "--y",
                    "10",
                    "--gap",
                    "12",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 30)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 10)
            self.assertEqual(updated.find_visual(page, "card2").position["y"], 72)
            self.assertEqual(updated.find_visual(page, "card3").position["y"], 144)

    def test_visual_set_accepts_raw_property_aliases(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "card1",
                    "dropShadow.show=true",
                    "label.show=true",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            visual = Project.find(root / "Sample.pbip").find_visual(Project.find(root / "Sample.pbip").find_page("Demo"), "card1")
            self.assertTrue(get_property(visual.data, "shadow.show", VISUAL_PROPERTIES))
            self.assertTrue(get_property(visual.data, "cardLabel.show", VISUAL_PROPERTIES))

    def test_visual_set_suggests_nearby_property_names(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "chart1",
                    "dataLabel.show=true",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Did you mean", result.stdout)
            self.assertIn('"dataLabels.show"', result.stdout)

    def test_visual_set_unknown_chart_property_shows_exact_chart_prefix_hint(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "chart1",
                    "legend.seriesOrder=descending",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn('chart:legend.seriesOrder', result.stdout)
            self.assertIn('For a raw', result.stdout)

    def test_visual_properties_can_filter_and_show_aliases(self) -> None:
        runner = CliRunner()

        result = runner.invoke(
            app,
            [
                "visual",
                "properties",
                "--match",
                "dropShadow",
                "--show-aliases",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("shadow.show", result.stdout)
        self.assertIn("Accepted", result.stdout)
        self.assertIn("dropShadow", result.stdout)

    def test_visual_set_all_prevalidates_and_does_not_partially_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            for idx in range(2):
                visual = ReportAuthoring(project).create_visual(page, "cardVisual")
                visual.data["name"] = f"card{idx}"
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set-all",
                    "background.show=true",
                    "notARealProperty=true",
                    "--page", "Demo",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            for visual in restored.get_visuals(page):
                self.assertIsNone(get_property(visual.data, "background.show", VISUAL_PROPERTIES))

    def test_visual_set_all_supports_dry_run(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            for idx in range(2):
                visual = ReportAuthoring(project).create_visual(page, "cardVisual")
                visual.data["name"] = f"card{idx}"
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set-all",
                    "background.show=true",
                    "--page", "Demo",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertIn("background.show", result.stdout)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            for visual in restored.get_visuals(page):
                self.assertIsNone(get_property(visual.data, "background.show", VISUAL_PROPERTIES))

    def test_visual_set_all_skips_noop_writes(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            for idx in range(2):
                visual = ReportAuthoring(project).create_visual(page, "cardVisual")
                visual.data["name"] = f"card{idx}"
                set_property(visual.data, "background.show", "true", VISUAL_PROPERTIES)
                visual.save()

            real_write_json = __import__("pbi.project", fromlist=["_write_json"])._write_json
            visual_writes = 0

            def counted_write_json(path, data, **kwargs):
                nonlocal visual_writes
                if path.name == "visual.json":
                    visual_writes += 1
                return real_write_json(path, data, **kwargs)

            with mock.patch("pbi.project._write_json", side_effect=counted_write_json):
                result = runner.invoke(
                    app,
                    [
                        "visual",
                        "set-all",
                        "background.show=true",
                        "--page", "Demo",
                        "--project",
                        str(root / "Sample.pbip"),
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No changes applied", result.stdout)
            self.assertEqual(visual_writes, 0)

    def test_visual_sort_cli_uses_get_set_clear_subcommands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            set_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "set",
                    "Demo",
                    "chart1",
                    "Sales.Total Revenue",
                    "--direction",
                    "asc",
                    "--field-type",
                    "measure",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            get_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "get",
                    "Demo",
                    "chart1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Ascending", get_result.stdout)

            clear_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "clear",
                    "Demo",
                    "chart1",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

    def test_visual_sort_set_rejects_visuals_without_sort_support(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "shape")
            visual.data["name"] = "shape1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "set",
                    "Demo",
                    "shape1",
                    "Product.Category",
                    "--field-type",
                    "column",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("does not support sorting", result.stdout)

    def test_visual_set_rejects_action_properties_for_visuals_without_action_support(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "chart1",
                    "action.type=WebUrl",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("does not expose visual actions", result.stdout)
