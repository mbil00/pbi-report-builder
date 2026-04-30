"""Shared visual apply helpers."""

from __future__ import annotations

import copy
import re
from typing import Any

from .state import ApplyResult
from pbi.project import Project, Visual
from pbi.properties import (
    VISUAL_PROPERTIES,
    normalize_property_name,
    set_property,
)
from pbi.roundtrip import iter_nested_property_assignments
from pbi.styles import StylePreset, get_style
from pbi.textbox import set_textbox_content


def record_schema_warnings(
    result: ApplyResult,
    *,
    context: str,
    warnings: list[str],
) -> None:
    """Record schema-derived property warnings with apply context."""
    for warning in warnings:
        result.warnings.append(f"{context}: Schema: {warning}")


def apply_nested_properties(
    data: dict,
    spec: dict,
    *,
    exclude_keys: set[str],
    registry: dict,
    result: ApplyResult,
    context: str,
    dry_run: bool,
    prefix: str = "",
    ignore_selector_errors: bool = False,
    ignore_unknown_roots: set[str] | None = None,
) -> None:
    """Flatten nested YAML dicts into dot-separated property names and apply them."""
    for prop_name, value in iter_nested_property_assignments(
        spec,
        exclude_keys=exclude_keys,
        prefix=prefix,
    ):
        str_value = str(value)
        if dry_run:
            result.properties_set += 1
            continue
        try:
            sw = set_property(data, prop_name, str_value, registry)
            result.properties_set += 1
            record_schema_warnings(result, context=context, warnings=sw)
        except ValueError as e:
            if ignore_selector_errors and "[" in prop_name and "]" in prop_name:
                continue
            root = prop_name.split(".", 1)[0]
            if ignore_unknown_roots and root in ignore_unknown_roots:
                continue
            result.errors.append(f"{context}: {prop_name}: {e}")


def expand_visual_shorthand(spec: dict[str, Any]) -> dict[str, Any]:
    """Expand convenient visual YAML shorthands into canonical property mappings."""
    title = spec.get("title")
    if not isinstance(title, str):
        return spec

    expanded = dict(spec)
    expanded["title"] = {"show": True, "text": title}
    return expanded


def raw_object_roots(raw_pbir: dict) -> set[str]:
    """Return YAML object roots projected from the raw visual payload."""
    visual = raw_pbir.get("visual", {})
    roots = set(visual.get("objects", {}).keys())
    roots.update(visual.get("visualContainerObjects", {}).keys())
    roots.update(
        {
            "shadow" if "dropShadow" in roots else "",
            "subtitle" if "subTitle" in roots else "",
            "header" if "visualHeader" in roots else "",
            "tooltip" if "visualTooltip" in roots else "",
            "action" if "visualLink" in roots else "",
            "xAxis" if "categoryAxis" in roots else "",
            "yAxis" if "valueAxis" in roots else "",
            "line" if "lineStyles" in roots else "",
            "dataColors" if "dataPoint" in roots else "",
        }
    )
    roots.discard("")
    return roots


def apply_textbox_content(
    visual: Visual,
    vis_spec: dict,
    result: ApplyResult,
) -> None:
    """Apply plain text content to a textbox visual."""
    text = str(vis_spec.get("text", ""))
    style = vis_spec.get("textStyle", {})
    if not isinstance(style, dict):
        style = {}
    set_textbox_content(visual.data, text=text, style_updates=style)
    result.properties_set += 1


