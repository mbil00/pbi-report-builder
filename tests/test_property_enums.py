"""Hand-written property enums accept what Desktop accepts.

``set_property`` checks a ``VISUAL_PROPERTIES`` enum before the extracted
Desktop capability schema, so a hand-written list narrower than the schema
rejects values Desktop writes (#77: ``legend.position: TopRight``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from pbi.properties import VISUAL_PROPERTIES, set_property
from tests.support import cli, read_json

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "pbi" / "data" / "visual_capabilities.json"

# Hand-written enums that still differ from the schema.
KNOWN_ENUM_DRIFT = {
    "xAxis.gridlineStyle": "#112",
    "yAxis.gridlineStyle": "#112",
    "labels.position": "#112",
    "labels.labelStyle": "#112",
    "columnHeaders.alignment": "#112",
}

LEGEND_POSITIONS = (
    "Top", "TopCenter", "TopRight", "Left", "Right",
    "LeftCenter", "RightCenter", "Bottom", "BottomCenter", "BottomRight",
)


@cache
def _schema_enums(object_name: str, prop: str) -> frozenset[str]:
    """Union of the schema enum for ``object.prop`` across all visual types."""
    visuals = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["visuals"]
    values: set[str] = set()
    for visual in visuals.values():
        ptype = visual.get("objects", {}).get(object_name, {}).get(prop)
        if isinstance(ptype, list):
            values.update(ptype)
    return frozenset(values)


def _objects_enums() -> list:
    params = []
    for name, prop in sorted(VISUAL_PROPERTIES.items()):
        if not prop.enum_values or prop.objects_path != "objects":
            continue
        if not _schema_enums(prop.container_key, prop.container_prop):
            continue
        marks = []
        if name in KNOWN_ENUM_DRIFT:
            marks.append(pytest.mark.xfail(reason=KNOWN_ENUM_DRIFT[name], strict=True))
        params.append(pytest.param(name, id=name, marks=marks))
    return params


@pytest.mark.parametrize("name", _objects_enums())
def test_handcrafted_enum_matches_schema(name: str) -> None:
    prop = VISUAL_PROPERTIES[name]
    schema = _schema_enums(prop.container_key, prop.container_prop)
    assert set(prop.enum_values) == schema


def test_legend_positions_are_desktops() -> None:
    assert VISUAL_PROPERTIES["legend.position"].enum_values == LEGEND_POSITIONS


@pytest.mark.parametrize("value", LEGEND_POSITIONS)
def test_set_legend_position_accepts_desktop_value(value: str) -> None:
    data = {"visual": {"visualType": "lineClusteredColumnComboChart"}}
    set_property(data, "legend.position", value, VISUAL_PROPERTIES)
    raw = data["visual"]["objects"]["legend"][0]["properties"]["position"]
    assert raw == {"expr": {"Literal": {"Value": f"'{value}'"}}}


def test_set_legend_position_rejects_unknown_value() -> None:
    data = {"visual": {"visualType": "lineClusteredColumnComboChart"}}
    with pytest.raises(ValueError, match="TopLeft"):
        set_property(data, "legend.position", "TopLeft", VISUAL_PROPERTIES)


def _revenue_by_month(root: Path) -> Path:
    [path] = [
        path
        for path in root.rglob("visual.json")
        if read_json(path).get("name") == "revenueByMonth"
    ]
    return path


def _legend_position(path: Path) -> str:
    legend = read_json(path)["visual"]["objects"]["legend"]
    return legend[0]["properties"]["position"]["expr"]["Literal"]["Value"]


def test_report01_page_roundtrip_keeps_desktop_top_right(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    """report-01's Desktop-saved ``TopRight`` legend exports and applies back."""
    root = fixture_copy("report-01-kitchen-sink")
    visual = _revenue_by_month(root)
    assert _legend_position(visual) == "'TopRight'"

    spec = tmp_path / "overview.yaml"
    exported = cli("export", "--page", "Executive Overview", "-o", str(spec), project=root)
    assert exported.exit_code == 0, exported.output
    assert "position: TopRight" in spec.read_text(encoding="utf-8")

    applied = cli("apply", str(spec), project=root)
    assert applied.exit_code == 0, applied.output
    assert _legend_position(visual) == "'TopRight'"


def test_visual_set_writes_bottom_right(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy("report-01-kitchen-sink")
    result = cli(
        "visual", "set", "Executive Overview", "revenueByMonth", "legend.position=BottomRight",
        project=root,
    )
    assert result.exit_code == 0, result.output
    assert _legend_position(_revenue_by_month(root)) == "'BottomRight'"
