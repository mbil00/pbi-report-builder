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
    expand_visual_shorthand,
    parse_position,
    parse_size,
    raw_object_roots,
    record_schema_warnings,
    resolve_style_assignments,
)
from pbi.project import Project, Page, Visual, sanitize_visual_name
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
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
    vis_spec = expand_visual_shorthand(vis_spec)
    vis_spec = _normalize_visual_page_refs(project, vis_spec)
    page_name = page.display_name
    vis_name = vis_spec.get("name")
    vis_id = vis_spec.get("id")
    vis_type = vis_spec.get("type")
    visual_baseline: dict | None = None

    if vis_type == "group":
        _apply_group_visual(
            project,
            page,
            vis_spec,
            result,
            dry_run=dry_run,
            keep_visual_ids=keep_visual_ids,
            session=session,
            page_state=page_state,
        )
        return

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
            record_schema_warnings(result, context=context, warnings=sw)
        except ValueError as e:
            result.errors.append(f'{context}: style "{style_name}" {prop_name}: {e}')
            return

    raw_pbir = vis_spec.get("pbir")
    if isinstance(raw_pbir, dict):
        apply_raw_visual_payload(visual, raw_pbir)
        if isinstance(vis_spec.get("type"), str):
            visual.data.setdefault("visual", {})["visualType"] = vis_spec["type"]

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
        "group",
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

    if "group" in vis_spec:
        group_ref = vis_spec.get("group")
        if isinstance(group_ref, str) and group_ref:
            try:
                group_visual = page_state.find_visual(group_ref)
            except ValueError as e:
                result.errors.append(f"{context}: group {e}")
                return
            if "visualGroup" not in group_visual.data:
                result.errors.append(f'{context}: "{group_ref}" is not a group container.')
                return
            visual.data["parentGroupName"] = group_visual.name
        else:
            visual.data.pop("parentGroupName", None)
        result.properties_set += 1

    if "bindings" in vis_spec:
        apply_bindings(
            project,
            visual,
            vis_spec["bindings"],
            result,
            context=context,
            session=session,
        )

    if "sort" in vis_spec:
        apply_sort(project, visual, vis_spec["sort"], result, context=context)

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
            visual_type=visual.visual_type,
            project=project,
            model=session.get_model(project),
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


def finalize_visual_page_refs(
    project: Project,
    pages_spec: list[dict],
    *,
    session: _ApplySession,
) -> None:
    """Canonicalize page-linked visual refs after all pages have been created."""
    for page_spec in pages_spec:
        if not isinstance(page_spec, dict):
            continue
        page_name = page_spec.get("name")
        if not isinstance(page_name, str) or not page_name:
            continue
        try:
            page = project.find_page(page_name)
        except ValueError:
            continue

        visuals = project.get_visuals(page)
        by_id = {visual.folder.name: visual for visual in visuals}
        by_name = {visual.name: visual for visual in visuals}

        for vis_spec in page_spec.get("visuals", []):
            if not isinstance(vis_spec, dict):
                continue
            visual = None
            vis_id = vis_spec.get("id")
            if isinstance(vis_id, str) and vis_id:
                visual = by_id.get(vis_id)
            if visual is None:
                vis_name = vis_spec.get("name")
                if isinstance(vis_name, str) and vis_name:
                    visual = by_name.get(vis_name)
            if visual is None:
                continue

            original_data = copy.deepcopy(visual.data)
            changed = False
            for prop_name in ("action.page", "action.drillthrough", "tooltip.section"):
                current = get_property(visual.data, prop_name, VISUAL_PROPERTIES)
                resolved = _resolve_page_ref(project, current)
                if resolved is not None and resolved != current:
                    set_property(visual.data, prop_name, resolved, VISUAL_PROPERTIES)
                    changed = True

            if changed:
                _save_visual_if_changed(project, visual, original_data=original_data, session=session)


