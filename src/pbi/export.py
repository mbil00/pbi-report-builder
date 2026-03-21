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
from pbi.roundtrip import (
    export_bindings,
    export_object_properties,
    export_page_roundtrip_fields,
    prune_visual_pbir,
)
from pbi.styles import apply_style_reference, match_style_preset


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

    # Visuals
    visual_list = []
    for vis in visuals:
        if "visualGroup" in vis.data:
            continue  # Skip groups for now (groups are structural)
        exported = _export_visual(project, vis)
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
    return _export_visual(project, visual)


def _export_visual(project: Project, visual: Visual) -> dict:
    """Export a single visual as a dict."""
    pos = visual.position
    page_lookup = {page.name: page.display_name for page in project.get_pages()}
    result: dict[str, Any] = {}
    result["id"] = visual.folder.name

    # Name — use friendly name, skip hex IDs
    is_hex = all(c in "0123456789abcdef" for c in visual.name) and len(visual.name) >= 16
    if not is_hex:
        result["name"] = visual.name

    result["type"] = visual.visual_type
    result["position"] = f"{pos.get('x', 0)}, {pos.get('y', 0)}"
    result["size"] = f"{pos.get('width', 0)} x {pos.get('height', 0)}"

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
    paragraphs = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get("general", [{}])[0]
        .get("properties", {})
        .get("paragraphs", [])
    )
    if not paragraphs:
        return None

    # Extract text from first paragraph's first text run
    first_para = paragraphs[0] if paragraphs else {}
    text_runs = first_para.get("textRuns", [])
    if not text_runs:
        return None

    run = text_runs[0]
    raw_text = run.get("value", "")
    # Strip surrounding quotes from PBI literal format
    text = raw_text.strip("'") if raw_text.startswith("'") and raw_text.endswith("'") else raw_text
    if not text:
        return None

    result: dict[str, Any] = {"text": text}
    style = run.get("textStyle", {})
    if style:
        text_style: dict[str, Any] = {}
        font_family = style.get("fontFamily", "")
        if isinstance(font_family, str) and font_family.strip("'"):
            text_style["fontFamily"] = font_family.strip("'")
        font_size = style.get("fontSize", "")
        if isinstance(font_size, str) and font_size.strip("'").rstrip("pt"):
            text_style["fontSize"] = int(font_size.strip("'").rstrip("pt"))
        color = style.get("color")
        if isinstance(color, dict):
            from pbi.properties import decode_pbi_value
            decoded = decode_pbi_value(color)
            if decoded:
                text_style["fontColor"] = decoded
        elif isinstance(color, str):
            text_style["fontColor"] = color.strip("'")
        font_weight = style.get("fontWeight", "")
        if isinstance(font_weight, str) and "bold" in font_weight.lower():
            text_style["bold"] = True
        if text_style:
            result["textStyle"] = text_style

    return result


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
