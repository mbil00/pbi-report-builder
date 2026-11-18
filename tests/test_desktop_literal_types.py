"""Numeric literals written the way Desktop saves them (#104, R5).

Desktop writes a whole decimal as ``4D``/``0D``, never ``4.0D``, and saves
cardVisual ``value.fontSize``, ``layout.columnCount`` and ``layout.cellPadding``
as decimals although the extracted schema types them ``fmt``/``int``. Setting a
property to the number it already holds keeps the saved literal text, so an
unedited export -> apply leaves the file alone.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pbi.card import expand_kpis
from pbi.properties import VISUAL_PROPERTIES, set_property
from tests.support import cli, literal_value, read_json, report_definition

SHAPES = "report-04-desktop-shapes"
SAMPLE = "sample-report"
KITCHEN_SINK = "report-01-kitchen-sink"
DELIVERY_KPIS = "e04657c5351eee897c20"  # report-04 Overview cardVisual


def _visual_file(root: Path, visual: str) -> Path:
    return next(report_definition(root).glob(f"pages/*/visuals/{visual}/visual.json"))


def _literal(raw: dict) -> str:
    return raw["expr"]["Literal"]["Value"]


@pytest.mark.parametrize(
    ("fixture", "page", "visual"),
    [
        # cardVisual value.fontSize 28D/24D/20D per measure
        pytest.param(SHAPES, "Overview", DELIVERY_KPIS, id="report-04-card-font-size"),
        # keyDrivers.numericTargetSelectedKind 0D
        pytest.param(SAMPLE, "14 visuals with bindings", "13ccb523443b4a2550ad", id="sample-key-drivers"),
        # tableEx column widths the CLI once wrote as 150.0D stay as saved
        pytest.param(KITCHEN_SINK, "Regional Detail", "898c9fceaa276a7d2159", id="report-01-column-widths"),
    ],
)
def test_unedited_page_apply_keeps_literals(
    fixture_copy: Callable[[str], Path], tmp_path: Path, fixture: str, page: str, visual: str
) -> None:
    root = fixture_copy(fixture)
    path = _visual_file(root, visual)
    before = path.read_bytes()

    spec = tmp_path / "page.yaml"
    exported = cli("export", "--page", page, "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("prop", "value", "expected"),
    [
        ("chart:value.fontSize [Measures Table.Task Count]", "30", "30D"),
        ("chart:layout.columnCount", "2", "2D"),
        ("chart:layout.cellPadding", "4", "4D"),
        ("chart:accentBar.width", "4", "4D"),
        ("chart:accentBar.width", "0.5", "0.5D"),
    ],
)
def test_visual_set_writes_desktop_literal(
    fixture_copy: Callable[[str], Path], prop: str, value: str, expected: str
) -> None:
    root = fixture_copy(SHAPES)
    result = cli("visual", "set", "Overview", DELIVERY_KPIS, f"{prop}={value}", project=root)
    assert result.exit_code == 0, result.output

    obj, name = prop.removeprefix("chart:").split(" [")[0].split(".")
    written = [
        _literal(entry["properties"][name])
        for entry in read_json(_visual_file(root, DELIVERY_KPIS))["visual"]["objects"][obj]
        if name in entry.get("properties", {})
    ]
    assert expected in written


def _card(literal: str) -> dict:
    return {
        "visual": {
            "visualType": "cardVisual",
            "objects": {"accentBar": [{"properties": {"width": {"expr": {"Literal": {"Value": literal}}}}}]},
        }
    }


@pytest.mark.parametrize(
    ("saved", "value", "expected"),
    [
        pytest.param("4.0D", "4", "4.0D", id="same-number-keeps-text"),
        pytest.param("4D", "4.0", "4D", id="same-number-desktop-text"),
        pytest.param("4.0D", "5", "5D", id="new-number-desktop-text"),
        pytest.param("4L", "4", "4D", id="other-type-rewritten"),
    ],
)
def test_reset_keeps_saved_literal_only_for_same_number(saved: str, value: str, expected: str) -> None:
    data = _card(saved)
    set_property(data, "chart:accentBar.width", value, VISUAL_PROPERTIES)
    assert _literal(data["visual"]["objects"]["accentBar"][0]["properties"]["width"]) == expected


def test_kpi_shorthand_writes_whole_decimals_without_fraction() -> None:
    data = {"visual": {"visualType": "cardVisual", "objects": {}}}
    expand_kpis(
        data,
        [{"measure": "Measures Table.Task Count", "fontSize": 28.0, "displayUnits": 1.0}],
        accent_bar={"width": 4.0},
        layout={"columns": 2.0},
    )
    objects = data["visual"]["objects"]
    assert literal_value(objects["accentBar"][0]["properties"]["width"]) == "4D"
    assert literal_value(objects["value"][0]["properties"]["fontSize"]) == "28D"
    assert literal_value(objects["value"][0]["properties"]["labelDisplayUnits"]) == "1D"
    assert literal_value(objects["layout"][0]["properties"]["columnCount"]) == "2D"
