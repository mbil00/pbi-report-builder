"""Desktop visual content an unedited export -> apply keeps (#108, R2).

Each test runs a page export -> apply on a copy of a Desktop-saved fixture and
checks that one visual file is unchanged. The full-report round trips stay
xfails in ``test_fixture_harness`` until the filter and bookmark shapes land.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pbi.apply.visual_queries import _kept_field_parameters
from pbi.properties import VISUAL_PROPERTIES, set_property
from pbi.roundtrip_primitives import prune_visual_pbir
from tests.support import cli, read_json, report_definition

SHAPES = "report-04-desktop-shapes"
SAMPLE = "sample-report"
FIELD_PARAMETER_CHART = "fd84289803c981e2182a"  # Y bound through the Metric Selector field parameter
FIELD_PARAMETERS = [
    {
        "parameterExpr": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": "Metric Selector"}},
                "Property": "Metric Selector",
            }
        },
        "index": 0,
        "length": 3,
    }
]


def _visual_path(root: Path, visual: str) -> Path:
    return next(report_definition(root).glob(f"pages/*/visuals/{visual}/visual.json"))


def _export_apply(root: Path, tmp_path: Path, page: str) -> None:
    spec = tmp_path / "page.yaml"
    exported = cli("export", "--page", page, "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output


@pytest.mark.parametrize(
    ("fixture", "page", "visual"),
    [
        # pivotTable expansionStates[0].root: {}
        pytest.param(SHAPES, "Task Board", "a375982550080600757e", id="report-04-expansion-root"),
        pytest.param(SAMPLE, "14 visuals with bindings", "a39a1ddb012bb0073054", id="sample-expansion-root"),
        # smart narrative text run defaultCase: {"textRuns": []}
        pytest.param(SAMPLE, "14 visuals with bindings", "6df756cd99120b990564", id="sample-narrative-default-case"),
        # shape fill keeps its single {"id": "default"} entry
        pytest.param(SHAPES, "QA Hidden", "e3587fb939c2801b80d5", id="report-04-shape-fill"),
        # queryState.Y.fieldParameters
        pytest.param(SHAPES, "QA Hidden", FIELD_PARAMETER_CHART, id="report-04-field-parameters"),
    ],
)
def test_unedited_page_apply_keeps_visual_file(
    fixture_copy: Callable[[str], Path], tmp_path: Path, fixture: str, page: str, visual: str
) -> None:
    root = fixture_copy(fixture)
    before = _visual_path(root, visual).read_bytes()

    _export_apply(root, tmp_path, page)

    assert _visual_path(root, visual).read_bytes() == before


def _apply_y(root: Path, tmp_path: Path, y: list[str]) -> dict:
    spec = tmp_path / "chart.yaml"
    spec.write_text(
        yaml.safe_dump({
            "pages": [{
                "name": "QA Hidden",
                "visuals": [{
                    "id": FIELD_PARAMETER_CHART,
                    "type": "clusteredColumnChart",
                    "bindings": {"Y": y},
                }],
            }],
        }),
        encoding="utf-8",
    )
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output
    return read_json(_visual_path(root, FIELD_PARAMETER_CHART))["visual"]["query"]["queryState"]["Y"]


PARAMETER_FIELDS = [
    "Measures Table.Total Hours (measure)",
    "Measures Table.Task Count (measure)",
    "Measures Table.Expense Amount (measure)",
]


def test_field_parameter_follows_its_projections_when_they_move(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)

    y = _apply_y(root, tmp_path, ["Measures Table.Open Tasks (measure)", *PARAMETER_FIELDS])

    assert [p["queryRef"] for p in y["projections"]][1:] == [
        "Measures Table.Total Hours",
        "Measures Table.Task Count",
        "Measures Table.Expense Amount",
    ]
    assert y["fieldParameters"] == [{**FIELD_PARAMETERS[0], "index": 1}]


def test_field_parameter_goes_when_its_projections_are_unbound(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)

    y = _apply_y(root, tmp_path, PARAMETER_FIELDS[:2])

    assert len(y["projections"]) == 2
    assert "fieldParameters" not in y


def _measure_projection(query_ref: str) -> dict:
    field = {"Measure": {"Expression": {"SourceRef": {"Entity": "M"}}, "Property": "Hours"}}
    return {"field": field, "queryRef": query_ref}


def test_field_parameter_stays_on_its_own_projection_beside_the_same_measure() -> None:
    # A direct Hours binding, then the parameter's Hours projection (same
    # field, its own query ref): the parameter keeps index 1.
    projections = [_measure_projection("M.Hours"), _measure_projection("M.Hours1")]
    state = {"projections": projections, "fieldParameters": [{**FIELD_PARAMETERS[0], "index": 1, "length": 1}]}

    assert _kept_field_parameters(state, projections) == state["fieldParameters"]


def test_field_parameter_is_dropped_when_its_new_place_is_ambiguous() -> None:
    hours = _measure_projection("M.Hours")
    other = {**_measure_projection("M.Other"), "field": {"Measure": {"Property": "Other"}}}
    state = {"projections": [hours], "fieldParameters": [{**FIELD_PARAMETERS[0], "length": 1}]}

    assert _kept_field_parameters(state, [other, hours, hours]) == []
    assert _kept_field_parameters(state, [other, hours]) == [{**FIELD_PARAMETERS[0], "index": 1, "length": 1}]


def _card_with_default_entry() -> dict:
    return {
        "visual": {
            "visualType": "cardVisual",
            "objects": {
                "accentBar": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}, "selector": {"id": "default"}}]
            },
        }
    }


def test_explicit_measure_ref_default_is_a_query_ref() -> None:
    data = _card_with_default_entry()

    set_property(data, "accentBar.color", "#112233", VISUAL_PROPERTIES, measure_ref="default")

    entries = data["visual"]["objects"]["accentBar"]
    assert "color" not in entries[0]["properties"]
    assert entries[1]["selector"] == {"metadata": "default"}
    assert "color" in entries[1]["properties"]


def test_default_bracket_selector_writes_desktop_default_entry() -> None:
    data = {
        "visual": {
            "visualType": "shape",
            "objects": {
                "fill": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}, "selector": {"id": "default"}}]
            },
        }
    }

    set_property(data, "fill.fillColor [default]", "#112233", VISUAL_PROPERTIES)

    entries = data["visual"]["objects"]["fill"]
    assert len(entries) == 1
    assert entries[0]["selector"] == {"id": "default"}
    assert entries[0]["properties"]["fillColor"] == {
        "solid": {"color": {"expr": {"Literal": {"Value": "'#112233'"}}}}
    }


def test_pbir_keeps_source_empties_only_beside_kept_content() -> None:
    expansion = {"roles": ["Rows"], "levels": [{"queryRefs": ["T.A"], "isPinned": True}], "root": {}}
    raw = {
        "visual": {
            "visualType": "pivotTable",
            "expansionStates": [expansion],
            # Desktop's empty slicer-style entry and pbi's scaffolded roles carry
            # nothing apply would lose: dicts merge, so the file keeps them.
            "objects": {"general": [{"properties": {}}]},
            "query": {"queryState": {"Values": {"projections": []}}},
        },
        "filterConfig": {"filters": []},
    }

    assert prune_visual_pbir(raw, {}) == {"visual": {"expansionStates": [expansion]}}
