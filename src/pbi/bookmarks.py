"""Bookmark management for PBIR reports.

Bookmarks capture page state (active section, visual visibility/display states,
filters) as snapshots that can be restored. Stored as individual JSON files in
definition/bookmarks/.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from pbi.project import Project, Page, Visual, _read_json, _write_json


BOOKMARK_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json"
BOOKMARKS_META_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarkMetadata/1.0.0/schema.json"


@dataclass
class BookmarkInfo:
    """Summary of a bookmark for listing."""

    name: str
    display_name: str
    active_section: str
    file: str
    target_visuals: list[str] = field(default_factory=list)
    suppress_data: bool = False
    suppress_display: bool = False


def _bookmarks_dir(project: Project) -> Path:
    return project.definition_folder / "bookmarks"


def _meta_path(project: Project) -> Path:
    return _bookmarks_dir(project) / "bookmarks.json"


def _load_meta(project: Project) -> dict:
    path = _meta_path(project)
    if path.exists():
        return _read_json(path)
    return {
        "$schema": BOOKMARKS_META_SCHEMA,
        "bookmarkOrder": [],
    }


def _save_meta(project: Project, meta: dict) -> None:
    path = _meta_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, meta)


def list_bookmarks(project: Project) -> list[BookmarkInfo]:
    """List all bookmarks in the project."""
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        return []

    result = []
    for f in sorted(bm_dir.glob("*.bookmark.json")):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        exploration = data.get("explorationState", {})
        options = data.get("options", {})

        result.append(BookmarkInfo(
            name=data.get("name", f.stem.replace(".bookmark", "")),
            display_name=data.get("displayName", ""),
            active_section=exploration.get("activeSection", ""),
            file=f.name,
            target_visuals=options.get("targetVisualNames", []),
            suppress_data=options.get("suppressData", False),
            suppress_display=options.get("suppressDisplay", False),
        ))

    # Sort by bookmark order if available
    meta = _load_meta(project)
    order = meta.get("bookmarkOrder", [])
    if order:
        order_map = {name: i for i, name in enumerate(order)}
        result.sort(key=lambda b: order_map.get(b.name, 999))

    return result


def get_bookmark(project: Project, identifier: str) -> dict:
    """Get a bookmark's full data by name or display name."""
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        raise FileNotFoundError("No bookmarks directory found")

    # Try exact file match first
    for f in bm_dir.glob("*.bookmark.json"):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        bm_name = data.get("name", "")
        display = data.get("displayName", "")
        if bm_name == identifier or display == identifier:
            return data
        if identifier.lower() in display.lower() or identifier.lower() in bm_name.lower():
            return data

    raise FileNotFoundError(f'Bookmark "{identifier}" not found')


def create_bookmark(
    project: Project,
    display_name: str,
    page: Page,
    visuals: list[Visual],
    *,
    hidden_visuals: list[str] | None = None,
    target_visuals: list[str] | None = None,
    suppress_data: bool = False,
    suppress_display: bool = False,
    suppress_active_section: bool = False,
) -> dict:
    """Create a new bookmark capturing page state.

    Args:
        project: The PBIP project.
        display_name: Human-readable bookmark name.
        page: The active page for this bookmark.
        visuals: All visuals on the page (used to capture states).
        hidden_visuals: List of visual names to mark as hidden in the bookmark.
        target_visuals: If set, bookmark applies only to these visuals.
        suppress_data: If True, bookmark does not capture data/filter state.
        suppress_display: If True, bookmark does not capture display state.
        suppress_active_section: If True, bookmark does not switch pages.

    Returns:
        The created bookmark data dict.
    """
    bm_dir = _bookmarks_dir(project)
    bm_dir.mkdir(parents=True, exist_ok=True)

    bookmark_id = secrets.token_hex(10)
    hidden_set = set(hidden_visuals or [])

    # Build visual container states
    visual_containers: dict = {}
    for vis in visuals:
        vis_name = vis.name
        container_state: dict = {}

        if vis_name in hidden_set:
            container_state["singleVisual"] = {
                "displayState": {"mode": "hidden"},
            }

        if container_state:
            visual_containers[vis_name] = container_state

    # Build exploration state
    exploration_state: dict = {
        "version": "2.1",
        "activeSection": page.name,
        "sections": {
            page.name: {},
        },
    }

    if visual_containers:
        exploration_state["sections"][page.name]["visualContainers"] = visual_containers

    # Build options
    options: dict = {}
    if suppress_active_section:
        options["suppressActiveSection"] = True
    if suppress_data:
        options["suppressData"] = True
    if suppress_display:
        options["suppressDisplay"] = True
    if target_visuals:
        options["applyOnlyToTargetVisuals"] = True
        options["targetVisualNames"] = list(target_visuals)

    data = {
        "$schema": BOOKMARK_SCHEMA,
        "displayName": display_name,
        "name": bookmark_id,
        "explorationState": exploration_state,
    }

    if options:
        data["options"] = options

    # Write bookmark file
    file_path = bm_dir / f"{bookmark_id}.bookmark.json"
    _write_json(file_path, data)

    # Update metadata
    meta = _load_meta(project)
    meta.setdefault("bookmarkOrder", []).append(bookmark_id)
    _save_meta(project, meta)

    return data


