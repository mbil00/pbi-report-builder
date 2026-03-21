"""Shared helpers for visual commands."""

from __future__ import annotations

import copy

import typer

from pbi.images import build_image_resource_property
from pbi.properties import (
    VISUAL_PROPERTIES,
    canonical_object_property_name,
    get_known_default,
    get_property,
    set_property,
)
from pbi.textbox import (
    parse_textbox_style_value,
    set_textbox_content,
    textbox_text,
    textbox_text_style_value,
)

from ..common import console, get_project


def resolve_page_target(project, page: str):
    """Resolve a project and page reference with CLI-friendly errors."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    return proj, pg


def resolve_visual_target(project, page: str, visual: str):
    """Resolve a project, page, and visual reference with CLI-friendly errors."""
    proj, pg = resolve_page_target(project, page)
    try:
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    return proj, pg, vis


def collect_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool = True,
) -> list[tuple[str, str]]:
    """Collect explicit visual properties for inspection views."""
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if include_core:
        for prop_name, prop_def in VISUAL_PROPERTIES.items():
            if not prop_def.json_path:
                continue
            value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
            if value is None:
                continue
            key = (prop_name, str(value))
            if key in seen:
                continue
            seen.add(key)
            rows.append((prop_name, str(value)))

    from pbi.properties import decode_pbi_value

    for section in ("visualContainerObjects", "objects"):
        section_data = visual_data.get("visual", {}).get(section, {})
        if not isinstance(section_data, dict):
            continue
        for obj_name, entries in section_data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                selector = entry.get("selector", {})
                selector_name = selector.get("metadata") or selector.get("id")
                for prop_name, raw_value in entry.get("properties", {}).items():
                    decoded = decode_pbi_value(raw_value)
                    canonical = canonical_object_property_name(
                        obj_name,
                        prop_name,
                        VISUAL_PROPERTIES,
                        objects_path=section,
                        selector=selector.get("id"),
                    )
                    label = canonical
                    if selector_name:
                        label = f"{label} [{selector_name}]"
                    key = (label, str(decoded))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append((label, str(decoded)))

    return rows


def resolve_visual_property_value(
    visual_data: dict,
    prop_name: str,
    *,
    include_defaults: bool = False,
) -> tuple[object | None, str]:
    """Resolve an explicit or known-default value for a single visual property."""
    value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
    if value is not None:
        return value, "explicit"
    if include_defaults:
        visual_type = visual_data.get("visual", {}).get("visualType")
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is not None:
            return default, "default"
    return None, ""


def collect_effective_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool,
    include_defaults: bool,
) -> list[tuple[str, str, str]]:
    """Collect effective visual properties with their source."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    visual_type = visual_data.get("visual", {}).get("visualType")

    explicit_rows = collect_visual_property_rows(visual_data, include_core=include_core)
    for prop_name, value in explicit_rows:
        rows.append((prop_name, value, "explicit"))
        seen.add(prop_name)

    if not include_defaults:
        return rows

    for prop_name, prop_def in sorted(VISUAL_PROPERTIES.items()):
        group = "core" if prop_def.json_path else "container"
        if not include_core and group == "core":
            continue
        if prop_def.visual_types and visual_type not in prop_def.visual_types:
            continue
        if prop_name in seen:
            continue
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is None:
            continue
        rows.append((prop_name, str(default), "default"))

    return rows


def flatten_visual_diff_spec(
    visual_spec: dict,
    *,
    include_core: bool,
) -> dict[str, str]:
    """Flatten a canonical exported visual spec into path/value rows for diffing."""
    filtered = copy.deepcopy(visual_spec)
    filtered.pop("id", None)
    filtered.pop("name", None)
    if not include_core:
        for key in ("position", "size", "isHidden"):
            filtered.pop(key, None)
    else:
        position = filtered.get("position")
        if isinstance(position, str):
            parts = [part.strip() for part in position.split(",", 1)]
            if len(parts) == 2:
                filtered["position"] = {"x": parts[0], "y": parts[1]}
        size = filtered.get("size")
        if isinstance(size, str):
            parts = [part.strip() for part in size.lower().split("x", 1)]
            if len(parts) == 2:
                filtered["size"] = {"width": parts[0], "height": parts[1]}

    return flatten_diff_spec(filtered)


def flatten_diff_spec(
    spec: dict,
    *,
    ignore_keys: set[str] | None = None,
) -> dict[str, str]:
    """Flatten a structured exported spec into dotted path/value rows."""
    filtered = copy.deepcopy(spec)
    for key in ignore_keys or set():
        filtered.pop(key, None)

    rows: dict[str, str] = {}
    _flatten_diff_value(filtered, rows)
    return rows


