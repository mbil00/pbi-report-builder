"""Shared helpers for instantiating visuals from exported YAML specs."""

from __future__ import annotations

from typing import Any

from pbi.apply.visual_support import apply_raw_visual_payload, parse_position, parse_size
from pbi.filters import add_categorical_filter, add_exclude_filter
from pbi.project import Page, Project, Visual, sanitize_visual_name
from pbi.properties import VISUAL_PROPERTIES, set_property
from pbi.roles import normalize_visual_role
from pbi.textbox import set_textbox_content


def create_visual_from_spec(
    project: Project,
    page: Page,
    spec: dict[str, Any],
    *,
    x: int | float | None = None,
    y: int | float | None = None,
    name: str | None = None,
) -> Visual:
    """Create one visual from an apply/export-compatible visual spec."""
    vis_type = str(spec.get("type", "shape"))
    base_x, base_y = parse_position(spec.get("position", "0, 0"))
    width, height = parse_size(spec.get("size", "300 x 200"))
    visual = project.create_visual(
        page,
        vis_type,
        x=base_x if x is None else x,
        y=base_y if y is None else y,
        width=width,
        height=height,
    )

    target_name = name or spec.get("name")
    if isinstance(target_name, str) and target_name:
        visual.data["name"] = sanitize_visual_name(target_name)

    apply_visual_spec(project, visual, spec)
    visual.save()
    return visual


def apply_visual_spec(project: Project, visual: Visual, spec: dict[str, Any]) -> None:
    """Apply exported visual spec properties/bindings/filters to a created visual."""
    skip_keys = {
        "id",
        "name",
        "type",
        "position",
        "size",
        "bindings",
        "sort",
        "filters",
        "pbir",
        "style",
        "isHidden",
        "text",
        "textStyle",
        "group",
    }

    for key, value in spec.items():
        if key in skip_keys:
            continue
        if isinstance(value, dict):
            for subkey, subval in value.items():
                prop_name = f"{key}.{subkey}"
                try:
                    set_property(visual.data, prop_name, str(subval), VISUAL_PROPERTIES)
                except (ValueError, KeyError):
                    pass
        elif isinstance(value, (str, int, float, bool)):
            try:
                set_property(visual.data, key, str(value), VISUAL_PROPERTIES)
            except (ValueError, KeyError):
                pass

    bindings = spec.get("bindings", {})
    if isinstance(bindings, dict):
        for role, fields in bindings.items():
            canonical_role = normalize_visual_role(visual.visual_type, role)
            field_list = [fields] if isinstance(fields, str) else fields
            if not isinstance(field_list, list):
                continue
            for field_ref in field_list:
                if not isinstance(field_ref, str) or "." not in field_ref:
                    continue
                is_measure = "(measure)" in field_ref
                clean_ref = field_ref.replace("(measure)", "").strip()
                dot = clean_ref.find(".")
                entity = clean_ref[:dot]
                prop = clean_ref[dot + 1 :]
                field_type = "measure" if is_measure else "column"
                project.add_binding(visual, canonical_role, entity, prop, field_type=field_type)

    if spec.get("isHidden"):
        visual.data["isHidden"] = True

    filters = spec.get("filters", [])
    if isinstance(filters, list):
        for filt in filters:
            if not isinstance(filt, dict):
                continue
            field_ref = filt.get("field", "")
            values = filt.get("values", [])
            mode = filt.get("mode", "include")
            if field_ref and "." in field_ref and values:
                dot = field_ref.find(".")
                entity = field_ref[:dot]
                prop = field_ref[dot + 1 :]
                try:
                    if mode == "exclude":
                        add_exclude_filter(visual.data, entity, prop, values=values)
                    else:
                        add_categorical_filter(visual.data, entity, prop, values=values)
                except (ValueError, KeyError):
                    pass

    pbir = spec.get("pbir")
    if isinstance(pbir, dict):
        apply_raw_visual_payload(visual, pbir)

    if visual.visual_type == "textbox" and isinstance(spec.get("text"), str):
        style = spec.get("textStyle", {})
        set_textbox_content(
            visual.data,
            text=spec["text"],
            style_updates=style if isinstance(style, dict) else None,
        )
