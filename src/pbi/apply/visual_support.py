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
            for warning in sw:
                result.warnings.append(f"{context}: {warning}")
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
    project: Project | None = None,
) -> None:
    """Apply conditional formatting from the YAML spec."""
    from pbi.formatting import (
        GradientStop,
        build_gradient_format,
        build_measure_format,
        build_rules_format,
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

        dot = prop_path.find(".")
        if dot == -1:
            result.errors.append(f"{context}: conditionalFormatting key must be object.prop: {prop_path}")
            continue
        obj_name = prop_path[:dot]
        prop_name = prop_path[dot + 1 :]

        mode = config.get("mode", "measure")
        source = config.get("source", "")
        src_dot = source.find(".")
        if src_dot == -1:
            result.errors.append(f"{context}: conditionalFormatting source must be Table.Field: {source}")
            continue
        src_entity = source[:src_dot]
        src_prop = source[src_dot + 1 :]

        src_field_type = "measure"
        if project is not None and mode != "measure":
            try:
                from pbi.commands.common import resolve_field_type

                src_entity, src_prop, src_field_type = resolve_field_type(project, source, "auto")
            except (ValueError, FileNotFoundError):
                pass

        if dry_run:
            result.properties_set += 1
            continue

        column_ref = config.get("column")

        if mode == "measure":
            value = build_measure_format(src_entity, src_prop)
        elif mode == "gradient":
            min_spec = config.get("min", {})
            max_spec = config.get("max", {})
            mid_spec = config.get("mid")
            min_stop = GradientStop(str(min_spec.get("color", "#FF0000")), float(min_spec.get("value", 0)))
            max_stop = GradientStop(str(max_spec.get("color", "#00FF00")), float(max_spec.get("value", 100)))
            mid_stop = (
                GradientStop(str(mid_spec.get("color", "")), float(mid_spec.get("value", 50)))
                if mid_spec
                else None
            )
            null_strategy = config.get("nullStrategy")
            value = build_gradient_format(
                src_entity,
                src_prop,
                min_stop,
                max_stop,
                mid_stop,
                null_strategy=null_strategy,
                field_type=src_field_type,
            )
        elif mode == "rules":
            rules_list = config.get("rules", [])
            if not isinstance(rules_list, list) or not rules_list:
                result.errors.append(
                    f"{context}: conditionalFormatting rules mode requires a non-empty 'rules' list."
                )
                continue
            else_spec = config.get("else")
            else_color = (
                else_spec.get("color")
                if isinstance(else_spec, dict)
                else else_spec
                if isinstance(else_spec, str)
                else None
            )
            parsed_rules = []
            for rule in rules_list:
                if not isinstance(rule, dict):
                    result.errors.append(
                        f"{context}: each rule must be a mapping with 'if' and 'color' keys."
                    )
                    break
                rule_value = rule.get("if")
                rule_color = rule.get("color")
                if rule_value is None or rule_color is None:
                    result.errors.append(f"{context}: each rule must have 'if' and 'color' keys.")
                    break
                parsed_rules.append({"value": str(rule_value), "color": str(rule_color)})
            else:
                value = build_rules_format(
                    src_entity,
                    src_prop,
                    parsed_rules,
                    else_color=else_color,
                    field_type=src_field_type,
                )
            if len(parsed_rules) != len(rules_list):
                continue
        else:
            result.errors.append(
                f"{context}: conditionalFormatting mode must be 'measure', 'gradient', or 'rules': {mode}"
            )
            continue

        set_conditional_format(data, obj_name, prop_name, value, column=column_ref)
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
