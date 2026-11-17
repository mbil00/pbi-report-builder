"""Named facts from the read-only visual, page and report commands on report-01.

The fixture harness runs these commands only to check they don't crash or
write. These tests check what they print, against values saved in the
kitchen-sink fixture.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pbi.project import Project
from tests.support import KITCHEN_SINK_DIR, SHAPES_DIR, cli, copy_fixture, pbip_path, visual_by_title

OVERVIEW = "Executive Overview"


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Every command here is read-only, so the module shares one copy.
    return copy_fixture(KITCHEN_SINK_DIR.name, tmp_path_factory.mktemp("read"))


def pbi(root: Path, *args: str) -> str:
    result = cli(*args, project=root)
    assert result.exit_code == 0, result.output
    return result.output


def table(output: str) -> list[dict[str, str]]:
    """Parse the one Rich table in ``output`` into rows keyed by column title.

    Columns are cut at the header titles' offsets, so an empty cell stays
    empty instead of shifting the next value left.
    """
    lines = output.splitlines()
    rule = next(i for i, line in enumerate(lines) if line.strip().startswith("─"))
    header = lines[rule - 1]
    columns = [(match.group(), match.start()) for match in re.finditer(r"\S+(?: \S+)*", header)]
    rows = []
    for line in lines[rule + 1:]:
        if not line.strip():
            continue
        cells = {}
        for index, (title, start) in enumerate(columns):
            end = columns[index + 1][1] if index + 1 < len(columns) else None
            cells[title] = line[start:end].strip()
        rows.append(cells)
    return rows


def values(output: str, key: str = "Property", value: str = "Value") -> dict[str, str]:
    return {row[key]: row[value] for row in table(output)}


def test_visual_get_reads_listed_properties(root: Path) -> None:
    output = pbi(root, "visual", "get", OVERVIEW, "revenueByMonth", "title.text", "background.color", "subtitle.text")
    assert values(output) == {
        "title.text": "Revenue vs Target by Month",
        "background.color": "#FFFFFF",
        "subtitle.text": "",
    }
    # One property prints the bare value.
    assert pbi(root, "visual", "get", OVERVIEW, "revenueByMonth", "title.text").strip() == "Revenue vs Target by Month"


def test_visual_index_references_accept_bare_and_prefixed_numbers(root: Path) -> None:
    project = Project.find(pbip_path(root))
    second = project.get_visuals(project.find_page(OVERVIEW))[1]
    for ref in ("2", "#2"):
        assert pbi(root, "visual", "get", OVERVIEW, ref, "visualType").strip() == second.visual_type


def test_visual_get_overview_lists_geometry_and_canonical_object_properties(root: Path) -> None:
    rows = values(pbi(root, "visual", "get", OVERVIEW, "revenueByMonth"))
    assert rows["Name"] == "revenueByMonth"
    assert rows["Type"] == "lineClusteredColumnComboChart"
    assert rows["Position"] == "16, 200"
    assert rows["Size"] == "760 x 320"
    # Desktop saves `title.fontColor`; the overview shows the CLI name.
    assert rows["title.color"] == "#2D3436"
    assert "title.fontColor" not in rows
    assert rows["legend.position"] == "TopRight"
    assert "position.x" not in rows

    card = values(pbi(root, "visual", "get", OVERVIEW, "kpiStrip"))
    assert card["chart:accentBar.position"] == "Top"
    assert card["accentBar.color [Measures.Revenue]"] == "#0078D4"


def test_visual_get_all_props_adds_core_properties(root: Path) -> None:
    rows = values(pbi(root, "visual", "get", OVERVIEW, "kpiStrip", "--all-props"))
    assert {key: rows[key] for key in ("position.x", "position.y", "position.width", "visualType")} == {
        "position.x": "16",
        "position.y": "70",
        "position.width": "1248",
        "visualType": "cardVisual",
    }
    assert rows["accentBar.color [Measures.Margin]"] == "#107C10"


def test_visual_get_defaults_marks_each_value_source(root: Path) -> None:
    rows = table(pbi(root, "visual", "get", OVERVIEW, "revenueByMonth", "--defaults"))
    sources = {row["Property"]: (row["Value"], row["Source"]) for row in rows}
    assert sources["legend.position"] == ("TopRight", "explicit")
    assert sources["background.show"] == ("True", "explicit")
    assert sources["tooltip.show"] == ("True", "default")
    assert sources["header.show"] == ("False", "default")
    # An explicit value hides the known default for the same property.
    assert [row["Property"] for row in rows].count("background.show") == 1


def test_visual_get_page_filters_by_visual_type(root: Path) -> None:
    rows = table(pbi(root, "visual", "get-page", OVERVIEW, "--visual-type", "cardVisual"))
    assert {row["Visual"] for row in rows} == {"kpiStrip", "yoyCard"}
    assert {row["Type"] for row in rows} == {"cardVisual"}
    assert {"Visual": "kpiStrip", "Type": "cardVisual", "Property": "accentBar.color [Measures.Orders]",
            "Value": "#FFB900"} in rows


DIFF_KEYS = {
    "type": ("clusteredColumnChart", "lineClusteredColumnComboChart"),
    "title.text": ("Monthly Revenue", "Revenue vs Target by Month"),
    "title.fontSize": ("11.0", "14.0"),
    "title.color": ("#D83B01", "#2D3436"),
    "legend.show": ("", "true"),
    "legend.position": ("", "TopRight"),
    "bindings.Y2": ("", "_Measures.Revenue Target (measure)"),
}


@pytest.mark.parametrize(
    "extra,core",
    [
        pytest.param((), {}, id="default"),
        pytest.param(
            ("--all-props",),
            {"position.y": ("564", "200"), "size.width": ("620", "760"), "size.height": ("140", "320")},
            id="all-props",
        ),
    ],
)
def test_visual_diff_lists_only_differing_properties(root: Path, extra: tuple[str, ...], core: dict) -> None:
    output = pbi(root, "visual", "diff", "Regional Detail", "regionalTrend", OVERVIEW, "revenueByMonth", *extra)
    left, right = "Regional Detail/regionalTrend", f"{OVERVIEW}/revenueByMonth"
    rows = {row["Property"]: (row[left], row[right]) for row in table(output)}
    assert rows == {**DIFF_KEYS, **core}


def test_visual_inspect_shows_entries_with_selectors(root: Path) -> None:
    output = pbi(root, "visual", "inspect", OVERVIEW, "kpiStrip")
    accent = output.split("\naccentBar\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert accent[:4] == ["  [id=default]", "    position = Top", "    show = True", "    width = 4.0"]
    assert accent[4:6] == ["  [metadata=Measures.Revenue]", "    color = #0078D4"]

    container = pbi(root, "visual", "inspect", OVERVIEW, "yoyCard")
    assert "\ncontainer:background\n    color = #FAFAFA\n    show = True\n" in container

    sections = json.loads(pbi(root, "visual", "inspect", OVERVIEW, "kpiStrip", "--json"))
    revenue = next(e for e in sections["accentBar"] if e["selector"].get("metadata") == "Measures.Revenue")
    assert revenue["properties"] == {"color": "#0078D4"}


def test_visual_inspect_shows_desktop_selectors_and_expression_values(fixture_copy: Callable[[str], Path]) -> None:
    """report-04's ``Delivery KPIs`` card: a full Desktop selector and a measure-valued property."""
    root = fixture_copy(SHAPES_DIR.name)
    card = visual_by_title("Overview", "Delivery KPIs", root)["name"]
    output = pbi(root, "visual", "inspect", "Overview", card)
    reference = output.split("\nreferenceLabel\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert re.fullmatch(
        r"  \[id=field-[0-9a-f-]+, metadata=Measures Table\.Task Count, order=0, wildcard=0\]", reference[0]
    )
    # The value is a measure expression, printed as a one-line summary.
    assert reference[1].startswith("    value = ") and "Measure" in reference[1]
    assert len(reference) == 2


def test_page_and_report_get_read_listed_properties(root: Path) -> None:
    page = pbi(root, "page", "get", "Tooltip - Order Context", "width", "height", "displayOption")
    assert values(page) == {"width": "320", "height": "240", "displayOption": "FitToPage"}
    assert pbi(root, "page", "get", "Tooltip - Order Context", "width").strip() == "320"

    report = pbi(root, "report", "get", "layoutOptimization", "settings.useStylableVisualContainerHeader")
    assert values(report) == {"layoutOptimization": "", "settings.useStylableVisualContainerHeader": "True"}
