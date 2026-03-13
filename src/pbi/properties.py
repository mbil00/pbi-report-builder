"""Property resolution and editing for PBI visual and page JSON files.

Handles mapping between human-friendly property names (like "background.color")
and the actual PBI JSON structure (nested visualContainerObjects with expr literals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PropertyDef:
    json_path: str | None  # Dot path into the JSON, or None for container objects
    value_type: str  # "number", "string", "boolean", "color", "enum"
    description: str
    enum_values: tuple[str, ...] | None = None
    # For visualContainerObjects properties
    container_key: str | None = None
    container_prop: str | None = None


# ── Visual properties ──────────────────────────────────────────────

VISUAL_PROPERTIES: dict[str, PropertyDef] = {
    # Position
    "position.x": PropertyDef("position.x", "number", "X coordinate"),
    "position.y": PropertyDef("position.y", "number", "Y coordinate"),
    "position.width": PropertyDef("position.width", "number", "Width"),
    "position.height": PropertyDef("position.height", "number", "Height"),
    "position.z": PropertyDef("position.z", "number", "Z-order"),
    "position.tabOrder": PropertyDef("position.tabOrder", "number", "Tab order"),
    "position.angle": PropertyDef("position.angle", "number", "Rotation angle"),
    # Core
    "visualType": PropertyDef("visual.visualType", "string", "Visual chart type"),
    "isHidden": PropertyDef("isHidden", "boolean", "Hidden in view mode"),
    # Container formatting: background
    "background.color": PropertyDef(
        None, "color", "Background color",
        container_key="background", container_prop="color",
    ),
    "background.transparency": PropertyDef(
        None, "number", "Background transparency (0-100)",
        container_key="background", container_prop="transparency",
    ),
    # Container formatting: border
    "border.color": PropertyDef(
        None, "color", "Border color",
        container_key="border", container_prop="color",
    ),
    "border.show": PropertyDef(
        None, "boolean", "Show border",
        container_key="border", container_prop="show",
    ),
    "border.width": PropertyDef(
        None, "number", "Border width",
        container_key="border", container_prop="width",
    ),
    "border.radius": PropertyDef(
        None, "number", "Border radius",
        container_key="border", container_prop="radius",
    ),
    # Container formatting: title
    "title.text": PropertyDef(
        None, "string", "Title text",
        container_key="title", container_prop="text",
    ),
    "title.show": PropertyDef(
        None, "boolean", "Show title",
        container_key="title", container_prop="titleVisibility",
    ),
    "title.color": PropertyDef(
        None, "color", "Title font color",
        container_key="title", container_prop="fontColor",
    ),
    "title.fontSize": PropertyDef(
        None, "number", "Title font size",
        container_key="title", container_prop="fontSize",
    ),
    "title.fontFamily": PropertyDef(
        None, "string", "Title font family",
        container_key="title", container_prop="fontFamily",
    ),
    "title.alignment": PropertyDef(
        None, "enum", "Title alignment",
        container_key="title", container_prop="alignment",
        enum_values=("left", "center", "right"),
    ),
    # Container formatting: subtitle
    "subtitle.text": PropertyDef(
        None, "string", "Subtitle text",
        container_key="subTitle", container_prop="text",
    ),
    "subtitle.show": PropertyDef(
        None, "boolean", "Show subtitle",
        container_key="subTitle", container_prop="subTitleVisibility",
    ),
    "subtitle.color": PropertyDef(
        None, "color", "Subtitle font color",
        container_key="subTitle", container_prop="fontColor",
    ),
    "subtitle.fontSize": PropertyDef(
        None, "number", "Subtitle font size",
        container_key="subTitle", container_prop="fontSize",
    ),
    # Container formatting: padding
    "padding.top": PropertyDef(
        None, "number", "Top padding",
        container_key="padding", container_prop="top",
    ),
    "padding.bottom": PropertyDef(
        None, "number", "Bottom padding",
        container_key="padding", container_prop="bottom",
    ),
    "padding.left": PropertyDef(
        None, "number", "Left padding",
        container_key="padding", container_prop="left",
    ),
    "padding.right": PropertyDef(
        None, "number", "Right padding",
        container_key="padding", container_prop="right",
    ),
    # Container formatting: shadow
    "shadow.color": PropertyDef(
        None, "color", "Drop shadow color",
        container_key="dropShadow", container_prop="color",
    ),
    "shadow.show": PropertyDef(
        None, "boolean", "Show drop shadow",
        container_key="dropShadow", container_prop="show",
    ),
    "shadow.transparency": PropertyDef(
        None, "number", "Shadow transparency",
        container_key="dropShadow", container_prop="transparency",
    ),
    "shadow.position": PropertyDef(
        None, "string", "Shadow position",
        container_key="dropShadow", container_prop="position",
    ),
}

# ── Page properties ────────────────────────────────────────────────

PAGE_PROPERTIES: dict[str, PropertyDef] = {
    "displayName": PropertyDef("displayName", "string", "Page display name"),
    "width": PropertyDef("width", "number", "Page width in pixels"),
    "height": PropertyDef("height", "number", "Page height in pixels"),
    "displayOption": PropertyDef(
        "displayOption", "enum", "Display option",
        enum_values=("FitToPage", "FitToWidth", "ActualSize"),
    ),
    "visibility": PropertyDef(
        "visibility", "enum", "Page visibility",
        enum_values=("AlwaysVisible", "HiddenInViewMode"),
    ),
}


# ── Value encoding/decoding ────────────────────────────────────────

def encode_pbi_value(value: str, value_type: str) -> Any:
    """Encode a CLI string value into PBI JSON format."""
    if value_type == "color":
        color = value if value.startswith("#") else f"#{value}"
        return {"solid": {"color": color}}
    elif value_type == "number":
        num = float(value)
        return {"expr": {"Literal": {"Value": f"{num}D"}}}
    elif value_type == "boolean":
        b = value.lower() in ("true", "1", "yes", "on")
        return {"expr": {"Literal": {"Value": str(b).lower()}}}
    elif value_type == "string":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    elif value_type == "enum":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    return value


def decode_pbi_value(raw: Any) -> Any:
    """Decode a PBI JSON value into a human-readable form."""
    if isinstance(raw, dict):
        # Color: {"solid": {"color": "#hex"}}
        if "solid" in raw:
            return raw["solid"].get("color", raw)
        # Expr literal: {"expr": {"Literal": {"Value": "..."}}}
        if "expr" in raw:
            literal = raw.get("expr", {}).get("Literal", {}).get("Value")
            if literal is not None:
                return _decode_literal(literal)
        return raw
    return raw


def _decode_literal(value: str) -> Any:
    """Decode a PBI literal string like '42D', 'true', or \"'text'\"."""
    if value.endswith("D") or value.endswith("d"):
        try:
            return float(value[:-1])
        except ValueError:
            pass
    if value.endswith("L") or value.endswith("l"):
        try:
            return int(value[:-1])
        except ValueError:
            pass
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    # Quoted string
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


