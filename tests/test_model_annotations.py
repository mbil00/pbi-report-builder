from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import SemanticModel, set_model_annotation
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from tests.cli_regressions_support import make_project, write_model_table


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "real-report-fixtures"
MODEL_HEAVY_DIR = FIXTURE_ROOT / "report-02-model-heavy"
MODEL_HEAVY_PBIP = MODEL_HEAVY_DIR / "02-model-heavy.pbip"


def _write_model(root: Path, content: str) -> Path:
    definition = root / "Sample.SemanticModel" / "definition"
    definition.mkdir(parents=True, exist_ok=True)
    path = definition / "model.tmdl"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class ModelAnnotationTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> None:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 0
\tref table Sales
            """,
        )
        write_model_table(
            root,
            "Sales.tmdl",
            """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
            """,
        )

    def test_set_and_load_model_annotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)

            name, changed = set_model_annotation(root, "PBI_ProTooling", '["DevMode"]')
            self.assertEqual(name, "PBI_ProTooling")
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            self.assertEqual(model.annotations["PBI_ProTooling"], '["DevMode"]')

    def test_model_export_and_apply_round_trip_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            self._make_model_project(source)
            set_model_annotation(source, "PBI_ProTooling", '["DevMode"]')

            exported = yaml.safe_load(export_model_yaml(source))
            self.assertEqual(exported["model"]["annotations"]["PBI_ProTooling"], '["DevMode"]')

            target = Path(tmp) / "target"
            self._make_model_project(target)
            result = apply_model_yaml(target, yaml.safe_dump(exported, sort_keys=False))
            self.assertEqual(result.errors, [])
            self.assertIn("Model", result.model_updated)

            round_tripped = yaml.safe_load(export_model_yaml(target))
            self.assertEqual(round_tripped["model"]["annotations"], exported["model"]["annotations"])


class ModelAnnotationCliTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> Path:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 0
\tref table Sales
            """,
        )
        write_model_table(
            root,
            "Sales.tmdl",
            """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
            """,
        )
        return root / "Sample.pbip"

    def test_cli_annotation_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = self._make_model_project(Path(tmp))

            set_result = runner.invoke(
                app,
                ["model", "annotation", "set", "PBI_ProTooling", '["DevMode"]', "--project", str(pbip)],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            list_result = runner.invoke(app, ["model", "annotation", "list", "--json", "--project", str(pbip)])
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertTrue(any(row["name"] == "PBI_ProTooling" for row in rows))

            get_result = runner.invoke(app, ["model", "annotation", "get", "PBI_ProTooling", "--project", str(pbip)])
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn('["DevMode"]', get_result.stdout)

            delete_result = runner.invoke(
                app,
                ["model", "annotation", "delete", "PBI_ProTooling", "--force", "--project", str(pbip)],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)


class RealAnnotationFixtureTests(unittest.TestCase):
    def test_model_heavy_fixture_annotations_and_export(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            list_result = runner.invoke(
                app,
                ["model", "annotation", "list", "--json", "--project", str(pbip)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            names = {row["name"] for row in rows}
            self.assertIn("PBI_ProTooling", names)
            self.assertIn("PBI_QueryOrder", names)

            exported = yaml.safe_load(export_model_yaml(copied_root))
            self.assertIn("annotations", exported["model"])
            self.assertEqual(exported["model"]["annotations"]["PBI_ProTooling"], '["DevMode"]')
