"""Property resolution and editing for PBI visual and page JSON files.

Handles mapping between human-friendly property names (like "background.color")
and the actual PBI JSON structure (nested visualContainerObjects with expr literals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PropertyDef:
    json_path: str | None  # Dot path into the JSON, or None for object-style properties
    value_type: str  # "number", "string", "boolean", "color", "page_color", "enum"
    description: str
    enum_values: tuple[str, ...] | None = None
    # For object-style properties (both visualContainerObjects and visual.objects)
    container_key: str | None = None
    container_prop: str | None = None
    objects_path: str = "visualContainerObjects"  # or "objects" for chart formatting
    top_level: bool = False  # True for page-level objects (data.objects vs data.visual.objects)


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
        container_key="title", container_prop="show",
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
        container_key="subTitle", container_prop="show",
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
    # ── Chart formatting (visual.objects) ──────────────────────
    # Legend
    "legend.show": PropertyDef(
        None, "boolean", "Show legend",
        container_key="legend", container_prop="show", objects_path="objects",
    ),
    "legend.position": PropertyDef(
        None, "enum", "Legend position",
        container_key="legend", container_prop="position", objects_path="objects",
        enum_values=("Top", "Bottom", "Left", "Right", "TopCenter", "BottomCenter", "LeftCenter", "RightCenter"),
    ),
    "legend.color": PropertyDef(
        None, "color", "Legend text color",
        container_key="legend", container_prop="labelColor", objects_path="objects",
    ),
    "legend.fontSize": PropertyDef(
        None, "number", "Legend font size",
        container_key="legend", container_prop="fontSize", objects_path="objects",
    ),
    "legend.fontFamily": PropertyDef(
        None, "string", "Legend font family",
        container_key="legend", container_prop="fontFamily", objects_path="objects",
    ),
    # Category axis (X axis)
    "xAxis.show": PropertyDef(
        None, "boolean", "Show category axis",
        container_key="categoryAxis", container_prop="show", objects_path="objects",
    ),
    "xAxis.title": PropertyDef(
        None, "boolean", "Show category axis title",
        container_key="categoryAxis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "xAxis.titleText": PropertyDef(
        None, "string", "Category axis title text",
        container_key="categoryAxis", container_prop="axisTitle", objects_path="objects",
    ),
    "xAxis.color": PropertyDef(
        None, "color", "Category axis label color",
        container_key="categoryAxis", container_prop="labelColor", objects_path="objects",
    ),
    "xAxis.fontSize": PropertyDef(
        None, "number", "Category axis font size",
        container_key="categoryAxis", container_prop="fontSize", objects_path="objects",
    ),
    "xAxis.gridlines": PropertyDef(
        None, "boolean", "Show category axis gridlines",
        container_key="categoryAxis", container_prop="gridlineShow", objects_path="objects",
    ),
    "xAxis.gridlineColor": PropertyDef(
        None, "color", "Category axis gridline color",
        container_key="categoryAxis", container_prop="gridlineColor", objects_path="objects",
    ),
    # Value axis (Y axis)
    "yAxis.show": PropertyDef(
        None, "boolean", "Show value axis",
        container_key="valueAxis", container_prop="show", objects_path="objects",
    ),
    "yAxis.title": PropertyDef(
        None, "boolean", "Show value axis title",
        container_key="valueAxis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "yAxis.titleText": PropertyDef(
        None, "string", "Value axis title text",
        container_key="valueAxis", container_prop="axisTitle", objects_path="objects",
    ),
    "yAxis.color": PropertyDef(
        None, "color", "Value axis label color",
        container_key="valueAxis", container_prop="labelColor", objects_path="objects",
    ),
    "yAxis.fontSize": PropertyDef(
        None, "number", "Value axis font size",
        container_key="valueAxis", container_prop="fontSize", objects_path="objects",
    ),
    "yAxis.gridlines": PropertyDef(
        None, "boolean", "Show value axis gridlines",
        container_key="valueAxis", container_prop="gridlineShow", objects_path="objects",
    ),
    "yAxis.gridlineColor": PropertyDef(
        None, "color", "Value axis gridline color",
        container_key="valueAxis", container_prop="gridlineColor", objects_path="objects",
    ),
    "yAxis.start": PropertyDef(
        None, "number", "Value axis range start",
        container_key="valueAxis", container_prop="start", objects_path="objects",
    ),
    "yAxis.end": PropertyDef(
        None, "number", "Value axis range end",
        container_key="valueAxis", container_prop="end", objects_path="objects",
    ),
    # Secondary axis (Y2, for combo charts)
    "y2Axis.show": PropertyDef(
        None, "boolean", "Show secondary value axis",
        container_key="y2Axis", container_prop="show", objects_path="objects",
    ),
    "y2Axis.title": PropertyDef(
        None, "boolean", "Show secondary axis title",
        container_key="y2Axis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "y2Axis.titleText": PropertyDef(
        None, "string", "Secondary axis title text",
        container_key="y2Axis", container_prop="axisTitle", objects_path="objects",
    ),
    # Data labels
    "labels.show": PropertyDef(
        None, "boolean", "Show data labels",
        container_key="labels", container_prop="show", objects_path="objects",
    ),
    "labels.color": PropertyDef(
        None, "color", "Data label color",
        container_key="labels", container_prop="color", objects_path="objects",
    ),
    "labels.fontSize": PropertyDef(
        None, "number", "Data label font size",
        container_key="labels", container_prop="fontSize", objects_path="objects",
    ),
    "labels.fontFamily": PropertyDef(
        None, "string", "Data label font family",
        container_key="labels", container_prop="fontFamily", objects_path="objects",
    ),
    "labels.position": PropertyDef(
        None, "enum", "Data label position",
        container_key="labels", container_prop="labelPosition", objects_path="objects",
        enum_values=("Auto", "InsideEnd", "OutsideEnd", "InsideCenter", "InsideBase"),
    ),
    "labels.format": PropertyDef(
        None, "string", "Data label display units",
        container_key="labels", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "labels.precision": PropertyDef(
        None, "number", "Data label decimal places",
        container_key="labels", container_prop="labelPrecision", objects_path="objects",
    ),
    # Plot area
    "plotArea.transparency": PropertyDef(
        None, "number", "Plot area transparency",
        container_key="plotArea", container_prop="transparency", objects_path="objects",
    ),
    "plotArea.color": PropertyDef(
        None, "color", "Plot area background color",
        container_key="plotArea", container_prop="color", objects_path="objects",
    ),
    # Data colors
    "dataColors.default": PropertyDef(
        None, "color", "Default data color",
        container_key="dataPoint", container_prop="defaultColor", objects_path="objects",
    ),
    "dataColors.showAll": PropertyDef(
        None, "boolean", "Show all data colors",
        container_key="dataPoint", container_prop="showAllDataPoints", objects_path="objects",
    ),
    # Line formatting (line/area charts)
    "line.show": PropertyDef(
        None, "boolean", "Show line",
        container_key="lineStyles", container_prop="showMarker", objects_path="objects",
    ),
    "line.style": PropertyDef(
        None, "enum", "Line style",
        container_key="lineStyles", container_prop="lineStyle", objects_path="objects",
        enum_values=("solid", "dashed", "dotted"),
    ),
    "line.width": PropertyDef(
        None, "number", "Line stroke width",
        container_key="lineStyles", container_prop="strokeWidth", objects_path="objects",
    ),
    # Shape formatting
    "shapes.showMarkers": PropertyDef(
        None, "boolean", "Show data point markers",
        container_key="shapes", container_prop="showMarkers", objects_path="objects",
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
    # Page background (page.objects.background)
    "background.color": PropertyDef(
        None, "page_color", "Page background color",
        container_key="background", container_prop="color",
        objects_path="objects", top_level=True,
    ),
    "background.transparency": PropertyDef(
        None, "number", "Page background transparency (0-100)",
        container_key="background", container_prop="transparency",
        objects_path="objects", top_level=True,
    ),
    # Page outspace (area outside the page canvas)
    "outspace.color": PropertyDef(
        None, "page_color", "Outspace background color",
        container_key="outspace", container_prop="backgroundColor",
        objects_path="objects", top_level=True,
    ),
    "outspace.transparency": PropertyDef(
        None, "number", "Outspace transparency",
        container_key="outspace", container_prop="transparency",
        objects_path="objects", top_level=True,
    ),
}


# ── Value encoding/decoding ────────────────────────────────────────

def encode_pbi_value(value: str, value_type: str) -> Any:
    """Encode a CLI string value into PBI JSON format."""
    if value_type == "color":
        color = value if value.startswith("#") else f"#{value}"
        return {"solid": {"color": color}}
    elif value_type == "page_color":
        # Page-level colors nest the expr inside solid.color
        color = value if value.startswith("#") else f"#{value}"
        return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}
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
        # Color: {"solid": {"color": "#hex"}} or {"solid": {"color": {expr...}}}
        if "solid" in raw:
            color = raw["solid"].get("color", raw)
            # Recurse for page-level colors where color is an expr dict
            return decode_pbi_value(color) if isinstance(color, dict) else color
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
    """Read from object collections (visual-level or page-level)."""
    root = data if prop_def.top_level else data.get("visual", {})
    objects = root.get(prop_def.objects_path, {})
    entries = objects.get(prop_def.container_key, [])
    if not entries:
        return None
    props = entries[0].get("properties", {})
    raw = props.get(prop_def.container_prop)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _set_container_prop(data: dict, prop_def: PropertyDef, value: str) -> None:
    """Write to object collections, creating structure as needed."""
    root = data if prop_def.top_level else data.setdefault("visual", {})
    objects = root.setdefault(prop_def.objects_path, {})
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
    # Display page_color as "color" — the encoding difference is internal
    display_type = lambda t: "color" if t == "page_color" else t
    return [
        (name, display_type(p.value_type), p.description)
        for name, p in sorted(registry.items())
    ]
