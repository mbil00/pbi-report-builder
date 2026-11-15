"""`///` descriptions (#38) read and write the way Desktop saved them in report-04.

The write tests copy the Desktop-built report-04 project, strip its ``///``
lines, put each description back through the CLI and compare the TMDL with
what Desktop saved. CLI writes still turn Desktop's CRLF into LF (#52), so the
comparison normalizes line endings. They skip if `04-desktop-shapes.pbip` is
absent.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import SemanticModel
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from tests.test_desktop_shapes_fixture import SHAPES_DIR, SHAPES_PBIP

TABLES = Path("04-desktop-shapes.SemanticModel") / "definition" / "tables"

TASK_COUNT = "Number of tasks in the current filter context.\nCounts every Task row, including blocked tasks."
COMPLETED = 'Tasks with Status = "Completed" & counted once.'
OPEN = "Task Count minus Completed Tasks."
TASK = "One row per task. Source: Task.csv."
STATUS = "Workflow status: Not started, In progress, Blocked or Completed."
CALENDAR = "Year > Quarter > Month > Date drill path."


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopDescriptionReadTests(unittest.TestCase):
    def test_parser_reads_every_desktop_description(self) -> None:
        model = SemanticModel.load(SHAPES_DIR)
        task = model.find_table("Task")
        measures = model.find_table("Measures Table")

        self.assertEqual(task.description, TASK)
        self.assertEqual(task.find_column("Status").description, STATUS)
        self.assertEqual(measures.find_measure("Task Count").description, TASK_COUNT)
        self.assertEqual(measures.find_measure("Completed Tasks").description, COMPLETED)
        self.assertEqual(measures.find_measure("Open Tasks").description, OPEN)
        self.assertEqual(model.find_table("Date").find_hierarchy("Calendar").description, CALENDAR)

    def test_undescribed_objects_have_no_description(self) -> None:
        model = SemanticModel.load(SHAPES_DIR)
        measures = model.find_table("Measures Table")
        # Directly below a described measure: nothing may leak across.
        self.assertEqual(measures.find_measure("Completion %").description, "")
        self.assertEqual(measures.description, "")
        described = {
            ("Task", None), ("Task", "Status"),
            ("Measures Table", "Task Count"), ("Measures Table", "Completed Tasks"),
            ("Measures Table", "Open Tasks"), ("Date", "Calendar"),
        }
        found = set()
        for table in model.tables:
            if table.description:
                found.add((table.name, None))
            for item in [*table.columns, *table.measures, *table.hierarchies]:
                if item.description:
                    found.add((table.name, item.name))
        self.assertEqual(found, described)


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopDescriptionWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for path in SHAPES_DIR.glob("04-desktop-shapes.*"):
            target = self.root / path.name
            if path.is_dir():
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)
        self.pbip = self.root / "04-desktop-shapes.pbip"
        self.runner = CliRunner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _invoke(self, *args: str) -> str:
        result = self.runner.invoke(app, [*args, "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 0, result.stdout)
        return result.stdout

    def _path(self, table: str) -> Path:
        return self.root / TABLES / f"{table}.tmdl"

    def _desktop(self, table: str) -> str:
        return _lf((SHAPES_DIR / TABLES / f"{table}.tmdl").read_text(encoding="utf-8-sig"))

    def _written(self, table: str) -> str:
        return _lf(self._path(table).read_text(encoding="utf-8-sig"))

    def _strip_descriptions(self, table: str) -> None:
        path = self._path(table)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        path.write_text("\n".join(l for l in lines if not l.lstrip().startswith("///")) + "\n", encoding="utf-8")

    def test_cli_writes_match_desktop(self) -> None:
        for table in ("Task", "Measures Table", "Date"):
            self._strip_descriptions(table)
        self.assertEqual(SemanticModel.load(self.root).find_table("Task").description, "")

        self._invoke("model", "table", "set", "Task", f"description={TASK}")
        self._invoke("model", "column", "set", "Task.Status", f"description={STATUS}")
        self._invoke("model", "measure", "set", "Measures Table.Task Count", f"description={TASK_COUNT}")
        self._invoke("model", "measure", "set", "Measures Table.Completed Tasks", f"description={COMPLETED}")
        self._invoke("model", "measure", "set", "Measures Table.Open Tasks", f"description={OPEN}")
        spec = {"hierarchies": {"Date": [{
            "name": "Calendar",
            "levels": ["Year", "Quarter", "MonthName", "Date"],
            "description": CALENDAR,
        }]}}
        result = apply_model_yaml(self.root, yaml.safe_dump(spec))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.hierarchies_updated, ["Date.Calendar"])

        for table in ("Task", "Measures Table", "Date"):
            with self.subTest(table=table):
                self.assertEqual(self._written(table), self._desktop(table))

    def test_setting_the_same_description_does_not_write(self) -> None:
        before = self._path("Measures Table").read_bytes()
        out = self._invoke("model", "measure", "set", "Measures Table.Task Count", f"description={TASK_COUNT}")
        self.assertIn("No change", out)
        out = self._invoke("model", "table", "set", "Task", f"description={TASK}")
        self.assertIn("No change", out)
        self.assertEqual(self._path("Measures Table").read_bytes(), before)

    def test_replace_and_clear_keep_neighbours(self) -> None:
        self._invoke("model", "measure", "set", "Measures Table.Task Count", "description=Rows in Task.")
        text = self._written("Measures Table")
        self.assertIn("\t/// Rows in Task.\n\tmeasure 'Task Count'", text)
        self.assertNotIn("Counts every Task row", text)

        self._invoke("model", "measure", "set", "Measures Table.Task Count", "description=")
        text = self._written("Measures Table")
        self.assertIn("\tlineageTag: f26f848f-8b6f-454e-b686-ec6650d39254\n\n\tmeasure 'Task Count'", text)
        self.assertIn(f"\t/// {COMPLETED}\n\tmeasure 'Completed Tasks'", text)

        self._invoke("model", "table", "set", "Task", "description=")
        self.assertTrue(self._written("Task").startswith("table Task\n"))

    def test_create_measure_with_description_via_apply(self) -> None:
        spec = {"measures": {"Measures Table": [{
            "name": "Blocked Tasks",
            "expression": 'CALCULATE ( [Task Count], Task[Status] = "Blocked" )',
            "description": "Tasks waiting on something.\nSee the Task Board page.",
        }]}}
        result = apply_model_yaml(self.root, yaml.safe_dump(spec))
        self.assertEqual(result.errors, [])
        text = self._written("Measures Table")
        self.assertIn(
            "\t/// Tasks waiting on something.\n\t/// See the Task Board page.\n\tmeasure 'Blocked Tasks' =",
            text,
        )
        measure = SemanticModel.load(self.root).find_table("Measures Table").find_measure("Blocked Tasks")
        self.assertEqual(measure.description, "Tasks waiting on something.\nSee the Task Board page.")

    def test_export_carries_descriptions_and_apply_keeps_them(self) -> None:
        exported = yaml.safe_load(export_model_yaml(self.root))
        self.assertEqual(exported["tables"]["Task"]["description"], TASK)
        self.assertEqual(exported["columns"]["Task"]["Status"]["description"], STATUS)
        by_name = {m["name"]: m for m in exported["measures"]["Measures Table"]}
        self.assertEqual(by_name["Task Count"]["description"], TASK_COUNT)
        self.assertEqual(by_name["Completed Tasks"]["description"], COMPLETED)
        self.assertNotIn("description", by_name["Completion %"])
        calendar = next(h for h in exported["hierarchies"]["Date"] if h["name"] == "Calendar")
        self.assertEqual(calendar["description"], CALENDAR)

        before = {t: self._path(t).read_bytes() for t in ("Task", "Measures Table", "Date")}
        spec = {
            "tables": {"Task": {"description": TASK}},
            "columns": {"Task": {"Status": {"description": STATUS}}},
            "measures": {"Measures Table": [
                {"name": name, "description": by_name[name]["description"]}
                for name in ("Task Count", "Completed Tasks", "Open Tasks")
            ]},
            "hierarchies": {"Date": [calendar]},
        }
        result = apply_model_yaml(self.root, yaml.safe_dump(spec))
        self.assertEqual(result.errors, [])
        self.assertFalse(result.has_changes)
        self.assertEqual({t: self._path(t).read_bytes() for t in before}, before)

    def test_cli_prints_bracketed_descriptions_literally(self) -> None:
        text = "Paths use [/] as the separator; [bold] is literal."
        for kind, target, get_args in (
            ("table", "Task", ["Task"]),
            ("column", "Task.Status", ["Task.Status"]),
            ("measure", "Measures Table.Task Count", ["Measures Table", "Task Count"]),
        ):
            with self.subTest(kind=kind):
                out = self._invoke("model", kind, "set", target, f"description={text}")
                self.assertIn(text, out)
                out = self._invoke("model", kind, "get", *get_args)
                self.assertIn(text, out)

    def test_hierarchy_recreate_keeps_description(self) -> None:
        spec = {"hierarchies": {"Date": [{"name": "Calendar", "levels": ["Year", "MonthName", "Date"]}]}}
        result = apply_model_yaml(self.root, yaml.safe_dump(spec))
        self.assertEqual(result.errors, [])
        self.assertIn(f"\t/// {CALENDAR}\n\thierarchy Calendar", self._written("Date"))


class LegacyDescriptionPropertyTests(unittest.TestCase):
    """The invalid ``description:`` property form is read, and replaced on write."""

    def test_set_description_replaces_legacy_property(self) -> None:
        from tests.test_model_extensions import _make_project, _write_table

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tdescription: Old text
\t\tlineageTag: m-1
""")
            self.assertEqual(SemanticModel.load(root).find_table("Sales").find_measure("Revenue").description, "Old text")
            spec = {"measures": {"Sales": [{"name": "Revenue", "description": "Old text"}]}}
            result = apply_model_yaml(root, yaml.safe_dump(spec))
            self.assertEqual(result.errors, [])
            self.assertEqual(result.measures_updated, ["Sales.Revenue"])
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "table Sales\n\t/// Old text\n\tmeasure Revenue = SUM(Sales[Amount])\n\t\tlineageTag: m-1\n",
            )


if __name__ == "__main__":
    unittest.main()