# ── Property get/set operations ────────────────────────────────────

def get_property(data: dict, prop_name: str, registry: dict[str, PropertyDef]) -> Any:
    """Get a property value from a JSON structure."""
    prop_def = registry.get(prop_name)

    if prop_def and prop_def.container_key:
        return _get_container_prop(data, prop_def)
    elif prop_def and prop_def.json_path:
        return _get_by_path(data, prop_def.json_path)
    else:
        # Raw path fallback
        return _get_by_path(data, prop_name)


def set_property(data: dict, prop_name: str, value: str, registry: dict[str, PropertyDef]) -> None:
    """Set a property value in a JSON structure."""
    prop_def = registry.get(prop_name)

    if prop_def and prop_def.enum_values:
        # Validate enum value
        if value not in prop_def.enum_values:
            raise ValueError(
                f'Invalid value "{value}" for {prop_name}. '
                f"Valid: {', '.join(prop_def.enum_values)}"
            )

    if prop_def and prop_def.container_key:
        _set_container_prop(data, prop_def, value)
    elif prop_def and prop_def.json_path:
        coerced = _coerce_simple(value, prop_def.value_type)
        _set_by_path(data, prop_def.json_path, coerced)
    else:
        # Raw path fallback — try to auto-detect type
        _set_by_path(data, prop_name, _auto_coerce(value))


def _get_container_prop(data: dict, prop_def: PropertyDef) -> Any:
    """Read from visualContainerObjects (inside data.visual)."""
    visual = data.get("visual", {})
    objects = visual.get("visualContainerObjects", {})
    entries = objects.get(prop_def.container_key, [])
    if not entries:
        return None
    props = entries[0].get("properties", {})
    raw = props.get(prop_def.container_prop)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _set_container_prop(data: dict, prop_def: PropertyDef, value: str) -> None:
    """Write to visualContainerObjects (inside data.visual), creating structure as needed."""
    visual = data.setdefault("visual", {})
    objects = visual.setdefault("visualContainerObjects", {})
    entries = objects.setdefault(prop_def.container_key, [{}])
    if not entries:
        entries.append({})
    props = entries[0].setdefault("properties", {})
    props[prop_def.container_prop] = encode_pbi_value(value, prop_def.value_type)


def _get_by_path(data: dict, path: str) -> Any:
    """Navigate a dot-separated path into a dict."""
    current = data
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _set_by_path(data: dict, path: str, value: Any) -> None:
    """Set a value at a dot-separated path, creating dicts as needed."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _coerce_simple(value: str, value_type: str) -> Any:
    """Coerce a string to the appropriate Python type for direct JSON properties."""
    if value_type == "number":
        try:
            return int(value)
        except ValueError:
            return float(value)
    elif value_type == "boolean":
        return value.lower() in ("true", "1", "yes", "on")
    return value


def _auto_coerce(value: str) -> Any:
    """Auto-detect type for raw path values."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def list_properties(registry: dict[str, PropertyDef]) -> list[tuple[str, str, str]]:
    """Return (name, type, description) for all properties in a registry."""
    return [
        (name, p.value_type, p.description)
        for name, p in sorted(registry.items())
    ]
