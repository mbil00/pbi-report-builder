"""Page authoring helpers."""

from __future__ import annotations

import secrets
import shutil

from pbi.project import Page, Project, _read_json, _write_json
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA


def create_page(
    project: Project,
    display_name: str,
    width: int = 1280,
    height: int = 720,
    display_option: str = "FitToPage",
) -> Page:
    """Create a new page."""
    page_id = secrets.token_hex(10)
    page_dir = project.definition_folder / "pages" / page_id
    page_dir.mkdir(parents=True)
    (page_dir / "visuals").mkdir()

    data = {
        "$schema": PAGE_SCHEMA,
        "name": page_id,
        "displayName": display_name,
        "displayOption": display_option,
        "width": width,
        "height": height,
        "visibility": "AlwaysVisible",
    }
    _write_json(page_dir / "page.json", data)
    add_page_to_order(project, page_id)
    page = Page(folder=page_dir, data=data)
    project._visuals_cache[page_dir] = []
    return page


def copy_page(project: Project, source: Page, new_name: str) -> Page:
    """Deep-copy a page and all its visuals."""
    new_id = secrets.token_hex(10)
    new_dir = project.definition_folder / "pages" / new_id
    shutil.copytree(source.folder, new_dir)

    new_data = _read_json(new_dir / "page.json")
    new_data["name"] = new_id
    new_data["displayName"] = new_name
    _write_json(new_dir / "page.json", new_data)

    visuals_dir = new_dir / "visuals"
    if visuals_dir.exists():
        for visual_dir in list(visuals_dir.iterdir()):
            if not visual_dir.is_dir():
                continue
            new_visual_id = secrets.token_hex(10)
            new_visual_dir = visuals_dir / new_visual_id
            visual_dir.rename(new_visual_dir)
            visual_json = new_visual_dir / "visual.json"
            if not visual_json.exists():
                continue
            visual_data = _read_json(visual_json)
            old_name = visual_data.get("name", "")
            old_folder = visual_dir.name
            if old_name == old_folder:
                visual_data["name"] = new_visual_id
            _write_json(visual_json, visual_data)

    add_page_to_order(project, new_id)
    project._invalidate_visuals_cache(new_dir)
    return Page(folder=new_dir, data=new_data)


def delete_page(project: Project, page: Page) -> None:
    """Delete a page and all its visuals."""
    shutil.rmtree(page.folder)
    project._invalidate_visuals_cache(page)
    remove_page_from_order(project, page.name)


def add_page_to_order(project: Project, page_id: str) -> None:
    """Append a page folder ID to the report page order metadata."""
    meta_path = project.definition_folder / "pages" / "pages.json"
    if meta_path.exists():
        meta = _read_json(meta_path)
    else:
        meta = {"$schema": PAGES_METADATA_SCHEMA}
    meta.setdefault("pageOrder", []).append(page_id)
    _write_json(meta_path, meta)
    project._invalidate_pages_cache()


def remove_page_from_order(project: Project, page_id: str) -> None:
    """Remove a page folder ID from the report page order metadata."""
    meta_path = project.definition_folder / "pages" / "pages.json"
    if not meta_path.exists():
        return

    meta = _read_json(meta_path)
    order = meta.get("pageOrder", [])
    if page_id in order:
        order.remove(page_id)
        meta["pageOrder"] = order
    if meta.get("activePageName") == page_id and order:
        meta["activePageName"] = order[0]
    _write_json(meta_path, meta)
    project._invalidate_pages_cache()


def set_page_order(project: Project, page_ids: list[str]) -> None:
    """Overwrite the page order with a new sequence of page folder IDs."""
    meta_path = project.definition_folder / "pages" / "pages.json"
    meta = (
        _read_json(meta_path)
        if meta_path.exists()
        else {"$schema": PAGES_METADATA_SCHEMA}
    )
    meta["pageOrder"] = page_ids
    _write_json(meta_path, meta)
    project._invalidate_pages_cache()


def set_active_page(project: Project, page_id: str) -> None:
    """Set the active page by folder ID."""
    meta_path = project.definition_folder / "pages" / "pages.json"
    meta = (
        _read_json(meta_path)
        if meta_path.exists()
        else {"$schema": PAGES_METADATA_SCHEMA}
    )
    meta["activePageName"] = page_id
    _write_json(meta_path, meta)
