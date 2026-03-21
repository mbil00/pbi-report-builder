from __future__ import annotations

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
from pbi.project import Project


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "real-report-fixtures"
KITCHEN_SINK_DIR = FIXTURE_ROOT / "report-01-kitchen-sink"
KITCHEN_SINK_PBIP = KITCHEN_SINK_DIR / "01-kitchen-sink.pbip"
MODEL_HEAVY_DIR = FIXTURE_ROOT / "report-02-model-heavy"
MODEL_HEAVY_PBIP = MODEL_HEAVY_DIR / "02-model-heavy.pbip"


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


if __name__ == "__main__":
    unittest.main()
