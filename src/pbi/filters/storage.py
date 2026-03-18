from __future__ import annotations

from typing import Any

from pbi.project import Project, _read_json, _write_json


def load_level_data(
    project: Project,
    page_name: str | None = None,
    visual_name: str | None = None,
) -> tuple[dict, str, Any]:
    """Load the JSON data for the specified filter level."""
    if visual_name and page_name:
        page = project.find_page(page_name)
        visual = project.find_visual(page, visual_name)
        return visual.data, "visual", visual
    if page_name:
        page = project.find_page(page_name)
        return page.data, "page", page

    path = project.definition_folder / "report.json"
    data = _read_json(path) if path.exists() else {}
    return data, "report", path


def save_level_data(data: dict, save_target: Any) -> None:
    """Save data back to the appropriate level."""
    if hasattr(save_target, "save"):
        save_target.data = data
        save_target.save()
        return

    _write_json(save_target, data)
