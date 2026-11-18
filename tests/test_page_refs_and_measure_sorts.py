"""Page-navigation targets and measure sorts in Desktop's shape (#113, R6).

Desktop saves a button's ``visualLink.navigationSection`` as the target page's
id (folder name) and a sort on a measure as a ``Measure`` field reference.
report-01 held two shapes that an early ``pbi`` wrote before it was saved in
Desktop: a page display name (``'Product Detail'``) as the navigation target,
and ``Column`` references to the ``_Measures.Revenue`` measure in three sorts.
The fixture was repaired in place. Apply still rewrites those legacy shapes to
Desktop's, and leaves the Desktop shape alone on an unedited export -> apply.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pbi.model import SemanticModel
from tests.support import FIXTURES, cli, read_json, report_definition

KITCHEN_SINK = "report-01-kitchen-sink"
HOME = "eb6cb5c033bc16fa450d"
NAV_BUTTONS = {
    # visual -> (target page id, target display name)
    "4962ffe2230372e47f86": ("ea8cde9a29fcc668fa67", "Product Detail"),
    "96c806cbe45b1de49dd1": ("5ff350fe1c9ba413c745", "Regional Detail"),
}
MEASURE_SORTS = {
    # visual -> page
    "77b69dede4525967c721": "43b651ae6527f03fbd85",
    "2931b2aea3d03b834970": "5ff350fe1c9ba413c745",
    "d4c8f3cb3bc934b11a5b": "ea8cde9a29fcc668fa67",
}


def _visual_path(root: Path, page: str, visual: str) -> Path:
    return report_definition(root) / "pages" / page / "visuals" / visual / "visual.json"


def _visual_files(root: Path) -> Iterator[Path]:
    yield from sorted(report_definition(root).glob("pages/*/visuals/*/visual.json"))


def _navigation_section(visual: dict) -> str | None:
    for entry in visual.get("visual", {}).get("visualContainerObjects", {}).get("visualLink", []):
        section = entry.get("properties", {}).get("navigationSection")
        if section is not None:
            return section["expr"]["Literal"]["Value"].strip("'")
    return None


def _sort_fields(visual: dict) -> list[tuple[str, str, str]]:
    sort = visual.get("visual", {}).get("query", {}).get("sortDefinition", {}).get("sort", [])
    fields = []
    for entry in sort:
        ((kind, ref),) = entry["field"].items()
        if "Expression" in ref and "SourceRef" in ref["Expression"]:
            fields.append((kind, ref["Expression"]["SourceRef"].get("Entity", ""), ref["Property"]))
    return fields


@pytest.mark.parametrize("name", list(FIXTURES))
def test_fixture_navigation_targets_are_page_ids(name: str) -> None:
    root = FIXTURES[name]
    page_ids = {path.name for path in (report_definition(root) / "pages").iterdir() if path.is_dir()}
    for path in _visual_files(root):
        section = _navigation_section(read_json(path))
        if section is not None:
            assert section in page_ids, f"{path.relative_to(root)}: navigationSection {section!r} is not a page id"


@pytest.mark.parametrize("name", list(FIXTURES))
def test_fixture_measure_sorts_are_measure_refs(name: str) -> None:
    root = FIXTURES[name]
    measures = {
        (table.name, measure.name) for table in SemanticModel.load(root).tables for measure in table.measures
    }
    for path in _visual_files(root):
        for kind, entity, prop in _sort_fields(read_json(path)):
            if (entity, prop) in measures:
                assert kind == "Measure", f"{path.relative_to(root)}: sort on measure {entity}.{prop} saved as {kind}"


def test_unedited_apply_keeps_nav_targets_and_measure_sorts(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(KITCHEN_SINK)
    paths = [_visual_path(root, HOME, visual) for visual in NAV_BUTTONS]
    paths += [_visual_path(root, page, visual) for visual, page in MEASURE_SORTS.items()]
    before = {path: path.read_bytes() for path in paths}

    spec = tmp_path / "report.yaml"
    exported = cli("export", "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output

    assert {path: path.read_bytes() for path in paths} == before


def test_apply_rewrites_legacy_shapes_to_desktop(fixture_copy: Callable[[str], Path], tmp_path: Path) -> None:
    """A project an early ``pbi`` wrote gets Desktop's page ids and ``Measure`` sorts back."""
    root = fixture_copy(KITCHEN_SINK)
    for visual, (page_id, display_name) in NAV_BUTTONS.items():
        path = _visual_path(root, HOME, visual)
        path.write_text(path.read_text(encoding="utf-8").replace(f"'{page_id}'", f"'{display_name}'"), encoding="utf-8")
        assert _navigation_section(read_json(path)) == display_name
    for visual, page in MEASURE_SORTS.items():
        path = _visual_path(root, page, visual)
        data = read_json(path)
        sort_field = data["visual"]["query"]["sortDefinition"]["sort"][0]["field"]
        sort_field["Column"] = sort_field.pop("Measure")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    spec = tmp_path / "report.yaml"
    exported = cli("export", "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output

    for visual, (page_id, _) in NAV_BUTTONS.items():
        assert _navigation_section(read_json(_visual_path(root, HOME, visual))) == page_id
    for visual, page in MEASURE_SORTS.items():
        assert _sort_fields(read_json(_visual_path(root, page, visual))) == [("Measure", "_Measures", "Revenue")]

