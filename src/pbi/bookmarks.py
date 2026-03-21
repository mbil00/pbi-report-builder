"""Bookmark management for PBIR reports.

Bookmarks capture page state (active section, visual visibility/display states,
filters) as snapshots that can be restored. Stored as individual JSON files in
definition/bookmarks/.
"""

from __future__ import annotations

import copy
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
    group: str | None = None
    hidden_visuals: int = 0
    sort_states: int = 0
    filter_states: int = 0
    projection_states: int = 0
    object_states: int = 0


@dataclass(frozen=True)
class BookmarkGroupInfo:
    """Summary of a bookmark group in bookmarks.json metadata."""

    name: str
    children: list[str] = field(default_factory=list)


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

    meta = _load_meta(project)
    order = _bookmark_order(meta)
    group_lookup = _bookmark_group_lookup(meta)

    result = []
    for f in sorted(bm_dir.glob("*.bookmark.json")):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        exploration = data.get("explorationState", {})
        options = data.get("options", {})
        summary = summarize_bookmark_state(data)

        result.append(BookmarkInfo(
            name=data.get("name", f.stem.replace(".bookmark", "")),
            display_name=data.get("displayName", ""),
            active_section=exploration.get("activeSection", ""),
            file=f.name,
            target_visuals=options.get("targetVisualNames", []),
            suppress_data=options.get("suppressData", False),
            suppress_display=options.get("suppressDisplay", False),
            group=group_lookup.get(data.get("name", "")),
            hidden_visuals=summary["hiddenVisuals"],
            sort_states=summary["sortStates"],
            filter_states=summary["filterStates"],
            projection_states=summary["projectionStates"],
            object_states=summary["objectStates"],
        ))

    # Sort by bookmark order if available
    if order:
        order_map = {name: i for i, name in enumerate(order)}
        result.sort(key=lambda b: order_map.get(b.name, 999))

    return result


def list_bookmark_groups(project: Project) -> list[BookmarkGroupInfo]:
    """List bookmark groups defined in bookmarks metadata."""
    meta = _load_meta(project)
    groups: list[BookmarkGroupInfo] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if not isinstance(children, list):
            continue
        name = item.get("displayName") or item.get("name")
        if not isinstance(name, str) or not name:
            continue
        groups.append(
            BookmarkGroupInfo(
                name=name,
                children=[child for child in children if isinstance(child, str)],
            )
        )
    return groups


def get_bookmark(project: Project, identifier: str) -> dict:
    """Get a bookmark's full data by name or display name."""
    data, _ = _find_bookmark_file(project, identifier)
    return data


def normalize_bookmark_state(project: Project, state: dict) -> dict:
    """Normalize bookmark state page references from display names to folder ids."""
    normalized = copy.deepcopy(state)
    active_section = normalized.get("activeSection")
    if isinstance(active_section, str):
        try:
            normalized["activeSection"] = project.find_page(active_section).name
        except ValueError:
            pass

    sections = normalized.get("sections")
    if isinstance(sections, dict):
        remapped: dict[str, object] = {}
        for section_ref, section_state in sections.items():
            remapped_key = section_ref
            if isinstance(section_ref, str):
                try:
                    remapped_key = project.find_page(section_ref).name
                except ValueError:
                    remapped_key = section_ref
            remapped[remapped_key] = section_state
        normalized["sections"] = remapped

    return normalized


