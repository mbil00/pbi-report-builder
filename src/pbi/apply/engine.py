"""Declarative YAML apply engine facade for PBI reports."""

from __future__ import annotations

from typing import Any, Callable

import yaml

from pbi.report_roundtrip import apply_report_spec as _apply_report_spec
from pbi.theme_roundtrip import apply_theme_spec as _apply_theme_spec
from pbi.validate import ValidationIssue, validate_project

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
    baseline_validation = (
        _validation_issue_keys(validate_project(project, include_model_checks=False))
        if not dry_run
        else set()
    )

    try:
        spec = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.errors.append(f"Invalid YAML: {e}")
        return result

    if not isinstance(spec, dict):
        result.errors.append("YAML must be a mapping with a 'pages' key.")
        return result

    if not isinstance(spec.get("pages", []), list):
        result.errors.append("'pages' must be a list.")
        return result

    try:
        try:
            _apply_top_level_sections(
                project,
                spec,
                result,
                page_filter=page_filter,
                dry_run=dry_run,
                overwrite=overwrite,
                style_cache=style_cache,
                session=session,
            )

            if not dry_run:
                _validate_apply_invariants(project, result)
                _record_post_apply_validation(
                    project,
                    result,
                    baseline_validation=baseline_validation,
                )
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


def _apply_top_level_sections(
    project: Project,
    spec: dict[str, Any],
    result: ApplyResult,
    *,
    page_filter: str | None,
    dry_run: bool,
    overwrite: bool,
    style_cache: dict[str, StylePreset],
    session: _ApplySession,
) -> None:
    """Dispatch each top-level YAML section in phase order.

    Phase ordering is load-bearing:
      1. ``theme``    — document-wide visual style defaults; skipped under ``--page``
      2. ``report``   — report-level metadata; skipped under ``--page``
      3. ``pages``    — visual-bearing content; respects ``--page``
      4. finalize     — fixes cross-page visual refs after all pages applied
      5. ``bookmarks`` — references visuals, so must run after pages exist

    Adding a new top-level YAML section means editing this function and the
    symmetric dispatch in ``pbi/export.py``. See ADR-0001 for why the section
    list stays hard-coded rather than registered through a protocol.
    """
    if page_filter is None:
        _apply_doc_section(
            project, "theme", spec.get("theme"), result,
            _apply_theme_spec, dry_run=dry_run, session=session,
        )
        _apply_doc_section(
            project, "report", spec.get("report"), result,
            _apply_report_spec, dry_run=dry_run, session=session,
        )

    pages_spec = spec.get("pages", [])
    for page_spec in pages_spec:
        if not isinstance(page_spec, dict):
            result.errors.append(
                f"Each page must be a mapping, got: {type(page_spec).__name__}"
            )
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


def _apply_doc_section(
    project: Project,
    name: str,
    section_spec: Any,
    result: ApplyResult,
    apply_fn: Callable[..., tuple[bool, int]],
    *,
    dry_run: bool,
    session: _ApplySession,
) -> None:
    """Apply a document-scoped YAML section (``theme`` or ``report``)."""
    if section_spec is None:
        return
    if not isinstance(section_spec, dict):
        result.errors.append(f"'{name}' must be a mapping.")
        return
    if not section_spec:
        return
    session.ensure_snapshot(project)
    changed, touched = apply_fn(project, section_spec, dry_run=dry_run)
    if changed:
        result.properties_set += touched


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


def _record_post_apply_validation(
    project: Project,
    result: ApplyResult,
    *,
    baseline_validation: set[tuple[str, str, str, str]],
) -> None:
    """Promote new structural/schema validation issues into apply results."""
    for issue in validate_project(project, include_model_checks=False):
        identity = _validation_issue_identity(issue)
        if identity in baseline_validation:
            continue

        message = f"Post-apply validation: {issue.file}: {issue.message}"
        if issue.level == "error" or _is_schema_validation_warning(issue):
            _append_unique(result.errors, message)
        else:
            _append_unique(result.warnings, message)


def _validation_issue_keys(issues: list[ValidationIssue]) -> set[tuple[str, str, str, str]]:
    """Normalize validation issues for pre/post apply comparison."""
    return {_validation_issue_identity(issue) for issue in issues}


def _validation_issue_identity(issue: ValidationIssue) -> tuple[str, str, str, str]:
    """Return a stable identity for diffing validation output."""
    return (issue.file, issue.level, issue.message, issue.path)


def _is_schema_validation_warning(issue: ValidationIssue) -> bool:
    """Return True when a warning indicates schema-invalid PBIR output."""
    return issue.level == "warning" and "schema" in issue.message.lower()


def _append_unique(messages: list[str], message: str) -> None:
    """Append a result message only once."""
    if message not in messages:
        messages.append(message)
