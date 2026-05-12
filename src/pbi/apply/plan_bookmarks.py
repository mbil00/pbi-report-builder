"""Bookmarks **Apply Plan** planner.

Pure-function side of the bookmarks apply path: ``plan_bookmarks_spec`` reads
the project's current bookmarks (display-name -> id and file path), computes
each target bookmark payload (via ``_build_exploration_state`` /
``_build_bookmark_options`` / ``normalize_bookmark_state``), and assembles the
group hierarchy. The plan it returns is a flat list of
``BookmarkPersist`` operations plus the ``(display_name, group | None)``
list that the engine drives the **Apply Session** to persist (via
``session.write_bookmark`` per op + exactly one
``session.reconcile_bookmark_groups``).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.bookmarks import (
    _bookmarks_dir,
    _build_bookmark_options,
    _build_exploration_state,
    normalize_bookmark_state,
)
from pbi.project import Project, _read_json
from pbi.schema_refs import BOOKMARK_SCHEMA


def _index_existing_bookmarks_by_display(
    project: Project,
) -> dict[str, list[tuple[dict, Path]]]:
    """Index ``<bm_dir>/*.bookmark.json`` by exact ``displayName``.

    Scanned once at the top of the planner; the per-entry upsert lookup
    is a single dict probe afterwards. Pre-refactor dry-run never
    touched disk; this keeps the cost at O(M) reads per plan rather
    than O(N*M) for N spec entries.

    Distinct from ``pbi.bookmarks._find_bookmark_file`` which also does
    case-insensitive substring matching -- right for user-facing CLI
    lookups, wrong for upsert (would clobber unrelated bookmarks on
    single partial matches, and would surface unrelated-bookmark
    ambiguity on multi-partial matches against a spec name that should
    just be a new bookmark).
    """
    bm_dir = _bookmarks_dir(project)
    if not bm_dir.exists():
        return {}
    index: dict[str, list[tuple[dict, Path]]] = {}
    for f in bm_dir.glob("*.bookmark.json"):
        try:
            data = _read_json(f)
        except (json.JSONDecodeError, KeyError):
            continue
        name = data.get("displayName")
        if isinstance(name, str):
            index.setdefault(name, []).append((data, f))
    return index


@dataclass(frozen=True)
class BookmarkPersist:
    """A single bookmark JSON to write at a known target path.

    The planner produces one of these per spec entry that successfully
    resolved (payload built, file path computed). The session writes the
    ``payload`` to ``file_path`` exactly. ``display_name`` is carried for
    diagnostics and for the engine's ``ApplyResult`` accounting.
    """

    payload: dict[str, Any]
    file_path: Path
    display_name: str


@dataclass(frozen=True)
class BookmarksApplyPlan:
    """Bookmarks plan: per-op writes + one final group reconcile.

    ``operations`` is a list of bookmark JSON writes in spec order.
    ``groups`` is the ``(display_name, group_name | None)`` list that the
    engine passes verbatim to ``session.reconcile_bookmark_groups`` once,
    after every per-bookmark write has run -- so the bookmarks meta file
    is written exactly once per apply, with the full group hierarchy.
    ``errors`` is collected from missing-required-field failures rather
    than raised, so the engine surfaces them through ``ApplyResult.errors``.
    ``keys_touched`` is ``len(operations)`` -- the number of unique
    bookmark writes the plan represents. Duplicate spec entries that
    collapsed into a single upsert count once, so dry-run and real-apply
    agree on the ``ApplyResult.properties_set`` total.
    """

    operations: list[BookmarkPersist] = field(default_factory=list)
    groups: list[tuple[str, str | None]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    keys_touched: int = 0


def plan_bookmarks_spec(
    project: Project,
    bookmarks_spec: list[Any],
) -> BookmarksApplyPlan:
    """Compute what writing ``bookmarks_spec`` would produce.

    Always returns a ``BookmarksApplyPlan`` (never ``None``); an empty spec
    yields an empty plan. Missing required fields produce entries in
    ``plan.errors`` rather than exceptions, so the engine can surface
    multiple bookmark errors per apply pass.
    """
    operations: list[BookmarkPersist] = []
    groups: list[tuple[str, str | None]] = []
    planned_by_display: dict[str, int] = {}
    planned_pages: dict[str, str] = {}
    errors: list[str] = []

    bm_dir = _bookmarks_dir(project)
    existing_by_display = _index_existing_bookmarks_by_display(project)

    for entry in bookmarks_spec:
        if not isinstance(entry, dict):
            errors.append("Bookmark must be a mapping.")
            continue

        name = entry.get("name", "")
        page_ref = entry.get("page", "")
        if not name or not page_ref:
            errors.append("Bookmark requires 'name' and 'page'.")
            continue

        try:
            page = project.find_page(page_ref)
        except ValueError as exc:
            errors.append(f'Bookmark "{name}": {exc}')
            continue

        display_name = str(name)
        planned_index = planned_by_display.get(display_name)
        if planned_index is not None:
            if planned_pages.get(display_name) != page.name:
                # A second spec entry sharing a display name with an
                # earlier one but targeting a different page can't be
                # coalesced -- a bookmark belongs to exactly one page.
                # Surface the conflict instead of silently letting the
                # second entry win.
                errors.append(
                    f'Bookmark "{display_name}" listed multiple times '
                    f'with different "page" values; spec is ambiguous.'
                )
                continue
            planned = operations[planned_index]
            file_path = planned.file_path
            bookmark_id = planned.payload.get("name")
            if not isinstance(bookmark_id, str) or not bookmark_id:
                bookmark_id = secrets.token_hex(10)
        else:
            matches = existing_by_display.get(name, [])
            if len(matches) > 1:
                # Multiple existing bookmarks share this exact ``displayName``
                # -- genuine ambiguity, we can't pick which to upsert.
                names = ", ".join(d.get("displayName", "") for d, _ in matches)
                errors.append(
                    f'Bookmark "{name}": Ambiguous bookmark "{name}". '
                    f'Matches: {names}'
                )
                continue
            if matches:
                existing, file_path = matches[0]
                bookmark_id = existing.get("name")
                if not isinstance(bookmark_id, str) or not bookmark_id:
                    bookmark_id = secrets.token_hex(10)
            else:
                bookmark_id = secrets.token_hex(10)
                file_path = bm_dir / f"{bookmark_id}.bookmark.json"

        visuals = project.get_visuals(page)
        hide = entry.get("hide", []) or None
        target = entry.get("target") or None
        capture_data = bool(entry.get("captureData", True))
        capture_display = bool(entry.get("captureDisplay", True))
        capture_page = bool(entry.get("capturePage", True))
        state = entry.get("state")
        options = entry.get("options")

        normalized_state = (
            normalize_bookmark_state(project, state) if isinstance(state, dict) else None
        )

        payload: dict[str, Any] = {
            "$schema": BOOKMARK_SCHEMA,
            "displayName": name,
            "name": bookmark_id,
            "explorationState": _build_exploration_state(
                page,
                visuals,
                hidden_visuals=list(hide) if hide else None,
                exploration_state_patch=normalized_state,
            ),
        }

        bookmark_options = _build_bookmark_options(
            target_visuals=list(target) if target else None,
            suppress_data=not capture_data,
            suppress_display=not capture_display,
            suppress_active_section=not capture_page,
            options_patch=options if isinstance(options, dict) else None,
        )
        if bookmark_options:
            payload["options"] = bookmark_options

        persist = BookmarkPersist(
            payload=payload,
            file_path=file_path,
            display_name=display_name,
        )
        group = entry.get("group")
        group_entry = (
            display_name,
            str(group) if isinstance(group, str) and group else None,
        )
        if planned_index is None:
            planned_by_display[display_name] = len(operations)
            planned_pages[display_name] = page.name
            operations.append(persist)
            groups.append(group_entry)
        else:
            operations[planned_index] = persist
            groups[planned_index] = group_entry

    return BookmarksApplyPlan(
        operations=operations,
        groups=groups,
        errors=errors,
        keys_touched=len(operations),
    )
