"""Visual grouping helpers."""

from __future__ import annotations

import secrets

from pbi.project import Page, Project, Visual, sanitize_visual_name
from pbi.schema_refs import VISUAL_CONTAINER_SCHEMA


def create_group(
    project: Project,
    page: Page,
    visuals: list[Visual],
    display_name: str | None = None,
) -> Visual:
    """Group visuals together and return the group container visual."""
    if len(visuals) < 2:
        raise ValueError("Need at least 2 visuals to group")

    for visual in visuals:
        if visual.data.get("parentGroupName"):
            raise ValueError(
                f'Visual "{visual.name}" is already in group '
                f'"{visual.data["parentGroupName"]}"'
            )
        if "visualGroup" in visual.data:
            raise ValueError(f'"{visual.name}" is a group container, not a visual')

    min_x = min(visual.position.get("x", 0) for visual in visuals)
    min_y = min(visual.position.get("y", 0) for visual in visuals)
    max_x = max(
        visual.position.get("x", 0) + visual.position.get("width", 0)
        for visual in visuals
    )
    max_y = max(
        visual.position.get("y", 0) + visual.position.get("height", 0)
        for visual in visuals
    )
    max_z = max(visual.position.get("z", 0) for visual in visuals)

    group_id = secrets.token_hex(10)
    group_dir = page.folder / "visuals" / group_id
    group_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_visual_name(display_name) if display_name else group_id
    group_data = {
        "$schema": VISUAL_CONTAINER_SCHEMA,
        "name": safe_name,
        "position": {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
            "z": max_z + 1,
            "tabOrder": 0,
        },
        "visualGroup": {
            "displayName": display_name or group_id,
            "groupMode": "ScaleMode",
            "objects": {},
        },
    }
    group_visual = Visual(folder=group_dir, data=group_data)
    group_visual.save()

    for visual in visuals:
        visual.data["parentGroupName"] = group_data["name"]
        visual.save()

    project.clear_caches()
    return group_visual


def create_group_container(
    project: Project,
    page: Page,
    *,
    name: str | None = None,
    display_name: str | None = None,
    x: int = 0,
    y: int = 0,
    width: int = 0,
    height: int = 0,
) -> Visual:
    """Create an empty visual group container."""
    existing = project.get_visuals(page)
    max_z = max((visual.position.get("z", 0) for visual in existing), default=0)
    group_id = secrets.token_hex(10)
    group_dir = page.folder / "visuals" / group_id
    group_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_visual_name(name) if name else group_id
    group_data = {
        "$schema": VISUAL_CONTAINER_SCHEMA,
        "name": safe_name,
        "position": {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "z": max_z + 1,
            "tabOrder": len(existing),
        },
        "visualGroup": {
            "displayName": display_name or safe_name,
            "groupMode": "ScaleMode",
            "objects": {},
        },
    }
    group_visual = Visual(folder=group_dir, data=group_data)
    group_visual.save()
    project.clear_caches()
    return group_visual


def ungroup(project: Project, page: Page, group: Visual) -> list[Visual]:
    """Ungroup a visual group and return the freed child visuals."""
    if "visualGroup" not in group.data:
        raise ValueError(f'"{group.name}" is not a group')

    group_name = group.name
    children = []
    for visual in project.get_visuals(page):
        if visual.data.get("parentGroupName") == group_name:
            visual.data.pop("parentGroupName", None)
            visual.save()
            children.append(visual)

    project.delete_visual(group)
    project.clear_caches()
    return children
