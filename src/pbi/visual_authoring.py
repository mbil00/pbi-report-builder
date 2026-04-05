"""Visual authoring helpers."""

from __future__ import annotations

import secrets
import shutil

from pbi.project import Page, Project, Visual, sanitize_visual_name, _read_json, _write_json
from pbi.schema_refs import VISUAL_CONTAINER_SCHEMA


def create_visual(
    project: Project,
    page: Page,
    visual_type: str,
    x: int = 0,
    y: int = 0,
    width: int = 300,
    height: int = 200,
) -> Visual:
    """Create a new visual on a page with type-aware scaffolding."""
    from pbi.roles import get_visual_roles

    visual_id = secrets.token_hex(10)
    visual_dir = page.folder / "visuals" / visual_id
    visual_dir.mkdir(parents=True, exist_ok=True)

    existing = project._get_visuals_cached(page)
    max_z = max((visual.position.get("z", 0) for visual in existing), default=0)

    roles = get_visual_roles(visual_type)
    query_state: dict = {}
    for role in roles:
        query_state[role["name"]] = {"projections": []}

    data = {
        "$schema": VISUAL_CONTAINER_SCHEMA,
        "name": visual_id,
        "position": {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "z": max_z + 1000,
            "tabOrder": len(existing),
        },
        "visual": {
            "visualType": visual_type,
            "query": {"queryState": query_state},
            "objects": {},
        },
    }
    _write_json(visual_dir / "visual.json", data)
    visual = Visual(folder=visual_dir, data=data)
    existing.append(visual)
    existing.sort(
        key=lambda candidate: (
            candidate.position.get("y", 0),
            candidate.position.get("x", 0),
        )
    )
    return visual


def copy_visual(
    project: Project,
    source: Visual,
    target_page: Page,
    new_name: str | None = None,
) -> Visual:
    """Copy a visual, optionally to a different page."""
    new_id = secrets.token_hex(10)
    new_dir = target_page.folder / "visuals" / new_id
    shutil.copytree(source.folder, new_dir)

    new_data = _read_json(new_dir / "visual.json")
    new_data["name"] = sanitize_visual_name(new_name) if new_name else new_id
    _write_json(new_dir / "visual.json", new_data)
    project._invalidate_visuals_cache(target_page)
    return Visual(folder=new_dir, data=new_data)


def delete_visual(project: Project, visual: Visual) -> None:
    """Delete a visual."""
    page_path = visual.folder.parent.parent
    project._invalidate_visuals_cache(page_path)

    if "visualGroup" in visual.data:
        page = next(
            (candidate for candidate in project.get_pages() if candidate.folder == page_path),
            None,
        )
        if page is None:
            page_json = page_path / "page.json"
            if page_json.exists():
                page = Page(folder=page_path, data=_read_json(page_json))
        visuals = project._get_visuals_cached(page) if page is not None else []
        for candidate in visuals:
            if candidate.data.get("parentGroupName") == visual.name:
                candidate.data.pop("parentGroupName", None)
                candidate.save()

    shutil.rmtree(visual.folder)
