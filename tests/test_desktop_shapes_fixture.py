"""Tests for the report-04 Desktop-shapes fixture.

The build inputs (CSVs, theme, image, checklist) are generated and must stay
byte-stable. The Desktop-built PBIP was saved by hand in Power BI Desktop; the
shape tests pin what Desktop wrote, so CLI write paths can be derived from it.
They skip if `04-desktop-shapes.pbip` is absent.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import ModuleType

from pbi.model import SemanticModel
from pbi.project import Project
from tests.support import (
    RENAMED_DIR,
    REPO_ROOT,
    SHAPES_DATA,
    SHAPES_DIR,
    SHAPES_PBIP,
    literal_value,
    page_folders,
    page_visuals,
    read_json,
    report_definition,
    visual_by_title,
    visual_objects,
    visual_title,
)


EXPECTED_PAGES = [
    "Overview",
    "Task Board",
    "Filter Lab",
    "Chart Gallery",
    "Project Detail",
    "Person Tooltip",
    "QA Hidden",
]


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_fixture_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DesktopShapesInputsTests(unittest.TestCase):
    """The committed build inputs match what the generators produce."""

    def test_dataset_regenerates_byte_identical(self) -> None:
        datasets = _load_script("generate_fixture_datasets")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = datasets.generate_desktop_shapes(out)
            generated = sorted(path.name for path in out.iterdir())
            committed = sorted(path.name for path in SHAPES_DATA.iterdir())
            self.assertEqual(generated, committed)
            for name in generated:
                self.assertEqual(
                    (out / name).read_bytes(),
                    (SHAPES_DATA / name).read_bytes(),
                    f"{name} differs; rerun scripts/generate_fixture_datasets.py",
                )
        self.assertEqual(manifest["Task_rows"], 600)

    def test_checklist_regenerates_identical(self) -> None:
        checklists = _load_script("generate_fixture_build_checklists")
        rendered = checklists.build_checklist("report-04-desktop-shapes", SHAPES_DATA)
        committed = (SHAPES_DIR / "BUILD-CHECKLIST.md").read_text(encoding="utf-8")
        self.assertEqual(rendered, committed, "rerun scripts/generate_fixture_build_checklists.py")
        self.assertNotIn("@@", rendered)
        for page in EXPECTED_PAGES:
            self.assertIn(f"`{page}`", rendered)

    def test_resource_inputs_have_spaces_and_are_valid(self) -> None:
        theme = SHAPES_DATA / "Desktop Shapes Theme.json"
        self.assertIn('"name": "Desktop Shapes Theme"', theme.read_text(encoding="utf-8"))
        self.assertNotIn("textClasses", theme.read_text(encoding="utf-8"))

        png = (SHAPES_DATA / "Team Logo.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        idat_len = struct.unpack(">I", png[33:37])[0]
        self.assertEqual(png[37:41], b"IDAT")
        pixels = zlib.decompress(png[41:41 + idat_len])
        self.assertEqual(len(pixels), height * (1 + width * 3))


# --- Desktop output helpers -------------------------------------------------
#
# The fixture identifies visuals by title text (Desktop assigns random IDs) and
# the tests assert on shapes, not on positions, IDs or lineage tags. See the
# "Consuming The Fixture" and "What The Build Showed" sections of SPEC.md.
# The PBIR readers shared with other test modules live in tests/support.py.


def _tables_dir(root: Path = SHAPES_DIR) -> Path:
    return root / "04-desktop-shapes.SemanticModel" / "definition" / "tables"


def _tmdl(name: str, root: Path = SHAPES_DIR) -> str:
    return (_tables_dir(root) / f"{name}.tmdl").read_text(encoding="utf-8")


def _tmdl_block(text: str, header: str) -> str:
    """Return one tab-indented object block (header line plus deeper lines)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == header)
    indent = len(lines[start]) - len(lines[start].lstrip("\t"))
    block = [lines[start]]
    for line in lines[start + 1:]:
        depth = len(line) - len(line.lstrip("\t"))
        if line.strip() and depth <= indent:
            break
        block.append(line)
    return "\n".join(block)


