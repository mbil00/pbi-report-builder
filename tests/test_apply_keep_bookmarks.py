"""Desktop bookmarks an unedited export -> apply keeps (#108, R4).

Each round-trip test runs a page export -> apply on a copy of a Desktop-saved
fixture and checks that one bookmark file is unchanged: its ``$schema``, the
order and content of ``options`` (``targetVisualNames`` without
``applyOnlyToTargetVisuals``, even when empty), ``explorationState.filters`` /
``objects`` and the key order inside ``visualContainers``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.support import cli, read_json, report_definition

SHAPES = "report-04-desktop-shapes"
SAMPLE = "sample-report"


def _bookmark_file(root: Path, bookmark: str) -> Path:
    return next(report_definition(root).glob(f"bookmarks/{bookmark}.bookmark.json"))


def _export_page(root: Path, tmp_path: Path, page: str) -> Path:
    spec = tmp_path / "page.yaml"
    exported = cli("export", "--page", page, "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    return spec


def _apply(root: Path, spec: Path) -> None:
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output


def _bookmark_entry(spec: Path, name: str) -> dict:
    data = yaml.safe_load(spec.read_text(encoding="utf-8"))
    return next(entry for entry in data["bookmarks"] if entry["name"] == name)


@pytest.mark.parametrize(
    ("fixture", "page", "bookmark"),
    [
        # targetVisualNames without applyOnlyToTargetVisuals, options before
        # explorationState, explorationState.objects: {}
        pytest.param(SHAPES, "Task Board", "7eeb969d0757059a1b90", id="report-04-all-statuses"),
        pytest.param(SHAPES, "Task Board", "8df969a2b441003c37ea", id="report-04-blocked-only"),
        # targetVisualNames: [], suppressData, Desktop's visualContainers and singleVisual key order
        pytest.param(SHAPES, "Overview", "cebb79b2c49dc642be7d", id="report-04-hide-logo"),
        # $schema 2.0.0 and explorationState.filters
        pytest.param(SAMPLE, "07 Bookmarks", "15c8b821640b61170d78", id="sample-sorted"),
        pytest.param(SAMPLE, "07 Bookmarks", "4a7afaf5e2660745c101", id="sample-central-region"),
        pytest.param(SAMPLE, "07 Bookmarks", "6927579d9a537e8a70a2", id="sample-no-filters"),
        pytest.param(SAMPLE, "07 Bookmarks", "6c56fc06ad2b0e09e9de", id="sample-visibility"),
    ],
)
def test_unedited_page_apply_keeps_bookmark_file(
    fixture_copy: Callable[[str], Path], tmp_path: Path, fixture: str, page: str, bookmark: str
) -> None:
    root = fixture_copy(fixture)
    path = _bookmark_file(root, bookmark)
    before = path.read_bytes()

    _apply(root, _export_page(root, tmp_path, page))

    assert path.read_bytes() == before


def test_desktop_target_names_without_scope_export_as_options(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    # Desktop's "All visuals" scope keeps targetVisualNames without
    # applyOnlyToTargetVisuals; `target:` would turn it into selected-visuals scope.
    root = fixture_copy(SHAPES)
    spec = _export_page(root, tmp_path, "Task Board")

    entry = _bookmark_entry(spec, "Task Board - All Statuses")

    assert "target" not in entry
    assert entry["options"] == {
        "targetVisualNames": ["b41c5b1f9284d5c00054"],
        "preserveNewVisualVisibility": True,
    }
    assert entry["state"]["objects"] == {}


def test_edited_bookmark_keeps_desktop_schema_filters_and_order(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SAMPLE)
    path = _bookmark_file(root, "15c8b821640b61170d78")
    source = read_json(path)
    spec = _export_page(root, tmp_path, "07 Bookmarks")
    data = yaml.safe_load(spec.read_text(encoding="utf-8"))
    entry = next(item for item in data["bookmarks"] if item["name"] == "Sorted")
    entry["captureDisplay"] = False
    spec.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    _apply(root, spec)

    result = read_json(path)
    assert result["$schema"] == source["$schema"]
    assert list(result) == list(source)
    assert list(result["explorationState"]) == list(source["explorationState"])
    assert result["explorationState"]["filters"] == source["explorationState"]["filters"]
    assert result["options"] == {**source["options"], "suppressDisplay": True}


def test_added_target_replaces_remembered_selection(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    # Adding `target:` to an exported all-visuals bookmark must scope it to the
    # new list, not the targetVisualNames Desktop remembered under options.
    root = fixture_copy(SHAPES)
    spec = _export_page(root, tmp_path, "Task Board")
    data = yaml.safe_load(spec.read_text(encoding="utf-8"))
    entry = next(item for item in data["bookmarks"] if item["name"] == "Task Board - All Statuses")
    entry["target"] = ["731eaccec02d78d52c10"]
    spec.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    _apply(root, spec)

    options = read_json(_bookmark_file(root, "7eeb969d0757059a1b90"))["options"]
    assert options["applyOnlyToTargetVisuals"] is True
    assert options["targetVisualNames"] == ["731eaccec02d78d52c10"]
    assert options["preserveNewVisualVisibility"] is True
