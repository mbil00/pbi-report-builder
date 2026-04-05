"""Shared report.json I/O helpers."""

from __future__ import annotations

from pbi.project import Project, _write_json
from pbi.resources import normalize_resource_packages
from pbi.schema_refs import REPORT_SCHEMA


def read_report_json(
    project: Project,
    *,
    ensure_schema: bool = False,
    normalize_resources_flag: bool = False,
) -> dict:
    """Read report.json through the project abstraction."""
    report = project.get_report_meta()
    if ensure_schema:
        report.setdefault("$schema", REPORT_SCHEMA)
    if normalize_resources_flag:
        normalize_resource_packages(report)
    return report


def write_report_json(project: Project, report: dict) -> None:
    """Persist report.json using the shared JSON writer."""
    _write_json(project.definition_folder / "report.json", report)
