"""Slicer sync groups (`sync`) and saved default selections (`selected`) (#42).

The fixture tests copy the Desktop-built report-04 project, strip the sync
groups and saved selections Desktop wrote, rebuild them through `pbi apply` (or
the `pbi visual slicer` commands) and compare the JSON with what Desktop saved.
They skip if `04-desktop-shapes.pbip` is absent.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.project import Project
from pbi.slicer_state import (
    apply_slicer_selection,
    apply_sync_group,
    export_slicer_selection,
    export_sync_group,
    normalize_selection_spec,
    normalize_sync_spec,
    parse_sync_spec,
    without_selection_props,
)
from tests.test_data_colors import _title_of
from tests.test_desktop_shapes_fixture import SHAPES_DIR, SHAPES_PBIP, _objects, _visual

# (page, title, YAML spec that rebuilds what Desktop wrote)
DESKTOP_SELECTIONS = [
    ("Task Board", "Priority Slicer", ["High"]),
    ("Task Board", "Status Slicer", ["Blocked", "In progress"]),
    ("Task Board", "Team Slicer", {"except": ["Design"]}),
    ("Task Board", "Date Range Slicer", {"from": dt.date(2024, 3, 1), "to": dt.date(2025, 6, 30)}),
]
SYNCED = [("Overview", "Portfolio Slicer"), ("Task Board", "Portfolio Slicer"), ("Chart Gallery", "Portfolio Slicer")]
DESKTOP_GROUP = {"groupName": "PortfolioSync", "fieldChanges": True, "filterChanges": True}


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class SlicerStateDesktopTests(unittest.TestCase):
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

    def _find(self, page: str, title: str):
        project = Project.find(self.pbip)
        matches = [v for v in project.get_visuals(project.find_page(page)) if _title_of(v.data) == title]
        self.assertEqual(len(matches), 1, title)
        return project, matches[0]

    def _strip(self) -> None:
        """Remove every sync group and saved selection Desktop wrote."""
        for page, title in SYNCED + [(page, title) for page, title, _spec in DESKTOP_SELECTIONS]:
            _project, visual = self._find(page, title)
            visual.data["visual"].pop("syncGroup", None)
            visual.data["visual"]["objects"] = without_selection_props(visual.data["visual"]["objects"])
            visual.save()

    def _run(self, *args: str) -> str:
        result = self.runner.invoke(app, [*args, "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 0, result.stdout)
        return result.stdout

    def _apply(self, spec: dict) -> str:
        path = self.root / "apply.yaml"
        path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return self._run("apply", str(path))

    def _authored_yaml(self) -> dict:
        pages: dict[str, list[dict]] = {}
        for page, title in SYNCED:
            _project, visual = self._find(page, title)
            pages.setdefault(page, []).append({"id": visual.folder.name, "type": "slicer", "sync": "PortfolioSync"})
        for page, title, spec in DESKTOP_SELECTIONS:
            _project, visual = self._find(page, title)
            pages.setdefault(page, []).append({"id": visual.folder.name, "type": "slicer", "selected": spec})
        return {"pages": [{"name": name, "visuals": visuals} for name, visuals in pages.items()]}

    def _assert_matches_desktop(self) -> None:
        for page, title in SYNCED:
            with self.subTest(visual=f"{page}/{title}"):
                self.assertEqual(self._find(page, title)[1].data["visual"]["syncGroup"], DESKTOP_GROUP)
        for page, title, _spec in DESKTOP_SELECTIONS:
            _project, visual = self._find(page, title)
            desktop = _visual(page, title)
            with self.subTest(visual=title):
                for name in ("general", "data", "selection"):
                    self.assertEqual(visual.data["visual"]["objects"].get(name, []), _objects(desktop, name), name)

    def test_apply_writes_desktop_shapes(self) -> None:
        self._strip()
        self._apply(self._authored_yaml())
        self._assert_matches_desktop()

        # Applying again changes nothing.
        titles = SYNCED + [(page, title) for page, title, _spec in DESKTOP_SELECTIONS]
        before = {key: copy.deepcopy(self._find(*key)[1].data) for key in titles}
        self._apply(self._authored_yaml())
        for key in titles:
            self.assertEqual(self._find(*key)[1].data, before[key])

    def test_export_round_trips_through_apply(self) -> None:
        exported = {page: yaml.safe_load(self._run("export", "--page", page)) for page in ("Overview", "Task Board", "Chart Gallery")}

        def exported_visual(page: str, title: str) -> dict:
            _project, visual = self._find(page, title)
            return next(v for p in exported[page]["pages"] for v in p["visuals"] if v.get("id") == visual.folder.name)

        for page, title in SYNCED:
            with self.subTest(visual=f"{page}/{title}"):
                spec = exported_visual(page, title)
                self.assertEqual(spec["sync"], "PortfolioSync")
                self.assertNotIn("selected", spec)
                self.assertNotIn("syncGroup", spec.get("pbir", {}).get("visual", {}))
        self.assertTrue(exported_visual("Chart Gallery", "Portfolio Slicer")["isHidden"])

        for page, title, expected in DESKTOP_SELECTIONS:
            with self.subTest(visual=title):
                spec = exported_visual(page, title)
                self.assertEqual(spec["selected"], expected)
                self.assertNotIn("pbir", spec)  # nothing left that YAML can't express
                self.assertFalse([key for key in spec if "isInvertedSelectionMode" in key or "Date" in key])

        # Rebuild from the exported slicers only (the Task Board matrix doesn't
        # round-trip its hierarchy binding yet, which is unrelated).
        self._strip()
        for page, data in exported.items():
            data["pages"][0]["visuals"] = [v for v in data["pages"][0]["visuals"] if v["type"] == "slicer"]
            self._apply(data)
        self._assert_matches_desktop()

    def test_diff_after_apply_shows_no_changes(self) -> None:
        self._strip()
        authored = self._authored_yaml()
        self._apply(authored)
        out = self._run("diff", str(self.root / "apply.yaml"))
        self.assertIn("No differences found", out)

        # The long form with both flags on and a string date are the same state.
        _project, visual = self._find("Task Board", "Portfolio Slicer")
        _project, dates = self._find("Task Board", "Date Range Slicer")
        path = self.root / "long.yaml"
        path.write_text(
            f"pages:\n- name: Task Board\n  visuals:\n  - id: {visual.folder.name}\n    type: slicer\n"
            "    sync: {group: PortfolioSync, fields: true, filters: true}\n"
            f"  - id: {dates.folder.name}\n    type: slicer\n    selected: {{from: '2024-03-01', to: 2025-06-30}}\n",
            encoding="utf-8",
        )
        self.assertIn("No differences found", self._run("diff", str(path)))

    def test_null_clears_and_type_mismatch_is_an_error(self) -> None:
        _project, team = self._find("Task Board", "Team Slicer")
        _project, portfolio = self._find("Task Board", "Portfolio Slicer")
        self._apply({"pages": [{"name": "Task Board", "visuals": [
            {"id": team.folder.name, "type": "slicer", "selected": None},
            {"id": portfolio.folder.name, "type": "slicer", "sync": None},
        ]}]})
        _project, team = self._find("Task Board", "Team Slicer")
        self.assertEqual(export_slicer_selection(team.data), (False, None))
        self.assertNotIn("isInvertedSelectionMode", _objects(team.data, "data")[0]["properties"])
        self.assertNotIn("syncGroup", self._find("Task Board", "Portfolio Slicer")[1].data["visual"])

        _project, status = self._find("Task Board", "Status Slicer")
        before = copy.deepcopy(status.data)
        path = self.root / "bad.yaml"
        path.write_text(yaml.safe_dump({"pages": [{"name": "Task Board", "visuals": [
            {"id": status.folder.name, "type": "slicer", "selected": {"from": "2024-01-01", "to": "2024-02-01"}},
        ]}]}), encoding="utf-8")
        result = self.runner.invoke(app, ["apply", str(path), "--project", str(self.pbip)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("needs a date column", result.stdout)
        self.assertEqual(self._find("Task Board", "Status Slicer")[1].data, before)

    def test_sync_on_a_non_slicer_is_an_error(self) -> None:
        project = Project.find(self.pbip)
        page = project.find_page("Task Board")
        matrix = next(v for v in project.get_visuals(page) if v.visual_type == "pivotTable")
        path = self.root / "bad.yaml"
        path.write_text(yaml.safe_dump({"pages": [{"name": "Task Board", "visuals": [
            {"id": matrix.folder.name, "type": "pivotTable", "sync": "S"},
        ]}]}), encoding="utf-8")
        result = self.runner.invoke(app, ["apply", str(path), "--project", str(self.pbip)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("only apply to slicers", result.stdout)

    def test_stamping_an_exported_spec_restores_sync_and_selection(self) -> None:
        from pbi.export import export_visual_spec
        from pbi.visual_stamping import create_visual_from_spec

        for page, title, _spec in DESKTOP_SELECTIONS + [("Task Board", "Portfolio Slicer", None)]:
            with self.subTest(visual=title):
                project, visual = self._find(page, title)
                spec = export_visual_spec(project, visual)
                spec.pop("id")
                stamped = create_visual_from_spec(project, project.find_page("QA Hidden"), spec)
                desktop = _visual(page, title)
                self.assertEqual(stamped.data["visual"].get("syncGroup"), desktop["visual"].get("syncGroup"))
                self.assertEqual(export_slicer_selection(stamped.data), export_slicer_selection(desktop))

    def test_style_capture_ignores_sync_and_selection(self) -> None:
        from pbi.export import export_visual_spec
        from pbi.styles import apply_style_reference, extract_style_properties

        project, visual = self._find("Task Board", "Team Slicer")
        spec = export_visual_spec(project, visual)
        spec["sync"] = "S"
        properties = extract_style_properties(spec)
        self.assertFalse(any(key.startswith(("sync", "selected")) for key in properties))
        styled = apply_style_reference(spec, "s")
        self.assertEqual((styled["sync"], styled["selected"]), ("S", {"except": ["Design"]}))

    def test_cli_commands_write_desktop_shapes(self) -> None:
        self._strip()
        ids = {title: self._find(page, title)[1].folder.name for page, title, _ in DESKTOP_SELECTIONS}
        for page, title in SYNCED:
            self._run("visual", "slicer", "sync", "set", page, self._find(page, title)[1].folder.name, "PortfolioSync")
        self._run("visual", "slicer", "selection", "set", "Task Board", ids["Priority Slicer"], "High")
        self._run("visual", "slicer", "selection", "set", "Task Board", ids["Status Slicer"], "Blocked", "In progress")
        self._run("visual", "slicer", "selection", "set", "Task Board", ids["Team Slicer"], "Design", "--except")
        self._run(
            "visual", "slicer", "selection", "set", "Task Board", ids["Date Range Slicer"],
            "--from", "2024-03-01", "--to", "2025-06-30",
        )
        self._assert_matches_desktop()

        out = json.loads(self._run("visual", "slicer", "get", "Task Board", ids["Date Range Slicer"], "--json"))
        self.assertEqual(out["selected"], {"from": "2024-03-01", "to": "2025-06-30"})
        self.assertEqual(out["field"], "Date.Date")

        self._run("visual", "slicer", "selection", "clear", "Task Board", ids["Team Slicer"], "-f")
        self.assertEqual(export_slicer_selection(self._find("Task Board", "Team Slicer")[1].data), (False, None))
        portfolio = self._find("Task Board", "Portfolio Slicer")[1].folder.name
        self._run("visual", "slicer", "sync", "set", "Task Board", portfolio, "PortfolioSync", "--no-fields")
        self.assertEqual(
            self._find("Task Board", "Portfolio Slicer")[1].data["visual"]["syncGroup"],
            {"groupName": "PortfolioSync", "fieldChanges": False, "filterChanges": True},
        )
        self._run("visual", "slicer", "sync", "clear", "Task Board", portfolio, "-f")
        self.assertNotIn("syncGroup", self._find("Task Board", "Portfolio Slicer")[1].data["visual"])

        result = self.runner.invoke(app, ["visual", "slicer", "selection", "set", "Task Board", ids["Status Slicer"],
                                          "--from", "2024-01-01", "--project", str(self.pbip)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("needs both --from and --to", result.stdout)


def _slicer(column: str = "Status", entity: str = "Task", **objects) -> dict:
    return {
        "visual": {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [{
                "field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": column}},
                "queryRef": f"{entity}.{column}",
            }]}}},
            "objects": copy.deepcopy(objects),
        }
    }


def _literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _values(visual: dict) -> list[str]:
    condition = visual["visual"]["objects"]["general"][0]["properties"]["filter"]["filter"]["Where"][0]["Condition"]
    block = condition["Not"]["Expression"]["In"] if "Not" in condition else condition["In"]
    return [row[0]["Literal"]["Value"] for row in block["Values"]]


class SyncGroupUnitTests(unittest.TestCase):
    def test_short_and_long_forms(self) -> None:
        self.assertEqual(parse_sync_spec("G"), {"groupName": "G", "fieldChanges": True, "filterChanges": True})
        self.assertEqual(
            parse_sync_spec({"group": "G", "fields": False}),
            {"groupName": "G", "fieldChanges": False, "filterChanges": True},
        )
        self.assertIsNone(parse_sync_spec(None))
        self.assertEqual(normalize_sync_spec({"group": "G"}), "G")
        self.assertEqual(normalize_sync_spec({"group": "G", "filters": False}), {"group": "G", "fields": True, "filters": False})

    def test_invalid_specs(self) -> None:
        for spec in ("", {"group": "G", "fields": "yes"}, {"name": "G"}, ["G"], {"fields": True}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_sync_spec(spec)

    def test_apply_and_export(self) -> None:
        visual = _slicer()
        self.assertTrue(apply_sync_group(visual, {"group": "G", "filters": False}))
        self.assertFalse(apply_sync_group(visual, {"group": "G", "filters": False}))
        self.assertEqual(export_sync_group(visual), {"group": "G", "fields": True, "filters": False})
        visual["visual"]["syncGroup"]["extra"] = 1
        self.assertIsNone(export_sync_group(visual))  # stays in pbir
        self.assertTrue(apply_sync_group(visual, None))
        self.assertNotIn("syncGroup", visual["visual"])


class SelectionUnitTests(unittest.TestCase):
    def test_literals_follow_column_type(self) -> None:
        cases = [
            ("string", ["it's", True, 13], ["'it''s'", "'true'", "'13'"]),
            ("int64", [13, "-2"], ["13L", "-2L"]),
            ("double", [1.5, "2"], ["1.5D", "2D"]),
            ("decimal", ["500"], ["500M"]),
            ("boolean", [True, "False"], ["true", "false"]),
            ("dateTime", [dt.date(2024, 3, 1), "2024-03-02"], ["datetime'2024-03-01T00:00:00'", "datetime'2024-03-02T00:00:00'"]),
            (None, [True, 3, 1.5, "x", dt.date(2024, 1, 1)], ["true", "3L", "1.5D", "'x'", "datetime'2024-01-01T00:00:00'"]),
        ]
        for data_type, values, expected in cases:
            with self.subTest(data_type=data_type):
                visual = _slicer()
                apply_slicer_selection(visual, values, data_type=data_type)
                self.assertEqual(_values(visual), expected)

    def test_export_decodes_values(self) -> None:
        visual = _slicer()
        apply_slicer_selection(visual, ["a", 3, 1.5, True, dt.date(2024, 1, 2)], data_type=None)
        self.assertEqual(export_slicer_selection(visual), (True, ["a", 3, 1.5, True, dt.date(2024, 1, 2)]))
        self.assertEqual(normalize_selection_spec("a"), ["a"])
        self.assertIsNone(normalize_selection_spec([]))

    def test_invalid_specs_change_nothing(self) -> None:
        bad = [
            ({"from": "2024-02-01", "to": "2024-01-01"}, "dateTime"),
            ({"from": "2024-01-01"}, "dateTime"),
            ({"from": "2024-01-01T10:00", "to": "2024-01-02"}, "dateTime"),
            ({"except": []}, "string"),
            ([["nested"]], "string"),
            ([None], "string"),
            (["x"], "int64"),
            (["1.5"], "int64"),
            (["maybe"], "boolean"),
            ({"from": "2024-01-01", "to": "2024-01-02"}, "string"),
        ]
        for spec, data_type in bad:
            with self.subTest(spec=spec):
                visual = _slicer(data=[{"properties": {"mode": _literal("'Basic'")}}])
                before = copy.deepcopy(visual)
                with self.assertRaises(ValueError):
                    apply_slicer_selection(visual, spec, data_type=data_type)
                self.assertEqual(visual, before)

    def test_needs_one_bound_column(self) -> None:
        visual = _slicer()
        visual["visual"]["query"]["queryState"]["Values"]["projections"].append(
            copy.deepcopy(visual["visual"]["query"]["queryState"]["Values"]["projections"][0])
        )
        with self.assertRaises(ValueError):
            apply_slicer_selection(visual, ["a"], data_type=None)
        # Clearing doesn't need a field.
        self.assertEqual(apply_slicer_selection(visual, None, data_type=None), (False, []))

    def test_switching_kinds_replaces_owned_properties(self) -> None:
        visual = _slicer(
            data=[{"properties": {"mode": _literal("'Basic'")}}],
            general=[{"properties": {"orientation": _literal("1D")}}],
        )
        apply_slicer_selection(visual, {"except": ["a"]}, data_type="string")
        self.assertEqual(export_slicer_selection(visual), (True, {"except": ["a"]}))
        apply_slicer_selection(visual, {"from": "2024-01-01", "to": "2024-01-31"}, data_type="dateTime")
        props = visual["visual"]["objects"]["data"][0]["properties"]
        self.assertNotIn("isInvertedSelectionMode", props)
        self.assertEqual(props["mode"], _literal("'Between'"))
        self.assertEqual(props["endDate"], _literal("datetime'2024-01-31T00:00:00'"))

        # A list selection on a Between slicer drops the dates and warns about the mode.
        _changed, warnings = apply_slicer_selection(visual, ["a"], data_type="string")
        self.assertNotIn("startDate", props)
        self.assertEqual(len(warnings), 1)
        self.assertIn("Between mode", warnings[0])

        apply_slicer_selection(visual, None, data_type=None)
        general = visual["visual"]["objects"]["general"][0]["properties"]
        self.assertEqual(general, {"orientation": _literal("1D")})  # other properties stay
        self.assertEqual(props, {"mode": _literal("'Between'")})

    def test_single_select_warns_for_several_values(self) -> None:
        visual = _slicer(selection=[{"properties": {"strictSingleSelect": _literal("true")}}])
        self.assertEqual(apply_slicer_selection(visual, ["a"], data_type="string")[1], [])
        self.assertEqual(len(apply_slicer_selection(visual, ["a", "b"], data_type="string")[1]), 1)

    def test_export_leaves_unknown_shapes_in_pbir(self) -> None:
        visual = _slicer()
        apply_slicer_selection(visual, {"except": ["a"]}, data_type="string")
        visual["visual"]["objects"]["data"][0]["properties"].pop("isInvertedSelectionMode")
        self.assertEqual(export_slicer_selection(visual), (False, None))  # Not(In) without inverted mode

        visual = _slicer()
        apply_slicer_selection(visual, ["a"], data_type="string")
        visual["visual"]["objects"]["data"] = [{"properties": {"isInvertedSelectionMode": _literal("true")}}]
        self.assertEqual(export_slicer_selection(visual), (False, None))  # In with inverted mode

        visual = _slicer(column="Date", entity="Date")
        apply_slicer_selection(visual, {"from": "2024-01-01", "to": "2024-01-31"}, data_type="dateTime")
        visual["visual"]["objects"]["data"][0]["properties"]["endDate"] = _literal("datetime'2024-02-15T00:00:00'")
        self.assertEqual(export_slicer_selection(visual), (False, None))  # dates disagree with the filter

        visual = _slicer()
        apply_slicer_selection(visual, ["a"], data_type="string")
        visual["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Column"]["Property"] = "Other"
        self.assertEqual(export_slicer_selection(visual), (False, None))  # filter is on another column


if __name__ == "__main__":
    unittest.main()
