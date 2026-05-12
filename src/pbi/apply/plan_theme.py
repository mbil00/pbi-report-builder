"""Theme **Apply Plan** planner.

Pure-function side of the theme apply path: ``plan_theme_spec`` reads the
project's current theme JSON, merges the spec, defaults the theme name, and
detects no-op. The plan it returns is what the engine drives the **Apply
Session** to persist (via ``session.write_theme``) and what ``pbi diff`` uses
to render a faithful preview without touching disk.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pbi.project import Project
from pbi.spec_merge import merge_spec_into
from pbi.themes import get_theme_data


@dataclass(frozen=True)
class ThemeApplyPlan:
    """The computed result of merging a theme spec into the current theme.

    ``payload`` is the merged theme JSON to write. ``first_time`` is true
    when no theme document existed before this apply (the engine routes the
    write through ``apply_theme`` instead of ``save_theme_data``).
    ``keys_touched`` is the count of top-level spec keys present, used for
    ``ApplyResult.properties_set`` accounting.
    """

    payload: dict[str, Any]
    first_time: bool
    keys_touched: int


def plan_theme_spec(
    project: Project,
    theme_spec: dict[str, Any],
) -> ThemeApplyPlan | None:
    """Compute what writing ``theme_spec`` would produce.

    Returns ``None`` for an empty spec or a spec that merges cleanly into the
    existing theme without changing it (no-op).
    """
    if not theme_spec:
        return None

    try:
        current = copy.deepcopy(get_theme_data(project))
        had_theme = True
    except FileNotFoundError:
        current = {}
        had_theme = False

    updated = copy.deepcopy(current)
    keys_touched = 0
    for key, value in theme_spec.items():
        keys_touched += 1
        if value is None:
            updated.pop(key, None)
            continue
        if isinstance(updated.get(key), dict) and isinstance(value, dict):
            merge_spec_into(updated[key], value)
        else:
            updated[key] = copy.deepcopy(value)

    if had_theme and updated == current:
        return None

    if (
        "name" not in updated
        or not isinstance(updated["name"], str)
        or not updated["name"].strip()
    ):
        existing_name = current.get("name")
        if isinstance(existing_name, str) and existing_name.strip():
            updated["name"] = existing_name
        else:
            updated["name"] = "Custom Theme"

    return ThemeApplyPlan(
        payload=updated,
        first_time=not had_theme,
        keys_touched=keys_touched,
    )
