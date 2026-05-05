"""Round-trip helpers for report-level YAML export.

The ``report:`` apply path lives in ``pbi.apply.plan_report`` (pure-function
planner) plus ``PbirApplySession.write_report`` (persistence). This module is
export-only.
"""

from __future__ import annotations

import copy
from typing import Any

from pbi.project import Project
from pbi.resources import normalize_resource_packages


def export_report_spec(project: Project) -> dict[str, Any]:
    """Export report-level metadata for YAML round-trip."""
    report = copy.deepcopy(project.get_report_meta())
    if not report:
        return {}
    report.pop("$schema", None)
    normalize_resource_packages(report)
    return report
