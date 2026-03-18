"""Declarative YAML apply engine facade for PBI reports."""

from __future__ import annotations

import yaml

from .pages import apply_page
from .ops import (
    apply_bookmarks_spec as _apply_bookmarks,
)
from .state import (
    ApplyResult,
    ApplySession as _ApplySession,
)
from pbi.project import Project
from pbi.styles import StylePreset


def apply_yaml(
    project: Project,
    yaml_content: str,
    *,
    page_filter: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    continue_on_error: bool = False,
) -> ApplyResult:
    """Apply a YAML specification to the project."""
    result = ApplyResult()
    style_cache: dict[str, StylePreset] = {}
    session = _ApplySession(dry_run=dry_run)

    try:
        spec = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.errors.append(f"Invalid YAML: {e}")
        return result

    if not isinstance(spec, dict):
        result.errors.append("YAML must be a mapping with a 'pages' key.")
        return result

    pages_spec = spec.get("pages", [])
    if not isinstance(pages_spec, list):
        result.errors.append("'pages' must be a list.")
        return result

    try:
        try:
            for page_spec in pages_spec:
                if not isinstance(page_spec, dict):
                    result.errors.append(f"Each page must be a mapping, got: {type(page_spec).__name__}")
                    continue

                page_name = page_spec.get("name")
                if not page_name:
                    result.errors.append("Each page must have a 'name' key.")
                    continue

                if page_filter and page_name.lower() != page_filter.lower():
                    continue

                apply_page(
                    project,
                    page_spec,
                    result,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    style_cache=style_cache,
                    session=session,
                )

            bookmarks_spec = spec.get("bookmarks", [])
            if isinstance(bookmarks_spec, list) and bookmarks_spec:
                _apply_bookmarks(project, bookmarks_spec, result, dry_run=dry_run, session=session)
        except Exception:
            if session.snapshot_dir is not None:
                session.restore(project)
                result.rolled_back = True
            raise

        if result.errors and session.snapshot_dir is not None and not continue_on_error:
            session.restore(project)
            result.rolled_back = True

        return result
    finally:
        session.cleanup()
