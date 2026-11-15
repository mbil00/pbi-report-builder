"""CLI writes for textbox runs (#34) and filter literals (#35) match report-04.

Each test copies the Desktop-built report-04 project, makes the same edit
through the CLI that was made in Desktop, and compares the written JSON with
what Desktop saved. They skip if `04-desktop-shapes.pbip` is absent.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.fields import infer_measure_data_type
from pbi.filters import _format_literal
from pbi.model import SemanticModel
from pbi.project import Project
from pbi.textbox import set_textbox_content
from pbi.validate import _validate_textbox_runs
from tests.test_desktop_shapes_fixture import SHAPES_DIR, SHAPES_PBIP, _objects, _visual, _visuals

OPERATORS = {1: "greater-than", 2: "greater-than-or-equal"}


def _first_run_paragraphs(visual: dict) -> list[dict]:
    return visual["visual"]["objects"]["general"][0]["properties"]["paragraphs"]


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopLiteralWriteTests(unittest.TestCase):
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

    def _qa_visual(self, name: str) -> dict:
        project = Project.find(self.pbip)
        return project.find_visual(project.find_page("QA Hidden"), name).data

    # --- #34 textbox ---------------------------------------------------------

    def test_styled_run_matches_desktop(self) -> None:
        self._invoke("visual", "create", "QA Hidden", "textbox", "--name", "header")
        self._invoke(
            "visual", "set", "QA Hidden", "header",
            "text=Delivery Overview",
            "text.fontFamily=Georgia",
            "text.fontSize=24pt",
            "text.fontColor=#1F3A5F",
            "text.bold=true",
        )
        written = _first_run_paragraphs(self._qa_visual("header"))[0]["textRuns"][0]
        desktop = _first_run_paragraphs(_visual("Overview", "Overview Header"))[0]["textRuns"][0]
        self.assertEqual(written, desktop)

    def test_italic_run_and_unstyled_run_match_desktop(self) -> None:
        self._invoke("visual", "create", "QA Hidden", "textbox", "--name", "note", "--text", "Hidden page for fixture QA.")
        desktop_note = _objects(_visual("QA Hidden", "QA Note"), "general")[0]["properties"]["paragraphs"]
        self.assertEqual(_first_run_paragraphs(self._qa_visual("note")), desktop_note)

        self._invoke("visual", "set", "QA Hidden", "note", "text.italic=true", "text.fontColor=#D64550")
        style = _first_run_paragraphs(self._qa_visual("note"))[0]["textRuns"][0]["textStyle"]
        desktop_italic = _first_run_paragraphs(_visual("Overview", "Overview Header"))[1]["textRuns"][1]["textStyle"]
        self.assertEqual(style["fontStyle"], desktop_italic["fontStyle"])
        self.assertEqual(style["color"], desktop_italic["color"])

        # Turning a flag off drops the key, as Desktop omits unset styles.
        self._invoke("visual", "set", "QA Hidden", "note", "text.italic=false")
        style = _first_run_paragraphs(self._qa_visual("note"))[0]["textRuns"][0]["textStyle"]
        self.assertNotIn("fontStyle", style)

    def test_apply_writes_plain_strings_and_rejects_bad_font_size(self) -> None:
        good = self.root / "good.yaml"
        good.write_text(
            "pages:\n- name: QA Hidden\n  visuals:\n  - name: applied\n    type: textbox\n"
            "    text: It's done\n    textStyle: {fontSize: 12pt, fontColor: '#605E5C'}\n",
            encoding="utf-8",
        )
        self._invoke("apply", str(good))
        run = _first_run_paragraphs(self._qa_visual("applied"))[0]["textRuns"][0]
        self.assertEqual(run, {"value": "It's done", "textStyle": {"fontSize": "12pt", "color": "#605e5c"}})

        bad = self.root / "bad.yaml"
        bad.write_text(
            "pages:\n- name: QA Hidden\n  visuals:\n  - name: applied\n    type: textbox\n"
            "    text: x\n    textStyle: {fontSize: huge}\n",
            encoding="utf-8",
        )
        result = self.runner.invoke(app, ["apply", str(bad), "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("fontSize must be a number of points", result.stdout)
        self.assertIsInstance(result.exception, SystemExit)  # a clean exit, not a traceback

    def test_legacy_quoted_run_is_flagged_and_repaired(self) -> None:
        legacy = {
            "visual": {
                "visualType": "textbox",
                "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [{
                    "value": "'Sales Overview'",
                    "textStyle": {
                        "fontFamily": "'Segoe UI'",
                        "fontSize": "'22pt'",
                        "fontWeight": "'bold'",
                        "color": {"expr": {"Literal": {"Value": "'#1A1A1A'"}}},
                    },
                }]}]}}]},
            }
        }
        self.assertEqual(len(_validate_textbox_runs(legacy["visual"], "v.json")), 1)

        set_textbox_content(legacy, style_updates={"italic": True})
        run = _first_run_paragraphs(legacy)[0]["textRuns"][0]
        self.assertEqual(run, {
            "value": "Sales Overview",
            "textStyle": {
                "fontFamily": "Segoe UI",
                "fontSize": "22pt",
                "fontWeight": "bold",
                "color": "#1a1a1a",
                "fontStyle": "italic",
            },
        })
        self.assertEqual(_validate_textbox_runs(legacy["visual"], "v.json"), [])

    def test_desktop_textboxes_pass_validation(self) -> None:
        for page in ("Overview", "QA Hidden"):
            for visual in _visuals(page):
                with self.subTest(page=page, visual=visual["name"]):
                    self.assertEqual(_validate_textbox_runs(visual["visual"], "v.json"), [])

    # --- #35 filter literals -------------------------------------------------

    def test_measure_and_column_filter_literals_match_desktop(self) -> None:
        cases = []
        for visual in _visuals("Filter Lab"):
            for desktop_filter in visual.get("filterConfig", {}).get("filters", []):
                if desktop_filter.get("type") != "Advanced" or "filter" not in desktop_filter:
                    continue
                comparison = desktop_filter["filter"]["Where"][0]["Condition"].get("Comparison")
                if comparison is None:
                    continue
                field = desktop_filter["field"]
                kind = "Measure" if "Measure" in field else "Column"
                entity = field[kind]["Expression"]["SourceRef"]["Entity"]
                literal = comparison["Right"]["Literal"]["Value"]
                cases.append((f"{entity}.{field[kind]['Property']}", comparison["ComparisonKind"], literal))
        self.assertEqual(len(cases), 7)

        for field_ref, kind, literal in cases:
            with self.subTest(field=field_ref):
                self._invoke(
                    "filter", "create", field_ref,
                    "--page", "QA Hidden",
                    "--mode", "advanced",
                    "--operator", OPERATORS[kind],
                    "--value", literal[:-1],
                )
                project = Project.find(self.pbip)
                filters = project.find_page("QA Hidden").data["filterConfig"]["filters"]
                comparison = filters[-1]["filter"]["Where"][0]["Condition"]["Comparison"]
                self.assertEqual(comparison["ComparisonKind"], kind)
                self.assertEqual(comparison["Right"]["Literal"]["Value"], literal)

    def test_range_filter_on_untyped_measure_is_numeric(self) -> None:
        self._invoke(
            "filter", "create", "Measures Table.Hours Ratio",
            "--page", "QA Hidden", "--mode", "range", "--min", "1", "--max", "1.25",
        )
        project = Project.find(self.pbip)
        where = project.find_page("QA Hidden").data["filterConfig"]["filters"][-1]["filter"]["Where"]
        literals = [w["Condition"]["Comparison"]["Right"]["Literal"]["Value"] for w in where]
        self.assertEqual(literals, ["1D", "1.25D"])  # DIVIDE returns a double


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class MeasureTypeInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = SemanticModel.load(SHAPES_DIR)
        cls.measures = {m.name: m for t in cls.model.tables for m in t.measures}

    def _type(self, name: str) -> str:
        return infer_measure_data_type(self.model, self.measures[name])

    def test_types_from_dax(self) -> None:
        self.assertEqual(self._type("Task Count"), "int64")  # COUNTROWS
        self.assertEqual(self._type("Completed Tasks"), "int64")  # CALCULATE over [Task Count]
        self.assertEqual(self._type("Story Points"), "int64")  # SUM of an int64 column
        self.assertEqual(self._type("Expense Amount"), "decimal")  # CALCULATE(SUM(fixed decimal))
        self.assertEqual(self._type("Hours Ratio"), "double")  # DIVIDE
        self.assertEqual(self._type("Avg Hourly Rate"), "double")  # AVERAGE

    def test_fallbacks(self) -> None:
        # Subtraction isn't a recognised shape; "#,0" says nothing about the type.
        self.assertEqual(self._type("Open Tasks"), "numeric")
        self.assertEqual(self._type("Status Color"), "numeric")

    def test_numeric_fallback_types_by_value(self) -> None:
        self.assertEqual(_format_literal("10", "numeric"), "10L")
        self.assertEqual(_format_literal("0.95", "numeric"), "0.95D")
        self.assertEqual(_format_literal("High", "numeric"), "'High'")
        self.assertEqual(_format_literal("1.5", "int64"), "1.5D")
        self.assertEqual(_format_literal("500", "decimal"), "500M")
        # Unknown column types still quote, since the value may be text.
        self.assertEqual(_format_literal("10", None), "'10'")


if __name__ == "__main__":
    unittest.main()
