"""Shared lookup policies for pages, visuals, and similar entities."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Mapping, Sequence
from typing import TypeVar


T = TypeVar("T")


def find_page_by_identifier(
    pages: Sequence[T],
    identifier: str,
    *,
    folder_name: Callable[[T], str],
    display_name: Callable[[T], str],
) -> T:
    """Resolve a page-like object using the standard CLI precedence."""
    for page in pages:
        if folder_name(page) == identifier:
            return page

    id_lower = identifier.lower()
    for page in pages:
        if display_name(page).lower() == id_lower:
            return page

    matches = [page for page in pages if id_lower in display_name(page).lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f'"{display_name(page)}"' for page in matches)
        raise ValueError(f'Ambiguous page "{identifier}". Matches: {names}')

    try:
        idx = int(identifier) - 1
        if 0 <= idx < len(pages):
            return pages[idx]
    except ValueError:
        pass

    names = [display_name(page) for page in pages]
    close = difflib.get_close_matches(identifier, names, n=3, cutoff=0.5)
    if close:
        suggestion = ", ".join(f'"{name}"' for name in close)
        raise ValueError(f'Page "{identifier}" not found. Did you mean: {suggestion}?')

    available = ", ".join(f'"{name}"' for name in names)
    raise ValueError(f'Page "{identifier}" not found. Available: {available}')


def find_visual_by_identifier(
    visuals: Sequence[T],
    identifier: str,
    *,
    page_display_name: str,
    folder_name: Callable[[T], str],
    visual_name: Callable[[T], str],
    visual_type: Callable[[T], str],
    by_folder: Mapping[str, T] | None = None,
    by_name: Mapping[str, T] | None = None,
) -> T:
    """Resolve a visual-like object using the standard CLI precedence."""
    raw_identifier = identifier
    if identifier.startswith(("#", "@")):
        identifier = identifier[1:]

    if by_folder is not None:
        visual = by_folder.get(identifier)
        if visual is not None:
            return visual
    else:
        for visual in visuals:
            if folder_name(visual) == identifier:
                return visual

    if by_name is not None:
        visual = by_name.get(identifier)
        if visual is not None:
            return visual
    else:
        for visual in visuals:
            if visual_name(visual) == identifier:
                return visual

    try:
        idx = int(identifier) - 1
        if 0 <= idx < len(visuals):
            return visuals[idx]
    except ValueError:
        pass

    id_lower = identifier.lower()
    type_matches = [visual for visual in visuals if visual_type(visual).lower() == id_lower]
    if len(type_matches) == 1:
        return type_matches[0]

    matches = [visual for visual in visuals if id_lower in visual_name(visual).lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f'"{visual_name(visual)}" ({visual_type(visual)})' for visual in matches)
        raise ValueError(f'Ambiguous visual "{identifier}". Matches: {names}')

    all_names = [visual_name(visual) for visual in visuals] + [visual_type(visual) for visual in visuals]
    close = difflib.get_close_matches(identifier, all_names, n=3, cutoff=0.5)
    if close:
        suggestion = ", ".join(f'"{name}"' for name in close)
        raise ValueError(
            f'Visual "{raw_identifier}" not found on "{page_display_name}". '
            f"Did you mean: {suggestion}?"
        )

    available = ", ".join(
        f'{i + 1}: {visual_name(visual)} ({visual_type(visual)})'
        for i, visual in enumerate(visuals)
    )
    raise ValueError(
        f'Visual "{raw_identifier}" not found on "{page_display_name}". '
        f"Available: {available}"
    )
