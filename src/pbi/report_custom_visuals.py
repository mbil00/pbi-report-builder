"""Helpers for report-level organization custom visual metadata."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from pbi.project import Project, _write_json
from pbi.schema_refs import REPORT_SCHEMA


@dataclass(frozen=True)
class OrganizationCustomVisualInfo:
    name: str
    path: str
    disabled: bool


def list_organization_custom_visuals(project: Project) -> list[OrganizationCustomVisualInfo]:
    rows = []
    for entry in _custom_visual_rows(project.get_report_meta()):
        rows.append(
            OrganizationCustomVisualInfo(
                name=str(entry["name"]),
                path=str(entry["path"]),
                disabled=bool(entry.get("disabled", False)),
            )
        )
    return rows


def get_organization_custom_visual(project: Project, identifier: str) -> dict:
    return _find_custom_visual(project.get_report_meta(), identifier)


def set_organization_custom_visual(
    project: Project,
    name: str,
    path: str,
    *,
    disabled: bool = False,
) -> tuple[dict, bool, bool]:
    report = project.get_report_meta()
    report.setdefault("$schema", REPORT_SCHEMA)
    visuals = report.setdefault("organizationCustomVisuals", [])
    if not isinstance(visuals, list):
        raise ValueError("report.organizationCustomVisuals is not an array.")

    lowered = name.lower()
    for entry in visuals:
        if isinstance(entry, dict) and str(entry.get("name", "")).lower() == lowered:
            normalized = {
                "name": name,
                "path": path,
            }
            if disabled:
                normalized["disabled"] = True
            changed = entry != normalized
            entry.clear()
            entry.update(normalized)
            if changed:
                _save_report(project, report)
            return dict(entry), False, changed

    created = {
        "name": name,
        "path": path,
    }
    if disabled:
        created["disabled"] = True
    visuals.append(created)
    _save_report(project, report)
    return created, True, True


def delete_organization_custom_visual(project: Project, identifier: str) -> dict:
    report = project.get_report_meta()
    visuals = report.get("organizationCustomVisuals", [])
    if not isinstance(visuals, list):
        raise ValueError("No organization custom visuals configured.")

    entry = _find_custom_visual(report, identifier)
    visuals[:] = [
        row
        for row in visuals
        if not (
            isinstance(row, dict)
            and str(row.get("name", "")) == str(entry.get("name", ""))
            and str(row.get("path", "")) == str(entry.get("path", ""))
        )
    ]
    if not visuals:
        report.pop("organizationCustomVisuals", None)
    _save_report(project, report)
    return entry


def _custom_visual_rows(report: dict) -> list[dict]:
    visuals = report.get("organizationCustomVisuals", [])
    if not isinstance(visuals, list):
        return []
    rows = []
    for entry in visuals:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        path = entry.get("path")
        if not isinstance(name, str) or not isinstance(path, str):
            continue
        normalized = {"name": name, "path": path}
        if "disabled" in entry:
            normalized["disabled"] = bool(entry.get("disabled"))
        rows.append(normalized)
    return rows


def _find_custom_visual(report: dict, identifier: str) -> dict:
    rows = _custom_visual_rows(report)
    lowered = identifier.lower()

    for entry in rows:
        if entry["name"].lower() == lowered:
            return entry
        if entry["path"].lower() == lowered:
            return entry

    partial = [entry for entry in rows if lowered in entry["name"].lower() or lowered in entry["path"].lower()]
    if len(partial) == 1:
        return partial[0]

    names = [entry["name"] for entry in rows]
    matches = difflib.get_close_matches(identifier, names, n=3, cutoff=0.5)
    if matches:
        raise ValueError(
            f'Organization custom visual "{identifier}" not found. Did you mean: {", ".join(matches)}?'
        )
    if names:
        raise ValueError(
            f'Organization custom visual "{identifier}" not found. Available: {", ".join(names)}'
        )
    raise ValueError("No organization custom visuals configured.")


def _save_report(project: Project, report: dict) -> None:
    report.setdefault("$schema", REPORT_SCHEMA)
    _write_json(project.definition_folder / "report.json", report)
