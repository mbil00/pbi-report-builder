"""Validate flags visual roles and field refs the model lacks; legacy cards keep `Values` (#78).

report-02's cards were written by an old `pbi` with cardVisual's roles plus a
literal `Fields` role, and its `dept-bar` sort held a stringified Python dict.
The fixture is repaired; these tests put the old shapes back on a copy.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from pbi.apply import apply_yaml
from pbi.project import Project
from pbi.roles import normalize_visual_role, stored_visual_roles
from pbi.validate import validate_project
from tests.support import cli

FIXTURE = "report-02-model-heavy"


def _visual_path(root: Path, name: str) -> Path:
    for path in root.glob("*.Report/definition/pages/*/visuals/*/visual.json"):
        if json.loads(path.read_text(encoding="utf-8")).get("name") == name:
            return path
    raise AssertionError(f"visual {name!r} not found")


def _edit_visual(root: Path, name: str, edit: Callable[[dict], None]) -> Path:
    path = _visual_path(root, name)
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _errors(root: Path, **kwargs: Any) -> list[str]:
    issues = validate_project(Project.find(root), include_layout_checks=False, **kwargs)
    return [issue.message for issue in issues if issue.level == "error"]


def _source(entity: str) -> dict:
    return {"SourceRef": {"Entity": entity}}


def _column(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": _source(entity), "Property": prop}}


def _measure(entity: str, prop: str) -> dict:
    return {"Measure": {"Expression": _source(entity), "Property": prop}}


def _level(entity: str, hierarchy: str, level: str) -> dict:
    return {
        "HierarchyLevel": {
            "Expression": {"Hierarchy": {"Expression": _source(entity), "Hierarchy": hierarchy}},
            "Level": level,
        }
    }


def _bind(field: dict, role: str = "Category") -> Callable[[dict], None]:
    def edit(data: dict) -> None:
        data["visual"]["query"]["queryState"][role] = {
            "projections": [{"field": field, "queryRef": "x", "nativeQueryRef": "x"}]
        }

    return edit


def _sort(field: dict) -> Callable[[dict], None]:
    def edit(data: dict) -> None:
        data["visual"]["query"]["sortDefinition"] = {
            "sort": [{"field": field, "direction": "Descending"}]
        }

    return edit


# --- The shapes the old `pbi` wrote into report-02 -------------------------------


def _old_card_roles(data: dict) -> None:
    query_state = data["visual"]["query"]["queryState"]
    query_state["Fields"] = query_state.pop("Values")
    for role in ("Data", "Rows", "Tooltips"):
        query_state[role] = {"projections": []}


def test_repaired_fixture_validates_clean(fixture_copy: Callable[[str], Path]) -> None:
    assert _errors(fixture_copy(FIXTURE)) == []


def test_validate_flags_card_roles_old_pbi_wrote(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    _edit_visual(root, "card-actual", _old_card_roles)

    errors = _errors(root)

    assert errors == [
        f'Role "{role}" is not a data role of card. Roles: Values'
        for role in ("Fields", "Data", "Rows", "Tooltips")
    ]
    result = cli("validate", project=root)
    assert result.exit_code == 1
    assert 'Role "Fields" is not a data role of card' in result.output


def test_validate_flags_stringified_sort_ref(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    _edit_visual(root, "dept-bar", _sort(_column("{'GL_Actuals", "Actual Amount': 'descending'}")))

    assert _errors(root) == [
        'Visual "dept-bar" sort references table "{\'GL_Actuals", which is not in the semantic model'
    ]


# --- Model refs ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        pytest.param(_bind(_column("Departments", "Division")), 'binding "Category" references table "Departments"', id="table"),
        pytest.param(_bind(_column("Department", "Divisions")), 'binding "Category" references field "Department.Divisions"', id="column"),
        pytest.param(_bind(_measure("GL_Actuals", "Actual Amt"), "Y"), 'binding "Y" references field "GL_Actuals.Actual Amt"', id="measure"),
        pytest.param(
            _bind({"Aggregation": {"Expression": _column("GL_Actuals", "Amt"), "Function": 0}}, "Y"),
            'binding "Y" references field "GL_Actuals.Amt"',
            id="aggregation",
        ),
        pytest.param(_bind(_level("Department", "Orgs", "Division")), 'binding "Category" references hierarchy "Department.Orgs"', id="hierarchy"),
        pytest.param(
            _bind(_level("Department", "Org", "Region")),
            'binding "Category" references level "Region" of hierarchy "Department.Org"',
            id="level",
        ),
        pytest.param(_sort(_measure("GL_Actuals", "Budget Amount")), 'sort references field "GL_Actuals.Budget Amount"', id="sort"),
    ],
)
def test_validate_flags_refs_missing_from_model(
    fixture_copy: Callable[[str], Path], edit: Callable[[dict], None], problem: str
) -> None:
    root = fixture_copy(FIXTURE)
    _edit_visual(root, "dept-bar", edit)

    assert _errors(root) == [f'Visual "dept-bar" {problem}, which is not in the semantic model']
    assert _errors(root, include_model_checks=False) == []


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(_bind(_column("department", "DIVISION")), id="case-insensitive"),
        pytest.param(_bind(_level("Department", "Org", "Division")), id="hierarchy-level"),
        pytest.param(_bind({"Aggregation": {"Expression": _column("GL_Actuals", "Amount"), "Function": 0}}, "Y"), id="aggregation"),
        # Field kind isn't checked: report-01 holds Column sort refs on measures (#113).
        pytest.param(_sort(_column("GL_Actuals", "Actual Amount")), id="column-ref-to-measure"),
    ],
)
def test_validate_accepts_refs_the_model_has(
    fixture_copy: Callable[[str], Path], edit: Callable[[dict], None]
) -> None:
    root = fixture_copy(FIXTURE)
    _edit_visual(root, "dept-bar", edit)

    assert _errors(root) == []


def test_validate_accepts_report_extension_measures(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    _edit_visual(root, "dept-bar", _sort(_measure("Report Measures", "Share")))
    _edit_visual(root, "card-actual", _bind(_measure("GL_Actuals", "Report Total"), "Values"))
    definition = next(root.glob("*.Report/definition"))
    (definition / "reportExtensions.json").write_text(
        json.dumps({
            "name": "extension",
            "entities": [
                {"name": "Report Measures", "measures": [{"name": "Share", "expression": "1"}]},
                {"name": "GL_Actuals", "measures": [{"name": "Report Total", "expression": "1"}]},
            ],
        }),
        encoding="utf-8",
    )

    assert _errors(root) == []


# --- Roles ---------------------------------------------------------------------------


def test_validate_accepts_desktop_cardvisual_rows_and_custom_visual_roles(
    fixture_copy: Callable[[str], Path],
) -> None:
    root = fixture_copy(FIXTURE)

    def to_card_visual(data: dict) -> None:
        data["visual"]["visualType"] = "cardVisual"
        query_state = data["visual"]["query"]["queryState"]
        query_state["Data"] = query_state.pop("Values")
        # Desktop's sample-report binds a cardVisual Rows field (#109).
        query_state["Rows"] = {"projections": []}

    _edit_visual(root, "card-actual", to_card_visual)
    _edit_visual(root, "card-budget", lambda data: data["visual"].update(visualType="myCustomVisual1234"))

    assert _errors(root) == []


# --- Legacy card round-trip --------------------------------------------------------


def test_export_apply_keeps_legacy_card_values_role(fixture_copy: Callable[[str], Path], tmp_path: Path) -> None:
    root = fixture_copy(FIXTURE)
    spec = tmp_path / "report.yaml"
    assert cli("export", "-o", spec, project=root).exit_code == 0

    result = cli("apply", spec, project=root)

    assert result.exit_code == 0, result.output
    query_state = json.loads(_visual_path(root, "card-actual").read_text(encoding="utf-8"))["visual"]["query"]["queryState"]
    assert list(query_state) == ["Values"]
    assert query_state["Values"]["projections"][0]["queryRef"] == "GL_Actuals.Actual Amount"


@pytest.mark.parametrize("role", ["Values", "Fields"])
def test_apply_creates_legacy_card_with_its_own_roles(fixture_copy: Callable[[str], Path], role: str) -> None:
    root = fixture_copy(FIXTURE)
    project = Project.find(root)
    spec = {
        "pages": [{
            "name": "Finance Overview",
            "visuals": [{
                "name": "new-card",
                "type": "card",
                "bindings": {role: "GL_Actuals.Actual Amount (measure)"},
            }],
        }],
    }

    result = apply_yaml(project, yaml.safe_dump(spec, sort_keys=False))

    assert result.errors == []
    data = json.loads(_visual_path(root, "new-card").read_text(encoding="utf-8"))
    assert data["visual"]["visualType"] == "card"
    assert list(data["visual"]["query"]["queryState"]) == ["Values"]
    assert _errors(root) == []


def test_stored_card_roles_differ_from_the_card_alias() -> None:
    assert [role["name"] for role in stored_visual_roles("card")] == ["Values"]
    assert [role["name"] for role in stored_visual_roles("cardVisual")] == ["Data", "Tooltips"]
    assert [role["name"] for role in stored_visual_roles("table")] == ["Values"]
    assert normalize_visual_role("card", "values") == "Values"
    assert normalize_visual_role("card", "Fields") == "Values"
    assert normalize_visual_role("cardVisual", "Values") == "Data"
    assert normalize_visual_role("treemap", "Y") == "Values"