def apply_conditional_formatting(
    data: dict,
    cf_spec: dict,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
    visual_type: str | None = None,
    project: Project | None = None,
    model: Any = None,
) -> None:
    """Apply conditional formatting from the YAML spec."""
    from pbi.fields import resolve_field_info
    from pbi.formatting import (
        conditional_formatting_intent_from_config,
        resolve_conditional_formatting,
        set_conditional_format,
    )
    if not isinstance(cf_spec, dict):
        result.errors.append(
            f"{context}: conditionalFormatting must be a mapping of property -> config, not a {type(cf_spec).__name__}."
        )
        return

    for prop_path, config in cf_spec.items():
        if not isinstance(config, dict):
            result.errors.append(f"{context}: conditionalFormatting.{prop_path} must be a mapping.")
            continue

        try:
            intent = conditional_formatting_intent_from_config(prop_path, config)
        except ValueError as e:
            result.errors.append(f"{context}: {e}")
            continue

        def _field_resolver(field_ref: str, preferred_type: str) -> tuple[str, str, str, str | None]:
            if project is None:
                entity, prop = field_ref.split(".", 1)
                return entity, prop, "measure" if preferred_type == "measure" else "column", None
            effective_type = "measure" if preferred_type == "measure" and model is None else (
                "auto" if preferred_type == "measure" else preferred_type
            )
            return resolve_field_info(
                project,
                field_ref,
                effective_type,
                model=model,
                strict=True,
            )

        resolved = resolve_conditional_formatting(
            intent,
            field_resolver=_field_resolver,
            visual_type=visual_type,
        )
        if resolved.errors:
            result.errors.extend(f"{context}: {error}" for error in resolved.errors)
            continue
        result.warnings.extend(f"{context}: {warning}" for warning in resolved.warnings)

        if dry_run:
            result.properties_set += 1
            continue

        set_conditional_format(
            data,
            resolved.target.object_name,
            resolved.target.property_name,
            resolved.value or {},
            column=resolved.column,
        )
        result.properties_set += 1


def parse_number(value: Any) -> int | float:
    """Parse a JSON/YAML scalar into an int or float."""
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)

    text = str(value).strip()
    number = float(text)
    return int(number) if number.is_integer() else number


def parse_position(value: Any) -> tuple[int | float, int | float]:
    """Parse position from '50, 80' or a dict {'x': 50, 'y': 80}."""
    if isinstance(value, dict):
        return parse_number(value.get("x", 0)), parse_number(value.get("y", 0))
    parts = str(value).split(",")
    if len(parts) == 2:
        return parse_number(parts[0]), parse_number(parts[1])
    return 0, 0


def parse_size(value: Any) -> tuple[int | float, int | float]:
    """Parse size from '600 x 400' or a dict {'width': 600, 'height': 400}."""
    if isinstance(value, dict):
        return parse_number(value.get("width", 300)), parse_number(value.get("height", 200))
    text = str(value)
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*x\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if match:
        return parse_number(match.group(1)), parse_number(match.group(2))
    return 300, 200


def apply_raw_visual_payload(visual: Visual, raw_pbir: dict) -> None:
    """Restore the exact exported PBIR payload for a visual."""
    for key, value in raw_pbir.items():
        if isinstance(value, dict) and isinstance(visual.data.get(key), dict):
            _deep_merge_dict(visual.data[key], value)
        else:
            visual.data[key] = copy.deepcopy(value)


def _deep_merge_dict(target: dict, source: dict) -> None:
    """Merge source into target, preserving scaffold fields already created."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge_dict(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def count_dry_run_changes(vis_spec: dict, result: ApplyResult) -> None:
    """Count property changes for dry-run reporting."""
    exclude = {"id", "name", "type", "position", "size", "bindings", "sort", "filters", "isHidden", "pbir", "style"}
    for key, value in vis_spec.items():
        if key in exclude:
            continue
        if isinstance(value, dict):
            result.properties_set += len(value)
        else:
            result.properties_set += 1

    if "bindings" in vis_spec:
        for _role, ref in vis_spec["bindings"].items():
            if isinstance(ref, list):
                result.bindings_added += len(ref)
            else:
                result.bindings_added += 1

    if "filters" in vis_spec:
        result.filters_added += len(vis_spec["filters"])


def resolve_style_assignments(
    project: Project,
    style_spec: Any,
    *,
    visual_type: str | None,
    style_cache: dict[str, StylePreset],
) -> list[tuple[str, str, Any]]:
    """Resolve ordered style references into applicable property assignments."""
    if style_spec is None:
        return []
    if isinstance(style_spec, str):
        style_names = [style_spec]
    elif isinstance(style_spec, list) and all(isinstance(item, str) for item in style_spec):
        style_names = style_spec
    else:
        raise ValueError("'style' must be a string or list of strings.")

    assignments: list[tuple[str, str, Any]] = []
    for style_name in style_names:
        if style_name not in style_cache:
            style_cache[style_name] = get_style(project, style_name)
        preset = style_cache[style_name]
        for raw_prop_name, value in preset.properties.items():
            prop_name = normalize_property_name(raw_prop_name, VISUAL_PROPERTIES)
            prop_def = VISUAL_PROPERTIES.get(prop_name)
            if visual_type and prop_def and prop_def.visual_types and visual_type not in prop_def.visual_types:
                continue
            assignments.append((style_name, prop_name, value))
    return assignments
