"""Detailed YAML export for round-trip with pbi apply.

Produces a complete YAML representation of pages and visuals that can be
fed back into pbi apply to reproduce or update the report state.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml

from pbi.project import Project, Page, Visual
from pbi.properties import decode_pbi_value
from pbi.filters import filter_field_refs, get_filters, parse_filter


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

    # Page-level objects (background, outspace)
    page_objects = page.data.get("objects", {})
    if page_objects:
        _export_page_objects(page_dict, page_objects)

    # Page-level filters
    page_filters = _export_filters(page.data)
    if page_filters:
        page_dict["filters"] = page_filters

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


def _export_visual(project: Project, visual: Visual) -> dict:
    """Export a single visual as a dict."""
    pos = visual.position
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

    # Container formatting (title, background, border, etc.)
    container_objs = visual.data.get("visual", {}).get("visualContainerObjects", {})
    if container_objs:
        _export_object_properties(result, container_objs)

    # Chart formatting (legend, axes, labels, etc.)
    chart_objs = visual.data.get("visual", {}).get("objects", {})
    if chart_objs:
        _export_object_properties(result, chart_objs)

    # Data bindings
    bindings = project.get_bindings(visual)
    if bindings:
        bindings_dict: dict[str, Any] = {}
        by_role: dict[str, list[tuple[str, str, str]]] = {}
        for role, entity, prop, ftype in bindings:
            by_role.setdefault(role, []).append((entity, prop, ftype))

        for role, fields in by_role.items():
            if len(fields) == 1:
                entity, prop, ftype = fields[0]
                ref = f"{entity}.{prop}"
                if ftype == "measure":
                    ref += " (measure)"
                bindings_dict[role] = ref
            else:
                refs = []
                for entity, prop, ftype in fields:
                    ref = f"{entity}.{prop}"
                    if ftype == "measure":
                        ref += " (measure)"
                    refs.append(ref)
                bindings_dict[role] = refs
        result["bindings"] = bindings_dict

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
    raw_visual = copy.deepcopy(visual.data)
    raw_visual.pop("$schema", None)
    raw_visual.pop("name", None)
    raw_visual.pop("position", None)
    if raw_visual:
        result["pbir"] = raw_visual

    return result


def _export_object_properties(target: dict, objects: dict) -> None:
    """Export PBI object collections into nested YAML-friendly dicts.

    Converts {"title": [{"properties": {"show": {...}, "text": {...}}}]}
    into {"title": {"show": true, "text": "Hello"}}.
    """
    for obj_key, entries in objects.items():
        if not isinstance(entries, list) or not entries:
            continue

        # Use known property names to find friendly CLI names
        obj_dict: dict[str, Any] = {}
        for entry in entries:
            selector = entry.get("selector")
            props = entry.get("properties", {})
            for prop_name, raw_val in props.items():
                decoded = decode_pbi_value(raw_val)
                if selector:
                    sel_id = selector.get("id", selector.get("metadata", "?"))
                    key = f"{prop_name} [{sel_id}]"
                else:
                    key = prop_name
                obj_dict[key] = decoded

        if obj_dict:
            # Find a friendly prefix if this matches a registered property group
            friendly_key = _find_friendly_key(obj_key)
            target[friendly_key] = obj_dict


def _find_friendly_key(obj_key: str) -> str:
    """Map PBI object keys to friendlier YAML keys."""
    mapping = {
        "visualContainerObjects": "container",
        "dropShadow": "shadow",
        "subTitle": "subtitle",
        "visualHeader": "header",
        "visualTooltip": "tooltip",
        "visualLink": "action",
        "categoryAxis": "xAxis",
        "valueAxis": "yAxis",
        "lineStyles": "line",
        "dataPoint": "dataColors",
    }
    return mapping.get(obj_key, obj_key)


def _export_page_objects(page_dict: dict, objects: dict) -> None:
    """Export page-level objects (background, outspace)."""
    for obj_key, entries in objects.items():
        if not isinstance(entries, list) or not entries:
            continue
        props: dict[str, Any] = {}
        for entry in entries:
            for prop_name, raw_val in entry.get("properties", {}).items():
                props[prop_name] = decode_pbi_value(raw_val)
        if props:
            page_dict[obj_key] = props


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
