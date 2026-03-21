from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import SemanticModel, create_perspective, set_perspective
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from pbi.modeling import PerspectiveMemberSpec
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


class PerspectiveModelTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> None:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tref table Sales
\tref table Date
            """,
        )
        write_model_table(
            root,
            "Sales.tmdl",
            """
table Sales
\tmeasure Revenue = SUM ( Sales[Amount] )
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
            """,
        )
        write_model_table(
            root,
            "Date.tmdl",
            """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Year

\thierarchy Calendar
\t\tlevel Year
\t\t\tcolumn: Year
            """,
        )

    def test_create_and_load_perspective(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)

            name, changed = create_perspective(
                root,
                "Authoring",
                PerspectiveMemberSpec(
                    columns=["Date.Year"],
                    measures=["Sales.Revenue"],
                    hierarchies=["Date.Calendar"],
                ),
            )
            self.assertTrue(changed)
            self.assertEqual(name, "Authoring")

            model = SemanticModel.load(root)
            perspective = model.find_perspective("Authoring")
            self.assertEqual([item.table for item in perspective.tables], ["Date", "Sales"])
            date_entry = perspective.find_table("Date")
            self.assertEqual(date_entry.columns, ["Year"])
            self.assertEqual(date_entry.hierarchies, ["Calendar"])
            sales_entry = perspective.find_table("Sales")
            self.assertEqual(sales_entry.measures, ["Revenue"])

    def test_set_perspective_replaces_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)
            create_perspective(root, "Authoring", PerspectiveMemberSpec(columns=["Date.Year"]))

            name, changed = set_perspective(
                root,
                "Authoring",
                PerspectiveMemberSpec(include_all_tables=["Sales"]),
            )
            self.assertEqual(name, "Authoring")
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            perspective = model.find_perspective("Authoring")
            self.assertEqual(len(perspective.tables), 1)
            self.assertTrue(perspective.tables[0].include_all)
            self.assertEqual(perspective.tables[0].table, "Sales")

    def test_model_export_and_apply_round_trip_perspectives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root / "source")
            source = root / "source"
            create_perspective(
                source,
                "Authoring",
                PerspectiveMemberSpec(columns=["Date.Year"], measures=["Sales.Revenue"]),
            )

            exported = yaml.safe_load(export_model_yaml(source))
            self.assertIn("perspectives", exported)
            self.assertEqual(exported["perspectives"]["Authoring"]["tables"]["Date"]["columns"], ["Year"])

            self._make_model_project(root / "target")
            target = root / "target"
            result = apply_model_yaml(target, yaml.safe_dump(exported, sort_keys=False))
            self.assertEqual(result.errors, [])
            self.assertEqual(result.perspectives_created, ["Authoring"])

            round_tripped = yaml.safe_load(export_model_yaml(target))
            self.assertEqual(round_tripped["perspectives"], exported["perspectives"])


class PerspectiveCliTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> Path:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tref table Sales
\tref table Date
            """,
        )
        write_model_table(
            root,
            "Sales.tmdl",
            """
table Sales
\tmeasure Revenue = SUM ( Sales[Amount] )
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
            """,
        )
        write_model_table(
            root,
            "Date.tmdl",
            """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Year

\thierarchy Calendar
\t\tlevel Year
\t\t\tcolumn: Year
            """,
        )
        return root / "Sample.pbip"

    def test_cli_create_list_get_set_delete(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = self._make_model_project(Path(tmp))

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "perspective",
                    "create",
                    "Authoring",
                    "--column",
                    "Date.Year",
                    "--measure",
                    "Sales.Revenue",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            list_result = runner.invoke(app, ["model", "perspective", "list", "--json", "--project", str(pbip)])
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(rows[0]["name"], "Authoring")

            get_result = runner.invoke(app, ["model", "perspective", "get", "Authoring", "--json", "--project", str(pbip)])
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["tables"][0]["table"], "Date")

            set_result = runner.invoke(
                app,
                [
                    "model",
                    "perspective",
                    "set",
                    "Authoring",
                    "--include-all",
                    "Sales",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)
            self.assertIn("Updated perspective", set_result.stdout)

            delete_result = runner.invoke(
                app,
                ["model", "perspective", "delete", "Authoring", "--force", "--project", str(pbip)],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertIn("Deleted perspective", delete_result.stdout)


class RealPerspectiveFixtureTests(unittest.TestCase):
    def test_model_heavy_fixture_perspective_commands_and_export(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "perspective",
                    "create",
                    "Finance Review",
                    "--include-all",
                    "Account",
                    "--measure",
                    "Budget.Budget Amount",
                    "--measure",
                    "GL_Actuals.Actual Amount",
                    "--hierarchy",
                    "Department.Org",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            get_result = runner.invoke(
                app,
                ["model", "perspective", "get", "Finance Review", "--json", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["name"], "Finance Review")
            self.assertEqual(len(parsed["tables"]), 4)

            exported = yaml.safe_load(export_model_yaml(copied_root))
            self.assertIn("perspectives", exported)
            self.assertIn("Finance Review", exported["perspectives"])
            self.assertEqual(
                exported["perspectives"]["Finance Review"]["tables"]["Department"]["hierarchies"],
                ["Org"],
            )
