"""Conditional formatting for PBI visual objects.

Supports measure-based (color by DAX measure) and FillRule gradient
(2-stop or 3-stop color scale) conditional formatting on any visual
object property.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ── Data types ────────────────────────────────────────────────────

@dataclass
class GradientStop:
    """A color stop in a gradient."""
    color: str   # hex color, e.g. "#FF0000"
    value: float  # numeric threshold


@dataclass
class ConditionalFormatInfo:
    """Parsed conditional formatting entry for display."""
    object_name: str
    property_name: str
    format_type: str  # "measure", "gradient2", "gradient3", "rules"
    field_ref: str  # "Table.Field" for the driving measure/field
    details: str  # Human-readable summary
    column: str = ""  # Per-column target (empty = all columns)


# ── JSON node builders ────────────────────────────────────────────

def _measure_expr(entity: str, prop: str) -> dict:
    """Build a PBI Measure expression node."""
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def _literal_expr(value: str) -> dict:
    """Build a PBI Literal expression node."""
    return {"Literal": {"Value": value}}


def _wildcard_selector() -> dict:
    """Build the standard dataViewWildcard selector for conditional formatting."""
    return {"data": [{"dataViewWildcard": {"matchingOption": 0}}]}


# ── Format builders ───────────────────────────────────────────────

def build_measure_format(entity: str, prop: str) -> dict:
    """Build a measure-based conditional formatting value.

    Returns the property value dict that replaces a static color value.
    The measure should return a hex color string at runtime.
    """
    return {
        "solid": {
            "color": {
                "expr": _measure_expr(entity, prop)
            }
        }
    }


def build_gradient_format(
    input_entity: str,
    input_prop: str,
    min_stop: GradientStop,
    max_stop: GradientStop,
    mid_stop: GradientStop | None = None,
) -> dict:
    """Build a FillRule gradient conditional formatting value.

    If mid_stop is provided, uses linearGradient3; otherwise linearGradient2.
    """
    def _stop(stop: GradientStop) -> dict:
        color = stop.color if stop.color.startswith("#") else f"#{stop.color}"
        return {
            "color": {"expr": _literal_expr(f"'{color}'")},
            "value": {"expr": _literal_expr(f"{stop.value}D")},
        }

    if mid_stop is not None:
        gradient = {
            "linearGradient3": {
                "min": _stop(min_stop),
                "mid": _stop(mid_stop),
                "max": _stop(max_stop),
            }
        }
    else:
        gradient = {
            "linearGradient2": {
                "min": _stop(min_stop),
                "max": _stop(max_stop),
            }
        }

    return {
        "solid": {
            "color": {
                "expr": {
                    "FillRule": {
                        "Input": _measure_expr(input_entity, input_prop),
                        "FillRule": gradient,
                    }
                }
            }
        }
    }


def build_rules_format(
    input_entity: str,
    input_prop: str,
    rules: list[dict],
    *,
    else_color: str | None = None,
) -> dict:
    """Build a rules-based conditional formatting value.

    Each rule is a dict with 'value' (string to match) and 'color' (hex color).
    Uses Conditional expression with equality comparisons.
    """
    def _color_literal(color: str) -> dict:
        c = color if color.startswith("#") else f"#{color}"
        return _literal_expr(f"'{c}'")

    cases = []
    for rule in rules:
        cases.append({
            "Condition": {
                "Comparison": {
                    "ComparisonKind": 0,
                    "Left": _measure_expr(input_entity, input_prop),
                    "Right": _literal_expr(f"'{rule['value']}'"),
                }
            },
            "Value": _color_literal(rule["color"]),
        })

    conditional: dict = {"Cases": cases}
    if else_color:
        conditional["Else"] = _color_literal(else_color)

    return {
        "solid": {
            "color": {
                "expr": {
                    "Conditional": conditional,
                }
            }
        }
    }


def _column_selector(column_ref: str) -> dict:
    """Build a per-column selector targeting a specific field."""
    return {
        "data": [{"dataViewWildcard": {"matchingOption": 0}}],
        "metadata": column_ref,
    }


# ── Read/display ──────────────────────────────────────────────────

def get_conditional_formats(visual_data: dict) -> list[ConditionalFormatInfo]:
    """Extract all conditional formatting entries from a visual."""
    results = []
    objects = visual_data.get("visual", {}).get("objects", {})

    for obj_name, entries in objects.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            props = entry.get("properties", {})
            selector = entry.get("selector", {})
            column = selector.get("metadata", "")
            for prop_name, prop_val in props.items():
                info = _parse_conditional_value(obj_name, prop_name, prop_val)
                if info is not None:
                    info.column = column
                    results.append(info)

    return results


def _parse_conditional_value(
    obj_name: str, prop_name: str, value: Any,
) -> ConditionalFormatInfo | None:
    """Check if a property value contains conditional formatting."""
    if not isinstance(value, dict):
        return None

    # Drill into {"solid": {"color": {"expr": ...}}}
    color_node = value.get("solid", {}).get("color", {})
    if not isinstance(color_node, dict):
        return None

    expr = color_node.get("expr")
    if expr is None:
        return None

    # Measure-based
    if "Measure" in expr:
        m = expr["Measure"]
        entity = m.get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
        prop = m.get("Property", "?")
        return ConditionalFormatInfo(
            object_name=obj_name,
            property_name=prop_name,
            format_type="measure",
            field_ref=f"{entity}.{prop}",
            details=f"Measure: {entity}.{prop}",
        )

    # Rules-based (Conditional)
    if "Conditional" in expr:
        cond = expr["Conditional"]
        cases = cond.get("Cases", [])
        # Try to extract source field from first case's Condition
        entity, prop = "?", "?"
        if cases:
            left = cases[0].get("Condition", {}).get("Comparison", {}).get("Left", {})
            for key in ("Measure", "Column"):
                if key in left:
                    entity = left[key].get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
                    prop = left[key].get("Property", "?")
                    break

        rule_parts = []
        for case in cases:
            cmp = case.get("Condition", {}).get("Comparison", {})
            right_val = _extract_literal(cmp.get("Right", {}))
            color_val = _extract_literal(case.get("Value", {}))
            rule_parts.append(f"{right_val}={color_val}")

        else_node = cond.get("Else")
        if else_node:
            rule_parts.append(f"else={_extract_literal(else_node)}")

        return ConditionalFormatInfo(
            object_name=obj_name,
            property_name=prop_name,
            format_type="rules",
            field_ref=f"{entity}.{prop}",
            details=", ".join(rule_parts),
        )

    # FillRule gradient
    if "FillRule" in expr:
        fr = expr["FillRule"]
        input_expr = fr.get("Input", {})
        # Input can be Measure or Column
        for key in ("Measure", "Column"):
            if key in input_expr:
                entity = input_expr[key].get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
                prop = input_expr[key].get("Property", "?")
                break
        else:
            entity, prop = "?", "?"

        rule = fr.get("FillRule", {})
        if "linearGradient3" in rule:
            fmt_type = "gradient3"
            details = _summarize_gradient(rule["linearGradient3"])
        elif "linearGradient2" in rule:
            fmt_type = "gradient2"
            details = _summarize_gradient(rule["linearGradient2"])
        else:
            fmt_type = "gradient"
            details = "Unknown gradient"

        return ConditionalFormatInfo(
            object_name=obj_name,
            property_name=prop_name,
            format_type=fmt_type,
            field_ref=f"{entity}.{prop}",
            details=details,
        )

    return None


def _summarize_gradient(gradient: dict) -> str:
    """Build a human-readable summary like '#FF0000@0 -> #FFFF00@50 -> #00FF00@100'."""
    parts = []
    for key in ("min", "mid", "max"):
        stop = gradient.get(key)
        if stop is None:
            continue
        color = _extract_literal(stop.get("color", {}))
        val = _extract_literal(stop.get("value", {}))
        parts.append(f"{color} @ {val}")
    return " -> ".join(parts)


def _extract_literal(node: dict) -> str:
    """Extract a literal value from {'expr': {'Literal': {'Value': ...}}} or {'Literal': {'Value': ...}}."""
    # Support both wrapped (gradient stops) and unwrapped (rules) forms
    if "expr" in node:
        raw = node["expr"].get("Literal", {}).get("Value", "?")
    elif "Literal" in node:
        raw = node["Literal"].get("Value", "?")
    else:
        raw = "?"
    if isinstance(raw, str):
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1]
        if raw.endswith("D") or raw.endswith("d"):
            return raw[:-1]
    return str(raw)


# ── Set/clear operations ─────────────────────────────────────────

def set_conditional_format(
    visual_data: dict,
    object_name: str,
    property_name: str,
    value: dict,
    *,
    column: str | None = None,
) -> None:
    """Set conditional formatting on a visual object property.

    Creates or updates a selector-bearing entry in the object array,
    leaving the base static entry (index 0, no selector) untouched.

    If *column* is provided, the formatting targets only that column
    (using a metadata selector); otherwise it applies to all data points.
    """
    objects = visual_data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault(object_name, [])

    selector = _column_selector(column) if column else _wildcard_selector()
    match_metadata = column or ""

    # Find existing entry matching the same selector shape
    target = None
    for entry in entries:
        sel = entry.get("selector", {})
        dw = sel.get("data", [])
        has_wildcard = any("dataViewWildcard" in d for d in dw)
        entry_metadata = sel.get("metadata", "")
        if has_wildcard and entry_metadata == match_metadata:
            target = entry
            break

    if target is None:
        target = {"selector": selector, "properties": {}}
        entries.append(target)

    target.setdefault("properties", {})[property_name] = value


def clear_conditional_format(
    visual_data: dict,
    object_name: str,
    property_name: str,
) -> bool:
    """Remove conditional formatting for a specific property.

    Removes the property from any selector-bearing entry.
    If that leaves the entry empty, removes the entry entirely.
    Returns True if something was removed.
    """
    objects = visual_data.get("visual", {}).get("objects", {})
    entries = objects.get(object_name, [])

    removed = False
    to_remove = []
    for i, entry in enumerate(entries):
        sel = entry.get("selector", {})
        dw = sel.get("data", [])
        if any("dataViewWildcard" in d for d in dw):
            props = entry.get("properties", {})
            if property_name in props:
                del props[property_name]
                removed = True
            if not props:
                to_remove.append(i)

    for i in reversed(to_remove):
        entries.pop(i)

    if not entries:
        objects.pop(object_name, None)

    return removed