def summarize_bookmark_state(data: dict) -> dict[str, int]:
    """Summarize the kinds of state captured in a bookmark."""
    summary = {
        "sections": 0,
        "visualStates": 0,
        "hiddenVisuals": 0,
        "sortStates": 0,
        "filterStates": 0,
        "projectionStates": 0,
        "objectStates": 0,
    }
    exploration = data.get("explorationState", {})
    sections = exploration.get("sections", {})
    if not isinstance(sections, dict):
        return summary

    for section_state in sections.values():
        if not isinstance(section_state, dict):
            continue
        summary["sections"] += 1
        if any(key in section_state for key in ("filters", "filterConfig")):
            summary["filterStates"] += 1
        containers = section_state.get("visualContainers", {})
        if not isinstance(containers, dict):
            continue
        for visual_state in containers.values():
            if not isinstance(visual_state, dict):
                continue
            if visual_state:
                summary["visualStates"] += 1
            if "orderBy" in visual_state:
                summary["sortStates"] += 1
            if any(key in visual_state for key in ("filters", "filterConfig")):
                summary["filterStates"] += 1
            single_visual = visual_state.get("singleVisual", {})
            if not isinstance(single_visual, dict):
                continue
            display = single_visual.get("display", {})
            if isinstance(display, dict) and display.get("mode") == "hidden":
                summary["hiddenVisuals"] += 1
            if "objects" in single_visual:
                summary["objectStates"] += 1
            if any(key in single_visual for key in ("projections", "prototypeQuery", "projectionOrdering")):
                summary["projectionStates"] += 1

    return summary


def describe_bookmark_state(data: dict) -> list[tuple[str, str]]:
    """Return human-readable bookmark state rows for CLI inspection."""
    rows: list[tuple[str, str]] = []
    exploration = data.get("explorationState", {})
    sections = exploration.get("sections", {})
    if not isinstance(sections, dict):
        return rows

    for section_name, section_state in sections.items():
        if not isinstance(section_state, dict):
            continue
        if "filters" in section_state:
            rows.append((f"[dim]{section_name}[/dim] filters", f"{len(section_state['filters'])} item(s)"))
        if "filterConfig" in section_state:
            filters = section_state["filterConfig"].get("filters", []) if isinstance(section_state["filterConfig"], dict) else []
            rows.append((f"[dim]{section_name}[/dim] filterConfig", f"{len(filters)} filter(s)"))
        containers = section_state.get("visualContainers", {})
        if not isinstance(containers, dict):
            continue
        for visual_name, visual_state in containers.items():
            if not isinstance(visual_state, dict):
                continue
            parts: list[str] = []
            single_visual = visual_state.get("singleVisual", {})
            if isinstance(single_visual, dict):
                display = single_visual.get("display", {})
                if isinstance(display, dict):
                    mode = display.get("mode")
                    if isinstance(mode, str):
                        parts.append(mode)
                objects = single_visual.get("objects")
                if isinstance(objects, dict) and objects:
                    parts.append(f"objects: {', '.join(sorted(objects)[:3])}")
                if any(key in single_visual for key in ("projections", "prototypeQuery", "projectionOrdering")):
                    parts.append("projection state")
            if "orderBy" in visual_state:
                parts.append(f"sort: {_format_brief_state(visual_state['orderBy'])}")
            if "filters" in visual_state:
                count = len(visual_state["filters"]) if isinstance(visual_state["filters"], list) else 1
                parts.append(f"filters: {count}")
            if "filterConfig" in visual_state:
                filter_config = visual_state["filterConfig"]
                count = len(filter_config.get("filters", [])) if isinstance(filter_config, dict) else 0
                parts.append(f"filterConfig: {count}")
            if not parts and visual_state:
                parts.append(_format_brief_state(visual_state))
            if parts:
                rows.append((f"[dim]{section_name}[/dim] {visual_name}", ", ".join(parts)))

    return rows


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
    exploration_state_patch: dict | None = None,
    options_patch: dict | None = None,
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
    return _write_new_bookmark(
        project,
        display_name,
        page,
        visuals,
        hidden_visuals=hidden_visuals,
        target_visuals=target_visuals,
        suppress_data=suppress_data,
        suppress_display=suppress_display,
        suppress_active_section=suppress_active_section,
        exploration_state_patch=exploration_state_patch,
        options_patch=options_patch,
    )


