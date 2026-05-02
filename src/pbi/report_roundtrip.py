"""Round-trip helpers for report-level YAML export/apply."""

from __future__ import annotations

import copy
from typing import Any

from pbi.spec_merge import merge_spec_into
from pbi.project import Project
from pbi.report_io import write_report_json
from pbi.resources import normalize_resource_packages
from pbi.schema_refs import REPORT_SCHEMA


def export_report_spec(project: Project) -> dict[str, Any]:
    """Export report-level metadata for YAML round-trip."""
    report = copy.deepcopy(project.get_report_meta())
    if not report:
        return {}
    report.pop("$schema", None)
    normalize_resource_packages(report)
    return report


def apply_report_spec(
    project: Project,
    report_spec: dict[str, Any],
    *,
    dry_run: bool = False,
) -> tuple[bool, int]:
    """Apply a report-level YAML section.

    Returns (changed, top_level_keys_touched).
    """
    report = copy.deepcopy(project.get_report_meta())
    report.setdefault("$schema", REPORT_SCHEMA)
    before = copy.deepcopy(report)
    touched = 0

    for key, value in report_spec.items():
        touched += 1
        if value is None:
            report.pop(key, None)
            continue
        normalized = _normalize_top_level_value(key, value)
        _merge_value(report, key, normalized)

    if report == before:
        return False, touched

    if not dry_run:
        write_report_json(project, report)
    return True, touched


def _merge_value(target: dict[str, Any], key: str, value: Any) -> None:
    current = target.get(key)
    if isinstance(current, dict) and isinstance(value, dict):
        merge_spec_into(current, value)
        return
    target[key] = copy.deepcopy(value)


def _normalize_top_level_value(key: str, value: Any) -> Any:
    if key == "resourcePackages":
        wrapper = {"resourcePackages": value}
        normalize_resource_packages(wrapper)
        return wrapper["resourcePackages"]
    return value
