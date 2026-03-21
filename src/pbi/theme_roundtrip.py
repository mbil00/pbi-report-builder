"""Round-trip helpers for theme YAML export/apply."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

from pbi.project import Project
from pbi.themes import apply_theme, get_theme_data, save_theme_data


def export_theme_spec(project: Project) -> dict[str, Any]:
    """Export the active custom theme for YAML round-trip."""
    try:
        return copy.deepcopy(get_theme_data(project))
    except FileNotFoundError:
        return {}


def apply_theme_spec(
    project: Project,
    theme_spec: dict[str, Any],
    *,
    dry_run: bool = False,
) -> tuple[bool, int]:
    """Apply a theme YAML section.

    Returns (changed, top_level_keys_touched).
    """
    if not theme_spec:
        return False, 0

    try:
        current = copy.deepcopy(get_theme_data(project))
        had_theme = True
    except FileNotFoundError:
        current = {}
        had_theme = False

    updated = copy.deepcopy(current)
    touched = 0
    for key, value in theme_spec.items():
        touched += 1
        if value is None:
            updated.pop(key, None)
            continue
        if isinstance(updated.get(key), dict) and isinstance(value, dict):
            _merge_dict(updated[key], value)
        else:
            updated[key] = copy.deepcopy(value)

    if updated == current and had_theme:
        return False, touched

    if "name" not in updated or not isinstance(updated["name"], str) or not updated["name"].strip():
        updated["name"] = (
            current.get("name")
            if isinstance(current.get("name"), str) and current.get("name", "").strip()
            else "Custom Theme"
        )

    if not dry_run:
        if had_theme:
            save_theme_data(project, updated)
        else:
            _apply_new_theme(project, updated)

    return True, touched


def _merge_dict(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if value is None:
            target.pop(key, None)
            continue
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            _merge_dict(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _apply_new_theme(project: Project, data: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        tmp_path = Path(handle.name)

    try:
        apply_theme(project, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
