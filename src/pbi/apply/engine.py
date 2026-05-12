"""Declarative YAML apply engine facade for PBI reports."""

from __future__ import annotations

from typing import Any

import yaml

from pbi.apply.plan_bookmarks import plan_bookmarks_spec
from pbi.apply.plan_report import plan_report_spec
from pbi.apply.plan_theme import plan_theme_spec
from pbi.apply.session import PbirWriteSession
from pbi.validate import ValidationIssue, validate_project

from .pages import apply_page
from .session import run_apply
from .state import (
    ApplyResult,
    PbirApplySession as _PbirApplySession,
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

    style_cache: dict[str, StylePreset] = {}
    session = _PbirApplySession(project=project, dry_run=dry_run)
    baseline_validation = (
        _validation_issue_keys(validate_project(project, include_model_checks=False))
        if not dry_run
        else set()
    )

    def body() -> ApplyResult:
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
        return result

    return run_apply(session, body, continue_on_error=continue_on_error)


def _apply_top_level_sections(
    project: Project,
    spec: dict[str, Any],
    result: ApplyResult,
    *,
    page_filter: str | None,
    dry_run: bool,
    overwrite: bool,
    style_cache: dict[str, StylePreset],
    session: _PbirApplySession,
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
        _apply_theme_branch(
            project, spec.get("theme"), result,
            dry_run=dry_run, session=session,
        )
        _apply_report_branch(
            project, spec.get("report"), result,
            dry_run=dry_run, session=session,
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
        _apply_bookmarks_branch(
            project, bookmarks_spec, result,
            dry_run=dry_run, session=session,
        )


def _apply_theme_branch(
    project: Project,
    section_spec: Any,
    result: ApplyResult,
    *,
    dry_run: bool,
    session: PbirWriteSession,
) -> None:
    """Apply the ``theme`` YAML section through the planner + session.

    ``plan_theme_spec`` is the pure-function half (read current theme, merge,
    default name, detect no-op). The engine then drives the session to
    persist the plan via ``session.write_theme``. Disk I/O lives nowhere
    except inside the session method.
    """
    if section_spec is None:
        return
    if not isinstance(section_spec, dict):
        result.errors.append("'theme' must be a mapping.")
        return
    if not section_spec:
        return

    plan = plan_theme_spec(project, section_spec)
    if plan is None:
        return

    if not dry_run:
        session.write_theme(plan.payload, first_time=plan.first_time)
    result.properties_set += plan.keys_touched


def _apply_report_branch(
    project: Project,
    section_spec: Any,
    result: ApplyResult,
    *,
    dry_run: bool,
    session: PbirWriteSession,
) -> None:
    """Apply the ``report`` YAML section through the planner + session.

    ``plan_report_spec`` is the pure-function half (read current
    ``report.json``, normalize ``resourcePackages``, merge per top-level
    key, detect no-op). The engine then drives the session to persist the
    plan via ``session.write_report``. Disk I/O lives nowhere except inside
    the session method.
    """
    if section_spec is None:
        return
    if not isinstance(section_spec, dict):
        result.errors.append("'report' must be a mapping.")
        return
    if not section_spec:
        return

    plan = plan_report_spec(project, section_spec)
    if plan is None:
        return

    if not dry_run:
        session.write_report(plan.payload)
    result.properties_set += plan.keys_touched


def _apply_bookmarks_branch(
    project: Project,
    bookmarks_spec: list[Any],
    result: ApplyResult,
    *,
    dry_run: bool,
    session: PbirWriteSession,
) -> None:
    """Apply the ``bookmarks`` YAML section through the planner + session.

    ``plan_bookmarks_spec`` computes per-bookmark target payloads (with state
    normalization, hide/target lists, capture flags) and the group hierarchy.
    The engine then drives the session to persist the plan: one
    ``session.write_bookmark`` per ``BookmarkPersist`` operation, then
    exactly one ``session.reconcile_bookmark_groups`` at the end. The
    bookmarks meta file is written exactly once per apply, by
    ``reconcile_bookmark_groups``, with the full group hierarchy.
    """
    plan = plan_bookmarks_spec(project, bookmarks_spec)
    result.errors.extend(plan.errors)
    result.properties_set += plan.keys_touched

    if dry_run:
        return

    written: set[str] = set()
    for op in plan.operations:
        try:
            session.write_bookmark(op.payload, file_path=op.file_path)
        except (OSError, ValueError) as exc:
            result.errors.append(f'Bookmark "{op.display_name}": {exc}')
            continue
        written.add(op.display_name)

    # ``reconcile_bookmark_groups`` calls ``_find_bookmark_file`` on every
    # entry; including bookmarks whose write failed would raise and abort
    # the entire reconcile, losing group membership for the ones that did
    # write.
    reconcilable_groups = [
        (display, group) for display, group in plan.groups if display in written
    ]
    if reconcilable_groups:
        try:
            session.reconcile_bookmark_groups(reconcilable_groups)
        except (ValueError, FileNotFoundError) as exc:
            result.errors.append(f"Bookmark groups: {exc}")


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
