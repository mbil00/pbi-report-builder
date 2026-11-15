"""seriesColors: fixed data colours per category value or measure series (#41).

The fixture tests copy the Desktop-built report-04 project, strip the
`dataPoint` entries Desktop wrote, rebuild them through `pbi apply` and compare
the JSON with what Desktop saved. They skip if `04-desktop-shapes.pbip` is absent.
"""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.data_colors import apply_series_colors, export_series_colors
from pbi.project import Project
from pbi.roundtrip_primitives import export_object_properties, prune_visual_pbir
from pbi.properties import VISUAL_PROPERTIES
from tests.test_desktop_shapes_fixture import SHAPES_DIR, SHAPES_PBIP, _objects, _visual

# (page, title, seriesColors spec in the order Desktop wrote the entries)
DESKTOP_CASES = [
    ("Overview", "Tasks by Status", {"Task.Status": {
        "Not started": "#A0A0A0", "In progress": "#F2A900", "Completed": "#20A741", "Blocked": "#D64550",
    }}),
    ("Chart Gallery", "Hours by Team", {"Person.Team": {
        "Design": "#8E6CEF", "QA": "#20A741", "Operations": "#F2A900",
    }}),
    ("Chart Gallery", "Billable Split", {"Time & Expenses.IsBillable": {True: "#20a741", False: "#a0a0a0"}}),
    ("Chart Gallery", "Tasks per Story Points", {"Task.StoryPoints": {13: "#D64550"}}),
    ("Chart Gallery", "Hours by Measure Series", {"Measures Table.Estimate Hours": "#a0c4ff"}),
]


def _title_of(visual_data: dict) -> str | None:
    for entry in visual_data.get("visual", {}).get("visualContainerObjects", {}).get("title", []):
        raw = entry.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        if isinstance(raw, str):
            return raw.strip("'")
    return None


