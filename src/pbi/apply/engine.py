"""Declarative YAML apply engine facade for PBI reports."""

from __future__ import annotations

import yaml

from pbi.report_roundtrip import apply_report_spec as _apply_report_spec
from pbi.theme_roundtrip import apply_theme_spec as _apply_theme_spec

from .pages import apply_page
from .ops import (
    apply_bookmarks_spec as _apply_bookmarks,
)
from .state import (
    ApplyResult,
    ApplySession as _ApplySession,
)
from .visuals import finalize_visual_page_refs as _finalize_visual_page_refs
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
            theme_spec = spec.get("theme")
            report_spec = spec.get("report")
            if page_filter is None:
                if theme_spec is not None and not isinstance(theme_spec, dict):
                    result.errors.append("'theme' must be a mapping.")
                elif isinstance(theme_spec, dict) and theme_spec:
                    session.ensure_snapshot(project)
                    changed, touched = _apply_theme_spec(project, theme_spec, dry_run=dry_run)
                    if changed:
                        result.properties_set += touched

                if report_spec is not None and not isinstance(report_spec, dict):
                    result.errors.append("'report' must be a mapping.")
                elif isinstance(report_spec, dict) and report_spec:
                    session.ensure_snapshot(project)
                    changed, touched = _apply_report_spec(project, report_spec, dry_run=dry_run)
                    if changed:
                        result.properties_set += touched

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

            _finalize_visual_page_refs(project, pages_spec, session=session)

            bookmarks_spec = spec.get("bookmarks", [])
            if isinstance(bookmarks_spec, list) and bookmarks_spec:
                _apply_bookmarks(project, bookmarks_spec, result, dry_run=dry_run, session=session)

            if not dry_run:
                _validate_apply_invariants(project, result)
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


def _validate_apply_invariants(project: Project, result: ApplyResult) -> None:
    """Catch critical structural breakage before apply returns success."""
    from pbi.bookmarks import _load_meta

    for page in project.get_pages():
        group_names = {
            visual.name
            for visual in project.get_visuals(page)
            if "visualGroup" in visual.data
        }
        for visual in project.get_visuals(page):
            if "visualGroup" not in visual.data:
                if "visualType" not in visual.data.get("visual", {}):
                    result.errors.append(
                        f'{page.display_name}/{visual.name}: apply produced a visual without visual.visualType.'
                    )
                parent = visual.data.get("parentGroupName")
                if isinstance(parent, str) and parent and parent not in group_names:
                    result.warnings.append(
                        f'{page.display_name}/{visual.name}: parentGroupName "{parent}" has no matching group container.'
                    )

    for item in _load_meta(project).get("items", []):
        if isinstance(item, dict) and isinstance(item.get("children"), list):
            if not isinstance(item.get("name"), str) or not item.get("name"):
                result.errors.append("Bookmark groups must include a name identifier.")
