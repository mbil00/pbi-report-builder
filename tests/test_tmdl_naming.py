"""TMDL file names, line endings and the model.tmdl ``ref table`` list (#52, #57).

Desktop's report-04 build is the reference: ``Q/A Notes`` is stored as
``Q%2FA Notes.tmdl``, ``Owner's Info.tmdl`` keeps its apostrophe, every file
uses CRLF, and ``ref table`` lists imported tables first and created ones after
them, in creation order. The tests copy that project, make the change through
the CLI and compare against what Desktop wrote. They skip if
`04-desktop-shapes.pbip` is absent.
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
from pbi.modeling.writes import tmdl_file_name
from tests.test_desktop_shapes_fixture import SHAPES_DIR, SHAPES_PBIP
from tests.test_model_extensions import _make_project, _write_table

DEFINITION = Path("04-desktop-shapes.SemanticModel") / "definition"
DESKTOP_MODEL = SHAPES_DIR / DEFINITION / "model.tmdl"


def _lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8-sig").split("\r\n")


def _is_crlf(data: bytes) -> bool:
    return b"\n" in data and data.count(b"\n") == data.count(b"\r\n")


class TmdlFileNameTests(unittest.TestCase):
    def test_matches_desktop_file_names(self) -> None:
        self.assertEqual(tmdl_file_name("Q/A Notes"), "Q%2FA Notes.tmdl")
        self.assertEqual(tmdl_file_name("Owner's Info"), "Owner's Info.tmdl")
        self.assertEqual(tmdl_file_name("Rates (EUR)"), "Rates (EUR).tmdl")
        self.assertEqual(tmdl_file_name("Time & Expenses"), "Time & Expenses.tmdl")
        self.assertEqual(tmdl_file_name("Measures Table"), "Measures Table.tmdl")

    def test_desktop_fixture_names_round_trip(self) -> None:
        tables = SHAPES_DIR / DEFINITION / "tables"
        if not tables.exists():
            self.skipTest("report-04 Desktop output not built yet")
        model = SemanticModel.load(SHAPES_DIR)
        for table in model.tables:
            with self.subTest(table=table.name):
                self.assertEqual(table.definition_path.name, tmdl_file_name(table.name))

    def test_other_characters_windows_refuses_are_escaped(self) -> None:
        self.assertEqual(tmdl_file_name('a\\b:c*d?e"f<g>h|i'), "a%5Cb%3Ac%2Ad%3Fe%22f%3Cg%3Eh%7Ci.tmdl")

    def test_percent_is_escaped_so_names_never_share_a_file(self) -> None:
        self.assertEqual(tmdl_file_name("A/B"), "A%2FB.tmdl")
        self.assertEqual(tmdl_file_name("A%2FB"), "A%252FB.tmdl")
        self.assertEqual(tmdl_file_name("50% Margin"), "50%25 Margin.tmdl")


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopTmdlNamingTests(unittest.TestCase):
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
        self.definition = self.root / DEFINITION
        self.tables = self.definition / "tables"
        self.model_path = self.definition / "model.tmdl"
        self.runner = CliRunner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _invoke(self, *args: str) -> str:
        result = self.runner.invoke(app, [*args, "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 0, result.stdout)
        return result.stdout

    def _desktop_with_refs_after_last(self, *refs: str) -> list[str]:
        lines = _lines(DESKTOP_MODEL)
        last = max(i for i, line in enumerate(lines) if line.startswith("ref table "))
        return [*lines[: last + 1], *refs, *lines[last + 1 :]]

    def test_created_tables_use_desktop_names_and_crlf(self) -> None:
        self._invoke("model", "table", "create", "Q/A Copy", "{ 1, 2 }")
        self._invoke("model", "table", "create", "Owner's Copy", "{ 1, 2 }")

        qa = self.tables / "Q%2FA Copy.tmdl"
        owner = self.tables / "Owner's Copy.tmdl"
        self.assertTrue(qa.exists())
        self.assertTrue(owner.exists())
        self.assertTrue(qa.read_bytes().startswith(b"table 'Q/A Copy'\r\n"))
        self.assertTrue(owner.read_bytes().startswith(b"table 'Owner''s Copy'\r\n"))
        self.assertTrue(_is_crlf(qa.read_bytes()))

        model = SemanticModel.load(self.root)
        self.assertEqual(model.find_table("Q/A Copy").definition_path, qa)
        self.assertEqual(model.find_table("Owner's Copy").definition_path, owner)

    def test_created_tables_append_ref_lines_in_creation_order(self) -> None:
        self._invoke("model", "table", "create", "Q/A Copy", "{ 1, 2 }")
        self._invoke("model", "field-parameter", "create", "Metric Picker",
                     "Measures Table.Task Count", "Measures Table.Total Hours")
        self._invoke("model", "table", "create", "Owner's Copy", "{ 1, 2 }")

        self.assertTrue(_is_crlf(self.model_path.read_bytes()))
        self.assertEqual(
            _lines(self.model_path),
            self._desktop_with_refs_after_last(
                "ref table 'Q/A Copy'", "ref table 'Metric Picker'", "ref table 'Owner''s Copy'",
            ),
        )
        self.assertTrue((self.tables / "Metric Picker.tmdl").exists())

    def test_apply_field_parameter_appends_ref_line(self) -> None:
        spec = {"fieldParameters": {"Metric Picker": {"fields": [
            {"field": "Measures Table.Task Count", "label": "Tasks"},
        ]}}}
        result = apply_model_yaml(self.root, yaml.safe_dump(spec))
        self.assertEqual(result.errors, [])
        self.assertEqual(_lines(self.model_path), self._desktop_with_refs_after_last("ref table 'Metric Picker'"))
        self.assertTrue(_is_crlf((self.tables / "Metric Picker.tmdl").read_bytes()))

    def test_dry_run_writes_nothing(self) -> None:
        before = self.model_path.read_bytes()
        self._invoke("model", "table", "create", "Q/A Copy", "{ 1, 2 }", "--dry-run")
        self._invoke("model", "field-parameter", "create", "Metric Picker", "Measures Table.Task Count", "--dry-run")
        self.assertEqual(self.model_path.read_bytes(), before)
        self.assertFalse((self.tables / "Q%2FA Copy.tmdl").exists())
        self.assertFalse((self.tables / "Metric Picker.tmdl").exists())

    def test_edit_keeps_crlf(self) -> None:
        path = self.tables / "Measures Table.tmdl"
        self._invoke("model", "measure", "create", "Measures Table", "Blocked Tasks",
                     'CALCULATE ( [Task Count], Task[Status] = "Blocked" )')
        data = path.read_bytes()
        self.assertTrue(_is_crlf(data))
        self.assertIn(b"\tmeasure 'Blocked Tasks' = ", data)

    def test_rename_moves_file_and_ref_line(self) -> None:
        out = self._invoke("model", "table", "rename", "Q/A Notes", "QA Log")

        self.assertFalse((self.tables / "Q%2FA Notes.tmdl").exists())
        renamed = self.tables / "QA Log.tmdl"
        self.assertTrue(renamed.read_bytes().startswith(b"table 'QA Log'\r\n"))
        self.assertTrue(_is_crlf(renamed.read_bytes()))
        self.assertIn("model.tmdl", out)

        expected = [
            "ref table 'QA Log'" if line == "ref table 'Q/A Notes'" else line
            for line in _lines(DESKTOP_MODEL)
        ]
        self.assertEqual(_lines(self.model_path), expected)
        # PBI_QueryOrder names the query, which a rename doesn't change.
        self.assertIn('"Q/A Notes"', self.model_path.read_text(encoding="utf-8"))

    def test_rename_to_name_with_slash_escapes_file_name(self) -> None:
        self._invoke("model", "table", "rename", "Owner's Info", "Owner/Lead Info")
        self.assertTrue((self.tables / "Owner%2FLead Info.tmdl").exists())
        self.assertIn("ref table 'Owner/Lead Info'", _lines(self.model_path))
        self.assertNotIn("ref table 'Owner''s Info'", _lines(self.model_path))


class TmdlWriteEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _make_project(self.root)
        self.table = _write_table(self.root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = 1
""")
        self.model_path = self.root / "Sample.SemanticModel" / "definition" / "model.tmdl"
        self.runner = CliRunner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _invoke(self, *args: str):
        return self.runner.invoke(app, [*args, "--project", str(self.root / "Sample.pbip")])

    def test_lf_file_stays_lf(self) -> None:
        result = self._invoke("model", "measure", "create", "Sales", "Cost", "2")
        self.assertEqual(result.exit_code, 0, result.stdout)
        data = self.table.read_bytes()
        self.assertIn(b"measure Cost = 2\n", data)
        self.assertNotIn(b"\r\n", data)

    def test_model_without_ref_list_is_left_alone(self) -> None:
        self.model_path.write_bytes(b"model Model\r\n\tculture: en-US\r\n")
        result = self._invoke("model", "table", "create", "Extra", "{ 1 }")
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertEqual(self.model_path.read_bytes(), b"model Model\r\n\tculture: en-US\r\n")

    def _assert_refused(self, result, file_name: str) -> None:
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(file_name, result.stdout)

    def test_rename_refuses_to_overwrite_a_legacy_file(self) -> None:
        # "Revenue Sales" saved under the pre-#52 name, which is the new name of "Revenue_Sales".
        legacy = _write_table(self.root, "Revenue_Sales.tmdl", "table 'Revenue Sales'\n\tmeasure Kept = 1")
        before = {path: path.read_bytes() for path in self.table.parent.iterdir()}
        result = self._invoke("model", "table", "rename", "Sales", "Revenue_Sales")
        self._assert_refused(result, "Revenue_Sales.tmdl")
        self.assertEqual({path: path.read_bytes() for path in self.table.parent.iterdir()}, before)
        self.assertIn(b"measure Kept", legacy.read_bytes())

    def test_role_and_perspective_create_refuse_existing_files(self) -> None:
        from pbi.modeling.writes_perspectives import PerspectiveMemberSpec, create_perspective
        from pbi.modeling.writes_roles import RoleSpec, create_role

        definition = self.root / "Sample.SemanticModel" / "definition"
        for folder, name, create, spec in (
            ("roles", "Readers", create_role, RoleSpec()),
            ("perspectives", "Sales View", create_perspective, PerspectiveMemberSpec(include_all_tables=["Sales"])),
        ):
            with self.subTest(folder=folder):
                path = definition / folder / f"{name}.tmdl"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"not a definition the model knows about\r\n")
                with self.assertRaisesRegex(ValueError, "already exists"):
                    create(self.root, name, spec)
                self.assertEqual(path.read_bytes(), b"not a definition the model knows about\r\n")

    def test_field_parameter_refuses_a_file_staged_in_the_same_session(self) -> None:
        from pbi.modeling.writes import TmdlEditSession
        from pbi.modeling.writes_field_parameters import create_field_parameter

        model = SemanticModel.load(self.root)
        session = TmdlEditSession()
        create_field_parameter(self.root, "Picker", ["Sales.Revenue"], None, model=model, edit_session=session)
        with self.assertRaisesRegex(ValueError, "Picker.tmdl"):
            create_field_parameter(self.root, "Picker", ["Sales.Revenue"], None, model=model, edit_session=session)

    def test_create_refuses_to_overwrite_an_existing_file(self) -> None:
        _write_table(self.root, "Extra.tmdl", "table Other\n\tmeasure X = 1")
        result = self._invoke("model", "table", "create", "Extra", "{ 1 }")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Extra.tmdl", result.stdout)
        self.assertIn(b"table Other", (self.table.parent / "Extra.tmdl").read_bytes())


if __name__ == "__main__":
    unittest.main()
