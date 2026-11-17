"""Bindings on visuals that hold Desktop ``Aggregation`` projections (#73).

report-04's Project Detail tables bind ``Sum(Task.ActualHours)``-style
``Aggregation`` projections. Applying bindings to such a visual used to crash
with ``Invalid field type 'aggregation'``. The full-report round-trip is still
covered (as an xfail) by ``test_fixture_harness``; these tests pin the page
and visual paths that #73 broke.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pbi.project import Project
from pbi.visual_builders import existing_bound_fields
from tests.support import cli, read_json

FIXTURE = "report-04-desktop-shapes"
PAGE = "Project Detail"
# Both tableEx visuals on Project Detail hold an Aggregation projection.
AGGREGATION_VISUALS = ("fd745b46aca9deb264b7", "a7caba173e06542d0936")


def _query_states(root: Path) -> dict[str, object]:
    project = Project.find(root)
    page = project.find_page(PAGE)
    return {
        name: read_json(project.find_visual(page, name).folder / "visual.json")["visual"]["query"]
        for name in AGGREGATION_VISUALS
    }


def test_page_export_apply_keeps_aggregation_bindings(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(FIXTURE)
    before = _query_states(root)
    spec = tmp_path / "page.yaml"

    exported = cli("export", "--page", PAGE, "-o", spec, project=root)
    assert exported.exit_code == 0, exported.output
    applied = cli("apply", spec, project=root)

    assert applied.exit_code == 0, applied.output
    assert _query_states(root) == before


def test_existing_aggregation_binding_resolves_as_its_column(
    fixture_project: Callable[[str], Project],
) -> None:
    project = fixture_project(FIXTURE)
    visual = project.find_visual(project.find_page(PAGE), AGGREGATION_VISUALS[0])

    fields = {(f.entity, f.prop): f for f in existing_bound_fields(project, visual)}

    actual_hours = fields[("Task", "ActualHours")]
    assert actual_hours.role == "Values"
    assert actual_hours.field_type == "column"
    assert actual_hours.data_type is not None


def test_bind_on_visual_with_aggregation_projection(
    fixture_copy: Callable[[str], Path],
) -> None:
    root = fixture_copy(FIXTURE)

    result = cli("visual", "bind", PAGE, AGGREGATION_VISUALS[0], "Values", "Task.Category", project=root)

    assert result.exit_code == 0, result.output
    assert "Bound" in result.output
