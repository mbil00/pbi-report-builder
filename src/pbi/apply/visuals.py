"""Visual-level apply orchestration."""

from __future__ import annotations

import copy

from .ops import apply_filters_spec as _apply_filters
from .state import (
    ApplyResult,
    ApplySession as _ApplySession,
    PageVisualState as _PageVisualState,
    save_visual_if_changed as _save_visual_if_changed,
)
from .visual_queries import (
    apply_bindings,
    apply_sort,
)
from .visual_support import (
    apply_conditional_formatting,
    apply_nested_properties,
    apply_raw_visual_payload,
    apply_textbox_content,
    count_dry_run_changes,
    parse_position,
    parse_size,
    raw_object_roots,
    resolve_style_assignments,
)
from pbi.project import Project, Page, Visual, sanitize_visual_name
from pbi.properties import VISUAL_PROPERTIES, set_property
from pbi.styles import StylePreset


def apply_visual(
    project: Project,
    page: Page,
    vis_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
    style_cache: dict[str, StylePreset],
    keep_visual_ids: set[str] | None = None,
    session: _ApplySession,
    page_state: _PageVisualState,
) -> None:
    """Apply a single visual specification."""
    page_name = page.display_name
    vis_name = vis_spec.get("name")
    vis_id = vis_spec.get("id")
    vis_type = vis_spec.get("type")
    visual_baseline: dict | None = None

    if not vis_name and not vis_type:
        result.errors.append(f"Page {page_name}: visual must have 'name' or 'type'.")
        return

    visual: Visual | None = None
    if vis_id:
        visual = page_state._by_folder.get(vis_id)
    if vis_name:
        try:
            visual = visual or page_state.find_visual(vis_name)
        except ValueError:
            pass

    if visual is not None:
        visual_baseline = copy.deepcopy(visual.data)

    if visual is not None and vis_type and visual.visual_type != vis_type:
        old_type = visual.visual_type
        x, y = parse_position(
            vis_spec.get("position", f"{visual.position.get('x', 0)}, {visual.position.get('y', 0)}")
        )
        w, h = parse_size(
            vis_spec.get(
                "size",
                f"{visual.position.get('width', 300)} x {visual.position.get('height', 200)}",
            )
        )
        if dry_run:
            result.visuals_deleted.append((page_name, vis_name or visual.name))
            result.visuals_created.append((page_name, vis_name or vis_type))
        else:
            session.ensure_snapshot(project)
            project.delete_visual(visual)
            page_state.remove(visual)
            visual = project.create_visual(page, vis_type, x=x, y=y, width=w, height=h)
            if vis_name:
                visual.data["name"] = sanitize_visual_name(vis_name)
                visual.save()
            visual_baseline = copy.deepcopy(visual.data)
            page_state.add(visual)
            result.visuals_deleted.append((page_name, f"{vis_name or visual.name} ({old_type})"))
            result.visuals_created.append((page_name, vis_name or vis_type))
    elif visual is None and vis_type:
        x, y = parse_position(vis_spec.get("position", "0, 0"))
        w, h = parse_size(vis_spec.get("size", "300 x 200"))
        if dry_run:
            result.visuals_created.append((page_name, vis_name or vis_type))
        else:
            session.ensure_snapshot(project)
            visual = project.create_visual(page, vis_type, x=x, y=y, width=w, height=h)
            if vis_name:
                visual.data["name"] = sanitize_visual_name(vis_name)
                visual.save()
            visual_baseline = copy.deepcopy(visual.data)
            page_state.add(visual)
            result.visuals_created.append((page_name, vis_name or vis_type))
    elif visual is None:
        result.errors.append(
            f'Page {page_name}: visual "{vis_name}" not found and no \'type\' specified for creation.'
        )
        return
    else:
        result.visuals_updated.append((page_name, vis_name or visual.name))

    visual_type = visual.visual_type if visual is not None else vis_type
    context = f"{page_name}/{vis_name or visual.name if visual is not None else vis_type}"
    try:
        style_assignments = resolve_style_assignments(
            project,
            vis_spec.get("style"),
            visual_type=visual_type,
            style_cache=style_cache,
        )
    except (FileNotFoundError, ValueError) as e:
        result.errors.append(f"{context}: {e}")
        return

    visual_error_count = len(result.errors)

    if dry_run:
        result.properties_set += len(style_assignments)
        count_dry_run_changes(vis_spec, result)
        return

    if keep_visual_ids is not None:
        keep_visual_ids.add(visual.folder.name)

    for style_name, prop_name, value in style_assignments:
        try:
            sw = set_property(visual.data, prop_name, str(value), VISUAL_PROPERTIES)
            result.properties_set += 1
            for warning in sw:
                result.warnings.append(f"{context}: {warning}")
        except ValueError as e:
            result.errors.append(f'{context}: style "{style_name}" {prop_name}: {e}')
            return

    raw_pbir = vis_spec.get("pbir")
    if isinstance(raw_pbir, dict):
        apply_raw_visual_payload(visual, raw_pbir)

    if "position" in vis_spec:
        x, y = parse_position(vis_spec["position"])
        visual.data.setdefault("position", {})["x"] = x
        visual.data["position"]["y"] = y
        result.properties_set += 2

    if "size" in vis_spec:
        w, h = parse_size(vis_spec["size"])
        visual.data.setdefault("position", {})["width"] = w
        visual.data["position"]["height"] = h
        result.properties_set += 2

    pos = visual.data.setdefault("position", {})
    for key in ("x", "y", "width", "height"):
        if key in vis_spec and key not in ("position", "size"):
            pos[key] = int(vis_spec[key])
            result.properties_set += 1

    if "text" in vis_spec and visual_type == "textbox":
        apply_textbox_content(visual, vis_spec, result)

    exclude_keys = {
        "id",
        "name",
        "type",
        "position",
        "size",
        "bindings",
        "sort",
        "filters",
        "conditionalFormatting",
        "isHidden",
        "pbir",
        "style",
        "kpis",
        "layout",
        "accentBar",
        "referenceLabelLayout",
        "text",
        "textStyle",
        "x",
        "y",
        "width",
        "height",
    }
    apply_nested_properties(
        visual.data,
        vis_spec,
        exclude_keys=exclude_keys,
        registry=VISUAL_PROPERTIES,
        result=result,
        context=context,
        dry_run=dry_run,
        ignore_selector_errors=isinstance(raw_pbir, dict),
        ignore_unknown_roots=raw_object_roots(raw_pbir) if isinstance(raw_pbir, dict) else None,
    )

    if "isHidden" in vis_spec:
        visual.data["isHidden"] = bool(vis_spec["isHidden"])
        result.properties_set += 1

    if "bindings" in vis_spec:
        apply_bindings(project, visual, vis_spec["bindings"], result, session=session)

    if "sort" in vis_spec:
        apply_sort(project, visual, vis_spec["sort"], result)

    if "filters" in vis_spec:
        _apply_filters(
            visual.data,
            vis_spec["filters"],
            result,
            context=context,
            dry_run=dry_run,
            project=project,
            session=session,
        )

    if "conditionalFormatting" in vis_spec:
        apply_conditional_formatting(
            visual.data,
            vis_spec["conditionalFormatting"],
            result,
            context=context,
            dry_run=dry_run,
            project=project,
        )

    if "kpis" in vis_spec:
        kpis_list = vis_spec["kpis"]
        if not isinstance(kpis_list, list):
            result.errors.append(f"{context}: kpis must be a list of KPI definitions.")
        else:
            from pbi.card import expand_kpis

            try:
                count = expand_kpis(
                    visual.data,
                    kpis_list,
                    layout=vis_spec.get("layout"),
                    accent_bar=vis_spec.get("accentBar"),
                    ref_label_layout=vis_spec.get("referenceLabelLayout"),
                )
                result.properties_set += count
            except (ValueError, KeyError) as e:
                result.errors.append(f"{context}: kpis expansion failed: {e}")

    if len(result.errors) != visual_error_count:
        return

    if visual_baseline is not None:
        _save_visual_if_changed(project, visual, original_data=visual_baseline, session=session)
    page_state.refresh()
