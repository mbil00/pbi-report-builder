"""Detailed YAML export for round-trip with pbi apply.

Produces a complete YAML representation of pages and visuals that can be
fed back into pbi apply to reproduce or update the report state.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml

from pbi.bookmarks import export_bookmarks
from pbi.project import Project, Page, Visual
from pbi.properties import PAGE_PROPERTIES, VISUAL_PROPERTIES, get_property
from pbi.filters import filter_field_refs, get_filters, parse_filter
from pbi.report_roundtrip import export_report_spec
from pbi.roundtrip import (
    export_bindings,
    export_object_properties,
    export_page_roundtrip_fields,
    prune_visual_pbir,
)
from pbi.styles import apply_style_reference, match_style_preset
from pbi.textbox import extract_textbox_spec
from pbi.theme_roundtrip import export_theme_spec


def export_page(project: Project, page: Page) -> dict:
    """Export a single page as a dict suitable for YAML serialization."""
    visuals = project.get_visuals(page)
    page_dict: dict[str, Any] = {
        "name": page.display_name,
        "width": page.width,
        "height": page.height,
        "displayOption": page.display_option,
    }

    if page.visibility != "AlwaysVisible":
        page_dict["visibility"] = page.visibility
    page_dict.update(export_page_roundtrip_fields(page.data))

    # Page-level objects (background, outspace)
    page_objects = page.data.get("objects", {})
    if page_objects:
        page_dict.update(
            export_object_properties(
                page_objects,
                PAGE_PROPERTIES,
                objects_path="objects",
            )
        )

    # Page-level filters
    page_filters = _export_filters(page.data)
    if page_filters:
        page_dict["filters"] = page_filters

    # Page-level interactions
    interactions = page.data.get("visualInteractions", [])
    if interactions:
        page_dict["interactions"] = [
            {"source": e["source"], "target": e["target"], "type": e["type"]}
            for e in interactions
            if "source" in e and "target" in e and "type" in e
        ]

    # Visuals and visual groups.
    groups = {vis.name: vis for vis in visuals if "visualGroup" in vis.data}
    visual_list = []
    for vis in visuals:
        if "visualGroup" in vis.data:
            visual_list.append(_export_group(vis))
            continue
        exported = _export_visual(project, vis)
        parent_group = vis.data.get("parentGroupName")
        if isinstance(parent_group, str) and parent_group in groups:
            exported["group"] = parent_group
        visual_list.append(exported)

    if visual_list:
        page_dict["visuals"] = visual_list

    return page_dict


def export_pages(project: Project, page_filter: str | None = None) -> dict:
    """Export pages as a full apply-compatible dict.

    If page_filter is given, only export that page.
    """
    result: dict[str, Any] = {"version": 1}
    pages = project.get_pages()

    if page_filter:
        page = project.find_page(page_filter)
        pages = [page]
    else:
        theme_spec = export_theme_spec(project)
        if theme_spec:
            result["theme"] = theme_spec
        report_spec = export_report_spec(project)
        if report_spec:
            result["report"] = report_spec

    result["pages"] = [export_page(project, p) for p in pages]
    bookmark_page = pages[0] if page_filter and pages else None
    bookmarks = export_bookmarks(project, page=bookmark_page)
    if bookmarks:
        result["bookmarks"] = bookmarks
    return result


def export_yaml(project: Project, page_filter: str | None = None) -> str:
    """Export pages as a YAML string."""
    data = export_pages(project, page_filter)
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def export_visual_spec(project: Project, visual: Visual) -> dict:
    """Export one visual as a canonical apply-compatible dict."""
    if "visualGroup" in visual.data:
        return _export_group(visual)
    return _export_visual(project, visual)


def _export_visual(project: Project, visual: Visual) -> dict:
    """Export a single visual as a dict."""
    pos = visual.position
    page_lookup = {page.name: page.display_name for page in project.get_pages()}
    group_names = _group_names_for_visual(project, visual)
    result: dict[str, Any] = {}
    result["id"] = visual.folder.name

    # Name — use friendly name, skip hex IDs
    is_hex = all(c in "0123456789abcdef" for c in visual.name) and len(visual.name) >= 16
    if not is_hex:
        result["name"] = visual.name

    result["type"] = visual.visual_type
    result["position"] = f"{pos.get('x', 0)}, {pos.get('y', 0)}"
    result["size"] = f"{pos.get('width', 0)} x {pos.get('height', 0)}"
    parent_group = visual.data.get("parentGroupName")
    if isinstance(parent_group, str) and parent_group in group_names:
        result["group"] = parent_group

    if visual.data.get("isHidden"):
        result["isHidden"] = True
    drill_filter_other_visuals = get_property(
        visual.data,
        "drillFilterOtherVisuals",
        VISUAL_PROPERTIES,
    )
    if drill_filter_other_visuals is not None:
        result["drillFilterOtherVisuals"] = drill_filter_other_visuals

    # Container formatting (title, background, border, etc.)
    container_objs = visual.data.get("visual", {}).get("visualContainerObjects", {})
    if container_objs:
        result.update(
            export_object_properties(
                container_objs,
                VISUAL_PROPERTIES,
                objects_path="visualContainerObjects",
                root_aliases={
                    "dropShadow": "shadow",
                    "subTitle": "subtitle",
                    "visualHeader": "header",
                    "visualTooltip": "tooltip",
                    "visualLink": "action",
                },
            )
        )

    # Chart formatting (legend, axes, labels, etc.)
    chart_objs = visual.data.get("visual", {}).get("objects", {})
    if chart_objs:
        result.update(
            export_object_properties(
                chart_objs,
                VISUAL_PROPERTIES,
                objects_path="objects",
                skip_objects={"columnWidth"},
                root_aliases={
                    "categoryAxis": "xAxis",
                    "valueAxis": "yAxis",
                    "lineStyles": "line",
                    "dataPoint": "dataColors",
                },
            )
        )

    _normalize_exported_visual_page_refs(result, page_lookup)

    # Textbox content
    if visual.visual_type == "textbox":
        text_spec = _export_textbox_content(visual.data)
        if text_spec:
            result.update(text_spec)

    # Data bindings
    bindings = export_bindings(visual.data)
    if bindings:
        result["bindings"] = bindings

    # Sort
    sorts = project.get_sort(visual)
    if sorts:
        entity, prop, ftype, direction = sorts[0]
        suffix = " (measure)" if ftype == "measure" else ""
        result["sort"] = f"{entity}.{prop}{suffix} {direction}"

    # Visual-level filters
    vis_filters = _export_filters(visual.data)
    if vis_filters:
        result["filters"] = vis_filters

    # Preserve the exact PBIR payload so exported YAML can round-trip
    # complex visuals, selector-based properties, and unsupported shapes.
    raw_visual = prune_visual_pbir(visual.data, result)
    if raw_visual:
        result["pbir"] = raw_visual

    matched_style = match_style_preset(project, result)
    if matched_style is not None:
        result = apply_style_reference(result, matched_style.name)

    return result


def _export_group(group: Visual) -> dict[str, Any]:
    """Export a visual group container as an apply-compatible dict."""
    pos = group.position
    result: dict[str, Any] = {
        "id": group.folder.name,
        "name": group.name,
        "type": "group",
        "position": f"{pos.get('x', 0)}, {pos.get('y', 0)}",
        "size": f"{pos.get('width', 0)} x {pos.get('height', 0)}",
    }
    display_name = group.data.get("visualGroup", {}).get("displayName")
    if isinstance(display_name, str) and display_name and display_name != group.name:
        result["displayName"] = display_name
    parent_group = group.data.get("parentGroupName")
    if isinstance(parent_group, str) and parent_group:
        result["group"] = parent_group
    return result


def _group_names_for_visual(project: Project, visual: Visual) -> set[str]:
    """Return group names available on the visual's page."""
    page_dir = visual.folder.parent.parent
    for page in project.get_pages():
        if page.folder == page_dir:
            return {
                candidate.name
                for candidate in project.get_visuals(page)
                if "visualGroup" in candidate.data
            }
    return set()


