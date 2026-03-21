from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.export import export_yaml
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

    def test_model_heavy_model_export_apply_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)

            before = export_model_yaml(copied_root)
            result = apply_model_yaml(copied_root, before, dry_run=False)
            after = export_model_yaml(copied_root)

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


if __name__ == "__main__":
    unittest.main()
