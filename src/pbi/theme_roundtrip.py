"""Round-trip helpers for theme YAML export.

The apply side has moved to ``pbi.apply.plan_theme.plan_theme_spec`` (pure
planner) plus ``PbirApplySession.write_theme`` (the persistence half). This
module is now export-only.
"""

from __future__ import annotations

import copy
from typing import Any

from pbi.project import Project
from pbi.themes import get_theme_data


def export_theme_spec(project: Project) -> dict[str, Any]:
    """Export the active custom theme for YAML round-trip."""
    try:
        return copy.deepcopy(get_theme_data(project))
    except FileNotFoundError:
        return {}