def upsert_bookmark(
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
    exploration_state_patch: dict | None = None,
    options_patch: dict | None = None,
) -> dict:
    """Create or update a bookmark keyed by display name."""
    try:
        existing, file_path = _find_bookmark_file(project, display_name)
        bookmark_id = existing.get("name")
    except FileNotFoundError:
        existing = None
        file_path = None
        bookmark_id = None

    return _write_new_bookmark(
        project,
        display_name,
        page,
        visuals,
        hidden_visuals=hidden_visuals,
        target_visuals=target_visuals,
        suppress_data=suppress_data,
        suppress_display=suppress_display,
        suppress_active_section=suppress_active_section,
        exploration_state_patch=exploration_state_patch,
        options_patch=options_patch,
        bookmark_id=bookmark_id,
        file_path=file_path,
    )


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


def update_bookmark(
    project: Project,
    identifier: str,
    *,
    hidden_visuals: list[str] | None = None,
    visible_visuals: list[str] | None = None,
    page: Page | None = None,
    target_visuals: list[str] | None | object = None,
    clear_targets: bool = False,
    capture_data: bool | None = None,
    capture_display: bool | None = None,
    capture_page: bool | None = None,
    exploration_state_patch: dict | None = None,
    options_patch: dict | None = None,
) -> dict:
    """Update bookmark page/options/state while preserving unrelated state."""
    data, file_path = _find_bookmark_file(project, identifier)
    exploration = data.setdefault("explorationState", {})
    sections = exploration.setdefault("sections", {})

    if page is not None:
        if page.name not in sections:
            sections[page.name] = {"visualContainers": {}}
        exploration["activeSection"] = page.name

    if hidden_visuals or visible_visuals:
        active_section = exploration.get("activeSection", "")
        if active_section and active_section not in sections:
            sections[active_section] = {"visualContainers": {}}
        section = sections.get(active_section, {})
        containers = section.setdefault("visualContainers", {})

        if hidden_visuals:
            for vis_name in hidden_visuals:
                container = containers.setdefault(vis_name, {})
                single_visual = container.setdefault("singleVisual", {})
                single_visual["display"] = {"mode": "hidden"}

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

    options = copy.deepcopy(data.get("options", {}))
    if capture_page is not None:
        _set_toggle_option(options, "suppressActiveSection", not capture_page)
    if capture_data is not None:
        _set_toggle_option(options, "suppressData", not capture_data)
    if capture_display is not None:
        _set_toggle_option(options, "suppressDisplay", not capture_display)
    if clear_targets:
        options.pop("applyOnlyToTargetVisuals", None)
        options.pop("targetVisualNames", None)
    elif target_visuals is not None:
        if target_visuals:
            options["applyOnlyToTargetVisuals"] = True
            options["targetVisualNames"] = list(target_visuals)
        else:
            options.pop("applyOnlyToTargetVisuals", None)
            options.pop("targetVisualNames", None)
    if options_patch:
        _deep_merge(options, copy.deepcopy(options_patch))
    if options:
        data["options"] = options
    else:
        data.pop("options", None)

    if exploration_state_patch:
        exploration = data.setdefault("explorationState", {})
        _deep_merge(exploration, copy.deepcopy(exploration_state_patch))

    _write_json(file_path, data)
    return data