def _normalize_visual_page_refs(project: Project, vis_spec: dict) -> dict:
    """Resolve exported page display names back to target page folder ids."""
    normalized = copy.deepcopy(vis_spec)

    action = normalized.get("action")
    if isinstance(action, dict):
        for key in ("page", "drillthrough"):
            value = action.get(key)
            resolved = _resolve_page_ref(project, value)
            if resolved is not None:
                action[key] = resolved

    tooltip = normalized.get("tooltip")
    if isinstance(tooltip, dict):
        value = tooltip.get("section")
        resolved = _resolve_page_ref(project, value)
        if resolved is not None:
            tooltip["section"] = resolved

    for key in ("action.page", "action.drillthrough", "tooltip.section"):
        value = normalized.get(key)
        resolved = _resolve_page_ref(project, value)
        if resolved is not None:
            normalized[key] = resolved

    return normalized


def _resolve_page_ref(project: Project, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return project.find_page(value).name
    except ValueError:
        return None


def _apply_group_visual(
    project: Project,
    page: Page,
    vis_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
    keep_visual_ids: set[str] | None,
    session: _ApplySession,
    page_state: _PageVisualState,
) -> None:
    """Create or update a group container from a visual spec."""
    page_name = page.display_name
    group_name = vis_spec.get("name")
    group_id = vis_spec.get("id")
    if not isinstance(group_name, str) and not isinstance(group_id, str):
        result.errors.append(f"Page {page_name}: group must have 'name' or 'id'.")
        return

    visual: Visual | None = None
    if isinstance(group_id, str) and group_id:
        visual = page_state._by_folder.get(group_id)
    if visual is None and isinstance(group_name, str) and group_name:
        try:
            visual = page_state.find_visual(group_name)
        except ValueError:
            visual = None

    if visual is not None and "visualGroup" not in visual.data:
        result.errors.append(f'Page {page_name}: "{group_name or group_id}" exists but is not a group container.')
        return

    if dry_run:
        entry_name = str(group_name or group_id or "group")
        if visual is None:
            result.visuals_created.append((page_name, entry_name))
        else:
            result.visuals_updated.append((page_name, entry_name))
        count_dry_run_changes(vis_spec, result)
        return

    if visual is None:
        x, y = parse_position(vis_spec.get("position", "0, 0"))
        w, h = parse_size(vis_spec.get("size", "0 x 0"))
        session.ensure_snapshot(project)
        visual = project.create_group_container(
            page,
            name=str(group_name) if isinstance(group_name, str) else None,
            display_name=vis_spec.get("displayName") if isinstance(vis_spec.get("displayName"), str) else str(group_name or group_id or "group"),
            x=x,
            y=y,
            width=w,
            height=h,
        )
        page_state.add(visual)
        result.visuals_created.append((page_name, visual.name))
        visual_baseline = copy.deepcopy(visual.data)
    else:
        result.visuals_updated.append((page_name, visual.name))
        visual_baseline = copy.deepcopy(visual.data)

    if keep_visual_ids is not None:
        keep_visual_ids.add(visual.folder.name)

    if isinstance(group_name, str) and group_name:
        visual.data["name"] = sanitize_visual_name(group_name)
    if isinstance(vis_spec.get("displayName"), str) and vis_spec["displayName"]:
        visual.data.setdefault("visualGroup", {})["displayName"] = vis_spec["displayName"]

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

    if "group" in vis_spec:
        group_ref = vis_spec.get("group")
        if isinstance(group_ref, str) and group_ref:
            try:
                parent = page_state.find_visual(group_ref)
            except ValueError as e:
                result.errors.append(f'Page {page_name}/{visual.name}: group {e}')
                return
            if "visualGroup" not in parent.data:
                result.errors.append(f'Page {page_name}/{visual.name}: "{group_ref}" is not a group container.')
                return
            visual.data["parentGroupName"] = parent.name
        else:
            visual.data.pop("parentGroupName", None)
        result.properties_set += 1

    _save_visual_if_changed(project, visual, original_data=visual_baseline, session=session)
    page_state.refresh()
