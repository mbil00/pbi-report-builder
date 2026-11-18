"""Desktop filters an unedited export -> apply keeps (#108, R3).

Each round-trip test runs a page export -> apply on a copy of a Desktop-saved
fixture and checks that one file is unchanged: the filter keeps its name (no
``Filter_<hash>``), gains no ``isHiddenInViewMode`` / ``isLockedInViewMode`` /
``howCreated`` its source lacked, and a ``RelativeTime`` filter stays one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pbi.filters.parsing import _extract_relative_structured
from tests.support import cli, read_json, report_definition

SHAPES = "report-04-desktop-shapes"
SAMPLE = "sample-report"
FILTER_LAB_VISUAL = "837b840b86bb43a07ee7"  # RelativeDate filter without view-mode flags or howCreated
RELATIVE_TIME_VISUAL = "d8e7ea99dd81e99a0b03"  # RelativeTime filters, TimeUnit 6 and 7


def _page_file(root: Path, page: str) -> Path:
    return next(report_definition(root).glob(f"pages/{page}/page.json"))


def _visual_file(root: Path, visual: str) -> Path:
    return next(report_definition(root).glob(f"pages/*/visuals/{visual}/visual.json"))


def _export_page(root: Path, tmp_path: Path, page: str) -> Path:
    spec = tmp_path / "page.yaml"
    exported = cli("export", "--page", page, "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    return spec


def _apply(root: Path, spec: Path) -> None:
    applied = cli("apply", spec, project=root)
    assert applied.exit_code == 0, applied.output


@pytest.mark.parametrize(
    ("fixture", "page", "target"),
    [
        # No flags or howCreated on the source filter
        pytest.param(SHAPES, "Filter Lab", f"visual:{FILTER_LAB_VISUAL}", id="report-04-relative-date"),
        # howCreated: User, no flags; page-level and visual-level filters
        pytest.param(SAMPLE, "01 Relative Date", "page:7a39f7499ad94e100e0d", id="sample-page-filters"),
        pytest.param(SAMPLE, "01 Relative Date", "visual:dcf7bcc8185a099d336e", id="sample-in-this-filters"),
        # RelativeTime DateAdd(Now, -15, TimeUnit 6) .. Now stays RelativeTime
        pytest.param(SAMPLE, "02 Relative Time", f"visual:{RELATIVE_TIME_VISUAL}", id="sample-relative-time"),
    ],
)
def test_unedited_page_apply_keeps_filter_file(
    fixture_copy: Callable[[str], Path], tmp_path: Path, fixture: str, page: str, target: str
) -> None:
    root = fixture_copy(fixture)
    kind, name = target.split(":")
    path = _page_file(root, name) if kind == "page" else _visual_file(root, name)
    before = path.read_bytes()

    _apply(root, _export_page(root, tmp_path, page))

    assert path.read_bytes() == before


def _filter_lab_spec(spec_path: Path) -> tuple[dict, dict]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    visual = next(v for v in spec["pages"][0]["visuals"] if v.get("id") == FILTER_LAB_VISUAL)
    return spec, visual["filters"][0]


def test_edited_filter_keeps_its_name_and_omits_default_flags(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)
    spec_path = _export_page(root, tmp_path, "Filter Lab")
    spec, relative = _filter_lab_spec(spec_path)
    relative["count"] = 6
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")

    _apply(root, spec_path)

    written = read_json(_visual_file(root, FILTER_LAB_VISUAL))["filterConfig"]["filters"][0]
    assert written["name"] == "335632bba4432013c272"
    assert written["filter"]["Where"][0]["Condition"]["Between"]["LowerBound"]["DateSpan"]["Expression"][
        "DateAdd"
    ]["Amount"] == -6
    assert not {"isHiddenInViewMode", "isLockedInViewMode", "howCreated"} & written.keys()


def test_hidden_filter_writes_its_flag(fixture_copy: Callable[[str], Path], tmp_path: Path) -> None:
    root = fixture_copy(SHAPES)
    spec_path = _export_page(root, tmp_path, "Filter Lab")
    spec, relative = _filter_lab_spec(spec_path)
    relative["hidden"] = True
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")

    _apply(root, spec_path)

    written = read_json(_visual_file(root, FILTER_LAB_VISUAL))["filterConfig"]["filters"][0]
    assert written["name"] == "335632bba4432013c272"
    assert written["isHiddenInViewMode"] is True
    assert not {"isLockedInViewMode", "howCreated"} & written.keys()


def test_unnamed_new_filter_is_built_as_before(fixture_copy: Callable[[str], Path], tmp_path: Path) -> None:
    root = fixture_copy(SHAPES)
    spec_path = _export_page(root, tmp_path, "Filter Lab")
    spec, relative = _filter_lab_spec(spec_path)
    del relative["name"]
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")

    _apply(root, spec_path)

    written = read_json(_visual_file(root, FILTER_LAB_VISUAL))["filterConfig"]["filters"][0]
    assert written["name"].startswith("Filter_")
    assert written["howCreated"] == "User"


def _relative_time_filters(root: Path) -> dict[str, dict]:
    filters = read_json(_visual_file(root, RELATIVE_TIME_VISUAL))["filterConfig"]["filters"]
    return {f["name"]: f for f in filters}


def test_relative_time_with_unknown_unit_exports_raw(fixture_copy: Callable[[str], Path]) -> None:
    filters = _relative_time_filters(fixture_copy(SAMPLE))

    # TimeUnit 6 is not a unit pbi writes for RelativeTime: no structured form.
    assert _extract_relative_structured(filters["e26810aacd284a00c3b7"]) is None
    assert _extract_relative_structured(filters["c98e4e33084988c3b594"]) == {
        "operator": "InLast", "count": 1, "unit": "Minutes",
    }