def export_bookmarks(project: Project, *, page: Page | None = None) -> list[dict]:
    """Export bookmarks as apply-compatible YAML entries."""
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        return []

    page_lookup = {pg.name: pg.display_name for pg in project.get_pages()}
    page_name = page.name if page is not None else None
    meta = _load_meta(project)
    order = _bookmark_order(meta)
    order_map = {name: idx for idx, name in enumerate(order)}
    group_lookup = _bookmark_group_lookup(meta)
    rows: list[tuple[int, dict]] = []

    for f in sorted(bm_dir.glob("*.bookmark.json")):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue

        exploration = data.get("explorationState", {})
        active_section = exploration.get("activeSection", "")
        if page_name is not None and active_section != page_name:
            continue

        display_name = data.get("displayName") or data.get("name")
        if not isinstance(display_name, str) or not display_name:
            continue

        entry: dict = {
            "name": display_name,
            "page": page_lookup.get(active_section, active_section),
        }
        if group_lookup.get(data.get("name", "")):
            entry["group"] = group_lookup[data.get("name", "")]

        options = data.get("options", {})
        if options.get("targetVisualNames"):
            entry["target"] = list(options["targetVisualNames"])
        if options.get("suppressData"):
            entry["captureData"] = False
        if options.get("suppressDisplay"):
            entry["captureDisplay"] = False
        if options.get("suppressActiveSection"):
            entry["capturePage"] = False

        hidden: list[str] = []
        sections = exploration.get("sections", {})
        section = sections.get(active_section, {}) if isinstance(sections, dict) else {}
        containers = section.get("visualContainers", {}) if isinstance(section, dict) else {}
        if isinstance(containers, dict):
            for vis_name, vis_state in containers.items():
                if not isinstance(vis_state, dict):
                    continue
                single_visual = vis_state.get("singleVisual", {})
                if not isinstance(single_visual, dict):
                    continue
                display = single_visual.get("display", {})
                if isinstance(display, dict) and display.get("mode") == "hidden":
                    hidden.append(vis_name)
        if hidden:
            entry["hide"] = hidden

        state = _export_bookmark_state(data, hidden_visuals=hidden, page_lookup=page_lookup)
        if state:
            entry["state"] = state

        extra_options = _export_bookmark_options(options)
        if extra_options:
            entry["options"] = extra_options

        rows.append((order_map.get(data.get("name", ""), 999), entry))

    rows.sort(key=lambda item: (item[0], item[1]["name"]))
    return [entry for _idx, entry in rows]


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


def reconcile_bookmark_groups(
    project: Project,
    bookmarks: list[tuple[str, str | None]],
) -> None:
    """Apply bookmark group metadata for a set of bookmarks without dropping others."""
    meta = _load_meta(project)
    id_by_display: dict[str, str] = {}
    for display_name, _group in bookmarks:
        data, _ = _find_bookmark_file(project, display_name)
        bookmark_name = data.get("name")
        if isinstance(bookmark_name, str) and bookmark_name:
            id_by_display[display_name] = bookmark_name

    targeted_ids = set(id_by_display.values())
    preserved_items: list[dict] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        if "children" in item:
            children = [child for child in item.get("children", []) if isinstance(child, str) and child not in targeted_ids]
            if not children:
                continue
            updated = dict(item)
            updated["children"] = children
            preserved_items.append(updated)
            continue
        name = item.get("name")
        if isinstance(name, str) and name not in targeted_ids:
            preserved_items.append(item)

    grouped_children: dict[str, list[str]] = {}
    grouped_order: list[str] = []
    for display_name, group_name in bookmarks:
        bookmark_id = id_by_display.get(display_name)
        if bookmark_id is None:
            continue
        if not group_name:
            preserved_items.append({"name": bookmark_id})
            continue
        if group_name not in grouped_children:
            grouped_children[group_name] = []
            grouped_order.append(group_name)
        grouped_children[group_name].append(bookmark_id)

    for group_name in grouped_order:
        children = grouped_children[group_name]
        if len(children) == 1:
            preserved_items.append({"name": children[0]})
            continue
        preserved_items.append({"displayName": group_name, "children": children})

    meta["items"] = preserved_items
    _save_meta(project, meta)


