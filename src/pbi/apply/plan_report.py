"""Report **Apply Plan** planner.

Pure-function side of the report apply path: ``plan_report_spec`` reads the
project's current ``report.json``, normalizes ``resourcePackages`` on both
sides (so legacy ``{"resourcePackage": {...}}`` wrappers don't survive a
no-op detection or appear as phantom diffs), merges each top-level spec
key with ``None``-means-delete semantics, and detects no-op. The plan it
returns is what the engine drives the **Apply Session** to persist (via
``session.write_report``) and what ``pbi diff`` uses to render a faithful
preview without touching disk.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pbi.project import Project
from pbi.resources import normalize_resource_packages
from pbi.schema_refs import REPORT_SCHEMA
from pbi.spec_merge import merge_spec_into


@dataclass(frozen=True)
class ReportApplyPlan:
    """The computed result of merging a report spec into the current report.

    ``payload`` is the merged ``report.json`` document to write.
    ``keys_touched`` is the count of top-level spec keys present, used for
    ``ApplyResult.properties_set`` accounting.
    """

    payload: dict[str, Any]
    keys_touched: int


def plan_report_spec(
    project: Project,
    report_spec: dict[str, Any],
) -> ReportApplyPlan | None:
    """Compute what writing ``report_spec`` would produce.

    Returns ``None`` for an empty spec or a spec that merges cleanly into the
    existing report without changing it (no-op). The ``$schema`` key is
    set on the payload if it was missing on the current report (matching
    what apply persists), but its addition alone is not enough to flip
    the no-op detector to a non-``None`` plan.
    """
    if not report_spec:
        return None

    current = copy.deepcopy(project.get_report_meta())
    current.setdefault("$schema", REPORT_SCHEMA)
    # Migrate legacy ``{"resourcePackage": {...}}`` wrapper shapes to the
    # published schema on the current snapshot so re-applies don't show a
    # phantom diff and ``pbi diff`` previews match what apply would write.
    normalize_resource_packages(current)
    before = copy.deepcopy(current)

    updated = copy.deepcopy(current)
    keys_touched = 0
    for key, value in report_spec.items():
        keys_touched += 1
        if value is None:
            updated.pop(key, None)
            continue
        normalized = _normalize_top_level_value(key, value)
        _merge_value(updated, key, normalized)

    if updated == before:
        return None

    return ReportApplyPlan(
        payload=updated,
        keys_touched=keys_touched,
    )


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