def update_bookmark_visuals(
    project: Project,
    identifier: str,
    *,
    hidden_visuals: list[str] | None = None,
    visible_visuals: list[str] | None = None,
) -> dict:
    """Update which visuals are hidden/visible in a bookmark.

    Args:
        project: The PBIP project.
        identifier: Bookmark name or display name.
        hidden_visuals: Visual names to set as hidden.
        visible_visuals: Visual names to set as visible (remove hidden state).

    Returns:
        Updated bookmark data.
    """
    data, file_path = _find_bookmark_file(project, identifier)

    # Get or create the sections
    exploration = data.setdefault("explorationState", {})
    sections = exploration.setdefault("sections", {})
    active_section = exploration.get("activeSection", "")

    if active_section and active_section not in sections:
        sections[active_section] = {}

    section = sections.get(active_section, {})
    containers = section.setdefault("visualContainers", {})

    # Apply hidden
    if hidden_visuals:
        for vis_name in hidden_visuals:
            containers[vis_name] = {
                "singleVisual": {
                    "displayState": {"mode": "hidden"},
                },
            }

    # Apply visible (remove hidden state)
    if visible_visuals:
        for vis_name in visible_visuals:
            if vis_name in containers:
                del containers[vis_name]

    # Clean up empty structures
    if not containers:
        section.pop("visualContainers", None)

    if active_section:
        sections[active_section] = section

    _write_json(file_path, data)
    return data


def delete_bookmark(project: Project, identifier: str) -> str:
    """Delete a bookmark. Returns its display name."""
    data, file_path = _find_bookmark_file(project, identifier)
    display_name = data.get("displayName", identifier)
    bm_name = data.get("name", "")

    file_path.unlink()

    # Update metadata
    meta = _load_meta(project)
    order = meta.get("bookmarkOrder", [])
    if bm_name in order:
        order.remove(bm_name)
        meta["bookmarkOrder"] = order
    _save_meta(project, meta)

    return display_name


def _find_bookmark_file(project: Project, identifier: str) -> tuple[dict, Path]:
    """Find a bookmark file by name or display name. Returns (data, path)."""
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        raise FileNotFoundError("No bookmarks directory found")

    # Exact match first
    for f in bm_dir.glob("*.bookmark.json"):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        bm_name = data.get("name", "")
        display = data.get("displayName", "")
        if bm_name == identifier or display == identifier:
            return data, f

    # Partial match
    for f in bm_dir.glob("*.bookmark.json"):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        bm_name = data.get("name", "")
        display = data.get("displayName", "")
        if identifier.lower() in display.lower() or identifier.lower() in bm_name.lower():
            return data, f

    raise FileNotFoundError(f'Bookmark "{identifier}" not found')