def _flatten_diff_value(
    value: object,
    rows: dict[str, str],
    *,
    prefix: str = "",
) -> None:
    """Recursively flatten a nested exported spec into dotted paths."""
    if isinstance(value, dict):
        if not value and prefix:
            rows[prefix] = "{}"
            return
        for key, child in value.items():
            child_prefix = key if not prefix else f"{prefix}.{key}"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    if isinstance(value, list):
        if not value:
            rows[prefix] = "[]"
            return
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    rows[prefix] = _stringify_diff_value(value)


def _stringify_diff_value(value: object) -> str:
    """Stringify scalar values for visual diff output."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def prepare_visual_property_updates(
    data: dict,
    pairs: list[tuple[str, str]],
    *,
    measure_ref: str | None = None,
    project=None,
) -> tuple[dict, list[tuple[str, object, object]]]:
    """Apply a property batch to a copy of the visual for validation."""
    updated = copy.deepcopy(data)
    changes: list[tuple[str, object, object]] = []
    ordered_pairs = sorted(
        pairs,
        key=lambda item: 0 if item[0] in {"type", "visualType"} else 1,
    )
    for prop, value in ordered_pairs:
        visual_type = updated.get("visual", {}).get("visualType")
        if prop in {"type", "visualType"}:
            old = updated.get("visual", {}).get("visualType")
            new = _apply_visual_type_update(updated, value)
            changes.append((prop, old, new))
            continue

        if prop in {"chart:image.sourceFile", "image.sourceFile"}:
            if project is None:
                raise ValueError("image.sourceFile requires project context.")
            old = _current_image_resource_ref(updated)
            _set_visual_image_source(updated, project, value)
            changes.append((prop, old, value))
            continue

        if visual_type == "textbox":
            if prop in {"chart:paragraph.text", "paragraph.text"}:
                old = textbox_text(updated)
                set_textbox_content(updated, text=value)
                changes.append((prop, old, textbox_text(updated)))
                continue

            if prop == "text":
                old = textbox_text(updated)
                set_textbox_content(updated, text=value)
                changes.append((prop, old, textbox_text(updated)))
                continue

            textbox_style_key = _textbox_style_key(prop)
            if textbox_style_key is not None:
                old = textbox_text_style_value(updated, textbox_style_key)
                parsed = parse_textbox_style_value(textbox_style_key, value)
                set_textbox_content(updated, style_updates={textbox_style_key: parsed})
                new = textbox_text_style_value(updated, textbox_style_key)
                changes.append((prop, old, new))
                continue

        old = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        try:
            set_property(updated, prop, value, VISUAL_PROPERTIES, measure_ref=measure_ref)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        changes.append((prop, old, new))
    return updated, changes


def _apply_visual_type_update(data: dict, visual_type: str) -> str:
    from pbi.roles import get_visual_roles, normalize_visual_type

    canonical = normalize_visual_type(visual_type)
    visual = data.setdefault("visual", {})
    visual["visualType"] = canonical
    query_state = visual.setdefault("query", {}).setdefault("queryState", {})
    for role in get_visual_roles(canonical):
        query_state.setdefault(role["name"], {"projections": []})
    return canonical


def _set_visual_image_source(data: dict, project, resource_ref: str) -> None:
    set_property(data, "chart:image.sourceType", "image", VISUAL_PROPERTIES)
    objects = data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault("image", [])
    if entries:
        target = entries[0]
    else:
        target = {"properties": {}}
        entries.append(target)
    target.setdefault("properties", {})["sourceFile"] = build_image_resource_property(project, resource_ref)


def _current_image_resource_ref(data: dict) -> str | None:
    entries = data.get("visual", {}).get("objects", {}).get("image", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = entry.get("properties", {}).get("sourceFile", {})
        image = source.get("image", {}) if isinstance(source, dict) else {}
        item = (
            image.get("url", {})
            .get("expr", {})
            .get("ResourcePackageItem", {})
            .get("ItemName")
        )
        if item:
            return item
    return None


def _textbox_style_key(prop: str) -> str | None:
    if prop.startswith("text."):
        key = prop.split(".", 1)[1]
    elif prop.startswith("textStyle."):
        key = prop.split(".", 1)[1]
    else:
        return None
    return key if key in {"fontFamily", "fontSize", "fontColor", "bold", "italic"} else None