def _relationships(root: Path = SHAPES_DIR) -> list[dict[str, str]]:
    text = (root / "04-desktop-shapes.SemanticModel" / "definition" / "relationships.tmdl").read_text(encoding="utf-8")
    result = []
    for chunk in text.split("relationship ")[1:]:
        props = {}
        for line in chunk.splitlines()[1:]:
            if ":" in line:
                key, _, value = line.strip().partition(":")
                props[key.strip()] = value.strip()
        result.append(props)
    return result


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class DesktopShapesFixtureTests(unittest.TestCase):
    """The committed Desktop output still has the shapes SPEC.md documents."""

    # --- structure ----------------------------------------------------------

    def test_pages_match_spec(self) -> None:
        project = Project.find(SHAPES_PBIP)
        self.assertEqual([page.display_name for page in project.get_pages()], EXPECTED_PAGES)

    def test_page_kinds(self) -> None:
        pages = {name: read_json(path / "page.json") for name, path in page_folders().items()}
        self.assertEqual(pages["Project Detail"]["pageBinding"]["type"], "Drillthrough")
        self.assertEqual(pages["Person Tooltip"]["pageBinding"]["type"], "Tooltip")
        self.assertEqual(pages["Person Tooltip"]["type"], "Tooltip")
        hidden = {name for name, page in pages.items() if page.get("visibility") == "HiddenInViewMode"}
        self.assertEqual(hidden, {"Person Tooltip", "QA Hidden"})

    def test_titles_unique_per_page(self) -> None:
        for page in EXPECTED_PAGES:
            titles = [visual_title(v) for v in page_visuals(page)]
            self.assertNotIn(None, titles, page)
            self.assertEqual(len(titles), len(set(titles)), page)

    def test_model_has_special_character_tables(self) -> None:
        project = Project.find(SHAPES_PBIP)
        names = {table.name for table in SemanticModel.load(project.root).tables}
        for expected in (
            "Rates (EUR)", "Time & Expenses", "Measures Table", "Portfolio Target", "Q/A Notes", "Owner's Info",
        ):
            self.assertIn(expected, names)
        self.assertEqual(len(names), 21)

    # --- #52 TMDL naming ----------------------------------------------------

    def test_tmdl_file_names_and_quoting(self) -> None:
        files = {path.name for path in _tables_dir().iterdir()}
        self.assertIn("Q%2FA Notes.tmdl", files)
        self.assertIn("Owner's Info.tmdl", files)
        self.assertTrue(_tmdl("Owner's Info").startswith("table 'Owner''s Info'"))
        self.assertIn(b"\r\n", (_tables_dir() / "Task.tmdl").read_bytes())
        model = (SHAPES_DIR / "04-desktop-shapes.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
        self.assertIn(
            'annotation PBI_QueryOrder = ["Date","Project","Person","Rates (EUR)","Task","Tag","TaskTag",'
            '"Time & Expenses","Q/A Notes","Portfolio Target"]',
            model,
        )

    # --- #38 descriptions ---------------------------------------------------

    def test_descriptions_sit_above_their_objects(self) -> None:
        measures = _tmdl("Measures Table").splitlines()
        index = next(i for i, line in enumerate(measures) if line.startswith("\tmeasure 'Task Count'"))
        self.assertEqual(
            measures[index - 2:index],
            [
                "\t/// Number of tasks in the current filter context.",
                "\t/// Counts every Task row, including blocked tasks.",
            ],
        )
        self.assertIn('\t/// Tasks with Status = "Completed" & counted once.\n\tmeasure \'Completed Tasks\'',
                      _tmdl("Measures Table"))
        task = _tmdl("Task")
        self.assertTrue(task.startswith("/// One row per task. Source: Task.csv.\ntable Task"))
        self.assertIn("\t/// Workflow status: Not started, In progress, Blocked or Completed.\n\tcolumn Status", task)
        self.assertIn("\t/// Year > Quarter > Month > Date drill path.\n\thierarchy Calendar", _tmdl("Date"))

    # --- #46 cardinality ----------------------------------------------------

    def test_relationships_write_only_non_defaults(self) -> None:
        rels = {(r["fromColumn"], r["toColumn"]): r for r in _relationships()}
        self.assertEqual(len(rels), 12)
        self.assertEqual(rels[("Task.DueDate", "Date.Date")].get("isActive"), "false")
        self.assertEqual(rels[("TaskTag.TaskKey", "Task.TaskKey")].get("crossFilteringBehavior"), "bothDirections")
        one_to_one = rels[("'Q/A Notes'.ProjectKey", "Project.ProjectKey")]
        self.assertEqual(one_to_one.get("fromCardinality"), "one")
        self.assertNotIn("toCardinality", one_to_one)
        many_to_many = rels[("'Portfolio Target'.Portfolio", "Project.Portfolio")]
        self.assertEqual(many_to_many.get("toCardinality"), "many")
        self.assertNotIn("fromCardinality", many_to_many)
        self.assertNotIn("crossFilteringBehavior", many_to_many)
        plain = rels[("Task.CreatedDate", "Date.Date")]
        self.assertEqual(set(plain), {"fromColumn", "toColumn"})

    # --- #45 / #46 validate ---------------------------------------------------

    def test_validate_accepts_desktop_output(self) -> None:
        from pbi.validate import validate_project

        issues = validate_project(Project.find(SHAPES_PBIP))
        errors = [f"{i.file}: {i.message}" for i in issues if i.level == "error"]
        self.assertEqual(errors, [])
        # Measures from `Measures Table` (which keeps Desktop's hidden placeholder
        # column) and from fact tables need no relationship path.
        path_warnings = [i.message for i in issues if "relationship path" in i.message]
        self.assertEqual(path_warnings, [])

    # --- column and measure metadata ------------------------------------------

    def test_format_strings_and_column_metadata(self) -> None:
        measures = _tmdl("Measures Table")
        self.assertNotIn("formatString", _tmdl_block(measures, "measure 'Hours Ratio' = DIVIDE ( [Actual Hours], [Estimate Hours] )"))
        self.assertIn("\t\tformatString: 0\n", _tmdl_block(measures, "measure 'Story Points' = SUM ( Task[StoryPoints] )"))
        self.assertIn('formatString: """€""#,0.00"" /h"""', measures)
        self.assertIn('formatString: "€"\\ #,0.00;-"€"\\ #,0.00;"€"\\ #,0.00', measures)
        self.assertIn("displayFolder: Counts\\Status", measures)
        self.assertIn("summarizeBy: average", _tmdl_block(_tmdl("Q%2FA Notes"), "column QAScore"))
        self.assertIn("dataType: decimal", _tmdl_block(_tmdl("Time & Expenses"), "column Amount"))
        self.assertIn("dataCategory: Country", _tmdl_block(_tmdl("Person"), "column Country"))
        self.assertIn("sortByColumn: 'Duration Band Order'", _tmdl("Task"))
        self.assertIn("sortByColumn: StatusRank", _tmdl("Task"))
        self.assertIn("source = Row(\"Column\", BLANK())", measures)

    # --- #40 calculated table columns -------------------------------------------

    def test_calculated_table_column_names(self) -> None:
        self.assertIn("\tcolumn Value\n", _tmdl("Hours Band"))
        priority = _tmdl("Priority Levels")
        self.assertIn("sourceColumn: [Value1]", priority)
        self.assertIn("sourceColumn: [Value2]", priority)
        self.assertIn("sourceColumn: Task[Status]", _tmdl("Status Summary"))
        self.assertIn("sourceColumn: Project[Portfolio]", _tmdl("Portfolio Status"))
        self.assertIn("sourceColumn: [Budget EUR]", _tmdl("Project List"))

    # --- #34 textbox runs ---------------------------------------------------

    def test_textbox_paragraphs_and_runs(self) -> None:
        header = visual_objects(visual_by_title("Overview", "Overview Header"), "general")[0]["properties"]["paragraphs"]
        self.assertEqual([len(p["textRuns"]) for p in header], [1, 2])
        title_run = header[0]["textRuns"][0]
        self.assertEqual(title_run["value"], "Delivery Overview")
        self.assertEqual(
            title_run["textStyle"],
            {"fontWeight": "bold", "fontFamily": "Georgia", "fontSize": "24pt", "color": "#1f3a5f"},
        )
        plain, styled = header[1]["textRuns"]
        self.assertEqual(plain["value"], "Portfolio status for ")
        self.assertEqual(plain["textStyle"], {"fontSize": "12pt", "color": "#605e5c"})
        self.assertEqual(styled["textStyle"]["fontStyle"], "italic")
        self.assertEqual(styled["textStyle"]["color"], "#d64550")

        link = visual_objects(visual_by_title("Overview", "Overview Link"), "general")[0]["properties"]["paragraphs"][0]["textRuns"]
        self.assertEqual(link[0], {"value": "Open the "})
        self.assertEqual(link[1], {"value": "project handbook", "textStyle": {}, "url": "https://example.com/handbook"})

        note = visual_objects(visual_by_title("QA Hidden", "QA Note"), "general")[0]["properties"]["paragraphs"]
        self.assertEqual(note, [{"textRuns": [{"value": "Hidden page for fixture QA."}]}])

    # --- #41 data colours ---------------------------------------------------

    def _scope_literals(self, page: str, title: str) -> dict[object, object]:
        result = {}
        for entry in visual_objects(visual_by_title(page, title), "dataPoint"):
            comparison = entry["selector"]["data"][0]["scopeId"]["Comparison"]
            self.assertEqual(comparison["ComparisonKind"], 0)
            colour = literal_value(entry["properties"]["fill"]["solid"]["color"])
            result[comparison["Right"]["Literal"]["Value"]] = colour
        return result

    def test_data_colour_selectors(self) -> None:
        self.assertEqual(
            self._scope_literals("Overview", "Tasks by Status"),
            {"'Completed'": "'#20A741'", "'In progress'": "'#F2A900'",
             "'Not started'": "'#A0A0A0'", "'Blocked'": "'#D64550'"},
        )
        self.assertEqual(self._scope_literals("Chart Gallery", "Billable Split"),
                         {"true": "'#20A741'", "false": "'#A0A0A0'"})
        self.assertEqual(self._scope_literals("Chart Gallery", "Tasks per Story Points"), {"13L": "'#D64550'"})
        # Engineering #118DFF equals the theme's first data colour, so Desktop wrote no entry for it.
        self.assertNotIn("'Engineering'", self._scope_literals("Chart Gallery", "Hours by Team"))

        series = visual_objects(visual_by_title("Chart Gallery", "Hours by Measure Series"), "dataPoint")
        self.assertEqual([e["selector"] for e in series], [{"metadata": "Measures Table.Estimate Hours"}])

    # --- #42 slicers ----------------------------------------------------------

    def test_slicer_sync_group(self) -> None:
        synced = []
        for page in EXPECTED_PAGES:
            for visual in page_visuals(page):
                group = visual["visual"].get("syncGroup")
                if group:
                    synced.append((page, bool(visual.get("isHidden")), group))
        self.assertEqual(
            [(page, hidden) for page, hidden, _ in synced],
            [("Overview", False), ("Task Board", False), ("Chart Gallery", True)],
        )
        for _, _, group in synced:
            self.assertEqual(group, {"groupName": "PortfolioSync", "fieldChanges": True, "filterChanges": True})

    def _saved_condition(self, title: str) -> dict:
        general = visual_objects(visual_by_title("Task Board", title), "general")[0]["properties"]
        query = general["filter"]["filter"]
        self.assertEqual(query["Version"], 2)
        return query["Where"][0]["Condition"]

    def test_slicer_saved_selections(self) -> None:
        priority = self._saved_condition("Priority Slicer")["In"]["Values"]
        self.assertEqual(priority, [[{"Literal": {"Value": "'High'"}}]])
        self.assertEqual(
            literal_value(visual_objects(visual_by_title("Task Board", "Priority Slicer"), "selection")[0]["properties"]["strictSingleSelect"]),
            "true",
        )

        status = self._saved_condition("Status Slicer")["In"]["Values"]
        self.assertEqual(sorted(v[0]["Literal"]["Value"] for v in status), ["'Blocked'", "'In progress'"])

        team = self._saved_condition("Team Slicer")
        self.assertEqual(team["Not"]["Expression"]["In"]["Values"], [[{"Literal": {"Value": "'Design'"}}]])
        team_data = visual_objects(visual_by_title("Task Board", "Team Slicer"), "data")[0]["properties"]
        self.assertEqual(literal_value(team_data["isInvertedSelectionMode"]), "true")

        dates = self._saved_condition("Date Range Slicer")["And"]
        self.assertEqual(dates["Left"]["Comparison"]["ComparisonKind"], 2)
        self.assertEqual(dates["Left"]["Comparison"]["Right"]["Literal"]["Value"], "datetime'2024-03-01T00:00:00'")
        # The end bound is exclusive: the day after the picked end date.
        self.assertEqual(dates["Right"]["Comparison"]["ComparisonKind"], 3)
        self.assertEqual(dates["Right"]["Comparison"]["Right"]["Literal"]["Value"], "datetime'2025-07-01T00:00:00'")
        date_data = visual_objects(visual_by_title("Task Board", "Date Range Slicer"), "data")[0]["properties"]
        self.assertEqual(literal_value(date_data["mode"]), "'Between'")
        self.assertEqual(literal_value(date_data["endDate"]), "datetime'2025-06-30T00:00:00'")

        portfolio = visual_by_title("Task Board", "Portfolio Slicer")
        self.assertNotIn("filter", visual_objects(portfolio, "general")[0]["properties"])

    # --- #35 filter literals ------------------------------------------------

    def test_filter_literal_suffixes(self) -> None:
        expected = {
            "Filter - Integer Measure": (2, "1L"),
            "Filter - Decimal Measure": (1, "1.5D"),
            "Filter - No Format Integer": (2, "10L"),
            "Filter - No Format Decimal": (2, "0.95D"),
            "Filter - Currency Measure": (1, "500M"),
            "Filter - Percent Measure": (1, "0.5D"),
            "Filter - Numeric Column": (2, "3L"),
        }
        for title, (kind, literal) in expected.items():
            with self.subTest(title=title):
                filters = [f for f in visual_by_title("Filter Lab", title)["filterConfig"]["filters"] if "filter" in f]
                self.assertEqual(len(filters), 1)
                self.assertEqual(filters[0]["type"], "Advanced")
                comparison = filters[0]["filter"]["Where"][0]["Condition"]["Comparison"]
                self.assertEqual(comparison["ComparisonKind"], kind)
                self.assertEqual(comparison["Right"]["Literal"]["Value"], literal)

        top_n = [f for f in visual_by_title("Filter Lab", "Filter - Top N")["filterConfig"]["filters"] if "filter" in f]
        self.assertEqual(top_n[0]["type"], "TopN")
        relative = [f for f in visual_by_title("Filter Lab", "Filter - Relative Date")["filterConfig"]["filters"] if "filter" in f]
        self.assertEqual(relative[0]["type"], "RelativeDate")
        self.assertIn("Between", relative[0]["filter"]["Where"][0]["Condition"])

    # --- #33 / #54 card -----------------------------------------------------

    def test_card_per_series_and_reference_label(self) -> None:
        card = visual_by_title("Overview", "Delivery KPIs")
        self.assertEqual(card["visual"]["visualType"], "cardVisual")
        font_sizes = {e["selector"]["metadata"]: literal_value(e["properties"]["fontSize"]) for e in visual_objects(card, "value")}
        self.assertEqual(font_sizes, {
            "Measures Table.Task Count": "28D",
            "Measures Table.Completion %": "24D",
            "Measures Table.Total Hours": "24D",
            "Measures Table.Expense Amount": "20D",
        })
        self.assertEqual(len(visual_objects(card, "accentBar")), 4)
        callout = {json.dumps(e["selector"], sort_keys=True) for e in visual_objects(card, "cardCalloutArea")}
        self.assertEqual(callout, {'{"metadata": "Measures Table.Task Count"}', '{"id": "default"}'})
        reference = visual_objects(card, "referenceLabel")[0]
        self.assertEqual(reference["properties"]["value"]["expr"]["Measure"]["Property"], "Open Tasks")
        self.assertEqual(reference["selector"]["metadata"], "Measures Table.Task Count")
        self.assertTrue(reference["selector"]["id"].startswith("field-"))
        card_count = sum(
            1 for page in EXPECTED_PAGES for v in page_visuals(page) if v["visual"]["visualType"] == "cardVisual"
        )
        self.assertEqual(card_count, 4)

    # --- #29 / #49 theme and resources ------------------------------------------

    def test_theme_and_image_resources(self) -> None:
        report = read_json(report_definition() / "report.json")
        custom = report["themeCollection"]["customTheme"]
        self.assertRegex(custom["name"], r"^Desktop_Shapes_Theme\d+\.json$")
        registered = next(p for p in report["resourcePackages"] if p["name"] == "RegisteredResources")
        types = {item["type"]: item["name"] for item in registered["items"]}
        self.assertEqual(types["CustomTheme"], custom["name"])
        self.assertRegex(types["Image"], r"^Team_Logo\d+\.png$")

        resources = SHAPES_DIR / "04-desktop-shapes.Report" / "StaticResources" / "RegisteredResources"
        theme = read_json(resources / custom["name"])
        self.assertEqual(set(theme["textClasses"]), {"label", "title", "callout", "header"})
        self.assertEqual(theme["textClasses"]["callout"], {"fontSize": 30, "color": "#118DFF"})

        image = visual_objects(visual_by_title("Overview", "Team Logo Image"), "image")[0]["properties"]["sourceFile"]["image"]
        self.assertEqual(literal_value(image["name"]), "'Team Logo.png'")
        self.assertEqual(image["url"]["expr"]["ResourcePackageItem"]["ItemName"], types["Image"])

    # --- bookmarks ------------------------------------------------------------

    def test_bookmarks(self) -> None:
        folder = report_definition() / "bookmarks"
        meta = read_json(folder / "bookmarks.json")
        group = next(item for item in meta["items"] if "children" in item)
        self.assertEqual(group["displayName"], "Task Board Views")
        names = {}
        for path in folder.glob("*.bookmark.json"):
            bookmark = read_json(path)
            names[bookmark["displayName"]] = bookmark
        self.assertEqual(
            set(names), {"Task Board - All Statuses", "Task Board - Blocked Only", "Overview - Hide Logo"}
        )
        self.assertEqual({names[n]["name"] for n in names if n.startswith("Task Board")}, set(group["children"]))
        self.assertTrue(names["Overview - Hide Logo"]["options"]["suppressData"])

    # --- #55 rename snapshot ------------------------------------------------

    @unittest.skipUnless(RENAMED_DIR.exists(), "rename snapshot not committed")
    def test_rename_snapshot_rewrites_property_but_not_query_refs(self) -> None:
        measures = _tmdl("Measures Table", RENAMED_DIR)
        self.assertIn("measure 'Hours Logged' = SUM ( 'Time & Expenses'[Hours] )", measures)
        self.assertIn("DIVIDE ( [Hours Logged], DISTINCTCOUNT", measures)
        self.assertIn("(\"Total Hours\", NAMEOF('Measures Table'[Hours Logged]), 0)", _tmdl("Metric Selector", RENAMED_DIR))
        person = _tmdl("Person", RENAMED_DIR)
        self.assertIn("\tcolumn 'Person Name'", person)
        self.assertIn('Table.RenameColumns(#"Changed Type",{{"PersonName", "Person Name"}})', person)

        people = visual_by_title("Task Board", "People Hours", RENAMED_DIR)
        refs = {p["queryRef"]: p["field"] for p in people["visual"]["query"]["queryState"]["Values"]["projections"]}
        # queryRef keeps the old name; the field expression gets the new one.
        self.assertEqual(refs["Measures Table.Total Hours"]["Measure"]["Property"], "Hours Logged")
        self.assertEqual(refs["Person.PersonName"]["Column"]["Property"], "Person Name")

        card = visual_by_title("Overview", "Delivery KPIs", RENAMED_DIR)
        selectors = {e["selector"]["metadata"] for e in visual_objects(card, "accentBar")}
        self.assertIn("Measures Table.Total Hours", selectors)

        for page in EXPECTED_PAGES:
            for visual in page_visuals(page, RENAMED_DIR):
                text = json.dumps(visual)
                self.assertNotIn('"Property": "Total Hours"', text)
                self.assertNotIn('"Property": "PersonName"', text)


if __name__ == "__main__":
    unittest.main()
