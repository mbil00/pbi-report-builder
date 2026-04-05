"""Helpers for report-level metadata editing."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from pbi.project import Project
from pbi.properties import REPORT_PROPERTIES, get_property, set_property
from pbi.report_io import read_report_json, write_report_json
from pbi.resources import normalize_resource_packages
from pbi.schema_refs import REPORT_SCHEMA

REPORT_OBJECT_KEYS = (
    "annotations",
    "filterConfig",
    "objects",
    "organizationCustomVisuals",
    "resourcePackages",
    "settings",
    "themeCollection",
)


@dataclass(frozen=True)
class ReportPropertyChange:
    prop: str
    old: object
    new: object
    changed: bool


@dataclass(frozen=True)
class ReportAnnotationInfo:
    name: str
    value: str


@dataclass(frozen=True)
class ReportAnnotationUpdate:
    annotation: ReportAnnotationInfo
    created: bool
    changed: bool
    old_value: str | None


@dataclass(frozen=True)
class ReportObjectInfo:
    name: str
    present: bool
    value_type: str
    size: int


def set_report_properties(
    project: Project,
    assignments: list[tuple[str, str]],
) -> list[ReportPropertyChange]:
    report = _read_report(project, ensure_schema=True)
    report.setdefault("layoutOptimization", "None")
    report.setdefault("themeCollection", {})

    changes: list[ReportPropertyChange] = []
    for prop, value in assignments:
        old = get_property(report, prop, REPORT_PROPERTIES)
        try:
            set_property(report, prop, value, REPORT_PROPERTIES)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_property(report, prop, REPORT_PROPERTIES)
        changes.append(
            ReportPropertyChange(
                prop=prop,
                old=old,
                new=new,
                changed=str(old) != str(new),
            )
        )

    if any(change.changed for change in changes):
        _write_report(project, report)
    return changes


def list_report_annotations(project: Project) -> list[ReportAnnotationInfo]:
    return _annotation_rows(project.get_report_meta())


def get_report_annotation(project: Project, identifier: str) -> ReportAnnotationInfo:
    return _find_annotation(project.get_report_meta(), identifier)


def set_report_annotation(project: Project, name: str, value: str) -> ReportAnnotationUpdate:
    report = _read_report(project, ensure_schema=True)
    annotations = report.setdefault("annotations", [])
    if not isinstance(annotations, list):
        raise ValueError("report.annotations is not an array.")

    lowered = name.lower()
    for entry in annotations:
        if isinstance(entry, dict) and str(entry.get("name", "")).lower() == lowered:
            old = str(entry.get("value", ""))
            changed = old != value
            if changed:
                entry["name"] = name
                entry["value"] = value
                _write_report(project, report)
            return ReportAnnotationUpdate(
                annotation=ReportAnnotationInfo(name=name, value=value),
                created=False,
                changed=changed,
                old_value=old,
            )

    annotations.append({"name": name, "value": value})
    _write_report(project, report)
    return ReportAnnotationUpdate(
        annotation=ReportAnnotationInfo(name=name, value=value),
        created=True,
        changed=True,
        old_value=None,
    )


def delete_report_annotation(project: Project, identifier: str) -> ReportAnnotationInfo:
    report = project.get_report_meta()
    annotations = report.get("annotations", [])
    if not isinstance(annotations, list):
        raise ValueError("No annotations defined. Use `pbi report annotation set` to add one.")

    target = _find_annotation(report, identifier)
    annotations[:] = [
        entry
        for entry in annotations
        if not (
            isinstance(entry, dict)
            and str(entry.get("name", "")).lower() == target.name.lower()
            and str(entry.get("value", "")) == target.value
        )
    ]
    if not annotations:
        report.pop("annotations", None)
    _write_report(project, report)
    return target


def list_report_objects(project: Project) -> list[ReportObjectInfo]:
    report = project.get_report_meta()
    rows: list[ReportObjectInfo] = []
    for name in REPORT_OBJECT_KEYS:
        value = report.get(name)
        present = isinstance(value, (dict, list))
        rows.append(
            ReportObjectInfo(
                name=name,
                present=present,
                value_type="array" if isinstance(value, list) else ("object" if isinstance(value, dict) else ""),
                size=len(value) if isinstance(value, (dict, list)) else 0,
            )
        )
    return rows


def get_report_object(project: Project, identifier: str) -> tuple[str, object]:
    report = project.get_report_meta()
    key = resolve_report_object_key(identifier)
    return key, report.get(key)


def set_report_object(project: Project, identifier: str, value: object) -> tuple[str, bool]:
    report = _read_report(project, ensure_schema=True)
    key = resolve_report_object_key(identifier)
    normalized = normalize_report_object_value(key, value)

    if report.get(key) == normalized:
        return key, False

    report[key] = normalized
    _write_report(project, report)
    return key, True


def clear_report_object(project: Project, identifier: str) -> tuple[str, bool]:
    report = project.get_report_meta()
    key = resolve_report_object_key(identifier)
    if key not in report:
        return key, False

    report.pop(key, None)
    _write_report(project, report)
    return key, True


def get_report_data_source_variables(project: Project) -> str | None:
    value = project.get_report_meta().get("dataSourceVariables")
    return value if isinstance(value, str) and value else None


def set_report_data_source_variables(project: Project, payload: str) -> bool:
    report = _read_report(project, ensure_schema=True)
    if report.get("dataSourceVariables") == payload:
        return False

    report["dataSourceVariables"] = payload
    _write_report(project, report)
    return True


def clear_report_data_source_variables(project: Project) -> bool:
    report = project.get_report_meta()
    if "dataSourceVariables" not in report:
        return False

    report.pop("dataSourceVariables", None)
    _write_report(project, report)
    return True


def resolve_report_object_key(name: str) -> str:
    lowered = name.lower()
    for key in REPORT_OBJECT_KEYS:
        if key.lower() == lowered:
            return key
    matches = difflib.get_close_matches(name, REPORT_OBJECT_KEYS, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'Unknown report object "{name}". Did you mean: {", ".join(matches)}?')
    raise ValueError(f'Unknown report object "{name}". Available: {", ".join(REPORT_OBJECT_KEYS)}')


def normalize_report_object_value(key: str, value: object) -> object:
    if not isinstance(value, (dict, list)):
        raise ValueError("Report objects must be JSON objects or arrays.")
    if key == "resourcePackages":
        wrapper = {"resourcePackages": value}
        normalize_resource_packages(wrapper)
        return wrapper["resourcePackages"]
    return value


def _annotation_rows(report: dict) -> list[ReportAnnotationInfo]:
    annotations = report.get("annotations", [])
    if not isinstance(annotations, list):
        return []

    rows: list[ReportAnnotationInfo] = []
    for entry in annotations:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if isinstance(name, str) and isinstance(value, str):
            rows.append(ReportAnnotationInfo(name=name, value=value))
    return rows


def _find_annotation(report: dict, identifier: str) -> ReportAnnotationInfo:
    rows = _annotation_rows(report)
    lowered = identifier.lower()

    for entry in rows:
        if entry.name.lower() == lowered:
            return entry

    names = [entry.name for entry in rows]
    matches = difflib.get_close_matches(identifier, names, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'Annotation "{identifier}" not found. Did you mean: {", ".join(matches)}?')
    if names:
        raise ValueError(f'Annotation "{identifier}" not found. Available: {", ".join(names)}')
    raise ValueError("No annotations defined. Use `pbi report annotation set` to add one.")


def _read_report(project: Project, *, ensure_schema: bool = False) -> dict:
    return read_report_json(project, ensure_schema=ensure_schema)


def _write_report(project: Project, report: dict) -> None:
    report.setdefault("$schema", REPORT_SCHEMA)
    write_report_json(project, report)
