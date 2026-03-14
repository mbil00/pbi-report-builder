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
from pbi.schema_refs import BOOKMARK_SCHEMA, BOOKMARKS_METADATA_SCHEMA


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
        return _normalize_meta(_read_json(path))
    return {
        "$schema": BOOKMARKS_METADATA_SCHEMA,
        "items": [],
    }


def _save_meta(project: Project, meta: dict) -> None:
    path = _meta_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, _normalize_meta(meta))


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
    order = _bookmark_order(meta)
    if order:
        order_map = {name: i for i, name in enumerate(order)}
        result.sort(key=lambda b: order_map.get(b.name, 999))

    return result


def get_bookmark(project: Project, identifier: str) -> dict:
    """Get a bookmark's full data by name or display name."""
    data, _ = _find_bookmark_file(project, identifier)
    return data


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
                "display": {"mode": "hidden"},
            }

        if container_state:
            visual_containers[vis_name] = container_state

    # Build exploration state
    exploration_state: dict = {
        "version": "2.1",
        "activeSection": page.name,
        "sections": {
            page.name: {
                "visualContainers": visual_containers,
            },
        },
    }

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
    meta.setdefault("items", []).append({"name": bookmark_id})
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
        sections[active_section] = {"visualContainers": {}}

    section = sections.get(active_section, {})
    containers = section.setdefault("visualContainers", {})

    # Apply hidden
    if hidden_visuals:
        for vis_name in hidden_visuals:
            container = containers.setdefault(vis_name, {})
            single_visual = container.setdefault("singleVisual", {})
            single_visual["display"] = {"mode": "hidden"}

    # Apply visible (remove hidden state)
    if visible_visuals:
        for vis_name in visible_visuals:
            container = containers.get(vis_name)
            if not isinstance(container, dict):
                continue
            single_visual = container.get("singleVisual")
            if isinstance(single_visual, dict):
                single_visual.pop("display", None)
                if not single_visual:
                    container.pop("singleVisual", None)
            if not container:
                containers.pop(vis_name, None)

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
    meta["items"] = _remove_bookmark_from_meta(meta.get("items", []), bm_name)
    _save_meta(project, meta)

    return display_name


def _find_bookmark_file(project: Project, identifier: str) -> tuple[dict, Path]:
    """Find a bookmark file by name or display name. Returns (data, path)."""
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        raise FileNotFoundError("No bookmarks directory found")

    exact_matches: list[tuple[dict, Path]] = []
    partial_matches: list[tuple[dict, Path]] = []
    for f in bm_dir.glob("*.bookmark.json"):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        bm_name = data.get("name", "")
        display = data.get("displayName", "")
        if bm_name == identifier or display == identifier:
            exact_matches.append((data, f))
            continue
        if identifier.lower() in display.lower() or identifier.lower() in bm_name.lower():
            partial_matches.append((data, f))

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        matches = ", ".join(
            candidate.get("displayName") or candidate.get("name", "")
            for candidate, _ in exact_matches
        )
        raise ValueError(f'Ambiguous bookmark "{identifier}". Matches: {matches}')
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        matches = ", ".join(
            candidate.get("displayName") or candidate.get("name", "")
            for candidate, _ in partial_matches
        )
        raise ValueError(f'Ambiguous bookmark "{identifier}". Matches: {matches}')

    raise FileNotFoundError(f'Bookmark "{identifier}" not found')


def _normalize_meta(meta: dict) -> dict:
    """Normalize bookmarks metadata to the published schema shape."""
    if isinstance(meta.get("items"), list):
        meta["$schema"] = BOOKMARKS_METADATA_SCHEMA
        return meta

    items = []
    for name in meta.get("bookmarkOrder", []):
        if isinstance(name, str):
            items.append({"name": name})
    return {
        "$schema": BOOKMARKS_METADATA_SCHEMA,
        "items": items,
    }


def _bookmark_order(meta: dict) -> list[str]:
    """Flatten standalone bookmarks and grouped bookmarks into display order."""
    order: list[str] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if isinstance(children, list):
            order.extend(child for child in children if isinstance(child, str))
            continue
        name = item.get("name")
        if isinstance(name, str):
            order.append(name)
    return order


def _remove_bookmark_from_meta(items: list[dict], bookmark_name: str) -> list[dict]:
    """Remove a bookmark reference from bookmarks metadata."""
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") == bookmark_name and "children" not in item:
            continue
        if "children" in item:
            children = [
                child for child in item.get("children", [])
                if child != bookmark_name
            ]
            if not children:
                continue
            updated = dict(item)
            updated["children"] = children
            result.append(updated)
            continue
        result.append(item)
    return result