def _normalize_exported_visual_page_refs(
    visual_spec: dict[str, Any],
    page_lookup: dict[str, str],
) -> None:
    """Export page-linked visual properties using stable page display names."""
    action = visual_spec.get("action")
    if isinstance(action, dict):
        for key in ("page", "drillthrough"):
            value = action.get(key)
            if isinstance(value, str):
                action[key] = page_lookup.get(value, value)

    tooltip = visual_spec.get("tooltip")
    if isinstance(tooltip, dict):
        section = tooltip.get("section")
        if isinstance(section, str):
            tooltip["section"] = page_lookup.get(section, section)


def _export_textbox_content(visual_data: dict) -> dict[str, Any] | None:
    """Export textbox paragraphs into text/textStyle shorthand."""
    return extract_textbox_spec(visual_data)


def _export_filters(data: dict) -> list[dict]:
    """Export filters as structured dicts for YAML."""
    filters = get_filters(data)
    if not filters:
        return []

    result = []
    for f in filters:
        info = parse_filter(f)
        field_refs = filter_field_refs(f)
        entry: dict[str, Any] = {
            "field": field_refs[0] if field_refs else f"{info.field_entity}.{info.field_prop}",
            "type": info.filter_type,
            "raw": copy.deepcopy(f),
        }
        if info.name:
            entry["name"] = info.name
        if len(field_refs) > 1:
            entry["fields"] = field_refs
        if info.values:
            entry["values"] = info.values
        if info.is_hidden:
            entry["hidden"] = True
        if info.is_locked:
            entry["locked"] = True
        result.append(entry)
    return result
