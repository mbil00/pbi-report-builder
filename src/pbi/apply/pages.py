"""Page-level apply helpers."""

from __future__ import annotations

import copy

from .ops import (
    apply_filters_spec as _apply_filters,
    apply_interactions_spec as _apply_interactions,
)
from .state import (
    ApplyResult,
    ApplySession as _ApplySession,
    PageVisualState as _PageVisualState,
    save_page_if_changed as _save_page_if_changed,
)
from .visual_support import (
    apply_nested_properties,
    count_dry_run_changes,
)
from .visuals import apply_visual
from pbi.project import Project
from pbi.properties import PAGE_PROPERTIES, set_property
from pbi.roundtrip import apply_page_roundtrip_fields
from pbi.styles import StylePreset


def apply_page(
    project: Project,
    page_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
    overwrite: bool,
    style_cache: dict[str, StylePreset],
    session: _ApplySession,
) -> None:
    """Apply a single page specification."""
    page_name = page_spec["name"]
    page_baseline: dict | None = None

    page_is_new = False
    pre_visuals_created = len(result.visuals_created)
    pre_visuals_updated = len(result.visuals_updated)
    pre_visuals_deleted = len(result.visuals_deleted)
    pre_properties_set = result.properties_set
    pre_bindings_added = result.bindings_added
    pre_filters_added = result.filters_added
    pre_interactions_set = len(result.interactions_set)
    try:
        page = project.find_page(page_name)
        page_baseline = copy.deepcopy(page.data)
    except ValueError:
        width = page_spec.get("width", 1280)
        height = page_spec.get("height", 720)
        display_option = page_spec.get("displayOption", "FitToPage")
        page_is_new = True
        if dry_run:
            result.pages_created.append(page_name)
            page = None  # type: ignore[assignment]
        else:
            session.ensure_snapshot(project)
            page = project.create_page(
                page_name,
                width=width,
                height=height,
                display_option=display_option,
            )
            page_baseline = copy.deepcopy(page.data)
            result.pages_created.append(page_name)

    page_state = (
        None
        if (dry_run and page_is_new)
        else _PageVisualState(page=page, visuals=project.get_visuals(page))
    )

    if not (dry_run and page_is_new):
        page_error_count = len(result.errors)
        page_props = {
            "width": "width",
            "height": "height",
            "displayOption": "displayOption",
            "visibility": "visibility",
        }
        for yaml_key, prop_name in page_props.items():
            if yaml_key in page_spec:
                value = str(page_spec[yaml_key])
                if not dry_run:
                    try:
                        sw = set_property(page.data, prop_name, value, PAGE_PROPERTIES)
                        result.properties_set += 1
                        for warning in sw:
                            result.warnings.append(f"Page {page_name}: {warning}")
                    except ValueError as e:
                        result.errors.append(f"Page {page_name}: {prop_name}: {e}")
                else:
                    result.properties_set += 1

        try:
            result.properties_set += apply_page_roundtrip_fields(
                page.data,
                page_spec,
                project_root=project.root,
                dry_run=dry_run,
                model=session.get_model(project),
            )
        except ValueError as e:
            result.errors.append(f"Page {page_name}: {e}")
            return

        apply_nested_properties(
            page.data,
            page_spec,
            exclude_keys={
                "name",
                "width",
                "height",
                "displayOption",
                "visibility",
                "visuals",
                "filters",
                "interactions",
                "bookmarks",
                "type",
                "pageBinding",
                "tooltip",
                "drillthrough",
            },
            registry=PAGE_PROPERTIES,
            result=result,
            context=f"Page {page_name}",
            dry_run=dry_run,
        )

        if "filters" in page_spec:
            _apply_filters(
                page.data,
                page_spec["filters"],
                result,
                context=f"Page {page_name}",
                dry_run=dry_run,
                project=project,
                session=session,
            )

        page_can_save = len(result.errors) == page_error_count
    else:
        page_can_save = False

    visuals_spec = page_spec.get("visuals", [])
    if not isinstance(visuals_spec, list):
        result.errors.append(f"Page {page_name}: 'visuals' must be a list.")
        return

    kept_visual_ids: set[str] = set()
    ordered_visual_specs = [
        *[spec for spec in visuals_spec if isinstance(spec, dict) and spec.get("type") == "group"],
        *[spec for spec in visuals_spec if not (isinstance(spec, dict) and spec.get("type") == "group")],
    ]
    for vis_spec in ordered_visual_specs:
        if isinstance(vis_spec, dict):
            if dry_run and page_is_new:
                vis_name = vis_spec.get("name") or vis_spec.get("type", "unknown")
                result.visuals_created.append((page_name, vis_name))
                count_dry_run_changes(vis_spec, result)
            else:
                apply_visual(
                    project,
                    page,
                    vis_spec,
                    result,
                    dry_run=dry_run,
                    style_cache=style_cache,
                    keep_visual_ids=kept_visual_ids if overwrite else None,
                    session=session,
                    page_state=page_state,
                )

    if overwrite and not page_is_new and page_state is not None:
        for visual in list(page_state.visuals):
            if visual.folder.name not in kept_visual_ids:
                result.visuals_deleted.append((page_name, visual.name))
                if not dry_run:
                    session.ensure_snapshot(project)
                    project.delete_visual(visual)
                    page_state.remove(visual)

    if not (dry_run and page_is_new) and "interactions" in page_spec:
        _apply_interactions(
            project,
            page,
            page_spec["interactions"],
            result,
            context=f"Page {page_name}",
            dry_run=dry_run,
            session=session,
            page_state=page_state,
        )

    if not dry_run and page_can_save and page_baseline is not None:
        _save_page_if_changed(project, page, original_data=page_baseline, session=session)

    if not page_is_new:
        page_had_changes = (
            len(result.visuals_created) > pre_visuals_created
            or len(result.visuals_updated) > pre_visuals_updated
            or len(result.visuals_deleted) > pre_visuals_deleted
            or result.properties_set > pre_properties_set
            or result.bindings_added > pre_bindings_added
            or result.filters_added > pre_filters_added
            or len(result.interactions_set) > pre_interactions_set
        )
        if page_had_changes:
            result.pages_updated.append(page_name)