def create_bookmark_group(
    project: Project,
    display_name: str,
    bookmark_identifiers: list[str],
) -> BookmarkGroupInfo:
    """Create a bookmark group from existing bookmark ids/display names."""
    if len(bookmark_identifiers) < 2:
        raise ValueError("Bookmark groups require at least 2 bookmarks.")

    meta = _load_meta(project)
    children: list[str] = []
    standalone_names = _standalone_bookmark_names(meta)
    existing_groups = {group.name.lower() for group in list_bookmark_groups(project)}
    if display_name.lower() in existing_groups:
        raise ValueError(f'Bookmark group "{display_name}" already exists.')

    for identifier in bookmark_identifiers:
        data, _path = _find_bookmark_file(project, identifier)
        bookmark_name = data.get("name", "")
        if not bookmark_name:
            raise ValueError(f'Bookmark "{identifier}" has no internal identifier.')
        if bookmark_name in children:
            raise ValueError(f'Bookmark "{identifier}" was provided more than once.')
        if bookmark_name not in standalone_names:
            group_name = _bookmark_group_lookup(meta).get(bookmark_name)
            if group_name:
                raise ValueError(
                    f'Bookmark "{data.get("displayName", identifier)}" is already in group "{group_name}".'
                )
        children.append(bookmark_name)

    filtered_items: list[dict] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("name") in children and "children" not in item:
            continue
        filtered_items.append(item)

    filtered_items.append({
        "displayName": display_name,
        "children": children,
    })
    meta["items"] = filtered_items
    _save_meta(project, meta)
    return BookmarkGroupInfo(name=display_name, children=children)


def delete_bookmark_group(project: Project, identifier: str) -> BookmarkGroupInfo:
    """Delete a bookmark group and restore its children as standalone bookmarks."""
    meta = _load_meta(project)
    items = meta.get("items", [])
    updated: list[dict] = []
    removed: BookmarkGroupInfo | None = None

    for item in items:
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if isinstance(children, list):
            display_name = item.get("displayName") or item.get("name")
            if display_name == identifier:
                removed = BookmarkGroupInfo(
                    name=str(display_name),
                    children=[child for child in children if isinstance(child, str)],
                )
                for child in removed.children:
                    updated.append({"name": child})
                continue
        updated.append(item)

    if removed is None:
        raise FileNotFoundError(f'Bookmark group "{identifier}" not found')

    meta["items"] = updated
    _save_meta(project, meta)
    return removed


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


def _write_new_bookmark(
    project: Project,
    display_name: str,
    page: Page,
    visuals: list[Visual],
    *,
    hidden_visuals: list[str] | None,
    target_visuals: list[str] | None,
    suppress_data: bool,
    suppress_display: bool,
    suppress_active_section: bool,
    exploration_state_patch: dict | None,
    options_patch: dict | None,
    bookmark_id: str | None = None,
    file_path: Path | None = None,
) -> dict:
    bm_dir = _bookmarks_dir(project)
    bm_dir.mkdir(parents=True, exist_ok=True)

    bookmark_id = bookmark_id or secrets.token_hex(10)
    data = {
        "$schema": BOOKMARK_SCHEMA,
        "displayName": display_name,
        "name": bookmark_id,
        "explorationState": _build_exploration_state(
            page,
            visuals,
            hidden_visuals=hidden_visuals,
            exploration_state_patch=exploration_state_patch,
        ),
    }

    options = _build_bookmark_options(
        target_visuals=target_visuals,
        suppress_data=suppress_data,
        suppress_display=suppress_display,
        suppress_active_section=suppress_active_section,
        options_patch=options_patch,
    )
    if options:
        data["options"] = options

    target_path = file_path or (bm_dir / f"{bookmark_id}.bookmark.json")
    _write_json(target_path, data)

    meta = _load_meta(project)
    meta["items"] = _ensure_bookmark_meta_reference(meta.get("items", []), bookmark_id)
    _save_meta(project, meta)
    return data


def _build_exploration_state(
    page: Page,
    visuals: list[Visual],
    *,
    hidden_visuals: list[str] | None = None,
    exploration_state_patch: dict | None = None,
) -> dict:
    hidden_set = set(hidden_visuals or [])
    visual_containers: dict[str, dict] = {}
    for vis in visuals:
        if vis.name in hidden_set:
            visual_containers[vis.name] = {
                "singleVisual": {
                    "display": {"mode": "hidden"},
                }
            }

    exploration_state: dict = {
        "version": "2.1",
        "activeSection": page.name,
        "sections": {
            page.name: {
                "visualContainers": visual_containers,
            },
        },
    }
    if exploration_state_patch:
        _deep_merge(exploration_state, copy.deepcopy(exploration_state_patch))
    return exploration_state


