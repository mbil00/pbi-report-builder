from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.cli import app
from pbi.export import export_yaml
from pbi.interactions import get_interactions
from pbi.model import SemanticModel
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from pbi.properties import PAGE_PROPERTIES, VISUAL_PROPERTIES, get_property
from pbi.project import Project


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "real-report-fixtures"
KITCHEN_SINK_DIR = FIXTURE_ROOT / "report-01-kitchen-sink"
KITCHEN_SINK_PBIP = KITCHEN_SINK_DIR / "01-kitchen-sink.pbip"
MODEL_HEAVY_DIR = FIXTURE_ROOT / "report-02-model-heavy"
MODEL_HEAVY_PBIP = MODEL_HEAVY_DIR / "02-model-heavy.pbip"
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class RealReportFixtureTests(unittest.TestCase):
    def test_real_fixtures_load_with_expected_shape(self) -> None:
        kitchen = Project.find(KITCHEN_SINK_PBIP)
        kitchen_pages = kitchen.get_pages()
        self.assertEqual(
            [page.display_name for page in kitchen_pages],
            [
                "Executive Overview",
                "Product Detail",
                "Regional Detail",
                "Tooltip - Order Context",
                "Hidden QA Page",
            ],
        )
        self.assertGreaterEqual(sum(len(kitchen.get_visuals(page)) for page in kitchen_pages), 30)

        kitchen_model = SemanticModel.load(kitchen.root)
        self.assertIn("Targets", [table.name for table in kitchen_model.tables])
        self.assertIn("_Measures", [table.name for table in kitchen_model.tables])
        self.assertGreaterEqual(sum(len(table.measures) for table in kitchen_model.tables), 14)

        model = Project.find(MODEL_HEAVY_PBIP)
        model_pages = model.get_pages()
        self.assertEqual(
            [page.display_name for page in model_pages],
            ["Finance Overview", "Department Drill", "Account Detail"],
        )
        self.assertGreaterEqual(sum(len(model.get_visuals(page)) for page in model_pages), 20)

        semantic_model = SemanticModel.load(model.root)
        self.assertIn("Variance Bands", [table.name for table in semantic_model.tables])
        self.assertGreaterEqual(sum(len(table.measures) for table in semantic_model.tables), 15)

    def test_kitchen_sink_map_cli_reports_hidden_pages_and_group(self) -> None:
        result = CliRunner().invoke(app, ["map", "--project", str(KITCHEN_SINK_PBIP)])

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("- group: Navigation", result.stdout)
        self.assertIn("- name: Product Detail  # hidden", result.stdout)
        self.assertIn("- name: Tooltip - Order Context  # hidden", result.stdout)
        self.assertIn("- name: Hidden QA Page  # hidden", result.stdout)

    def test_kitchen_sink_map_page_cli_limits_output_to_selected_page(self) -> None:
        result = CliRunner().invoke(
            app,
            ["map", "--page", "Hidden QA Page", "--project", str(KITCHEN_SINK_PBIP)],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("- name: Hidden QA Page  # hidden", result.stdout)
        self.assertIn("qaChart", result.stdout)
        self.assertNotIn("- name: Executive Overview", result.stdout)
        self.assertNotIn("- group: Navigation", result.stdout)

    def test_kitchen_sink_validate_cli_reports_known_overlap_warnings(self) -> None:
        result = CliRunner().invoke(app, ["validate", "--project", str(KITCHEN_SINK_PBIP)])

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("3 warning(s)", result.stdout)
        self.assertIn('Visual "revByChannelLabel" overlaps "navToProduct"', result.stdout)
        self.assertIn('Visual "revByChannelLabel" overlaps "navToRegional"', result.stdout)
        self.assertIn('Visual "revByChannelLabel" overlaps "navFocusOnline"', result.stdout)

    def test_real_fixtures_diff_no_changes_for_exported_yaml(self) -> None:
        runner = CliRunner()

        for pbip in (KITCHEN_SINK_PBIP, MODEL_HEAVY_PBIP):
            project = Project.find(pbip)
            exported = export_yaml(project)

            with tempfile.TemporaryDirectory() as tmp:
                spec_path = Path(tmp) / "exported.yaml"
                spec_path.write_text(exported, encoding="utf-8")

                result = runner.invoke(app, ["diff", str(spec_path), "--project", str(pbip)])

            self.assertEqual(result.exit_code, 0, f"{pbip}: {result.stdout}")
            self.assertIn("No differences found.", result.stdout)

    def test_real_fixture_report_section_apply_and_diff(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            parsed = {
                "version": 1,
                "pages": [],
                "report": {
                    "annotations": [{"name": "README", "value": "Kitchen sink"}],
                    "organizationCustomVisuals": [{"name": "Retail Timeline", "path": "org/RetailTimeline.pbiviz"}],
                    "dataSourceVariables": '{"region":"EMEA"}',
                },
            }
            spec = yaml.safe_dump(parsed, sort_keys=False)

            diff_result = runner.invoke(app, ["diff", "-", "--project", str(pbip)], input=spec)
            self.assertEqual(diff_result.exit_code, 0, diff_result.stdout)
            self.assertIn("Report", diff_result.stdout)
            self.assertIn("report.annotations[0].name", diff_result.stdout)
            self.assertIn("report.organizationCustomVisuals[0].name", diff_result.stdout)
            self.assertIn("report.dataSourceVariables", diff_result.stdout)

            result = apply_yaml(Project.find(pbip), spec)
            self.assertEqual(result.errors, [])

            reloaded = Project.find(pbip)
            report = reloaded.get_report_meta()
            self.assertEqual(report["annotations"], [{"name": "README", "value": "Kitchen sink"}])
            self.assertEqual(
                report["organizationCustomVisuals"],
                [{"name": "Retail Timeline", "path": "org/RetailTimeline.pbiviz"}],
            )
            self.assertEqual(report["dataSourceVariables"], '{"region":"EMEA"}')

    def test_kitchen_sink_report_get_and_set_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            get_result = runner.invoke(
                app,
                ["report", "get", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("settings.pagesPosition", get_result.stdout)
            self.assertIn("Bottom", get_result.stdout)
            self.assertIn("settings.useEnhancedTooltips", get_result.stdout)
            self.assertIn("True", get_result.stdout)

            set_result = runner.invoke(
                app,
                [
                    "report",
                    "set",
                    "settings.useEnhancedTooltips=false",
                    "settings.pagesPosition=PagesPane",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)
            self.assertIn("settings.useEnhancedTooltips: True -> False", set_result.stdout)
            self.assertIn("settings.pagesPosition: Bottom -> PagesPane", set_result.stdout)

            reloaded = Project.find(pbip)
            report_meta = reloaded.get_report_meta()
            self.assertFalse(report_meta["settings"]["useEnhancedTooltips"])
            self.assertEqual(report_meta["settings"]["pagesPosition"], "PagesPane")

    def test_kitchen_sink_report_object_and_annotation_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            list_result = runner.invoke(
                app,
                ["report", "object", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            resource_row = next(row for row in rows if row["name"] == "resourcePackages")
            self.assertTrue(resource_row["present"])
            self.assertEqual(resource_row["type"], "array")

            get_result = runner.invoke(
                app,
                ["report", "object", "get", "resourcePackages", "--raw", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            packages = json.loads(get_result.stdout)
            self.assertEqual(packages[0]["name"], "SharedResources")
            self.assertEqual(packages[1]["name"], "RegisteredResources")

            set_annotation_result = runner.invoke(
                app,
                ["report", "annotation", "set", "README", "Kitchen sink fixture", "--project", str(pbip)],
            )
            self.assertEqual(set_annotation_result.exit_code, 0, set_annotation_result.stdout)

            get_annotation_result = runner.invoke(
                app,
                ["report", "annotation", "get", "README", "--raw", "--project", str(pbip)],
            )
            self.assertEqual(get_annotation_result.exit_code, 0, get_annotation_result.stdout)
            self.assertEqual(
                json.loads(get_annotation_result.stdout),
                {"name": "README", "value": "Kitchen sink fixture"},
            )

            delete_annotation_result = runner.invoke(
                app,
                ["report", "annotation", "delete", "README", "--force", "--project", str(pbip)],
            )
            self.assertEqual(delete_annotation_result.exit_code, 0, delete_annotation_result.stdout)

            reloaded = Project.find(pbip)
            self.assertNotIn("annotations", reloaded.get_report_meta())

    def test_kitchen_sink_report_resource_commands_manage_registered_resources(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name
            source = copied_root / "qa-shape.json"
            source.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")

            package_list_result = runner.invoke(
                app,
                ["report", "resource", "package", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(package_list_result.exit_code, 0, package_list_result.stdout)
            package_rows = json.loads(package_list_result.stdout)
            registered = next(row for row in package_rows if row["name"] == "RegisteredResources")
            self.assertEqual(registered["items"], 2)

            item_set_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "set",
                    "RegisteredResources",
                    "qa-shape.json",
                    "--type",
                    "ShapeMap",
                    "--name",
                    "QA Shape",
                    "--from-file",
                    str(source),
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(item_set_result.exit_code, 0, item_set_result.stdout)

            item_get_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "get",
                    "RegisteredResources",
                    "qa-shape.json",
                    "--raw",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(item_get_result.exit_code, 0, item_get_result.stdout)
            self.assertEqual(
                json.loads(item_get_result.stdout),
                {"name": "QA Shape", "path": "qa-shape.json", "type": "ShapeMap"},
            )

            registered_path = (
                copied_root / "01-kitchen-sink.Report" / "StaticResources" / "RegisteredResources" / "qa-shape.json"
            )
            self.assertTrue(registered_path.exists())

            delete_result = runner.invoke(
                app,
                [
                    "report",
                    "resource",
                    "item",
                    "delete",
                    "RegisteredResources",
                    "qa-shape.json",
                    "--drop-file",
                    "--force",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertFalse(registered_path.exists())

    def test_kitchen_sink_report_custom_visual_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            set_result = runner.invoke(
                app,
                [
                    "report",
                    "custom-visual",
                    "set",
                    "Retail Timeline",
                    "org/RetailTimeline.pbiviz",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            get_result = runner.invoke(
                app,
                [
                    "report",
                    "custom-visual",
                    "get",
                    "Retail Timeline",
                    "--raw",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertEqual(
                json.loads(get_result.stdout),
                {"name": "Retail Timeline", "path": "org/RetailTimeline.pbiviz"},
            )

            delete_result = runner.invoke(
                app,
                [
                    "report",
                    "custom-visual",
                    "delete",
                    "Retail Timeline",
                    "--force",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)

            reloaded = Project.find(pbip)
            self.assertNotIn("organizationCustomVisuals", reloaded.get_report_meta())

    def test_kitchen_sink_bookmark_cli_reports_expected_fixture_state(self) -> None:
        runner = CliRunner()

        list_result = runner.invoke(
            app,
            ["bookmark", "list", "--json", "--project", str(KITCHEN_SINK_PBIP)],
        )
        self.assertEqual(list_result.exit_code, 0, list_result.stdout)
        rows = json.loads(list_result.stdout)
        self.assertEqual(
            [row["displayName"] for row in rows],
            ["Default View", "Focus On Online", "Hide Slicers"],
        )

        get_result = runner.invoke(
            app,
            ["bookmark", "get", "Hide Slicers", "--raw", "--project", str(KITCHEN_SINK_PBIP)],
        )
        self.assertEqual(get_result.exit_code, 0, get_result.stdout)
        bookmark = json.loads(get_result.stdout)
        containers = (
            bookmark["explorationState"]["sections"][bookmark["explorationState"]["activeSection"]]["visualContainers"]
        )
        self.assertEqual(
            set(containers),
            {"slicerYear", "slicerCategory", "slicerRegion", "navHelp"},
        )
        self.assertTrue(
            all(
                entry["singleVisual"]["display"]["mode"] == "hidden"
                for entry in containers.values()
            )
        )

    def test_kitchen_sink_navigation_commands_rewire_real_buttons(self) -> None:
        from pbi.bookmarks import get_bookmark

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            page = "Executive Overview"

            set_page_result = runner.invoke(
                app,
                ["nav", "page", "set", page, "navHelp", "Regional Detail", "--project", str(pbip)],
            )
            self.assertEqual(set_page_result.exit_code, 0, set_page_result.stdout)

            set_bookmark_result = runner.invoke(
                app,
                ["nav", "bookmark", "set", page, "navToRegional", "Hide Slicers", "--project", str(pbip)],
            )
            self.assertEqual(set_bookmark_result.exit_code, 0, set_bookmark_result.stdout)

            set_url_result = runner.invoke(
                app,
                [
                    "nav",
                    "url",
                    "set",
                    page,
                    "navFocusOnline",
                    "https://example.com/support",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_url_result.exit_code, 0, set_url_result.stdout)

            reloaded = Project.find(pbip)
            overview = reloaded.find_page(page)
            regional_detail = reloaded.find_page("Regional Detail")
            hide_slicers = get_bookmark(reloaded, "Hide Slicers")

            nav_help = reloaded.find_visual(overview, "navHelp")
            self.assertEqual(get_property(nav_help.data, "action.type", VISUAL_PROPERTIES), "PageNavigation")
            self.assertEqual(get_property(nav_help.data, "action.page", VISUAL_PROPERTIES), regional_detail.name)
            self.assertIsNone(get_property(nav_help.data, "action.url", VISUAL_PROPERTIES))

            nav_to_regional = reloaded.find_visual(overview, "navToRegional")
            self.assertEqual(get_property(nav_to_regional.data, "action.type", VISUAL_PROPERTIES), "Bookmark")
            self.assertEqual(
                get_property(nav_to_regional.data, "action.bookmark", VISUAL_PROPERTIES),
                hide_slicers["name"],
            )
            self.assertIsNone(get_property(nav_to_regional.data, "action.page", VISUAL_PROPERTIES))

            nav_focus_online = reloaded.find_visual(overview, "navFocusOnline")
            self.assertEqual(get_property(nav_focus_online.data, "action.type", VISUAL_PROPERTIES), "WebUrl")
            self.assertEqual(
                get_property(nav_focus_online.data, "action.url", VISUAL_PROPERTIES),
                "https://example.com/support",
            )
            self.assertIsNone(get_property(nav_focus_online.data, "action.bookmark", VISUAL_PROPERTIES))

            clear_result = runner.invoke(
                app,
                ["nav", "action", "clear", page, "navFocusOnline", "--force", "--project", str(pbip)],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            reloaded = Project.find(pbip)
            nav_focus_online = reloaded.find_visual(reloaded.find_page(page), "navFocusOnline")
            self.assertIsNone(get_property(nav_focus_online.data, "action.type", VISUAL_PROPERTIES))
            self.assertIsNone(get_property(nav_focus_online.data, "action.url", VISUAL_PROPERTIES))
            self.assertIsNone(get_property(nav_focus_online.data, "action.bookmark", VISUAL_PROPERTIES))

    def test_real_fixture_page_binding_commands_report_tooltip_and_drillthrough_details(self) -> None:
        runner = CliRunner()

        drill_result = runner.invoke(
            app,
            ["page", "drillthrough", "get", "Product Detail", "--project", str(KITCHEN_SINK_PBIP)],
        )
        self.assertEqual(drill_result.exit_code, 0, drill_result.stdout)
        self.assertIn("Type", drill_result.stdout)
        self.assertIn("Drillthrough", drill_result.stdout)

        tooltip_result = runner.invoke(
            app,
            ["page", "tooltip", "get", "Tooltip - Order Context", "--project", str(KITCHEN_SINK_PBIP)],
        )
        self.assertEqual(tooltip_result.exit_code, 0, tooltip_result.stdout)
        self.assertIn("Tooltip", tooltip_result.stdout)
        self.assertIn("320", tooltip_result.stdout)
        self.assertIn("240", tooltip_result.stdout)

    def test_real_fixture_nav_drillthrough_and_tooltip_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            set_drill_result = runner.invoke(
                app,
                [
                    "nav",
                    "drillthrough",
                    "set",
                    "Executive Overview",
                    "navToProduct",
                    "Product Detail",
                    "--tooltip",
                    "Open detail",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_drill_result.exit_code, 0, set_drill_result.stdout)

            set_tooltip_result = runner.invoke(
                app,
                [
                    "nav",
                    "tooltip",
                    "set",
                    "Executive Overview",
                    "revenueByMonth",
                    "Tooltip - Order Context",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_tooltip_result.exit_code, 0, set_tooltip_result.stdout)

            get_action_result = runner.invoke(
                app,
                ["nav", "action", "get", "Executive Overview", "navToProduct", "--project", str(pbip)],
            )
            self.assertEqual(get_action_result.exit_code, 0, get_action_result.stdout)
            self.assertIn("Drillthrough", get_action_result.stdout)

            get_tooltip_result = runner.invoke(
                app,
                ["nav", "tooltip", "get", "Executive Overview", "revenueByMonth", "--project", str(pbip)],
            )
            self.assertEqual(get_tooltip_result.exit_code, 0, get_tooltip_result.stdout)
            self.assertIn("ReportPage", get_tooltip_result.stdout)

            reloaded = Project.find(pbip)
            overview = reloaded.find_page("Executive Overview")
            product_detail = reloaded.find_page("Product Detail")
            tooltip_page = reloaded.find_page("Tooltip - Order Context")

            nav_to_product = reloaded.find_visual(overview, "navToProduct")
            self.assertEqual(get_property(nav_to_product.data, "action.type", VISUAL_PROPERTIES), "Drillthrough")
            self.assertEqual(
                get_property(nav_to_product.data, "action.drillthrough", VISUAL_PROPERTIES),
                product_detail.name,
            )
            self.assertEqual(get_property(nav_to_product.data, "action.tooltip", VISUAL_PROPERTIES), "Open detail")

            revenue_by_month = reloaded.find_visual(overview, "revenueByMonth")
            self.assertEqual(get_property(revenue_by_month.data, "tooltip.type", VISUAL_PROPERTIES), "ReportPage")
            self.assertEqual(get_property(revenue_by_month.data, "tooltip.section", VISUAL_PROPERTIES), tooltip_page.name)

            clear_tooltip_result = runner.invoke(
                app,
                [
                    "nav",
                    "tooltip",
                    "clear",
                    "Executive Overview",
                    "revenueByMonth",
                    "--force",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(clear_tooltip_result.exit_code, 0, clear_tooltip_result.stdout)

            reloaded = Project.find(pbip)
            revenue_by_month = reloaded.find_visual(reloaded.find_page("Executive Overview"), "revenueByMonth")
            self.assertIsNone(get_property(revenue_by_month.data, "tooltip.type", VISUAL_PROPERTIES))
            self.assertIsNone(get_property(revenue_by_month.data, "tooltip.section", VISUAL_PROPERTIES))

    def test_model_heavy_model_cli_inspection_commands(self) -> None:
        runner = CliRunner()

        deps_result = runner.invoke(
            app,
            ["model", "deps", "GL_Actuals.Actual Amount", "--project", str(MODEL_HEAVY_PBIP)],
        )
        self.assertEqual(deps_result.exit_code, 0, deps_result.stdout)
        self.assertIn("GL_Actuals.Amount (column)", deps_result.stdout)
        self.assertIn("Forecast.Actual YoY (measure)", deps_result.stdout)

        search_result = runner.invoke(
            app,
            ["model", "search", "Actual", "--project", str(MODEL_HEAVY_PBIP)],
        )
        self.assertEqual(search_result.exit_code, 0, search_result.stdout)
        self.assertIn("GL_Actuals.Actual Amount", search_result.stdout)
        self.assertIn("Forecast.Actual vs Budget", search_result.stdout)

        path_result = runner.invoke(
            app,
            ["model", "path", "GL_Actuals", "Account", "--project", str(MODEL_HEAVY_PBIP)],
        )
        self.assertEqual(path_result.exit_code, 0, path_result.stdout)
        self.assertIn("Path (1 hop)", path_result.stdout)
        self.assertIn("GL_Actuals.AccountKey", path_result.stdout)
        self.assertIn("Account.AccountKey", path_result.stdout)

        check_result = runner.invoke(
            app,
            ["model", "check", "--project", str(MODEL_HEAVY_PBIP)],
        )
        self.assertEqual(check_result.exit_code, 0, check_result.stdout)
        self.assertIn("11 warning(s), 6 info(s)", check_result.stdout)
        self.assertIn("Auto-detected relationship", check_result.stdout)
        self.assertIn("Inactive relationship", check_result.stdout)

    def test_model_heavy_model_export_apply_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)

            before = export_model_yaml(copied_root)
            result = apply_model_yaml(copied_root, before, dry_run=False)
            after = export_model_yaml(copied_root)

            self.assertEqual(result.errors, [])
            self.assertEqual(before, after)

    def test_page_import_from_real_fixture_copies_resources(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            target_project = Project.find(pbip)
            before_pages = [page.display_name for page in target_project.get_pages()]

            import_result = runner.invoke(
                app,
                [
                    "page",
                    "import",
                    "--from-project",
                    str(KITCHEN_SINK_PBIP),
                    "--page",
                    "Product Detail",
                    "--name",
                    "Imported Product Detail",
                    "--include-resources",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(import_result.exit_code, 0, import_result.stdout)
            self.assertIn('Imported "Product Detail" from 01-kitchen-sink as "Imported Product Detail"', import_result.stdout)
            self.assertIn("Copied 1 image resource(s)", import_result.stdout)

            reloaded = Project.find(pbip)
            after_pages = [page.display_name for page in reloaded.get_pages()]
            self.assertEqual(len(after_pages), len(before_pages) + 1)
            self.assertIn("Imported Product Detail", after_pages)
            imported_page = reloaded.find_page("Imported Product Detail")
            self.assertEqual(len(reloaded.get_visuals(imported_page)), 7)

    def test_kitchen_sink_interaction_commands_set_and_clear_real_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name
            page = "Executive Overview"

            before_result = runner.invoke(
                app,
                ["interaction", "list", page, "--project", str(pbip)],
            )
            self.assertEqual(before_result.exit_code, 0, before_result.stdout)
            self.assertIn("No custom interactions", before_result.stdout)

            set_result = runner.invoke(
                app,
                [
                    "interaction",
                    "set",
                    page,
                    "revenueByMonth",
                    "revenueByChannel",
                    "--mode",
                    "NoFilter",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            reloaded = Project.find(pbip)
            interactions = get_interactions(reloaded.find_page(page))
            self.assertEqual(
                interactions,
                [{"source": "revenueByMonth", "target": "revenueByChannel", "type": "NoFilter"}],
            )

            clear_result = runner.invoke(
                app,
                [
                    "interaction",
                    "clear",
                    page,
                    "revenueByMonth",
                    "revenueByChannel",
                    "--force",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            reloaded = Project.find(pbip)
            self.assertEqual(get_interactions(reloaded.find_page(page)), [])

    def test_kitchen_sink_visual_get_and_set_cli_updates_real_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name
            page = "Executive Overview"

            get_result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    page,
                    "revenueByMonth",
                    "title.text",
                    "background.color",
                    "border.color",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Revenue vs Target by Month", get_result.stdout)
            self.assertIn("#FFFFFF", get_result.stdout)
            self.assertIn("#E0E0E0", get_result.stdout)

            set_chart_result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    page,
                    "revenueByMonth",
                    "title.text=Revenue Trend by Fiscal Month",
                    "background.color=#FFF8E7",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_chart_result.exit_code, 0, set_chart_result.stdout)

            set_slicer_result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    page,
                    "slicerYear",
                    "title.text=Fiscal Year",
                    "border.color=#B85C00",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_slicer_result.exit_code, 0, set_slicer_result.stdout)

            reloaded = Project.find(pbip)
            overview = reloaded.find_page(page)

            revenue_by_month = reloaded.find_visual(overview, "revenueByMonth")
            self.assertEqual(
                get_property(revenue_by_month.data, "title.text", VISUAL_PROPERTIES),
                "Revenue Trend by Fiscal Month",
            )
            self.assertEqual(
                get_property(revenue_by_month.data, "background.color", VISUAL_PROPERTIES),
                "#FFF8E7",
            )

            slicer_year = reloaded.find_visual(overview, "slicerYear")
            self.assertEqual(get_property(slicer_year.data, "title.text", VISUAL_PROPERTIES), "Fiscal Year")
            self.assertEqual(get_property(slicer_year.data, "border.color", VISUAL_PROPERTIES), "#B85C00")

    def test_model_heavy_builder_create_extends_real_fixture_and_round_trips(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            project = Project.find(pbip)
            builder_page = project.create_page("Builder Smoke")

            commands = [
                [
                    "visual",
                    "create",
                    "Builder Smoke",
                    "lineClusteredColumnComboChart",
                    "--name",
                    "builderCombo",
                    "--x",
                    "20",
                    "--y",
                    "20",
                    "--bind",
                    "Category=Department.Division",
                    "--bind",
                    "Y=GL_Actuals.Actual Amount",
                    "--bind",
                    "Y2=Budget.Budget Amount",
                    "--preset",
                    "chart",
                    "--project",
                    str(pbip),
                ],
                [
                    "visual",
                    "create",
                    "Builder Smoke",
                    "donutChart",
                    "--name",
                    "builderDonut",
                    "--x",
                    "700",
                    "--y",
                    "20",
                    "--bind",
                    "Category=Account.AccountGroup",
                    "--bind",
                    "Y=GL_Actuals.Actual Amount",
                    "--preset",
                    "chart",
                    "--project",
                    str(pbip),
                ],
                [
                    "visual",
                    "create",
                    "Builder Smoke",
                    "pivotTable",
                    "--name",
                    "builderMatrix",
                    "--x",
                    "20",
                    "--y",
                    "400",
                    "--width",
                    "1240",
                    "--height",
                    "260",
                    "--bind",
                    "Rows=Department.Division",
                    "--bind",
                    "Values=Forecast.Actual vs Budget",
                    "--preset",
                    "table",
                    "--project",
                    str(pbip),
                ],
                [
                    "visual",
                    "create",
                    "Builder Smoke",
                    "cardVisual",
                    "--name",
                    "builderCard",
                    "--x",
                    "700",
                    "--y",
                    "320",
                    "--bind",
                    "Data=Forecast.Actual vs Budget",
                    "--preset",
                    "card",
                    "--project",
                    str(pbip),
                ],
                [
                    "visual",
                    "create",
                    "Builder Smoke",
                    "slicer",
                    "--name",
                    "builderScenario",
                    "--x",
                    "980",
                    "--y",
                    "320",
                    "--bind",
                    "Values=Scenario.ScenarioName",
                    "--preset",
                    "slicer",
                    "--project",
                    str(pbip),
                ],
            ]

            for argv in commands:
                result = runner.invoke(app, argv)
                self.assertEqual(result.exit_code, 0, result.stdout)

            validate_result = runner.invoke(
                app,
                ["validate", "--project", str(pbip)],
            )
            self.assertEqual(validate_result.exit_code, 0, validate_result.stdout)
            self.assertNotIn("[red bold]", validate_result.stdout)

            reloaded = Project.find(pbip)
            builder_page = reloaded.find_page(builder_page.display_name)
            created_visuals = {visual.name: visual for visual in reloaded.get_visuals(builder_page)}
            self.assertEqual(
                set(created_visuals),
                {"builderCombo", "builderDonut", "builderMatrix", "builderCard", "builderScenario"},
            )
            self.assertEqual(
                get_property(created_visuals["builderScenario"].data, "title.text", VISUAL_PROPERTIES),
                "ScenarioName",
            )
            self.assertEqual(
                get_property(created_visuals["builderCard"].data, "title.text", VISUAL_PROPERTIES),
                "Actual vs Budget",
            )
            self.assertEqual(
                reloaded.get_sort(created_visuals["builderScenario"]),
                [],
            )

            before = export_yaml(reloaded, page_filter="Builder Smoke")
            result = apply_yaml(reloaded, before, page_filter="Builder Smoke")
            after = export_yaml(Project.find(pbip), page_filter="Builder Smoke")

            self.assertEqual(result.errors, [])
            self.assertEqual(before, after)

    def test_kitchen_sink_component_create_and_apply_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            project = Project.find(pbip)
            hidden_page = project.find_page("Hidden QA Page")
            before_count = len(project.get_visuals(hidden_page))

            create_result = runner.invoke(
                app,
                [
                    "component",
                    "create",
                    "Executive Overview",
                    "Navigation",
                    "--name",
                    "nav-cluster",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            self.assertIn('Saved component "nav-cluster"', create_result.stdout)

            component_path = copied_root / ".pbi-components" / "nav-cluster.yaml"
            self.assertTrue(component_path.exists())

            list_result = runner.invoke(
                app,
                ["component", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            component_row = next(row for row in rows if row["name"] == "nav-cluster")
            self.assertEqual(component_row["scope"], "project")
            self.assertEqual(component_row["visuals"], 3)

            apply_result = runner.invoke(
                app,
                [
                    "component",
                    "apply",
                    "Hidden QA Page",
                    "nav-cluster",
                    "--x",
                    "80",
                    "--y",
                    "120",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            self.assertIn('Created "nav-cluster" on "Hidden QA Page"', apply_result.stdout)

            reloaded = Project.find(pbip)
            hidden_page = reloaded.find_page("Hidden QA Page")
            after_visuals = reloaded.get_visuals(hidden_page)
            self.assertEqual(len(after_visuals), before_count + 4)
            self.assertTrue(
                any(
                    visual.data.get("visualGroup", {}).get("displayName") == "nav-cluster"
                    for visual in after_visuals
                )
            )

    def test_kitchen_sink_image_create_list_and_prune_cli(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            image_path = Path(tmp) / "unused.png"
            image_path.write_bytes(PNG_1X1)

            before_result = runner.invoke(
                app,
                ["image", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(before_result.exit_code, 0, before_result.stdout)
            before_rows = json.loads(before_result.stdout)
            self.assertEqual(len(before_rows), 2)

            create_result = runner.invoke(
                app,
                ["image", "create", str(image_path), "--project", str(pbip)],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            self.assertIn("Registered unused.png", create_result.stdout)

            after_create_result = runner.invoke(
                app,
                ["image", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(after_create_result.exit_code, 0, after_create_result.stdout)
            after_create_rows = json.loads(after_create_result.stdout)
            self.assertEqual(len(after_create_rows), 3)
            new_row = next(row for row in after_create_rows if row["name"].startswith("unused"))
            self.assertEqual(new_row["references"], 0)
            self.assertEqual(new_row["referencedBy"], [])

            prune_result = runner.invoke(
                app,
                ["image", "prune", "--force", "--project", str(pbip)],
            )
            self.assertEqual(prune_result.exit_code, 0, prune_result.stdout)
            self.assertIn("Removed 1 unreferenced image(s)", prune_result.stdout)

            after_prune_result = runner.invoke(
                app,
                ["image", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(after_prune_result.exit_code, 0, after_prune_result.stdout)
            after_prune_rows = json.loads(after_prune_result.stdout)
            self.assertEqual(len(after_prune_rows), 2)

    def test_kitchen_sink_theme_migrate_updates_fixture_colors(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            old_theme = Path(tmp) / "old-theme.json"
            new_theme = Path(tmp) / "new-theme.json"
            old_theme.write_text(
                json.dumps(
                    {
                        "name": "Old",
                        "pageBackground": "#F5F6FA",
                        "visualSurface": "#FFFFFF",
                        "accent": "#0078D4",
                    }
                ),
                encoding="utf-8",
            )
            new_theme.write_text(
                json.dumps(
                    {
                        "name": "New",
                        "pageBackground": "#EEF2FF",
                        "visualSurface": "#FFF8E7",
                        "accent": "#0063B1",
                    }
                ),
                encoding="utf-8",
            )

            dry_run_result = runner.invoke(
                app,
                [
                    "theme",
                    "migrate",
                    str(old_theme),
                    str(new_theme),
                    "--dry-run",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(dry_run_result.exit_code, 0, dry_run_result.stdout)
            self.assertIn("Would update", dry_run_result.stdout)
            self.assertIn("#FFFFFF", dry_run_result.stdout)
            self.assertIn("#FFF8E7", dry_run_result.stdout)
            self.assertIn("background.color on", dry_run_result.stdout)

            apply_result = runner.invoke(
                app,
                [
                    "theme",
                    "migrate",
                    str(old_theme),
                    str(new_theme),
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(apply_result.exit_code, 0, apply_result.stdout)
            self.assertIn("Updated", apply_result.stdout)
            self.assertIn("#FFFFFF", apply_result.stdout)
            self.assertIn("#FFF8E7", apply_result.stdout)
            self.assertIn("#F5F6FA", apply_result.stdout)
            self.assertIn("#EEF2FF", apply_result.stdout)

            reloaded = Project.find(pbip)
            overview = reloaded.find_page("Executive Overview")
            self.assertEqual(
                get_property(overview.data, "background.color", PAGE_PROPERTIES),
                "#EEF2FF",
            )
            revenue_by_month = reloaded.find_visual(overview, "revenueByMonth")
            self.assertEqual(
                get_property(revenue_by_month.data, "background.color", VISUAL_PROPERTIES),
                "#FFF8E7",
            )

    def test_kitchen_sink_apply_yaml_mutates_real_visual_property(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / KITCHEN_SINK_DIR.name
            shutil.copytree(KITCHEN_SINK_DIR, copied_root)
            pbip = copied_root / KITCHEN_SINK_PBIP.name

            project = Project.find(pbip)
            spec = {
                "pages": [
                    {
                        "name": "Executive Overview",
                        "visuals": [
                            {
                                "name": "revenueByMonth",
                                "title": {"text": "Revenue by Fiscal Month"},
                                "background": {"color": "#FDF1D6"},
                            }
                        ],
                    }
                ]
            }

            result = apply_yaml(project, yaml.safe_dump(spec, sort_keys=False))

            self.assertEqual(result.errors, [])
            self.assertFalse(result.rolled_back)

            reloaded = Project.find(pbip)
            overview = reloaded.find_page("Executive Overview")
            revenue_by_month = reloaded.find_visual(overview, "revenueByMonth")
            self.assertEqual(
                get_property(revenue_by_month.data, "title.text", VISUAL_PROPERTIES),
                "Revenue by Fiscal Month",
            )
            self.assertEqual(
                get_property(revenue_by_month.data, "background.color", VISUAL_PROPERTIES),
                "#FDF1D6",
            )


if __name__ == "__main__":
    unittest.main()
