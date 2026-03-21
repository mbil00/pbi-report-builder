from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import SemanticModel, create_partition, set_partition
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


class PartitionModelTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> None:
        make_project(root)
        _write_model(
            root,
            """
model Model
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

    def test_create_and_load_partition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)

            table_name, partition_name, changed = create_partition(
                root,
                "Sales",
                "Sales",
                "let\n    Source = Csv.Document(File.Contents(\"sales.csv\"))\nin\n    Source",
                source_type="m",
                mode="import",
            )
            self.assertTrue(changed)
            self.assertEqual((table_name, partition_name), ("Sales", "Sales"))

            model = SemanticModel.load(root)
            table = model.find_table("Sales")
            partition = table.find_partition("Sales")
            self.assertEqual(partition.source_type, "m")
            self.assertEqual(partition.mode, "import")
            self.assertIn("Csv.Document", partition.source_expression)

    def test_set_partition_updates_source_type_and_expression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)
            create_partition(root, "Sales", "Sales", "ROW(\"x\", 1)", source_type="calculated", mode="import")

            table_name, partition_name, changed = set_partition(
                root,
                "Sales",
                "Sales",
                source_expression="let\n    Source = #table({\"Amount\"}, {{1}})\nin\n    Source",
                source_type="m",
            )
            self.assertTrue(changed)
            self.assertEqual((table_name, partition_name), ("Sales", "Sales"))

            partition = SemanticModel.load(root).find_table("Sales").find_partition("Sales")
            self.assertEqual(partition.source_type, "m")
            self.assertIn("#table", partition.source_expression)

    def test_model_export_and_apply_round_trip_partitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            self._make_model_project(source)
            create_partition(
                source,
                "Sales",
                "Sales",
                "let\n    Source = Csv.Document(File.Contents(\"sales.csv\"))\nin\n    Source",
                source_type="m",
                mode="import",
            )

            exported = yaml.safe_load(export_model_yaml(source))
            self.assertIn("partitions", exported)
            self.assertEqual(exported["partitions"]["Sales"][0]["sourceType"], "m")

            target = Path(tmp) / "target"
            self._make_model_project(target)
            result = apply_model_yaml(target, yaml.safe_dump(exported, sort_keys=False))
            self.assertEqual(result.errors, [])
            self.assertEqual(result.partitions_created, ["Sales.Sales"])

            round_tripped = yaml.safe_load(export_model_yaml(target))
            self.assertEqual(round_tripped["partitions"], exported["partitions"])


class PartitionCliTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> Path:
        make_project(root)
        _write_model(
            root,
            """
model Model
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

    def test_cli_partition_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = self._make_model_project(Path(tmp))

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "partition",
                    "create",
                    "Sales",
                    "Sales",
                    "ROW(\"x\", 1)",
                    "--source-type",
                    "calculated",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            list_result = runner.invoke(app, ["model", "partition", "list", "--json", "--project", str(pbip)])
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(rows[0]["name"], "Sales")

            get_result = runner.invoke(app, ["model", "partition", "get", "Sales", "Sales", "--raw", "--project", str(pbip)])
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["sourceType"], "calculated")

            set_result = runner.invoke(
                app,
                [
                    "model",
                    "partition",
                    "set",
                    "Sales",
                    "Sales",
                    "sourceType=m",
                    "source=let\n    Source = #table({\"Amount\"}, {{1}})\nin\n    Source",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            delete_result = runner.invoke(
                app,
                ["model", "partition", "delete", "Sales", "Sales", "--force", "--project", str(pbip)],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)


class RealPartitionFixtureTests(unittest.TestCase):
    def test_model_heavy_fixture_partition_inspection_and_export(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            list_result = runner.invoke(
                app,
                ["model", "partition", "list", "Department", "--json", "--project", str(pbip)],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(rows[0]["name"], "Department")
            self.assertEqual(rows[0]["sourceType"], "m")

            get_result = runner.invoke(
                app,
                ["model", "partition", "get", "Department", "Department", "--raw", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["mode"], "import")
            self.assertIn("Csv.Document", parsed["source"])

            exported = yaml.safe_load(export_model_yaml(copied_root))
            self.assertIn("partitions", exported)
            self.assertEqual(exported["partitions"]["Department"][0]["name"], "Department")