@unittest.skipUnless(SHAPES_PBIP.exists(), "report-04 Desktop output not built yet (see BUILD-CHECKLIST.md)")
class SeriesColorsDesktopTests(unittest.TestCase):
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
        page_obj = project.find_page(page)
        matches = [v for v in project.get_visuals(page_obj) if _title_of(v.data) == title]
        self.assertEqual(len(matches), 1, title)
        return project, matches[0]

    def _strip_data_points(self) -> None:
        for page, title, _spec in DESKTOP_CASES:
            project, visual = self._find(page, title)
            visual.data["visual"]["objects"].pop("dataPoint")
            visual.save()

    def _apply(self, spec: dict) -> str:
        path = self.root / "apply.yaml"
        path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
        result = self.runner.invoke(app, ["apply", str(path), "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 0, result.stdout)
        return result.stdout

    def _authored_yaml(self) -> dict:
        pages: dict[str, list[dict]] = {}
        for page, title, spec in DESKTOP_CASES:
            _project, visual = self._find(page, title)
            pages.setdefault(page, []).append(
                {"id": visual.folder.name, "type": visual.visual_type, "seriesColors": spec}
            )
        return {"pages": [{"name": name, "visuals": visuals} for name, visuals in pages.items()]}

    def _assert_matches_desktop(self) -> None:
        for page, title, _spec in DESKTOP_CASES:
            _project, visual = self._find(page, title)
            with self.subTest(visual=title):
                self.assertEqual(
                    visual.data["visual"]["objects"]["dataPoint"],
                    _objects(_visual(page, title), "dataPoint"),
                )

    def test_apply_writes_desktop_shapes(self) -> None:
        self._strip_data_points()
        self._apply(self._authored_yaml())
        self._assert_matches_desktop()

        # Applying again changes nothing.
        before = {title: copy.deepcopy(self._find(page, title)[1].data) for page, title, _ in DESKTOP_CASES}
        self._apply(self._authored_yaml())
        for page, title, _spec in DESKTOP_CASES:
            self.assertEqual(self._find(page, title)[1].data, before[title])

    def test_export_round_trips_through_apply(self) -> None:
        exported = {}
        for page in ("Overview", "Chart Gallery"):
            result = self.runner.invoke(app, ["export", "--page", page, "--project", str(self.pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            exported[page] = yaml.safe_load(result.stdout)

        for page, title, spec in DESKTOP_CASES:
            _project, visual = self._find(page, title)
            exported_visual = next(
                v for p in exported[page]["pages"] for v in p["visuals"] if v.get("id") == visual.folder.name
            )
            with self.subTest(visual=title):
                if title == "Hours by Measure Series":
                    # Measure series keep the generic selector key.
                    self.assertNotIn("seriesColors", exported_visual)
                    self.assertEqual(
                        exported_visual["chart:dataPoint.fill [Measures Table.Estimate Hours]"], "#A0C4FF"
                    )
                    continue
                expected = {field: {k: v.upper() for k, v in values.items()} for field, values in spec.items()}
                self.assertEqual(exported_visual["seriesColors"], expected)
                self.assertNotIn("chart:dataPoint.fill", exported_visual)
                raw = exported_visual.get("pbir", {}).get("visual", {}).get("objects", {})
                self.assertNotIn("dataPoint", raw)

        self._strip_data_points()
        for page in ("Overview", "Chart Gallery"):
            self._apply(exported[page])
        self._assert_matches_desktop()

    def test_unsupported_column_type_is_an_error(self) -> None:
        _project, visual = self._find("Chart Gallery", "Hours by Team")
        spec = {"pages": [{"name": "Chart Gallery", "visuals": [{
            "id": visual.folder.name, "type": visual.visual_type,
            "seriesColors": {"Task.EstimateHours": {"1.5": "#20A741"}},
        }]}]}
        path = self.root / "bad.yaml"
        path.write_text(yaml.safe_dump(spec), encoding="utf-8")
        result = self.runner.invoke(app, ["apply", str(path), "--project", str(self.pbip)])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("aren't supported yet", result.stdout)


def _resolver(types: dict[str, tuple[str, str | None]]):
    def resolve(field_ref: str) -> tuple[str, str, str, str | None]:
        entity, prop = field_ref.split(".", 1)
        field_type, data_type = types[field_ref]
        return entity, prop, field_type, data_type
    return resolve


def _chart(*projections: tuple[str, str]) -> dict:
    return {"visual": {"visualType": "clusteredColumnChart", "query": {"queryState": {"Category": {"projections": [
        {"field": {"Column": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}} for e, p in projections
    ]}}}, "objects": {}}}


class SeriesColorsUnitTests(unittest.TestCase):
    def test_upsert_keeps_other_properties_and_null_removes(self) -> None:
        data = _chart(("T", "Status"))
        resolve = _resolver({"T.Status": ("column", "string")})
        apply_series_colors(data, {"T.Status": {"Done": "#111111", "O'Neil": "#222222"}}, resolve_field=resolve)
        entries = data["visual"]["objects"]["dataPoint"]
        self.assertEqual(entries[1]["selector"]["data"][0]["scopeId"]["Comparison"]["Right"],
                         {"Literal": {"Value": "'O''Neil'"}})
        entries[0]["properties"]["showAllDataPoints"] = {"expr": {"Literal": {"Value": "true"}}}

        count, warnings = apply_series_colors(
            data, {"T.Status": {"Done": "#333333", "O'Neil": None}}, resolve_field=resolve
        )
        self.assertEqual((count, warnings), (2, []))
        entries = data["visual"]["objects"]["dataPoint"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["properties"]["fill"]["solid"]["color"]["expr"]["Literal"]["Value"], "'#333333'")
        self.assertIn("showAllDataPoints", entries[0]["properties"])

        apply_series_colors(data, {"T.Status": {"Done": None}}, resolve_field=resolve)
        self.assertEqual(len(data["visual"]["objects"]["dataPoint"]), 1)  # keeps the other property

    def test_literals_follow_column_type(self) -> None:
        cases = [
            ("string", {13: "#111111", True: "#222222"}, ["'13'", "'true'"]),
            ("boolean", {"False": "#111111"}, ["false"]),
            ("int64", {"-4": "#111111", 7: "#222222"}, ["-4L", "7L"]),
            (None, {1: "#111111"}, ["1L"]),       # no model: inferred from the YAML keys
            (None, {False: "#111111"}, ["false"]),
            (None, {"x": "#111111"}, ["'x'"]),
        ]
        for data_type, values, expected in cases:
            with self.subTest(data_type=data_type, values=values):
                data = _chart(("T", "C"))
                apply_series_colors(data, {"T.C": values}, resolve_field=_resolver({"T.C": ("column", data_type)}))
                literals = [
                    e["selector"]["data"][0]["scopeId"]["Comparison"]["Right"]["Literal"]["Value"]
                    for e in data["visual"]["objects"]["dataPoint"]
                ]
                self.assertEqual(literals, expected)

    def test_invalid_specs_change_nothing(self) -> None:
        resolve = _resolver({
            "T.Status": ("column", "string"), "T.N": ("column", "int64"), "T.B": ("column", "boolean"),
            "T.D": ("column", "dateTime"), "M.Total": ("measure", "numeric"),
        })
        cases = [
            ("not a mapping", "must be a mapping"),
            ({"Status": "#111111"}, "Table.Field"),
            ({"T.Status": "#111111"}, "is a column"),
            ({"M.Total": {"a": "#111111"}}, "is a measure"),
            ({"T.Status": {"a": "red"}}, "#RRGGBB"),
            ({"T.Status": {"a": "#1234"}}, "#RRGGBB"),
            ({"T.N": {"1.5": "#111111"}}, "whole number"),
            ({"T.B": {"yes": "#111111"}}, "boolean"),
            ({"T.D": {"2026-01-01": "#111111"}}, "aren't supported yet"),
            # A bad value after a good one still writes nothing.
            ({"T.Status": {"ok": "#111111"}, "T.N": {"x": "#111111"}}, "whole number"),
        ]
        for spec, message in cases:
            with self.subTest(spec=spec):
                data = _chart(("T", "Status"))
                with self.assertRaisesRegex(ValueError, message):
                    apply_series_colors(data, spec, resolve_field=resolve)
                self.assertEqual(data["visual"]["objects"], {})

    def test_unbound_field_warns(self) -> None:
        data = _chart(("T", "Status"))
        _count, warnings = apply_series_colors(
            data, {"T.Other": {"a": "#111111"}}, resolve_field=_resolver({"T.Other": ("column", "string")})
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("isn't bound", warnings[0])

    def test_export_takes_only_representable_entries(self) -> None:
        def scoped(value: str, props: dict) -> dict:
            return {"properties": props, "selector": {"data": [{"scopeId": {"Comparison": {
                "ComparisonKind": 0,
                "Left": {"Column": {"Expression": {"SourceRef": {"Entity": "T"}}, "Property": "C"}},
                "Right": {"Literal": {"Value": value}},
            }}}]}}

        hex_fill = {"fill": {"solid": {"color": {"expr": {"Literal": {"Value": "'#20a741'"}}}}}}
        theme_fill = {"fill": {"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": 2, "Percent": 0}}}}}}
        entries = [
            scoped("'a'", hex_fill),
            scoped("'b'", theme_fill),                                   # theme colour
            scoped("1.5D", hex_fill),                                    # unsampled literal type
            scoped("'c'", {**hex_fill, "showAllDataPoints": {"expr": {"Literal": {"Value": "true"}}}}),
            {"properties": {"defaultColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#111111'"}}}}}}},
        ]
        data = {"visual": {"visualType": "clusteredColumnChart", "objects": {"dataPoint": copy.deepcopy(entries)}}}
        colors, taken = export_series_colors(data)
        self.assertEqual((colors, taken), ({"T.C": {"a": "#20A741"}}, [0]))

        # Value-scoped entries never flatten into a selector-less key.
        flat = export_object_properties(data["visual"]["objects"], VISUAL_PROPERTIES, objects_path="objects",
                                        root_aliases={"dataPoint": "dataColors"})
        self.assertEqual(json.dumps(flat), json.dumps({"dataColors": {"default": "#111111"}}))

        exported = {**flat, "seriesColors": colors}
        pruned = prune_visual_pbir(data, exported)
        self.assertEqual(pruned["visual"]["objects"]["dataPoint"], entries[1:4])


if __name__ == "__main__":
    unittest.main()
