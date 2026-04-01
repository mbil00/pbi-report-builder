from __future__ import annotations

import tempfile
import unittest
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
from pbi.project import Project, _read_json, _write_json
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from tests.cli_regressions_support import make_project


class VisualDiffRegressionTests(unittest.TestCase):
    def test_visual_diff_uses_canonical_exported_spec(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")

            left = project.create_visual(page, "tableEx")
            left.data["name"] = "left"
            project.add_binding(left, "Values", "Product", "Category")
            project.set_sort(left, "Product", "Category", descending=True)
            add_range_filter(left.data, "Sales", "Amount", min_val="10", max_val="20")
            left.data["visual"].setdefault("query", {})["queryMetadata"] = {"foo": "left"}
            left.save()

            right = project.create_visual(page, "tableEx")
            right.data["name"] = "right"
            project.add_binding(right, "Values", "Product", "Brand")
            project.set_sort(right, "Product", "Brand", descending=False)
            add_range_filter(right.data, "Sales", "Quantity", min_val="20", max_val="30")
            right.data["visual"].setdefault("query", {})["queryMetadata"] = {"foo": "right"}
            right.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "diff",
                    "Demo",
                    "left",
                    "Demo",
                    "right",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("bindings.Values", result.stdout)
            self.assertIn("Product.Category", result.stdout)
            self.assertIn("Product.Brand", result.stdout)
            self.assertIn("sort", result.stdout)
            self.assertIn("Descending", result.stdout)
            self.assertIn("Ascending", result.stdout)
            self.assertIn("filters[0].field", result.stdout)
            self.assertIn("Sales.Amount", result.stdout)
            self.assertIn("Sales.Quantity", result.stdout)
            self.assertIn("filters[0].values[0]", result.stdout)
            self.assertIn("pbir.visual.query.quer", result.stdout)
            self.assertIn("left", result.stdout)
            self.assertIn("right", result.stdout)


class VisualGetRegressionTests(unittest.TestCase):
    def test_visual_index_references_work_with_bare_and_prefixed_numbers(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            first = project.create_visual(page, "textSlicer", x=0, y=0)
            second = project.create_visual(page, "cardVisual", x=100, y=0)
            first.data["name"] = "7ac9f370abc"
            second.data["name"] = "26d0c6f4bee8"
            first.save()
            second.save()

            result_bare = runner.invoke(
                app,
                ["visual", "get", "Demo", "2", "visualType", "--project", str(root / "Sample.pbip")],
            )
            result_prefixed = runner.invoke(
                app,
                ["visual", "get", "Demo", "#2", "visualType", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result_bare.exit_code, 0, result_bare.stdout)
            self.assertIn("cardVisual", result_bare.stdout)
            self.assertEqual(result_prefixed.exit_code, 0, result_prefixed.stdout)
            self.assertIn("cardVisual", result_prefixed.stdout)

    def test_visual_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "background.color", "#123456", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "card1",
                    "title.show",
                    "background.color",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("True", result.stdout)
            self.assertIn("#123456", result.stdout)

    def test_visual_get_all_props_lists_core_and_object_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=300, height=100)
            visual.data["name"] = "card1"
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "background.color", "#123456", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "get", "Demo", "card1", "--all-props", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("position.x", result.stdout)
            self.assertIn("position.y", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertIn("10", result.stdout)

    def test_visual_get_defaults_resolves_known_default_values(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "chart1",
                    "background.show",
                    "title.show",
                    "tooltip.show",
                    "--defaults",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.show", result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("tooltip.show", result.stdout)
            self.assertIn("False", result.stdout)
            self.assertIn("True", result.stdout)
            self.assertIn("default", result.stdout)

    def test_visual_get_defaults_marks_explicit_values_over_known_defaults(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "background.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "card1",
                    "background.show",
                    "layout.backgroundShow",
                    "--defaults",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.show", result.stdout)
            self.assertIn("layout.backgroundShow", result.stdout)
            self.assertIn("explicit", result.stdout)
            self.assertIn("default", result.stdout)
            self.assertIn("True", result.stdout)

    def test_visual_get_overview_uses_canonical_property_names(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "shadow.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "cardShape.radius", "5", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "get", "Demo", "card1", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("shadow.show", result.stdout)
            self.assertIn("cardShape.radius", result.stdout)
            self.assertNotIn("dropShadow.show", result.stdout)
            self.assertNotIn("shapeCustomRectangle.rectangleRoundedCurve", result.stdout)

    def test_visual_get_page_lists_explicit_properties_for_matching_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            card = project.create_visual(page, "cardVisual")
            chart = project.create_visual(page, "barChart")
            card.data["name"] = "card1"
            chart.data["name"] = "chart1"
            set_property(card.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(chart.data, "title.show", "true", VISUAL_PROPERTIES)
            card.save()
            chart.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get-page",
                    "Demo",
                    "--visual-type",
                    "cardVisual",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("card1", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertNotIn("chart1", result.stdout)

    def test_visual_diff_reports_differences_between_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page_a = project.create_page("Demo A")
            page_b = project.create_page("Demo B")
            left = project.create_visual(page_a, "cardVisual", x=10, y=20, width=300, height=100)
            right = project.create_visual(page_b, "cardVisual", x=40, y=20, width=300, height=100)
            left.data["name"] = "cardLeft"
            right.data["name"] = "cardRight"
            set_property(left.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(right.data, "background.color", "#654321", VISUAL_PROPERTIES)
            left.save()
            right.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "diff",
                    "Demo A",
                    "cardLeft",
                    "Demo B",
                    "cardRight",
                    "--all-props",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertIn("#654321", result.stdout)
            self.assertIn("position.x", result.stdout)
            self.assertIn("10", result.stdout)
            self.assertIn("40", result.stdout)

    def test_page_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo", width=1440, height=900, display_option="FitToWidth")

            result = runner.invoke(
                app,
                [
                    "page",
                    "get",
                    "Demo",
                    "width",
                    "displayOption",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("width", result.stdout)
            self.assertIn("1440", result.stdout)
            self.assertIn("displayOption", result.stdout)
            self.assertIn("FitToWidth", result.stdout)

    def test_report_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            report_path = project.definition_folder / "report.json"
            data = _read_json(report_path)
            data["settings"] = {
                "pagesPosition": "Bottom",
                "useEnhancedTooltips": True,
            }
            _write_json(report_path, data)

            result = runner.invoke(
                app,
                [
                    "report",
                    "get",
                    "layoutOptimization",
                    "settings.pagesPosition",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("layoutOptimization", result.stdout)
            self.assertIn("None", result.stdout)
            self.assertIn("settings.pagesPosition", result.stdout)
            self.assertIn("Bottom", result.stdout)


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
            project.create_page("Demo")

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
            project.create_page("Demo")

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
            project.create_page("Demo")

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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=0, y=0, width=100, height=50)
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
            source_page = project.create_page("Source")
            target_page = project.create_page("Target")

            source = project.create_visual(source_page, "cardVisual")
            source.data["name"] = "sourceCard"
            set_property(source.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(source.data, "title.show", "true", VISUAL_PROPERTIES)
            source.save()

            for name in ("targetA", "targetB"):
                visual = project.create_visual(target_page, "cardVisual")
                visual.data["name"] = name
                visual.save()

            chart = project.create_visual(target_page, "barChart")
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
            page = project.create_page("Demo")
            specs = [("card1", 100), ("card2", 120), ("card3", 80)]
            for name, width in specs:
                visual = project.create_visual(page, "cardVisual", width=width, height=50)
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
            page = project.create_page("Demo")
            specs = [
                ("card1", 100, 50),
                ("card2", 120, 60),
                ("card3", 80, 40),
                ("card4", 90, 70),
            ]
            for name, width, height in specs:
                visual = project.create_visual(page, "cardVisual", width=width, height=height)
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
            page = project.create_page("Demo")
            specs = [("card1", 50), ("card2", 60), ("card3", 40)]
            for name, height in specs:
                visual = project.create_visual(page, "cardVisual", width=100, height=height)
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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
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
            page = project.create_page("Demo")
            for idx in range(2):
                visual = project.create_visual(page, "cardVisual")
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
            page = project.create_page("Demo")
            for idx in range(2):
                visual = project.create_visual(page, "cardVisual")
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

    def test_visual_sort_cli_uses_get_set_clear_subcommands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "shape")
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
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
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

class TestVisualInspect(unittest.TestCase):
    """pbi visual inspect deep dump command."""

    def test_inspect_shows_object_properties(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "tableEx")

            # Set some chart objects
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "My Table", VISUAL_PROPERTIES)

            # Add conditional formatting to create objects
            value = build_gradient_format(
                "T", "F", GradientStop("#FFF", 0), GradientStop("#000", 100),
            )
            set_conditional_format(visual.data, "values", "backColor", value, column="T.F")
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("values", result.stdout)
            self.assertIn("backColor", result.stdout)
            self.assertIn("metadata=T.F", result.stdout)

    def test_inspect_search_filters(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "card")
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "Hello", VISUAL_PROPERTIES)
            set_property(visual.data, "border.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--search", "title",
                 "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            # Should show title properties but not border
            self.assertIn("title", result.stdout.lower())

    def test_inspect_json_output(self):
        import json

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "card")
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--json",
                 "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            data = json.loads(result.stdout)
            self.assertIsInstance(data, dict)

class TestVisualAudit(unittest.TestCase):
    """IMP-01: visual audit collects properties and detects inconsistencies."""

    def test_collect_visual_property_rows_returns_tuples(self):
        from pbi.commands.visuals.helpers import collect_visual_property_rows

        data = {
            "visual": {
                "visualType": "slicer",
                "visualContainerObjects": {
                    "border": [{"properties": {
                        "show": {"expr": {"Literal": {"Value": "true"}}},
                        "radius": {"expr": {"Literal": {"Value": "6D"}}},
                    }}]
                },
            }
        }
        rows = collect_visual_property_rows(data, include_core=False)
        prop_names = [r[0] for r in rows]
        self.assertIn("border.show", prop_names)
        self.assertIn("border.radius", prop_names)
