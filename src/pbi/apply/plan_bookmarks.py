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

import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi.bookmarks import (
    _bookmarks_dir,
    _build_bookmark_options,
    _build_exploration_state,
    _find_bookmark_file,
    normalize_bookmark_state,
)
from pbi.project import Project
from pbi.schema_refs import BOOKMARK_SCHEMA


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
    ``keys_touched`` mirrors the prior per-bookmark ``properties_set``
    accounting.
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
    errors: list[str] = []
    keys_touched = 0

    bm_dir = _bookmarks_dir(project)

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
            planned = operations[planned_index]
            file_path = planned.file_path
            bookmark_id = planned.payload.get("name")
            if not isinstance(bookmark_id, str) or not bookmark_id:
                bookmark_id = secrets.token_hex(10)
        else:
            try:
                existing, file_path = _find_bookmark_file(project, name)
                # ``_find_bookmark_file`` falls back to case-insensitive
                # substring matching when no exact match exists -- right for
                # user-facing CLI lookups, a footgun for upsert. A spec entry
                # "Over" against a project with bookmark "OverviewFull" must
                # not clobber the unrelated bookmark's file; require an
                # exact display-name match to reuse its id and path.
                if existing.get("displayName") != name:
                    raise FileNotFoundError
                bookmark_id = existing.get("name")
                if not isinstance(bookmark_id, str) or not bookmark_id:
                    bookmark_id = secrets.token_hex(10)
            except FileNotFoundError:
                bookmark_id = secrets.token_hex(10)
                file_path = bm_dir / f"{bookmark_id}.bookmark.json"
            except ValueError as exc:
                # Ambiguous display-name match against existing bookmarks --
                # surface per-bookmark instead of crashing the whole apply.
                errors.append(f'Bookmark "{name}": {exc}')
                continue

        keys_touched += 1

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
            operations.append(persist)
            groups.append(group_entry)
        else:
            operations[planned_index] = persist
            groups[planned_index] = group_entry

    return BookmarksApplyPlan(
        operations=operations,
        groups=groups,
        errors=errors,
        keys_touched=keys_touched,
    )