def _build_bookmark_options(
    *,
    target_visuals: list[str] | None,
    suppress_data: bool,
    suppress_display: bool,
    suppress_active_section: bool,
    options_patch: dict | None = None,
) -> dict:
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
    if options_patch:
        _deep_merge(options, copy.deepcopy(options_patch))
    return options


def _export_bookmark_options(options: dict) -> dict:
    extra = copy.deepcopy(options)
    for key in ("suppressActiveSection", "suppressData", "suppressDisplay", "applyOnlyToTargetVisuals", "targetVisualNames"):
        extra.pop(key, None)
    return extra


def _export_bookmark_state(
    data: dict,
    *,
    hidden_visuals: list[str],
    page_lookup: dict[str, str],
) -> dict | None:
    exploration = data.get("explorationState", {})
    if not isinstance(exploration, dict):
        return None
    active_section = exploration.get("activeSection")
    state: dict = {}
    version = exploration.get("version")
    if version not in (None, "2.1"):
        state["version"] = version
    sections = exploration.get("sections", {})
    if not isinstance(sections, dict):
        return state or None

    exported_sections: dict[str, dict] = {}
    hidden_set = set(hidden_visuals)
    for section_name, section_state in sections.items():
        if not isinstance(section_state, dict):
            continue
        section_extra: dict = {}
        for key, value in section_state.items():
            if key == "visualContainers":
                continue
            section_extra[key] = copy.deepcopy(value)

        containers = section_state.get("visualContainers", {})
        if isinstance(containers, dict):
            exported_containers: dict[str, dict] = {}
            for visual_name, visual_state in containers.items():
                if not isinstance(visual_state, dict):
                    continue
                if _is_hidden_only_container(visual_state) and visual_name in hidden_set and section_name == active_section:
                    continue
                if visual_state:
                    exported_containers[visual_name] = copy.deepcopy(visual_state)
            if exported_containers:
                section_extra["visualContainers"] = exported_containers

        if section_name != active_section or section_extra:
            exported_sections[page_lookup.get(section_name, section_name)] = section_extra or {"visualContainers": {}}

    if exported_sections:
        state["sections"] = exported_sections
    return state or None


def _is_hidden_only_container(visual_state: dict) -> bool:
    return visual_state == {
        "singleVisual": {
            "display": {"mode": "hidden"},
        }
    }


def _deep_merge(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
            continue
        target[key] = value


def _set_toggle_option(options: dict, key: str, enabled: bool) -> None:
    if enabled:
        options[key] = True
    else:
        options.pop(key, None)


def _format_brief_state(value: object) -> str:
    text = json.dumps(value, ensure_ascii=True, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 48 else text[:45] + "..."


def _ensure_bookmark_meta_reference(items: list[dict], bookmark_name: str) -> list[dict]:
    """Ensure bookmark metadata contains one top-level reference for the bookmark."""
    result: list[dict] = []
    found = False
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("name") == bookmark_name and "children" not in item:
            if not found:
                result.append(item)
                found = True
            continue
        result.append(item)
    if not found:
        result.append({"name": bookmark_name})
    return result


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


def _bookmark_group_lookup(meta: dict) -> dict[str, str]:
    """Map bookmark ids to their containing group display name."""
    result: dict[str, str] = {}
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        children = item.get("children")
        if not isinstance(children, list):
            continue
        display_name = item.get("displayName") or item.get("name")
        if not isinstance(display_name, str) or not display_name:
            continue
        for child in children:
            if isinstance(child, str):
                result[child] = display_name
    return result


def _standalone_bookmark_names(meta: dict) -> set[str]:
    """Return bookmark ids that are standalone top-level items."""
    result: set[str] = set()
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        if "children" in item:
            continue
        name = item.get("name")
        if isinstance(name, str):
            result.add(name)
    return result


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
